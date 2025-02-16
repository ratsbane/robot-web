import os
import sys
import time
import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncio
# --- Add STServo Path ---
sdk_path = os.path.abspath('/home/pi/so-arm-configure/')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)
# --- End added lines ---

from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# --- Set working directory and sys.path ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
sys.path.insert(0, current_dir)


# --- Flask App Initialization ---  <-- Note: It's FastAPI now!
app = FastAPI()

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
    if port_handler:
        port_handler.closePort()

# --- Camera Setup ---
camera = cv2.VideoCapture(0)  # Use the correct index!
if not camera.isOpened():
    print("Error: Could not open camera")
    camera = None

async def generate_frames():
    while True:
        if camera:
            success, frame = camera.read()
            if not success:
                await asyncio.sleep(0.1)  # Non-blocking sleep
                continue
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])  # Adjust quality as needed
            if not ret:
                await asyncio.sleep(0.1)
                continue
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            await asyncio.sleep(1)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')  # Empty frame


@app.get("/")
async def read_root():
    with open("templates/robot.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


# --- Robot Control Service Communication ---
RCS_HOST = 'localhost'
RCS_PORT = 9000

def send_command_to_rcs(command: str) -> str:
    """Sends a command to the Robot Control Service and returns the response."""
    import socket # THIS MUST BE HERE

    print(f"send_command_to_rcs called with command: {command}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"Connecting to RCS at {RCS_HOST}:{RCS_PORT}")
            s.connect((RCS_HOST, RCS_PORT))
            print(f"Connected to RCS")
            print(f"Sending command to RCS: {command}")
            s.sendall(command.encode('utf-8'))
            response = s.recv(1024)  # Receive response
            response_str = response.decode('utf-8') #Decode
            print(f"Received response from RCS: {response_str}")
            return response_str
    except ConnectionRefusedError:
        print("Error: Robot Control Service not running.")
        return "Error: Robot Control Service not running."
    except Exception as e:
        print(f"Error in send_command_to_rcs: {e}")
        return f"Error: {e}"

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected (FastAPI WebSocket)")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received command (FastAPI): {data}")

            # --- Send Command to RCS and Get Response ---
            response = send_command_to_rcs(data)

            # --- Send Response Back to Client ---
            print(f"Sending response to client: {response}")
            await websocket.send_text(response)

    except WebSocketDisconnect:
        print("Client disconnected (FastAPI WebSocket)")
    except Exception as e:
        print(f"WebSocket error in handle_command: {e}")

