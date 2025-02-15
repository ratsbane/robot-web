import os
import sys
import time
import cv2
from flask import Flask, render_template, Response
from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# Get the absolute path of the current file (app.py)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Change the working directory to the directory containing app.py
os.chdir(current_dir)
sys.path.insert(0, current_dir)  # Add to sys.path

# --- Global Camera Initialization (BEFORE Flask app) ---
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Error: Could not open camera globally")
    camera = None


app = Flask(__name__)


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
    return "<html><body><h1>Camera Test</h1><img src='/video_feed'></body></html>"

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, preload=True, use_reloader=False) # No reloader



