from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import socket
import asyncio
from starlette.concurrency import run_in_threadpool
import time
import json

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
#   - <speed_value>: (Optional) Integer representing the speed. If omitted, a default speed is used.
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
#   - Stops all motors. No additional parameters.
#
# Connection Maintenance:
# The WebSocket server sends pings to keep the connection alive during periods of inactivity.
# This helps prevent timeouts and ensures the connection remains stable.


app = FastAPI()

# --- Robot Control Service Communication ---
RCS_HOST = 'localhost'
RCS_PORT = 9000
WS_PORT = 8000  # WebSocket server port

# List of valid motors and directions
VALID_MOTORS = ["base", "shoulder", "elbow", "wrist", "hand", "thumb"]
VALID_DIRECTIONS = ["inc", "dec"]


def send_command_to_rcs(command_json: str) -> str:
    """Sends a JSON command to the Robot Control Service and returns the response."""
    print(f"[{time.time()}] send_command_to_rcs called with command: {command_json}")  # Debug
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"[{time.time()}] Connecting to RCS at {RCS_HOST}:{RCS_PORT}")  # Debug
            s.connect((RCS_HOST, RCS_PORT))
            print(f"[{time.time()}] Connected to RCS")  # Debug
            print(f"[{time.time()}] Sending command to RCS: {command_json}")  # Debug
            s.sendall(command_json.encode('utf-8'))  # Send the JSON string, encoded
            print(f"[{time.time()}] Command sent to RCS")  # Debug
            response = s.recv(1024)
            response_str = response.decode('utf-8')
            print(f"[{time.time()}] Received response from RCS: {response_str}")  # Debug
            return response_str
    except ConnectionRefusedError:
        print(f"[{time.time()}] Error: Robot Control Service not running.")  # Debug
        return '{"success": false, "message": "Error: Robot Control Service not running."}'  # Return JSON
    except Exception as e:
        print(f"[{time.time()}] Error in send_command_to_rcs: {e}")  # Debug
        return json.dumps({"success": False, "message": f"Error: {e}"})  # Return JSON


def validate_command(data):
    """Validates command structure and returns (is_valid, error_message)"""
    if not isinstance(data, dict):
        return False, "Command must be a JSON object"
    
    if "command" not in data:
        return False, "Missing 'command' field"
    
    command_type = data.get("command")
    
    # Validate move command
    if command_type == "move":
        if "motor" not in data:
            return False, "Move command requires 'motor' field"
        if "direction" not in data:
            return False, "Move command requires 'direction' field"
        if data["motor"] not in VALID_MOTORS:
            return False, f"Invalid motor. Must be one of: {VALID_MOTORS}"
        if data["direction"] not in VALID_DIRECTIONS:
            return False, f"Invalid direction. Must be one of: {VALID_DIRECTIONS}"
        if "speed" in data and not isinstance(data["speed"], (int, float)):
            return False, "Speed value must be a number"
    
    # Validate move_to command
    elif command_type == "move_to":
        if "motor" not in data:
            return False, "Move_to command requires 'motor' field"
        if "position" not in data:
            return False, "Move_to command requires 'position' field"
        if data["motor"] not in VALID_MOTORS:
            return False, f"Invalid motor. Must be one of: {VALID_MOTORS}"
        if not isinstance(data["position"], (int, float)):
            return False, "Position value must be a number"
        if "speed" in data and not isinstance(data["speed"], (int, float)):
            return False, "Speed value must be a number"
    
    # Validate stop command
    elif command_type == "stop":
        if "motor" not in data:
            return False, "Stop command requires 'motor' field"
        if data["motor"] not in VALID_MOTORS:
            return False, f"Invalid motor. Must be one of: {VALID_MOTORS}"
    
    # Validate stop_all command
    elif command_type == "stop_all":
        # No additional validation needed for stop_all
        pass
    
    else:
        return False, f"Unknown command: {command_type}"
    
    return True, None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[{time.time()}] Client connected to WebSocket server on port {WS_PORT}")
    
    try:
        while True:
            try:
                # Set a timeout for receiving messages
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                print(f"[{time.time()}] Raw received command: {data}")

                # Try to parse the JSON
                try:
                    parsed_data = json.loads(data)
                    print(f"[{time.time()}] Parsed command: {parsed_data}")
                except json.JSONDecodeError as json_err:
                    error_response = json.dumps({
                        "success": False, 
                        "message": f"Invalid JSON: {str(json_err)}",
                        "received_data": data
                    })
                    print(f"[{time.time()}] JSON Decode Error: {error_response}")
                    await websocket.send_text(error_response)
                    continue

                # Validate command structure
                is_valid, error_message = validate_command(parsed_data)
                if not is_valid:
                    error_response = json.dumps({
                        "success": False, 
                        "message": error_message,
                        "received_data": parsed_data
                    })
                    print(f"[{time.time()}] Invalid command: {error_response}")
                    await websocket.send_text(error_response)
                    continue

                # Convert command to JSON string for RCS
                data_for_rcs = json.dumps(parsed_data)

                # Run send_command_to_rcs in a thread pool
                response = await run_in_threadpool(send_command_to_rcs, data_for_rcs)
                print(f"[{time.time()}] Sending response to client: {response}")
                await websocket.send_text(response)  # Send the raw JSON string back

            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "timestamp": time.time()
                    }))
                    print(f"[{time.time()}] Sent ping to keep connection alive")
                except Exception as ping_err:
                    print(f"[{time.time()}] Error sending ping: {ping_err}")
                    break
            except Exception as inner_err:
                error_response = json.dumps({
                    "success": False, 
                    "message": f"Unexpected error processing command: {str(inner_err)}"
                })
                print(f"[{time.time()}] Inner loop error: {error_response}")
                try:
                    await websocket.send_text(error_response)
                except Exception:
                    # If sending the error fails, break the loop
                    break

    except WebSocketDisconnect:
        print(f"[{time.time()}] Client disconnected from WebSocket server")
    except Exception as e:
        print(f"[{time.time()}] WebSocket error: {e}")
    finally:
        # Ensure cleanup happens
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    print(f"Starting WebSocket server on port {WS_PORT}...")
    print(f"Valid motors: {VALID_MOTORS}")
    print(f"Valid directions: {VALID_DIRECTIONS}")
    uvicorn.run(app, host="0.0.0.0", port=WS_PORT, reload=True)  # Added reload for convenience
