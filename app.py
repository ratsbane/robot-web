import os
import sys
import time
import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import socket
import asyncio  # Required for async

# --- Set working directory and sys.path ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
sys.path.insert(0, current_dir)

# --- No need to import arm_control here, it is in robot_control_service.py ---

app = FastAPI()

# --- Camera Setup ---
camera = cv2.VideoCapture(0)
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
    print(f"send_command_to_rcs called with command: {command}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"Connecting to RCS at {RCS_HOST}:{RCS_PORT}")
            s.connect((RCS_HOST, RCS_PORT))
            print(f"Connected to RCS")  # ADDED: Confirmation of connection
            print(f"Sending command to RCS: {command}")
            s.sendall(command.encode('utf-8'))
            print(f"Command sent to RCS")  # ADDED: Confirmation of send

            response = s.recv(1024)  # Receive response
            print(f"Raw response from RCS: {response}")  # ADDED: Raw bytes
            response_str = response.decode('utf-8')
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
            await websocket.send_text(response)

    except WebSocketDisconnect:
        print("Client disconnected (FastAPI WebSocket)")
    except Exception as e:
        print(f"WebSocket error: {e}")

