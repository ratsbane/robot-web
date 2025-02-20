import socket
import time
# --- Add these lines at the VERY TOP ---
import os
import sys
import json
import threading  # IMPORT THREADING
import asyncio

# Use the *correct* path to STservo_sdk here:
sdk_path = os.path.abspath('/home/pi/so-arm-configure/')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)
# --- End added lines ---

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

def handle_client(conn, addr):
    print(f"[{time.time()}] Connected by {addr}")  # Timestamp
    with conn:
        while True:
            try:
                print(f"[{time.time()}] Waiting to receive data...")
                data = conn.recv(1024)  # Receive data from the client
                print(f"[{time.time()}] Data received: {data}")
                if not data:
                    print(f"[{time.time()}] No data received. Breaking.")
                    break  # Client disconnected
                try:
                    command = json.loads(data.decode('utf-8').strip()) #Expect a JSON
                except:
                    conn.sendall(b"Error: Invalid JSON format")
                    continue
                print(f"[{time.time()}] Received command: {command}")

                command_queue.append(command) #Put command on the queue.
                result = {"success":True, "message": "Command received"} #Always send a JSON repsonse
                conn.sendall(json.dumps(result).encode('utf-8'))

            except ConnectionResetError:
                print(f"[{time.time()}] Client disconnected unexpectedly")
                break
            except Exception as e:
                print(f"[{time.time()}] Error handling client: {e}")
                conn.sendall(f"Error: {e}".encode('utf-8')) # Send the error to the client!
                break



import asyncio
import json

async def process_commands():
    """Processes commands from the queue and broadcasts updates when done."""
    global current_moving_motor, command_queue

    while True:
        if len(command_queue) > 0 and current_moving_motor is None:
            command = command_queue.pop(0)
            print(f"[{time.time()}] Processing command: {command}")

            result = None
            motor_name = command.get('motor')
            motor_id = None

            # Find motor ID
            for m_id, m_data in motor_controller.motor_limits.items():
                if m_data['name'] == motor_name:
                    motor_id = m_id
                    break
            if motor_id is None:
                for m_id, m_data in motor_controller.initial_motor_data.items():
                    if m_data['name'] == motor_name:
                        motor_id = m_id
                        break

            # Handle move command
            if command.get('command') == 'move':
                direction = command.get('direction')
                speed = command.get('speed', DEFAULT_SPEED)
                if motor_id is not None:
                    result = motor_controller.move_motor(motor_id, motor_name, direction, speed)
                    if result['success']:
                        current_moving_motor = motor_id  # Track moving motor

            elif command.get('command') == 'stop':
                if motor_id is not None:
                    result = motor_controller.move_motor(motor_id, motor_name, "stop", 0)
                    current_moving_motor = None

            elif command.get('command') == 'stop_all':
                result = {'success': True, 'message': "All motors stopped"}
                for motor_id in CALIBRATED_MOTORS:
                    motor_name = motor_controller.initial_motor_data[motor_id]['name']
                    motor_result = motor_controller.move_motor(motor_id, motor_name, "stop", 0)
                    if not motor_result['success']:
                        result = motor_result
                        break  # Stop on first error
                current_moving_motor = None

            # ✅ **Broadcast motor status after executing a move command**
            if result and result['success']:
                status_update = {
                    "success": True,
                    "motor": motor_name,
                    "end_position": result.get("end_position"),
                    "temp": result.get("temp"),
                    "message": "Motor status updated"
                }
                print(f"[{time.time()}] Sending motor update to websocket_server: {status_update}")

                # ✅ **Send update to `websocket_server.py` over a new TCP connection**
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect(("localhost", 9001))  # ✅ Replace with websocket_server's status port
                        s.sendall(json.dumps(status_update).encode('utf-8'))
                except Exception as e:
                    print(f"[{time.time()}] Error sending motor update to websocket_server: {e}")

        else:
            await asyncio.sleep(0.05)  # Prevent CPU overload







def main():
    """Start the robot control service and run the command processor asynchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # ✅ Correct way to run an async function in a non-async main()
    loop.create_task(process_commands())  # Schedule process_commands to run

    try:
        loop.run_forever()  # Keep the loop running
    except KeyboardInterrupt:
        print("Shutting down robot control service.")
    finally:
        loop.close()





if __name__ == '__main__':
    main()
