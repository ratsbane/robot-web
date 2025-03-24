from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import socket
import asyncio
from starlette.concurrency import run_in_threadpool
import time
import json
import os
import logging
import sys

# Configure logging based on environment variable
def setup_logging():
    # Get log level from environment variable (default to INFO)
    log_level_name = os.environ.get('WEBSOCKET_SERVER_LOG_LEVEL', 'INFO').upper()
    
    # Map string log levels to logging module constants
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
        'NONE': 100  # Custom level higher than any standard level
    }
    
    # Set default level if invalid level provided
    log_level = log_levels.get(log_level_name, logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout
    )
    
    # Create logger instance for our module
    logger = logging.getLogger('websocket_server')
    logger.setLevel(log_level)
    
    # Show startup message about log level
    if log_level < 100:  # If not NONE
        logger.info(f"Logging configured with level: {log_level_name}")
    
    return logger

# Initialize logger
logger = setup_logging()

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
# {
#   "command": "start_logging",
#   "action_name": "<name>",
#   "description": "<description>",  // Optional
#   "timeout": <timeout_in_seconds>,  // Optional
#   "video_sources": [                // Optional
#     {
#       "source": "<video_source_url>",
#       "method": "<stream_or_opencv>",
#       "camera_id": <camera_id_number>
#     }
#   ]
# }
#   - Starts logging robot actions in GR00T-compatible format.
#   - <name>: Name of the action being performed.
#   - <description>: Optional description of the action.
#   - <timeout_in_seconds>: Optional timeout to automatically stop logging.
#   - video_sources: Optional array of video source configurations.
#
# {
#   "command": "stop_logging"
# }
#   - Stops the currently active logging session.
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
    logger.debug(f"send_command_to_rcs called with command: {command_json}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            logger.debug(f"Connecting to RCS at {RCS_HOST}:{RCS_PORT}")
            s.connect((RCS_HOST, RCS_PORT))
            logger.debug(f"Connected to RCS")
            logger.debug(f"Sending command to RCS: {command_json}")
            s.sendall(command_json.encode('utf-8'))  # Send the JSON string, encoded
            logger.debug(f"Command sent to RCS")
            response = s.recv(1024)
            response_str = response.decode('utf-8')
            logger.debug(f"Received response from RCS: {response_str}")
            
            # Add the command type to the response for client-side tracking
            try:
                cmd_data = json.loads(command_json)
                resp_data = json.loads(response_str)
                if "command" in cmd_data and "command" not in resp_data:
                    resp_data["command"] = cmd_data["command"]
                    response_str = json.dumps(resp_data)
            except Exception as e:
                logger.error(f"Error enhancing response with command: {e}")
                
            return response_str
    except ConnectionRefusedError:
        logger.error(f"Error: Robot Control Service not running.")
        return '{"success": false, "message": "Error: Robot Control Service not running."}'  # Return JSON
    except Exception as e:
        logger.error(f"Error in send_command_to_rcs: {e}")
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
    
    # Validate start_logging command
    elif command_type == "start_logging":
        if "action_name" not in data:
            return False, "start_logging command requires 'action_name' field"
        
        # Optional timeout validation
        if "timeout" in data and not isinstance(data["timeout"], (int, float)):
            return False, "Timeout value must be a number"
            
        # Optional video_sources validation
        if "video_sources" in data:
            if not isinstance(data["video_sources"], list):
                return False, "video_sources must be an array"
                
            for source in data["video_sources"]:
                if not isinstance(source, dict):
                    return False, "Each video source must be an object"
                if "source" not in source:
                    return False, "Each video source requires a 'source' field"
                if "method" in source and source["method"] not in ["stream", "opencv"]:
                    return False, "Video source method must be 'stream' or 'opencv'"
    
    # Validate stop_logging command
    elif command_type == "stop_logging":
        # No additional validation needed for stop_logging
        pass
    
    else:
        return False, f"Unknown command: {command_type}"
    
    return True, None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"Client connected to WebSocket server on port {WS_PORT}")
    
    try:
        while True:
            try:
                # Set a timeout for receiving messages
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                logger.debug(f"Raw received command: {data}")

                # Try to parse the JSON
                try:
                    parsed_data = json.loads(data)
                    logger.debug(f"Parsed command: {parsed_data}")
                except json.JSONDecodeError as json_err:
                    error_response = json.dumps({
                        "success": False, 
                        "message": f"Invalid JSON: {str(json_err)}",
                        "received_data": data
                    })
                    logger.warning(f"JSON Decode Error: {error_response}")
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
                    logger.warning(f"Invalid command: {error_response}")
                    await websocket.send_text(error_response)
                    continue

                # Convert command to JSON string for RCS
                data_for_rcs = json.dumps(parsed_data)

                # Run send_command_to_rcs in a thread pool
                response = await run_in_threadpool(send_command_to_rcs, data_for_rcs)
                logger.debug(f"Sending response to client: {response}")
                await websocket.send_text(response)  # Send the raw JSON string back

            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "timestamp": time.time()
                    }))
                    logger.debug(f"Sent ping to keep connection alive")
                except Exception as ping_err:
                    logger.error(f"Error sending ping: {ping_err}")
                    break
            except Exception as inner_err:
                error_response = json.dumps({
                    "success": False, 
                    "message": f"Unexpected error processing command: {str(inner_err)}"
                })
                logger.error(f"Inner loop error: {error_response}")
                try:
                    await websocket.send_text(error_response)
                except Exception:
                    # If sending the error fails, break the loop
                    break

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from WebSocket server")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Ensure cleanup happens
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting WebSocket server on port {WS_PORT}...")
    logger.info(f"Valid motors: {VALID_MOTORS}")
    logger.info(f"Valid directions: {VALID_DIRECTIONS}")
    uvicorn.run(app, host="0.0.0.0", port=WS_PORT, reload=True)  # Added reload for convenience
