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

def send_command(command_dict):
    """Sends a command (as a dictionary) to the robot control service and prints the response."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((RCS_HOST, RCS_PORT))
            command_json = json.dumps(command_dict) # Convert dict to JSON string
            s.sendall(command_json.encode('utf-8'))
            response = s.recv(1024)
            try:
                response_json = response.decode('utf-8').strip()
                response_data = json.loads(response_json)  # Parse the JSON
                print(f"Response: {response_data}")  # Print the parsed JSON
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON response: {response.decode('utf-8').strip()}")
            return True
    except ConnectionRefusedError:
        print("Error: Could not connect to robot_control_service.py.  Is it running?")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_motor(motor_name, min_pos, max_pos):
    """Tests movement of a specific motor to min, max, and center."""
    print(f"\nTesting {motor_name} movement (min={min_pos}, max={max_pos})...")

    center_pos = (min_pos + max_pos) // 2

    # Move to minimum position
    print(f"Moving {motor_name} to minimum position ({min_pos})...")
    if not send_command({"command": "move_to", "motor": motor_name, "position": min_pos}):
        return False
    time.sleep(2)

    # Move to maximum position
    print(f"Moving {motor_name} to maximum position ({max_pos})...")
    if not send_command({"command": "move_to", "motor": motor_name, "position": max_pos}):
        return False
    time.sleep(2)

    # Move to center position
    print(f"Moving {motor_name} to center position ({center_pos})...")
    if not send_command({"command": "move_to", "motor": motor_name, "position": center_pos}):
        return False
    time.sleep(2)

    return True


def main():
    """Main function to test robot arm movements."""

    if not check_robot_control_service():
        print("Please start robot_control_service.py before running this test.")
        return

    input("Press Enter to begin testing the robot arm.  Observe the arm carefully!")

    # --- Load Calibration Data ---
    try:
        with open(CALIBRATION_FILE, "r") as f:
            calibration_data = json.load(f)
            # Convert keys to integers:
            calibration_data = {int(k): v for k,v in calibration_data.items()}
    except FileNotFoundError:
        print(f"Error: Calibration file not found at {CALIBRATION_FILE}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON in {CALIBRATION_FILE}")
        return
    except Exception as e:
        print(f"Error loading calibration file: {e}")
        return

    # --- Test Each Motor ---
    for motor_id, motor_data in calibration_data.items():  # Corrected iteration
      try:
        motor_name = motor_data['name']
        min_pos = motor_data['min']
        max_pos = motor_data['max']
        if not test_motor(motor_name, min_pos, max_pos):
            return  # Stop on the first failure
      except KeyError as e:
          print(f"Error accessing motor data: {e}")
          return

    print("\nAll tests completed.  Please visually confirm all movements were correct.")

if __name__ == '__main__':
    main()
