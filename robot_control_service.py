import socket
import time


import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

sdk_path = os.path.abspath('/home/pi/so-arm-configure/')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from STservo_sdk import *  # Ensure this is the correct import

from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# --- Robot Arm Initialization (as before) ---
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

def handle_client(conn, addr):
    print(f"Connected by {addr}")
    with conn:
        while True:
            try:
                data = conn.recv(1024)  # Receive data from the client
                if not data:
                    break  # Client disconnected
                command = data.decode('utf-8').strip()
                print(f"Received command: {command}")

                # --- Process Commands (using MotorController) ---
                result = None #Store result
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
                            result = {'success': False, 'message': f'Unknown motor: {motor_name}'}
                        elif direction_str == 'left' or direction_str == 'up':
                            result = motor_controller.move_motor(motor_id, motor_name, 500, -1)
                        elif direction_str == 'right' or direction_str == 'down':
                            result = motor_controller.move_motor(motor_id, motor_name, 500, 1)
                        else:
                           result = {'success': False, 'message': f'Invalid direction: {direction_str}'}


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
                            result = {'success':False, 'message':f'Unknown motor to stop: {motor_name}'}

                elif command == 'stop_all':
                    for motor_id in CALIBRATED_MOTORS:
                        motor_name = motor_controller.initial_motor_data[motor_id]['name']
                        result = motor_controller.move_motor(motor_id, motor_name, 0, 0)
                        if not result['success']:
                            break #Stop on first error

                elif command.startswith("move_"): #Handle hand and thumb
                     parts = command.split('_')
                     if len(parts) == 2 and parts[1] in ['hand', 'thumb']:
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
                            result = {'success':False, 'message': f'Unknown motor: {motor_name}'}
                        elif motor_name == 'hand':
                            motor_controller.toggle_wrist_direction()
                            result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.wrist_direction)
                        elif motor_name == 'thumb':
                            motor_controller.toggle_thumb_direction()
                            result = motor_controller.move_motor(motor_id, motor_name, 500, motor_controller.thumb_direction)

                else:
                    result = {'success':False, 'message':f'Unknown command: {command}'}

                # --- Send Response ---
                if result:
                    conn.sendall(result['message'].encode('utf-8'))
                else: #Should not happen, kept for safety.
                    conn.sendall(b"Error: No result from command processing.")


            except ConnectionResetError:
                print("Client disconnected unexpectedly")
                break
            except Exception as e:
                print(f"Error handling client: {e}")
                break

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Robot Control Service listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()  # Accept a connection
            handle_client(conn, addr)  # Handle the client in a function

if __name__ == '__main__':
    main()
