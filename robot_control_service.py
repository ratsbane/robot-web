import socket
import time
# --- Add these lines at the VERY TOP ---
import os
import sys
import json
# Use the *correct* path to STservo_sdk here:
sdk_path = os.path.abspath('/home/pi/so-arm-configure/')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)
# --- End added lines ---

from arm_control import MotorController, scan_interfaces_for_arm, PortHandler, sts, CALIBRATED_MOTORS

# --- TCP Socket Server ---
HOST = 'localhost'
PORT = 9000

# Global variables to hold the port handler and packet handler
port_handler = None
packet_handler = None
motor_controller = None

def handle_client(conn, addr):
    global motor_controller # Access the global motor_controller
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
                command = data.decode('utf-8').strip()
                print(f"[{time.time()}] Received command: {command}")

                result = None
                if command.startswith('move_'):
                    parts = command.split('_')
                    if len(parts) == 3:
                        motor_name = parts[1]
                        direction_str = parts[2]
                        motor_id = None

                        # Find Motor ID
                        if motor_controller: # Check that we have initialized.
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
                    result = {'success':True, 'message': "All motors stopped"}
                    for motor_id in CALIBRATED_MOTORS:
                        motor_name = motor_controller.initial_motor_data[motor_id]['name']
                        motor_result = motor_controller.move_motor(motor_id, motor_name, 0, 0)
                        if not motor_result['success']:
                            result = motor_result # Return the error
                            break # Stop on first error

                else:
                    result = {'success':False, 'message':f'Unknown command: {command}'}
                # --- Send Response ---
                if result:
                    response_json = json.dumps(result)
                    print(f"[{time.time()}] Sending response: {response_json}")
                    conn.sendall(response_json.encode('utf-8'))
                else:
                    conn.sendall(b"Error: No result from command processing.")

            except ConnectionResetError:
                print(f"[{time.time()}] Client disconnected unexpectedly")
                break
            except Exception as e:
                print(f"[{time.time()}] Error handling client: {e}")
                conn.sendall(f"Error: {e}".encode('utf-8'))
                break

def main():
    global port_handler, packet_handler, motor_controller  # Use global variables

    # --- Robot Arm Initialization (Moved INSIDE main) ---
    device = scan_interfaces_for_arm()
    if not device:
        print("No SO-ARM100 controller found. Exiting.")
        return  # Use return instead of exit()

    port_handler = PortHandler(device)
    packet_handler = sts(port_handler)
    if not port_handler.openPort():
        print(f"Failed to open port {device}")
        return
    if not port_handler.setBaudRate(1000000):
        print(f"Failed to set baud rate for {device}")
        return

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

    # --- TCP Socket Server (Wrapped in try...finally) ---
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            print(f"Robot Control Service listening on {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()
                handle_client(conn, addr)
    finally:
        if port_handler:
            print("Closing port handler...")
            port_handler.closePort()  # Close port on exit

if __name__ == '__main__':
    main()

