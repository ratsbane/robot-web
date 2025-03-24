#!/usr/bin/python3

import os
import json
import time
from datetime import datetime
import threading
import shutil
from video_capture import VideoCapture

class MotorEventLogger:
    """
    Logger that captures motor events in the LeRobot-compatible format for GR00T.
    Designed to log when motors start, stop, or change direction.
    """
    
    def __init__(self, base_dir="data", disk_threshold_gb=1, video_sources=None):
        self.base_dir = base_dir
        self.current_episode = None
        self.is_logging = False
        self.timestamp_counter = 0
        self.disk_threshold_bytes = disk_threshold_gb * 1024 * 1024 * 1024
        self.metadata = {}
        self.timeout_timer = None
        self.video_captures = []
        
        # Ensure base directory exists
        os.makedirs(base_dir, exist_ok=True)
        
        # Setup video capture if sources are provided
        if video_sources:
            self.setup_video_sources(video_sources)
    
    def setup_video_sources(self, video_sources):
        """
        Set up video capture sources
        
        Args:
            video_sources (list): List of dictionaries with video source configurations
                Each dictionary should contain:
                - 'source': URL or device ID
                - 'method': 'stream' or 'opencv'
                - 'camera_id': ID for the camera (used in filenames)
        """
        # Stop any existing captures
        self.stop_video_captures()
        
        # Create new captures
        for idx, source_config in enumerate(video_sources):
            source = source_config.get('source')
            method = source_config.get('method', 'stream')
            camera_id = source_config.get('camera_id', idx)
            
            capture = VideoCapture(
                video_source=source,
                capture_method=method,
                camera_id=camera_id
            )
            self.video_captures.append(capture)
    
    def start_video_captures(self):
        """Start all video captures"""
        for capture in self.video_captures:
            capture.start()
    
    def stop_video_captures(self):
        """Stop all video captures"""
        for capture in self.video_captures:
            capture.stop()
        self.video_captures = []
    
    def start_logging(self, action_name, description, timeout=None, **kwargs):
        """
        Start a new logging episode
        
        Args:
            action_name (str): Name of the action being performed
            description (str): Description of the episode
            timeout (int, optional): Timeout in seconds to automatically stop logging
            **kwargs: Additional metadata to store
            
        Returns:
            tuple: (success boolean, message string)
        """
        if self.is_logging:
            return False, "Logging already in progress"
        
        # Check disk space
        if self._check_disk_space() < self.disk_threshold_bytes:
            return False, "Not enough disk space available"
        
        # Create a new episode directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get the next episode number
        episode_dirs = [d for d in os.listdir(self.base_dir) 
                      if os.path.isdir(os.path.join(self.base_dir, d)) and d.startswith("episode_")]
        episode_count = len(episode_dirs)
        
        self.current_episode = f"episode_{episode_count:04d}"
        episode_dir = os.path.join(self.base_dir, self.current_episode)
        os.makedirs(episode_dir, exist_ok=True)
        
        # Save metadata
        self.metadata = {
            "action_name": action_name,
            "description": description,
            "start_time": timestamp,
            "timeout": timeout,
            "cameras": [{"camera_id": cap.camera_id} for cap in self.video_captures],
            **kwargs
        }
        
        with open(os.path.join(episode_dir, "metadata.json"), "w") as f:
            json.dump(self.metadata, f, indent=2)
        
        # Reset timestamp counter
        self.timestamp_counter = 0
        self.is_logging = True
        
        # Start video captures if available
        self.start_video_captures()
        
        # Set timeout if specified
        if timeout:
            self.timeout_timer = threading.Timer(timeout, self.stop_logging)
            self.timeout_timer.daemon = True
            self.timeout_timer.start()

        # TODO this is temporary, just for debugging
        try:
            with open(os.path.join(self.base_dir, "recording_test.txt"), "w") as f:
                f.write(f"Recording started at {datetime.now()}")
        except Exception as e:
            print(f"Error writing test file: {e}") 
        return True, f"Started logging to {episode_dir}"


    def stop_logging(self):
        """
        Stop the current logging episode
        
        Returns:
            tuple: (success boolean, message string)
        """
        if not self.is_logging:
            return False, "No logging in progress"
        
        # Cancel timeout timer if active
        if self.timeout_timer and self.timeout_timer.is_alive():
            self.timeout_timer.cancel()
        
        # Stop video captures
        self.stop_video_captures()
        
        self.is_logging = False
        
        # Update metadata with end time
        if self.current_episode:
            episode_dir = os.path.join(self.base_dir, self.current_episode)
            self.metadata["end_time"] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.metadata["total_events"] = self.timestamp_counter
            
            with open(os.path.join(episode_dir, "metadata.json"), "w") as f:
                json.dump(self.metadata, f, indent=2)
        
        return True, f"Logging stopped. Recorded {self.timestamp_counter} events."
    
    def log_motor_event(self, motor_id, motor_name, command, direction=None, speed=None, current_pos=None, target_pos=None):
        """
        Log a motor event
        
        Args:
            motor_id (int): ID of the motor
            motor_name (str): Name of the motor
            command (str): Command type (move, stop, etc)
            direction (str, optional): Direction of movement
            speed (int, optional): Speed setting
            current_pos (int, optional): Current position
            target_pos (int, optional): Target position
            
        Returns:
            bool: True if logged successfully, False otherwise
        """
        if not self.is_logging or not self.current_episode:
            return False
        
        # Check disk space
        if self._check_disk_space() < self.disk_threshold_bytes:
            self.stop_logging()
            return False
        
        episode_dir = os.path.join(self.base_dir, self.current_episode)
        timestamp_str = f"{self.timestamp_counter:08d}"
        
        # Create robot state and action data
        timestamp = time.time()
        formatted_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Robot state (positions of all joints)
        robot_state = {
            "timestamp": timestamp,
            "formatted_time": formatted_time,
            "motor_id": motor_id,
            "motor_name": motor_name,
            "current_position": current_pos
        }
        
        # Action data (what command was issued)
        action_data = {
            "timestamp": timestamp,
            "formatted_time": formatted_time,
            "command": command,
            "motor_id": motor_id,
            "motor_name": motor_name
        }
        
        if direction is not None:
            action_data["direction"] = direction
        
        if speed is not None:
            action_data["speed"] = speed
            
        if target_pos is not None:
            action_data["target_position"] = target_pos
        
        # Save robot state
        robot_state_file = os.path.join(episode_dir, f"{timestamp_str}_robot_state.json")
        with open(robot_state_file, "w") as f:
            json.dump(robot_state, f, indent=2)
        
        # Save action
        action_file = os.path.join(episode_dir, f"{timestamp_str}_action.json")
        with open(action_file, "w") as f:
            json.dump(action_data, f, indent=2)
        
        # Capture and save frames from all cameras
        for capture in self.video_captures:
            if capture:
                camera_file = os.path.join(episode_dir, f"{timestamp_str}_camera-{capture.camera_id}.jpg")
                capture.save_frame(camera_file)
        
        # Increment timestamp counter
        self.timestamp_counter += 1
        
        return True
    
    def _check_disk_space(self):
        """Check available disk space in bytes"""
        return shutil.disk_usage(self.base_dir).free
