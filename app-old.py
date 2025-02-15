from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
import cv2
import time
import json
from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS  # Import

app = Flask(__name__)
socketio = SocketIO(app)

# --- Robot Arm Initialization ---
device = scan_interfaces_for_arm()
arm_connected = False  # Global flag for connection status
if not device:
    print("No SO-ARM100 controller found.")
else:
    port_handler = PortHandler(device)
    packet_handler = sts(port_handler)
    if not port_handler.openPort():
        print(f"Failed to open port {device}")
    elif not port_handler.setBaudRate(1000000):
        print(f"Failed to set baud rate for {device}")
    else:
        motor_controller = MotorController(packet_handler)
        if not motor_controller.load_calibration():
            # Perform calibration and save results
            for motor_id in CALIBRATED_MOTORS:
                motor_data = motor_controller.initial_motor_data[motor_id]
                motor_controller.calibrate_motor(motor_id, motor_data["name"], motor_data["min_pos"], motor_data["max_pos"])
            motor_controller.save_calibration()

        # Initial positions after calibration/loading.
        for motor_id in CALIBRATED_MOTORS:
            if motor_id in motor_controller.motor_limits:
                midpoint = (motor_controller.motor_limits[motor_id]["min"] + motor_controller.motor_limits[motor_id]["max"]) // 2
                motor_controller.write_pos_ex(motor_id, midpoint, 300, 50)  # Use constants from arm_control.py
            else:
                print(f"Warning: Motor ID {motor_id} not found in calibration data.")
        time.sleep(3)  # Wait for motors to reach position
        arm_connected = True  # Set connection status

# --- Webcam Streaming ---
camera = cv2.VideoCapture(0)  # 0 is usually the default webcam
if not camera.isOpened():
    print("Error: Could not open camera.")
    camera = None  # Set camera to None if it fails to open

def generate_frames():
    """Generator function for MJPEG stream."""
    while True:
        if camera:  # Only read if camera is valid
            success, frame = camera.read()
            if not success:
                print("Failed to read from camera")
                break  # Stop if reading fails
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    print("Failed to encode frame")
                    continue  # Skip to next iteration
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            # Optionally, yield a placeholder image or error message if the camera is not available.
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')  # Empty frame
            time.sleep(1) # Prevent busy-loop if camera is down.

@app.route('/video_feed')
def video_feed():
    """Route for the MJPEG video stream."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- Web Page ---
@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template('robot.html')

# --- WebSocket Event Handlers ---
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    if arm_connected:
        emit('status', {'message': 'Connected to robot control server'})
    else:
        emit('status', {'message': 'Robot arm not connected!'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('command')
def handle_command(data):
    """Handle commands from the client (keyboard and, later, Xbox controller)."""
    if not arm_connected:
        emit('error', {'message': 'Robot arm not connected!'})
        return

    command = data['command']
    print(f"Received command: {command}")

    result = None

    if command.startswith('move_'):
        parts = command.split('_')
        if len(parts) == 3:  # e.g., move_base_left
            motor_name = parts[1]
            direction_str = parts[2]

            motor_id = None
            for m_id, m_data in motor_controller.motor_limits.items():
                if m_data['name'] == motor_name:
                    motor_id = m_id
                    break
            if motor_id is None:
                for m_id, m_data in motor_controller.initial_motor_data.items():
                    if m_data['name'] == motor_name:
                        motor_id = m_id
                        break
            if motor_id is None:
                emit('error', {'message': f'Unknown motor: {motor_name}'})
                return

            if direction_str == 'left' or direction_str == 'up':
                direction = -1
            elif direction_str == 'right' or direction_str == 'down':
                direction = 1
            else:
                emit('error', {'message': f'Invalid direction: {direction_str}'})
                return
            result = motor_controller.move_motor(motor_id, motor_name, 500, direction)  # Use move_motor

        elif len(parts) == 2 and parts[1] in ['hand', 'thumb']:  # Toggle commands (e.g., move_hand)
            motor_name = parts[1]

            motor_id = None
            for m_id, m_data in motor_controller.motor_limits.items():
                if m_data['name'] == motor_name:
                    motor_id = m_id
                    break

            if motor_id is None:  # Check initial_motor_data if not found
                for m_id, m_data in motor_controller.initial_motor_data.items():
                    if m_data['name'] == motor_name:
                        motor_id = m_id
                        break

            if motor_id is None:
                emit('error', {'message': f'Unknown motor: {motor_name}'})
                return

            if motor_name == 'hand':
                motor_controller.toggle_wrist_direction()
                result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.wrist_direction)
            elif motor_name == 'thumb':
                motor_controller.toggle_thumb_direction()
                result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.thumb_direction)


    elif command.startswith('stop_'): # Stop commands
        parts = command.split('_')
        if len(parts) == 2:
            motor_name = parts[1]
            motor_id = None
            for m_id, m_data in motor_controller.motor_limits.items():
                if m_data['name'] == motor_name:
                    motor_id = m_id
                    break
            if motor_id is None: #Check in initial data too
                for m_id, m_data in motor_controller.initial_motor_data.items():
                    if m_data['name'] == motor_name:
                        motor_id = m_id
                        break

            if motor_id is not None:
                result = motor_controller.move_motor(motor_id, motor_name, 0, 0)
            else:
                 emit('error', {'message': f'Unknown motor to stop: {motor_name}'})
                 return

    else:
        emit('error', {'message': f'Unknown command: {command}'})
        return # Important to return after emitting an error.

    # Handle the result of the motor movement (success or failure)
    if result and result['success']:
        emit('status', {'message': result['message']})  # Send success message
    elif result:  # Implies result is not None and not successful
        emit('error', {'message': result['message']})  # Send error message


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

