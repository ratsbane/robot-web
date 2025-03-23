### Control a LeRobot arm via web ###

```cd /var/www/robot
source venv/bin/activate
pkill gunicorn  # Ensure no old instances
/var/www/robot/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --preload app:app```


### Service Control ###

Add the following lines to `/etc/systemd/system/robot_arm_control.service`:

```
[Unit]
Description=Robot Arm Control Service
After=network.target

[Service]
User=pi
Group=www-data
WorkingDirectory=/var/www/robot
ExecStart=/var/www/robot/venv/bin/python /var/www/robot/robot_control_service.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

And add these lines to `/etc/systemd/system/robot_arm_web.service`

```[Unit]
Description=Robot Arm Web Server (FastAPI)
After=network.target robot_arm_control.service
Requires=robot_arm_control.service

[Service]
User=pi
Group=www-data
WorkingDirectory=/var/www/robot
ExecStart=/var/www/robot/venv/bin/uvicorn app:app --host 0.0.0.0 --port 5000
Restart=on-failure

[Install]
WantedBy=multi-user.target```

#### Enable services ####

```
sudo systemctl enable robot_arm_control.service
sudo systemctl enable robot_arm_web.service
```
#### Start the services ####

```
sudo systemctl start robot_arm_control.service
sudo systemctl start robot_arm_web.service
```

#### Check status ####
```
sudo systemctl status robot_arm_control.service
sudo systemctl status robot_arm_web.service
```

#### Stop and restart ####

```
sudo systemctl stop robot_arm_control.service
sudo systemctl restart robot_arm_control.service
sudo systemctl stop robot_arm_web.service
sudo systemctl restart robot_arm_web.service
```

#### View Logs ####

```
sudo journalctl -u robot_arm_web.service -f
sudo journalctl -u robot_arm_control.service -f
```


# Motor Logging Usage Guide with Video Capture

This guide explains how to use the new motor logging functionality added to the robot control service. The logger captures motor events (start, stop, direction changes) along with camera frames in the LeRobot-compatible format for GR00T.

## Installation

1. Copy the `motor_event_logger.py`, `video_capture.py`, and updated `robot_control_service.py` files to your robot control directory.
2. Install required dependencies:
   ```bash
   pip install opencv-python requests numpy
   ```
3. Make sure all files have execution permissions:
   ```bash
   chmod +x motor_event_logger.py video_capture.py robot_control_service.py
   ```
4. Update the video stream URLs in `robot_control_service.py` to match your camera setup.

## Starting and Stopping Logging

Logging is controlled via the same TCP socket interface used for motor commands. You can send JSON commands to start and stop logging:

### Start Logging

```json
{
  "command": "start_logging",
  "action_name": "pick_and_place",
  "description": "Robot picks up object from location A and places at location B",
  "timeout": 300,
  "video_sources": [
    {
      "source": "http://localhost:8080/stream",
      "method": "stream",
      "camera_id": 0
    }
  ]
}
```

Parameters:
- `action_name`: Name of the action being performed (required)
- `description`: Description of what the robot is doing (optional)
- `timeout`: Maximum duration in seconds for logging (optional)
- `video_sources`: Array of camera configurations (optional, overrides default configs)
  - `source`: URL or device ID for the video source
  - `method`: 'stream' for HTTP streaming, 'opencv' for direct capture
  - `camera_id`: Camera identifier (used in filename)

Response:
```json
{
  "success": true,
  "message": "Started logging to robot_logs/episode_0001"
}
```

### Stop Logging

```json
{
  "command": "stop_logging"
}
```

Response:
```json
{
  "success": true,
  "message": "Logging stopped. Recorded 24 events."
}
```

## Log Directory Structure

By default, logs are stored in the `robot_logs` directory relative to where the service is running. Each episode creates a directory with the following structure:

```
robot_logs/
├── episode_0000/
│   ├── metadata.json
│   ├── 00000000_robot_state.json
│   ├── 00000000_action.json
│   ├── 00000000_camera-0.jpg
│   ├── 00000001_robot_state.json
│   ├── 00000001_action.json
│   ├── 00000001_camera-0.jpg
│   └── ...
├── episode_0001/
└── ...
```

### Metadata Format

Each episode has a `metadata.json` file with information about the logging session:

```json
{
  "action_name": "pick_and_place",
  "description": "Robot picks up object from location A and places at location B",
  "start_time": "20250323_143015",
  "end_time": "20250323_143112",
  "timeout": 300,
  "total_events": 24,
  "cameras": [
    {"camera_id": 0}
  ]
}
```

### Robot State Format

Each event has a `robot_state.json` file with the motor's current state:

```json
{
  "timestamp": 1711284615.325871,
  "formatted_time": "2025-03-23 14:30:15.325",
  "motor_id": 1,
  "motor_name": "base",
  "current_position": 512
}
```

### Action Format

Each event has an `action.json` file with information about the command executed:

```json
{
  "timestamp": 1711284615.325871,
  "formatted_time": "2025-03-23 14:30:15.325",
  "command": "move",
  "motor_id": 1,
  "motor_name": "base",
  "direction": "max",
  "speed": 500,
  "target_position": 1023
}
```

### Camera Image Format

For each motor event, the system captures an image from each configured camera:

- Images are saved as JPEG files with the naming convention `{timestamp}_camera-{camera_id}.jpg`
- The timestamp matches the corresponding robot_state and action files
- Multiple cameras will generate multiple image files per timestamp

## Automatic Features

- **Disk Space Monitoring**: Logging stops automatically when available disk space falls below 1GB.
- **Timeout**: Logging stops automatically after the specified timeout period.
- **Graceful Shutdown**: Logging stops properly when the service is terminated.
- **Frame Capture**: Automatically captures frames from configured video sources for each motor event.

## Video Source Configuration

There are two ways to configure video sources:

1. **Static Configuration**: Define video sources in the `robot_control_service.py` file:
   ```python
   video_sources = [
       {
           'source': 'http://localhost:8080/stream', 
           'method': 'stream',
           'camera_id': 0
       },
       {
           'source': '/dev/video0',  # For direct device access
           'method': 'opencv',
           'camera_id': 1
       }
   ]
   ```

2. **Dynamic Configuration**: Provide video sources in the start_logging command:
   ```json
   {
     "command": "start_logging",
     "action_name": "test_sequence",
     "video_sources": [
       {
         "source": "http://192.168.1.100:8080/video",
         "method": "stream",
         "camera_id": 0
       }
     ]
   }
   ```

## Example Usage with Python

```python
import socket
import json

def send_command(command):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('localhost', 9000))
        s.sendall(json.dumps(command).encode('utf-8'))
        response = s.recv(1024).decode('utf-8')
        return json.loads(response)

# Start logging with camera configuration
start_cmd = {
    "command": "start_logging",
    "action_name": "demo_sequence",
    "description": "Testing the gripper movement",
    "timeout": 120,
    "video_sources": [
        {
            "source": "http://localhost:8080/stream",
            "method": "stream",
            "camera_id": 0
        }
    ]
}
print(send_command(start_cmd))

# Send motor commands
move_cmd = {
    "command": "move",
    "motor": "gripper",
    "direction": "max",
    "speed": 300
}
print(send_command(move_cmd))

# Stop logging when done
stop_cmd = {
    "command": "stop_logging"
}
print(send_command(stop_cmd))
```

## Example Usage with WebSocket from JavaScript

```javascript
// Example from web interface
function startLogging() {
    const command = {
        command: "start_logging",
        action_name: document.getElementById("actionName").value,
        description: document.getElementById("actionDescription").value,
        timeout: parseInt(document.getElementById("timeout").value)
    };
    
    sendWebSocketCommand(command)
        .then(response => {
            console.log("Logging started:", response);
        });
}

function stopLogging() {
    const command = {
        command: "stop_logging"
    };
    
    sendWebSocketCommand(command)
        .then(response => {
            console.log("Logging stopped:", response);
        });
}
```
