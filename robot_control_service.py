import socket
import time
import os
import sys
import json
import threading


# --- Add these lines at the VERY TOP ---
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
    exit()

port_handler = PortHandler(device)
packet_handler = sts(port_handler)
if not port_handler.openPort() or not port_handler.setBaudRate(1000000):
    print(f"Failed to connect to robot arm.")
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
HOST = 'localhost'
PORT = 9000
DEFAULT_SPEED = 500  # Default speed if not specified in the command

def handle_client(conn, addr):
    print(f"[{time.time()}] Connected by {addr}")
    with conn:
        while True:
            try:
                print(f"[{time.time()}] Waiting to receive data...")
                data = conn.recv(1024)
                print(f"[{time.time()}] Data received: {data}")
                if not data:
                    print(f"[{time.time()}] No data received. Breaking.")
                    break

                # --- Parse JSON Command ---
                try:
                    command_json = data.decode('utf-8').strip()
                    command = json.loads(command_json)  # Parse the JSON
                except json.JSONDecodeError:
                    print(f"[{time.time()}] Error: Invalid JSON received.")
                    conn.sendall(b'{"success": false, "message": "Invalid JSON"}')
                    continue

                print(f"[{time.time()}] Received command: {command}")

                result = None
                if command.get('command') == 'move_to':
                    motor_name = command.get('motor')
                    position = command.get('position')
                    speed = command.get('speed', DEFAULT_SPEED)  # Get speed, default if missing

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
                        result = {'success': False, 'message': f'Unknown motor: {motor_name}'}
                    elif isinstance(position, int): #Check that position is valid
                        result = motor_controller.move_motor_to_position(motor_id, motor_name, position, speed)
                    else: #position invalid
                        result = {'success': False, 'message': f'Invalid position: {position}'}

                elif command.get('command') == 'stop':
                    motor_name = command.get('motor')
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
                        result = motor_controller.move_motor(motor_id, motor_name, 0, 0)  # Stop
                    else:
                        result = {'success': False, 'message': f'Unknown motor to stop: {motor_name}'}

                elif command.get('command') == 'stop_all':
                    result = {'success':True, 'message': "All motors stopped"}
                    for motor_id in CALIBRATED_MOTORS:
                        motor_name = motor_controller.initial_motor_data[motor_id]['name']
                        motor_result = motor_controller.move_motor(motor_id, motor_name, 0, 0)
                        if not motor_result['success']:
                            result = motor_result #Return error.
                            break # Stop on first error.

                else:
                    result = {'success': False, 'message': f'Unknown command: {command.get("command")}'}

                # --- Send Response ---
                if result:
                    response_json = json.dumps(result)
                    print(f"[{time.time()}] Sending response: {response_json}")
                    conn.sendall(response_json.encode('utf-8'))
                else:
                    conn.sendall(b'{"success": false, "message": "Unknown error"}')  # Always send JSON


            except ConnectionResetError:
                print(f"[{time.time()}] Client disconnected unexpectedly")
                break
            except Exception as e:
                print(f"[{time.time()}] Error handling client: {e}")
                conn.sendall(json.dumps({'success': False, 'message': str(e)}).encode('utf-8'))  # Send error as JSON
                break

def main():
    try: #Wrap in try/finally to ensure closure.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            print(f"Robot Control Service listening on {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
    finally:
        if port_handler:
            print("Closing port handler...")
            port_handler.closePort()

if __name__ == '__main__':
    main()
