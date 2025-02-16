import time
import pyudev
import json
# --- Add these lines at the VERY TOP ---
import os
import sys
sdk_path = os.path.abspath('/home/pi/so-arm-configure/STservo_sdk')
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from STservo_sdk import *


# Constants
CALIBRATION_SPEED = 300
CALIBRATION_ACCELERATION = 50
CALIBRATION_BACKOFF = 50
MOVEMENT_UPDATE_INTERVAL = 0.05
INITIAL_MIN_POS = 1024
INITIAL_MAX_POS = 3072
THUMB_INITIAL_MIN = 2048
THUMB_INITIAL_MAX = 2500
CALIBRATION_FILE = "calibration.json"
CALIBRATED_MOTORS = [1, 2, 3, 4, 6]  # Motors to calibrate, NO motor 5

# --- (Rest of your arm_control.py code - MotorController, scan_interfaces, etc.) ---

def scan_interfaces_for_arm():
    """Scan for SO-ARM100 robot arm connected via USB."""
    interfaces = []
    context = pyudev.Context()
    for device in context.list_devices(subsystem='tty'):
        device_node = device.device_node
        if device_node and "ttyACM" in device_node:
            print(f"Found SO-ARM100 interface: {device_node}")
            interfaces.append(device_node)

    if not interfaces:
        print("No SO-ARM100 controllers found")
        return None
    elif len(interfaces) == 1:
        print(f"Using SO-ARM100 at {interfaces[0]}")
        return interfaces[0]
    else:
        print("Multiple SO-ARM100 controllers found. Exiting.")
        sys.exit()


class MotorController:
    """Class to manage motor movements and calibration."""
    def __init__(self, packet_handler):
        self.packet_handler = packet_handler
        self.last_positions = {}
        self.wrist_direction = 1  # 1 for one direction, -1 for the opposite
        self.thumb_direction = 1  # Same toggle mechanism
        self.motor_limits = {}  # Store calibrated min/max positions
        self.update_interval = MOVEMENT_UPDATE_INTERVAL
        # Initial motor definitions (used before calibration or if loading fails)
        self.initial_motor_data = {
            1: {"name": "base", "min_pos": INITIAL_MIN_POS, "max_pos": INITIAL_MAX_POS},
            2: {"name": "shoulder", "min_pos": INITIAL_MIN_POS, "max_pos": INITIAL_MAX_POS},
            3: {"name": "elbow", "min_pos": INITIAL_MIN_POS, "max_pos": INITIAL_MAX_POS},
            4: {"name": "wrist", "min_pos": INITIAL_MIN_POS, "max_pos": INITIAL_MAX_POS},
            5: {"name": "hand", "min_pos": 0, "max_pos": 4095},  # No calibration
            6: {"name": "thumb", "min_pos": THUMB_INITIAL_MIN, "max_pos": THUMB_INITIAL_MAX}
        }

    def calibrate_motor(self, motor_id, motor_name, initial_min, initial_max):
        """Calibrate a single motor, moving other motors to midpoint."""
        print(f"Calibrating {motor_name} (Motor {motor_id})...")

        # Special case for motor 2: move motor 3 to its MAX position
        if motor_id == 2:
            if 3 in self.motor_limits:
                motor3_pos = self.motor_limits[3]["max"]
            else:
                motor3_pos = self.initial_motor_data[3]["max_pos"]
            self.write_pos_ex(3, motor3_pos, CALIBRATION_SPEED, CALIBRATION_ACCELERATION)
            time.sleep(2)  # Wait for motor 3

        # Move other motors to their midpoints
        for other_motor_id in CALIBRATED_MOTORS:
            if other_motor_id != motor_id:
                if other_motor_id in self.motor_limits:
                    midpoint = (self.motor_limits[other_motor_id]["min"] + self.motor_limits[other_motor_id]["max"]) // 2
                else:
                     midpoint = (self.initial_motor_data[other_motor_id]["min_pos"] + self.initial_motor_data[other_motor_id]["max_pos"]) // 2
                self.write_pos_ex(other_motor_id, midpoint, CALIBRATION_SPEED, CALIBRATION_ACCELERATION)
        time.sleep(2)


        # Move to initial minimum position.
        self.write_pos_ex(motor_id, initial_min, CALIBRATION_SPEED, CALIBRATION_ACCELERATION)
        time.sleep(2)

        # Move towards minimum
        self.move_to_limit(motor_id, -1)
        min_pos = self.find_limit(motor_id)
        if min_pos is not None:
            min_pos += CALIBRATION_BACKOFF
        else:
            min_pos = initial_min
            print(f"Warning: ReadPos failed during min calibration of {motor_name}. Using initial value.")
        print(f"  Calibrated minimum for {motor_name}: {min_pos}")

        # Move to initial maximum position.
        self.write_pos_ex(motor_id, initial_max, CALIBRATION_SPEED, CALIBRATION_ACCELERATION)
        time.sleep(2)

        # Move towards maximum
        self.move_to_limit(motor_id, 1)
        max_pos = self.find_limit(motor_id)
        if max_pos is not None:
            max_pos -= CALIBRATION_BACKOFF
        else:
            max_pos = initial_max
            print(f"Warning: ReadPos failed during max calibration of {motor_name}. Using initial value.")
        print(f"  Calibrated maximum for {motor_name}: {max_pos}")

        self.motor_limits[motor_id] = {"min": min_pos, "max": max_pos, "name": motor_name}
        return min_pos, max_pos

    def move_to_limit(self, motor_id, direction):
        """Moves the motor continuously towards a limit."""
        target_position = 0 if direction < 0 else 4095
        self.write_pos_ex(motor_id, target_position, CALIBRATION_SPEED, CALIBRATION_ACCELERATION)

    def find_limit(self, motor_id, direction):
        """Move motor until it stalls."""
        last_pos_result = self.packet_handler.ReadPos(motor_id)
        time.sleep(0.1)
        current_pos_result = self.packet_handler.ReadPos(motor_id)

        if last_pos_result is None or current_pos_result is None:
            print(f"Warning: ReadPos returned None for motor {motor_id}.")
            return None

        last_pos = last_pos_result[0]
        current_pos = current_pos_result[0]

        while abs(current_pos - last_pos) > 2:
            last_pos = current_pos
            time.sleep(0.1)
            current_pos_result = self.packet_handler.ReadPos(motor_id)
            if current_pos_result is None:
                print(f"Warning: ReadPos returned None for motor {motor_id} during stall detection.")
                return None
            current_pos = current_pos_result[0]
        return current_pos

    def move_motor(self, motor_id, motor_name, speed, direction):
        """Move motor and return status."""
        if motor_id not in self.motor_limits:
            return {"success": False, "message": f"Motor {motor_id} ({motor_name}) not calibrated!"}

        min_pos = self.motor_limits[motor_id]["min"]
        max_pos = self.motor_limits[motor_id]["max"]

        current_pos_result = self.packet_handler.ReadPos(motor_id)
        if current_pos_result is None:
            return {"success": False, "message": f"ReadPos failed for motor {motor_id}."}

        current_pos = current_pos_result[0]
        delta_position = int(speed * direction * self.update_interval)
        new_position = current_pos + delta_position
        new_position = max(min_pos, min(max_pos, new_position))

        result, error = self.packet_handler.WritePosEx(motor_id, new_position, speed, 50)
        if result != COMM_SUCCESS or error != 0:
            return {"success": False, "message": f"Failed to move {motor_name} (Motor {motor_id}) to position {new_position}"}

        return {"success": True, "message": f"Moved {motor_name} to {new_position}"}


    def write_pos_ex(self, motor_id, position, speed, acc):
        """Wrapper for WritePosEx."""
        result, error = self.packet_handler.WritePosEx(motor_id, position, speed, acc)
        if result != COMM_SUCCESS or error != 0:
            print(f"Failed to move Motor {motor_id} to position {position}")

    def toggle_wrist_direction(self):
        """Toggle wrist direction."""
        self.wrist_direction *= -1

    def toggle_thumb_direction(self):
        """Toggle thumb direction."""
        self.thumb_direction *= -1

    def load_calibration(self):
        """Loads calibration data."""
        try:
            with open(CALIBRATION_FILE, "r") as f:
                loaded_data = json.load(f)
                self.motor_limits = {int(k): v for k, v in loaded_data.items()}
            print("Calibration data loaded.")
            return True
        except FileNotFoundError:
            print("Calibration file not found.")
            return False
        except json.JSONDecodeError:
            print("Error decoding calibration file.")
            return False

    def save_calibration(self):
        """Saves calibration data."""
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(self.motor_limits, f, indent=4)
        print("Calibration data saved.")


