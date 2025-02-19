import socket
import time
import subprocess
import json
import os

# --- Configuration ---
RCS_HOST = 'localhost'
RCS_PORT = 9000
CALIBRATION_FILE = "../calibration.json"  # Path to calibration file

def check_robot_control_service():
    """Checks if robot_control_service.py is running."""
    try:
        output = subprocess.check_output(["pgrep", "-f", "robot_control_service.py"]).decode('utf-8')
        if output:
            print("robot_control_service.py is running.")
            return True
        else:
            print("robot_control_service.py is NOT running.")
            return False
    except subprocess.CalledProcessError:
        print("robot_control_service.py is NOT running.")
        return False
    except FileNotFoundError:
        print("Error: pgrep command not found.  Is procps installed?")
        return False


def send_command(s, command_dict):
    """Sends a command using an open socket."""
    try:
        command_json = json.dumps(command_dict)
        s.sendall(command_json.encode('utf-8'))  # Send command
        response = s.recv(1024)  # Receive response
        response_data = json.loads(response.decode('utf-8').strip())
        print(f"Response: {response_data}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False



def test_motor(s, motor_name, min_pos, max_pos):
    """Tests movement of a specific motor with a persistent socket."""
    print(f"\nTesting {motor_name} movement (min={min_pos}, max={max_pos})...")

    center_pos = (min_pos + max_pos) // 2

    for position in [min_pos, max_pos, center_pos]:
        print(f"Moving {motor_name} to position ({position})...")
        if not send_command(s, {"command": "move_to", "motor": motor_name, "position": position}):
            return False
        time.sleep(2)

    return True


def main():
    if not check_robot_control_service():
        print("Please start robot_control_service.py before running this test.")
        return

    input("Press Enter to begin testing the robot arm. Observe the arm carefully!")

    try:
        with open(CALIBRATION_FILE, "r") as f:
            calibration_data = json.load(f)
            calibration_data = {int(k): v for k, v in calibration_data.items()}
    except Exception as e:
        print(f"Error loading calibration file: {e}")
        return

    # Open socket once
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((RCS_HOST, RCS_PORT))

        # Test Each Motor
        for motor_id, motor_data in calibration_data.items():
            try:
                motor_name = motor_data['name']
                min_pos = motor_data['min']
                max_pos = motor_data['max']
                if not test_motor(s, motor_name, min_pos, max_pos):
                    return
            except KeyError as e:
                print(f"Error accessing motor data: {e}")
                return

    print("\nAll tests completed. Please visually confirm all movements were correct.")





if __name__ == '__main__':
    main()
