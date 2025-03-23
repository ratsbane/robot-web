#!/usr/bin/python3

import cv2
import requests
import numpy as np
import threading
import time
import os
from urllib.parse import urlparse

class VideoCapture:
    """
    Class to capture frames from an MJPEG stream or other video source.
    Supports both direct OpenCV capture and HTTP streaming.
    """
    
    def __init__(self, video_source, capture_method='stream', camera_id=0, buffer_size=10):
        """
        Initialize the video capture.
        
        Args:
            video_source (str): URL or device ID for the video source
            capture_method (str): 'stream' for HTTP streaming, 'opencv' for direct capture
            camera_id (int): Camera identifier (for GR00T naming convention)
            buffer_size (int): Number of frames to keep in buffer
        """
        self.video_source = video_source
        self.capture_method = capture_method.lower()
        self.camera_id = camera_id
        self.buffer_size = buffer_size
        self.is_running = False
        self.latest_frame = None
        self.frame_buffer = []
        self.lock = threading.Lock()
        self.capture_thread = None
        self.last_frame_time = 0
        
        # Parse URL if provided
        if isinstance(video_source, str) and '://' in video_source:
            parsed_url = urlparse(video_source)
            self.host = parsed_url.netloc
            self.stream_path = parsed_url.path
            if not self.stream_path:
                self.stream_path = '/'
                
        # For OpenCV direct capture
        self.cap = None
    
    def start(self):
        """Start the video capture thread"""
        if self.is_running:
            return False
            
        self.is_running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        return True
    
    def stop(self):
        """Stop the video capture thread"""
        self.is_running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
            
        if self.cap and self.capture_method == 'opencv':
            self.cap.release()
            self.cap = None
    
    def get_frame(self):
        """Get the most recent frame"""
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None
    
    def save_frame(self, save_path):
        """
        Save the current frame to the specified path
        
        Args:
            save_path (str): Full path where to save the image
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        frame = self.get_frame()
        if frame is not None:
            try:
                cv2.imwrite(save_path, frame)
                return True
            except Exception as e:
                print(f"Error saving frame: {e}")
        return False
    
    def _capture_loop(self):
        """Main capture loop that runs in a separate thread"""
        if self.capture_method == 'stream':
            self._stream_capture_loop()
        elif self.capture_method == 'opencv':
            self._opencv_capture_loop()
    
    def _stream_capture_loop(self):
        """Capture loop for HTTP streaming"""
        while self.is_running:
            try:
                # Make HTTP request to the stream
                with requests.get(self.video_source, stream=True, timeout=10) as r:
                    # Check if the request was successful
                    if r.status_code != 200:
                        print(f"Error accessing stream: HTTP {r.status_code}")
                        time.sleep(1)
                        continue
                    
                    # Read the stream content
                    bytes_data = bytes()
                    for chunk in r.iter_content(chunk_size=1024):
                        bytes_data += chunk
                        a = bytes_data.find(b'\xff\xd8')  # JPEG start
                        b = bytes_data.find(b'\xff\xd9')  # JPEG end
                        
                        if a != -1 and b != -1:
                            jpg = bytes_data[a:b+2]
                            bytes_data = bytes_data[b+2:]
                            
                            # Decode the image
                            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                with self.lock:
                                    self.latest_frame = frame
                                    self.last_frame_time = time.time()
                                    
                                    # Maintain buffer size
                                    self.frame_buffer.append(frame)
                                    if len(self.frame_buffer) > self.buffer_size:
                                        self.frame_buffer.pop(0)
                            
                            # Break from loop if not running anymore
                            if not self.is_running:
                                break
            
            except Exception as e:
                print(f"Error capturing from stream: {e}")
                time.sleep(1)  # Wait before retrying
    
    def _opencv_capture_loop(self):
        """Capture loop using OpenCV's VideoCapture"""
        try:
            # Initialize capture
            if self.cap is None:
                if isinstance(self.video_source, int):
                    self.cap = cv2.VideoCapture(self.video_source)
                else:
                    self.cap = cv2.VideoCapture(self.video_source)
                
                if not self.cap.isOpened():
                    print(f"Could not open video source: {self.video_source}")
                    return
            
            # Capture frames
            while self.is_running and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.latest_frame = frame
                        self.last_frame_time = time.time()
                        
                        # Maintain buffer size
                        self.frame_buffer.append(frame)
                        if len(self.frame_buffer) > self.buffer_size:
                            self.frame_buffer.pop(0)
                else:
                    print("Failed to grab frame")
                    break
                    
                time.sleep(0.01)  # Small delay to prevent CPU overuse
        
        except Exception as e:
            print(f"Error in OpenCV capture: {e}")
        
        finally:
            if self.cap:
                self.cap.release()
                self.cap = None
    
    def get_frame_rate(self):
        """Calculate approximate frame rate based on buffer timing"""
        if len(self.frame_buffer) < 2:
            return 0
            
        elapsed = self.last_frame_time - time.time()
        if elapsed <= 0:
            return 0
            
        return len(self.frame_buffer) / elapsed
