#!/usr/bin/env python3
"""
Video streaming server using Flask and OpenCV
"""
from flask import Flask, Response, render_template
import cv2
import argparse
import threading
import time
import os

# Create Flask application
app = Flask(__name__)

# Global variables
camera = None
output_frame = None
lock = threading.Lock()

# HTML template for the main page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Robot Camera</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            text-align: center;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #333;
        }
        .stream-container {
            margin-top: 20px;
        }
        img {
            max-width: 100%;
            border: 1px solid #ddd;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Robot Camera Stream</h1>
        <div class="stream-container">
            <img src="{{ url_for('video_feed') }}" alt="Robot Camera Stream">
        </div>
    </div>
</body>
</html>
"""

def capture_frames():
    """
    Capture frames from the camera and update the global output_frame variable
    """
    global output_frame, camera, lock
    
    # Initialize camera
    if camera is None:
        # Try to open the camera
        camera = cv2.VideoCapture(0)  # Use 0 for the default camera
        
        # Set resolution
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Allow camera to warm up
        time.sleep(2.0)
    
    # Keep capturing frames
    while True:
        success, frame = camera.read()
        
        if not success:
            print("Failed to capture frame from camera")
            time.sleep(0.1)
            continue
        
        # Acquire lock before updating the output frame
        with lock:
            output_frame = frame.copy()

def generate_frames():
    """
    Generate MJPEG stream from output_frame
    """
    global output_frame, lock
    
    while True:
        # Wait until we have a frame
        with lock:
            if output_frame is None:
                continue
            
            # Encode the frame as JPEG
            ret, encoded_frame = cv2.imencode('.jpg', output_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            if not ret:
                continue
            
            # Convert to bytes
            frame_bytes = encoded_frame.tobytes()
        
        # Yield the frame in MJPEG format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Add a short delay
        time.sleep(0.04)  # ~25 FPS

@app.route('/')
def index():
    """
    Serve the main HTML page
    """
    # Use the template instead of rendering from a file
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    """
    Route to serve the video feed
    """
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def render_template_string(template_string):
    """
    Simple function to replace Flask's render_template_string
    """
    # Replace the url_for function call with the actual URL
    return template_string.replace("{{ url_for('video_feed') }}", "/video_feed")

def main():
    """
    Main function to start the server
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Video Streaming Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on")
    args = parser.parse_args()
    
    # Start the frame capture thread
    frame_thread = threading.Thread(target=capture_frames, daemon=True)
    frame_thread.start()
    
    # Start the Flask server
    print(f"Starting video streaming server on http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)

if __name__ == "__main__":
    # First, make sure opencv and flask are installed
    try:
        import cv2
        import flask
    except ImportError:
        print("Required packages not found. Installing...")
        os.system("pip3 install opencv-python flask")
        print("Installation complete. Running server...")
    
    # Start the server
    main()
