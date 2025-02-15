import os
import sys
import time
import cv2
from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# --- Set working directory and sys.path ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
sys.path.insert(0, current_dir)

# --- Flask App Initialization ---
app = Flask(__name__)
socketio = SocketIO(app)

# --- Global Camera Initialization ---
camera = cv2.VideoCapture(0)  # Use the correct index!
if not camera.isOpened():
    print("Error: Could not open camera globally")
    camera = None

# --- Robot Arm Initialization ---
device = scan_interfaces_for_arm()
arm_connected = False
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
            for motor_id in CALIBRATED_MOTORS:
                motor_data = motor_controller.initial_motor_data[motor_id]
                motor_controller.calibrate_motor(motor_id, motor_data["name"], motor_data["min_pos"], motor_data["max_pos"])
            motor_controller.save_calibration()

        for motor_id in CALIBRATED_MOTORS:
            if motor_id in motor_controller.motor_limits:
                midpoint = (motor_controller.motor_limits[motor_id]["min"] + motor_controller.motor_limits[motor_id]["max"]) // 2
                motor_controller.write_pos_ex(motor_id, midpoint, 300, 50)
            else:
                print(f"Warning: Motor ID {motor_id} not found in calibration data.")
        time.sleep(3)
        arm_connected = True

    # --- Explicitly Close Serial Port ---
    if port_handler:
        port_handler.closePort()

# --- Video Streaming Function ---
def generate_frames():
    while True:
        if camera:
            success, frame = camera.read()
            if not success:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')
            time.sleep(1)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return render_template('robot.html')

# --- WebSocket Event Handlers ---
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to robot control server' if arm_connected else 'Robot arm not connected!'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('command')
def handle_command(data):
    if not arm_connected:
        emit('error', {'message': 'Robot arm not connected!'})
        return

    command = data['command']
    print(f"Received command: {command}")

    result = None

    if command.startswith('move_'):
        parts = command.split('_')
        if len(parts) == 3:
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
            result = motor_controller.move_motor(motor_id, motor_name, 500, direction)

        elif len(parts) == 2 and parts[1] in ['hand', 'thumb']:
            motor_name = parts[1]
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

            if motor_name == 'hand':
                motor_controller.toggle_wrist_direction()
                result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.wrist_direction)
            elif motor_name == 'thumb':
                motor_controller.toggle_thumb_direction()
                result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.thumb_direction)

    elif command.startswith('stop_'):
        parts = command.split('_')
        if len(parts) == 2:
            motor_name = parts[1]
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
            if motor_id is not None:
                result = motor_controller.move_motor(motor_id, motor_name, 0, 0)
            else:
                emit('error', {'message': f'Unknown motor to stop: {motor_name}'})
                return
    else:
        emit('error', {'message': f'Unknown command: {command}'})
        return

    if result and result['success']:
        emit('status', {'message': result['message']})
    elif result:
        emit('error', {'message': result['message']})

if __name__ == '__main__':
    # Do NOT use socketio.run() when running with Gunicorn
    # For development (without Gunicorn):
    # socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    # For production (with Gunicorn):  Don't use socketio.run here.
    pass

