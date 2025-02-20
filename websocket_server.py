

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import socket
import asyncio
from starlette.concurrency import run_in_threadpool  # Import
import time
import json  # Import json

# WebSocket command protocol (from web page to websocket_server.py):
# All commands are JSON objects.
#
# Commands:
# {
#   "command": "move",
#   "motor": "<motor_name>",
#   "direction": "<direction>",
#   "speed": <speed_value>  // Optional
# }
#   - Starts continuous movement of the specified motor.
#   - <motor_name>: "base", "shoulder", "elbow", "wrist", "hand", or "thumb".
#   - <direction>: "inc" (increase) or "dec" (decrease).
#   - <speed_value>: (Optional) Integer representing the speed.  If omitted, a default speed is used.
#
# {
#   "command": "move_to",
#   "motor": "<motor_name>",
#   "position": <target_position>,
#   "speed": <speed_value>  // Optional
# }
#   - Moves a specific motor to an absolute position.
#   - <motor_name>: "base", "shoulder", "elbow", "wrist", "hand", or "thumb".
#   - <position>: Integer representing the target position.
#   - <speed_value>: (Optional) Integer representing the speed. If omitted, a default speed is used.
#
# {
#   "command": "stop",
#   "motor": "<motor_name>"
# }
#   - Stops movement of the specified motor.
#   - <motor_name>: "base", "shoulder", "elbow", "wrist", "hand", or "thumb".
#
# {
#   "command": "stop_all"
# }
#   - Stops all motors.  No additional parameters.


app = FastAPI()

# --- Robot Control Service Communication ---
RCS_HOST = 'localhost'
RCS_PORT = 9000
WS_PORT = 8000  # WebSocket server port


def send_command_to_rcs(command_json: str) -> str:
    """Sends a JSON command to the Robot Control Service and returns the response."""
    print(f"[{time.time()}] send_command_to_rcs called with command: {command_json}")  # Debug
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"[{time.time()}] Connecting to RCS at {RCS_HOST}:{RCS_PORT}")  # Debug
            s.connect((RCS_HOST, RCS_PORT))
            print(f"[{time.time()}] Connected to RCS")  # Debug
            print(f"[{time.time()}] Sending command to RCS: {command_json}")  # Debug
            s.sendall(command_json.encode('utf-8')) # Send the JSON string, encoded
            print(f"[{time.time()}] Command sent to RCS")  # Debug
            response = s.recv(1024)
            response_str = response.decode('utf-8')
            print(f"[{time.time()}] Received response from RCS: {response_str}")  # Debug
            return response_str
    except ConnectionRefusedError:
        print(f"[{time.time()}] Error: Robot Control Service not running.")  # Debug
        return '{"success": false, "message": "Error: Robot Control Service not running."}' #Return JSON
    except Exception as e:
        print(f"[{time.time()}] Error in send_command_to_rcs: {e}")  # Debug
        return json.dumps({"success": false, "message": f"Error: {e}"}) #Return JSON



connected_clients = set()  # Store connected WebSocket clients


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles WebSocket connections from the web page."""
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"[{time.time()}] Client connected to WebSocket server")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"[{time.time()}] Received command from client: {data}")
            response_json = await run_in_threadpool(send_command_to_rcs, data)
            await websocket.send_text(response_json)

    except WebSocketDisconnect:
        print(f"[{time.time()}] Client disconnected from WebSocket server")
        connected_clients.remove(websocket)
    except Exception as e:
        print(f"[{time.time()}] WebSocket error: {e}")

async def listen_for_motor_updates():
    """Listens for motor status updates from `robot_control_service.py` and broadcasts them."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("localhost", 9001))  # ✅ Listening for motor updates on port 9001
    server.listen()

    while True:
        conn, _ = server.accept()
        with conn:
            data = conn.recv(1024)
            if not data:
                continue
            
            try:
                status_update = json.loads(data.decode("utf-8"))
                print(f"[{time.time()}] Received motor update: {status_update}")

                # ✅ **Broadcast update to all connected WebSocket clients**
                await broadcast_to_websockets(status_update)

            except json.JSONDecodeError:
                print(f"[{time.time()}] Error decoding motor update JSON: {data}")

async def broadcast_to_websockets(message):
    """Send motor updates to all connected WebSocket clients."""
    if connected_clients:
        message_json = json.dumps(message)
        await asyncio.gather(*[client.send_text(message_json) for client in connected_clients])

# Start listening for updates when the WebSocket server starts
asyncio.create_task(listen_for_motor_updates())













@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"[{time.time()}] Client connected to WebSocket server on port {WS_PORT}")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"[{time.time()}] Received command from client: {data}")
            response_json = await run_in_threadpool(send_command_to_rcs, data)
            await websocket.send_text(response_json)

    except WebSocketDisconnect:
        print(f"[{time.time()}] Client disconnected from WebSocket server")
        connected_clients.remove(websocket)
    except Exception as e:
        print(f"[{time.time()}] WebSocket error: {e}")

async def broadcast_to_websockets(message):
    """Send motor updates to all connected WebSocket clients."""
    if connected_clients:
        message_json = json.dumps(message)
        await asyncio.gather(*[client.send_text(message_json) for client in connected_clients])






if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WS_PORT, reload=True) # Added reload for convenience.

