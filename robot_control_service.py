#!/usr/bin/python3

import socket
import time
import os
import sys
import json
import threading

# Import the MotorEventLogger
from motor_event_logger import MotorEventLogger

# Use the *correct* path to STservo_sdk here:
sdk_path = os.path.abspath('/home/pi/so-arm-configure/')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# --- Robot Arm Initialization ---
device = scan_interfaces_for_arm()
if not device:
    print("No SO-ARM100 controller found. Exiting.")
    exit() #Exit if no arm is connected.

port_handler = PortHandler(device)
packet_handler = sts(port_handler)
if not port_handler.openPort():
    print(f"Failed to open port {device}")
    exit()
if not port_handler.setBaudRate(1000000):
    print(f"Failed to set baud rate for {device}")
    exit()

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

# --- TCP Socket Server ---
HOST = 'localhost'  # Listen on localhost (only accessible from the same machine)
PORT = 9000        # Choose a port (make sure it's not used by anything else)
DEFAULT_SPEED = 500 # Define default speed.

# --- Command Queue ---
command_queue = [] # List for commands  # Use a list as a simple queue
current_moving_motor = None  # Keep track of the currently moving motor

# Define video sources for recording
video_sources = [
    {
        'source': 'http://localhost:5000/video_feed', # Update with your actual stream URL
        'method': 'stream',
        'camera_id': 0
    }
]

# Initialize the motor event logger with video sources
logger = MotorEventLogger(base_dir="robot_logs", video_sources=video_sources)

def handle_client(conn, addr):
    with conn:
        while True:
            try:
                data = conn.recv(1024)  # Receive data from the client
                print(f"[{time.time()}] Data received: {data}")
                if not data:
                    break  # Client disconnected
                try:
                    command = json.loads(data.decode('utf-8').strip()) #Expect a JSON
                except:
                    conn.sendall(b"Error: Invalid JSON format")
                    continue

                # Handle recording commands
                if command.get('command') == 'start_logging':
                    action_name = command.get('action_name', 'unnamed_action')
                    description = command.get('description', '')
                    timeout = command.get('timeout')
                    
                    # Check if video sources are provided in the command
                    if 'video_sources' in command:
                        logger.setup_video_sources(command['video_sources'])
                    
                    success, message = logger.start_logging(
                        action_name=action_name, 
                        description=description, 
                        timeout=timeout
                    )
                    result = {"success": success, "message": message}
                    conn.sendall(json.dumps(result).encode('utf-8'))
                    continue
                
                elif command.get('command') == 'stop_logging':
                    success, message = logger.stop_logging()
                    result = {"success": success, "message": message}
                    conn.sendall(json.dumps(result).encode('utf-8'))
                    continue
                
                # Standard commands go to the queue
                command_queue.append(command) #Put command on the queue.
                result = {"success":True, "message": "Command received"} #Always send a JSON repsonse
                conn.sendall(json.dumps(result).encode('utf-8'))

            except ConnectionResetError:
                break
            except Exception as e:
                print(f"[{time.time()}] Error handling client: {e}")
                conn.sendall(f"Error: {e}".encode('utf-8')) # Send the error to the client!
                break


def process_commands():
    """Processes commands from the queue."""
    global current_moving_motor, command_queue  # Access the global variables

    while True:
        if len(command_queue) > 0:  # Always process commands if they exist
            command = command_queue.pop(0)  # Get the next command

            motor_name = command.get('motor')
            motor_id = None

            # Find Motor ID
            if motor_name:
                for m_id, m_data in motor_controller.motor_limits.items():
                    if m_data['name'] == motor_name:
                        motor_id = m_id
                        break
                if motor_id is None:
                    for m_id, m_data in motor_controller.initial_motor_data.items():
                        if m_data['name'] == motor_name:
                            motor_id = m_id
                            break

            if command.get('command') == 'move':  # Absolute positioning
                direction = command.get('direction')
                speed = command.get('speed', DEFAULT_SPEED)  # Get speed, use default.

                if motor_id is not None:
                    # Get current position before move
                    current_pos = None
                    try:
                        current_pos = motor_controller.read_pos(motor_id)
                    except:
                        pass
                    
                    # Execute the move
                    result = motor_controller.move_motor(motor_id, motor_name, direction, speed)
                    
                    # Log the motor event if recording is active
                    if result['success']:
                        current_moving_motor = motor_id  # Keep tracking
                        
                        # Try to get target position if possible
                        target_pos = None
                        if direction == 'max':
                            target_pos = motor_controller.motor_limits.get(motor_id, {}).get('max')
                        elif direction == 'min':
                            target_pos = motor_controller.motor_limits.get(motor_id, {}).get('min')
                        
                        # Log the move event
                        logger.log_motor_event(
                            motor_id=motor_id,
                            motor_name=motor_name,
                            command='move',
                            direction=direction,
                            speed=speed,
                            current_pos=current_pos,
                            target_pos=target_pos
                        )
                else:
                    result = {'success': False, 'message': f'Invalid move command or unknown motor: {motor_name}'}

            elif command.get('command') == 'stop':
                if motor_id is not None:
                    # Get current position before stop
                    current_pos = None
                    try:
                        current_pos = motor_controller.read_pos(motor_id)
                    except:
                        pass
                    
                    # Execute the stop
                    result = motor_controller.stop_motor(motor_id, motor_name)
                    
                    # Log the stop event if recording is active
                    if result['success']:
                        current_moving_motor = None  # Allow new commands
                        
                        # Log the stop event
                        logger.log_motor_event(
                            motor_id=motor_id,
                            motor_name=motor_name,
                            command='stop',
                            current_pos=current_pos
                        )
                else:
                    result = {'success': False, 'message': f'Unknown motor to stop: {motor_name}'}

            elif command.get('command') == 'stop_all':
                result = {'success': True, 'message': "All motors stopped"}
                
                for motor_id in CALIBRATED_MOTORS:
                    motor_name = motor_controller.initial_motor_data[motor_id]['name']
                    
                    # Get current position before stop
                    current_pos = None
                    try:
                        current_pos = motor_controller.read_pos(motor_id)
                    except:
                        pass
                    
                    # Stop the motor
                    motor_result = motor_controller.stop_motor(motor_id, motor_name)
                    
                    # Log the stop event
                    if motor_result['success']:
                        logger.log_motor_event(
                            motor_id=motor_id,
                            motor_name=motor_name,
                            command='stop_all',
                            current_pos=current_pos
                        )
                    
                    if not motor_result['success']:
                        result = motor_result  # Return the first error
                        break
                
                current_moving_motor = None  # Reset motor tracking

            else:
                result = {'success': False, 'message': f'Unknown command: {command.get("command")}'}

        else:
            time.sleep(0.05)  # Prevent CPU overuse




def main():
    # Start the command processing thread
    command_thread = threading.Thread(target=process_commands, daemon=True)
    command_thread.start()

    try: #Wrap in try/finally to ensure closure.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ADD THIS LINE
            s.bind((HOST, PORT))
            s.listen()
            print(f"Robot Control Service listening on {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()  # Accept a connection
                # Start a new thread to handle each client connection
                client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
    finally:
        # Stop recording if active before exiting
        if logger.is_logging:
            logger.stop_logging()
            
        if port_handler:
            print("Closing port handler...")
            port_handler.closePort() #Close the port when the service exits


if __name__ == '__main__':
    main()
