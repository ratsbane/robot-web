import socket
import time
import subprocess
import json

# --- Configuration ---
RCS_HOST = 'localhost'
RCS_PORT = 9000

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

def send_command(command):
    """Sends a command to the robot control service and prints the response."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((RCS_HOST, RCS_PORT))
            s.sendall(command.encode('utf-8'))
            response = s.recv(1024)
            try:
                response_json = response.decode('utf-8').strip()
                response_data = json.loads(response_json)
                print(f"Response: {response_data}")
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON response: {response.decode('utf-8').strip()}")
            return True
    except ConnectionRefusedError:
        print("Error: Could not connect to robot_control_service.py.  Is it running?")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_motor(motor_name):
    """Tests movement of a specific motor."""
    print(f"\nTesting {motor_name} movement...")

    if not send_command(f"move_{motor_name}_up"):  # Use "up" and "down"
        return False
    time.sleep(2)
    if not send_command(f"stop_{motor_name}"):
        return False
    time.sleep(1)
    if not send_command(f"move_{motor_name}_down"):  # Use "up" and "down"
        return False
    time.sleep(2)
    if not send_command(f"stop_{motor_name}"):
        return False
    time.sleep(1)
    return True


def main():
    """Main function to test robot arm movements."""

    if not check_robot_control_service():
        print("Please start robot_control_service.py before running this test.")
        return

    input("Press Enter to begin testing the robot arm.  Observe the arm carefully!")

    # Test all motors, including hand and thumb, using the same function
    motors = ["base", "shoulder", "elbow", "wrist", "hand", "thumb"]
    for motor in motors:
        if not test_motor(motor):
            return  # Stop on the first failure

    print("\nAll tests completed.  Please visually confirm all movements were correct.")

if __name__ == '__main__':
    main()
