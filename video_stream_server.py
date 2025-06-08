#!/usr/bin/env python3
"""
Improved video streaming server using Flask and OpenCV with better resource management
"""
from flask import Flask, Response, render_template
import cv2
import argparse
import threading
import time
import os
import gc
import signal
import logging
from logging.handlers import RotatingFileHandler

# Set up logging
log_dir = "/var/log/robot"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
log_file = os.path.join(log_dir, "video_stream.log")

# Create logger
logger = logging.getLogger("video_stream")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Create Flask application
app = Flask(__name__)

# Global variables
camera = None
output_frame = None
lock = threading.Lock()
frame_count = 0
last_frame_time = time.time()
active_streams = 0
max_fps = 15  # Limit FPS to reduce load
running = True
stream_event = threading.Event()

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
        .controls {
            margin-top: 20px;
        }
        .fps-display {
            margin-top: 10px;
            font-style: italic;
            color: #666;
        }
    </style>
    <script>
        // Add error handling for the image
        window.addEventListener('DOMContentLoaded', function() {
            const img = document.getElementById('stream-img');
            
            img.onerror = function() {
                console.error('Video stream error occurred');
                // After error, retry with a fresh URL (cache buster)
                setTimeout(function() {
                    if (img) {
                        img.src = '/video_feed?t=' + new Date().getTime();
                    }
                }, 1000);
            };
            
            // Periodically refresh the stream to prevent memory buildup
            setInterval(function() {
                if (img) {
                    img.src = '/video_feed?t=' + new Date().getTime();
                }
            }, 30000); // Refresh every 30 seconds
        });
    </script>
</head>
<body>
    <div class="container">
        <h1>Robot Camera Stream</h1>
        <div class="stream-container">
            <img id="stream-img" src="{{ url_for('video_feed') }}" alt="Robot Camera Stream">
        </div>
        <div class="fps-display">
            <span id="fps">Initializing...</span>
        </div>
    </div>
</body>
</html>
"""

def cleanup_resources():
    """Release camera and clean up resources"""
    global camera, running
    logger.info("Cleaning up resources...")
    running = False
    stream_event.set()  # Signal all threads to exit
    
    # Release camera
    if camera is not None:
        with lock:
            camera.release()
            camera = None
    
    # Force garbage collection
    gc.collect()
    logger.info("Cleanup complete")

def signal_handler(sig, frame):
    """Handle signals for graceful shutdown"""
    logger.info(f"Received signal {sig}, shutting down...")
    cleanup_resources()
    os._exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def open_camera():
    """Open camera with retry logic"""
    for attempt in range(5):
        try:
            cam = cv2.VideoCapture(0)
            if not cam.isOpened():
                logger.error(f"Failed to open camera on attempt {attempt+1}")
                time.sleep(2)
                continue
            
            # Set resolution and parameters for better performance
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cam.set(cv2.CAP_PROP_FPS, max_fps)
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffering
            
            logger.info("Camera opened successfully")
            return cam
        except Exception as e:
            logger.error(f"Error opening camera: {str(e)}")
            time.sleep(2)
    
    logger.error("Failed to open camera after multiple attempts")
    return None

def capture_frames():
    """Capture frames from the camera and update the global output_frame variable"""
    global output_frame, camera, lock, frame_count, last_frame_time, running
    
    logger.info("Starting frame capture thread")
    
    # Initialize camera
    if camera is None:
        camera = open_camera()
        if camera is None:
            logger.error("Could not initialize camera")
            return
    
    # Keep capturing frames
    frame_time = time.time()
    error_count = 0
    
    while running:
        try:
            # Rate limiting to prevent CPU overload and reduce browser strain
            current_time = time.time()
            elapsed = current_time - frame_time
            
            if elapsed < 1.0/max_fps:
                # Sleep to maintain desired FPS
                time.sleep(1.0/max_fps - elapsed)
            
            frame_time = time.time()
            
            # Check if there are active streams
            if active_streams == 0:
                # If no one is watching, slow down capture to save resources
                time.sleep(0.5)
                continue
            
            # Capture frame
            success, frame = camera.read()
            
            if not success:
                error_count += 1
                logger.warning(f"Failed to capture frame from camera (error {error_count})")
                
                # If too many consecutive errors, try to reopen camera
                if error_count > 5:
                    logger.error("Too many capture errors, reopening camera")
                    with lock:
                        if camera is not None:
                            camera.release()
                        camera = open_camera()
                        error_count = 0
                
                time.sleep(0.5)
                continue
            
            # Reset error counter on success
            error_count = 0
            
            # Update frame counter and calculate FPS
            frame_count += 1
            if frame_count % 30 == 0:  # Log FPS every 30 frames
                now = time.time()
                fps = 30 / (now - last_frame_time)
                last_frame_time = now
                logger.debug(f"Current FPS: {fps:.2f}")
            
            # Process frame to reduce size/complexity (optional)
            # Resize if needed to reduce bandwidth
            # frame = cv2.resize(frame, (320, 240))
            
            # Acquire lock before updating the output frame
            with lock:
                output_frame = frame.copy()
            
        except Exception as e:
            logger.error(f"Error in capture thread: {str(e)}")
            time.sleep(0.5)
    
    logger.info("Frame capture thread exiting")

def generate_frames():
    """Generate MJPEG stream from output_frame with better error handling"""
    global output_frame, lock, active_streams
    
    try:
        active_streams += 1
        logger.info(f"New stream connected. Active streams: {active_streams}")
        
        while running:
            try:
                # Wait until we have a frame
                with lock:
                    if output_frame is None:
                        continue
                    
                    # Encode the frame as JPEG with reduced quality for better performance
                    _, encoded_frame = cv2.imencode('.jpg', output_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    
                # Convert to bytes
                frame_bytes = encoded_frame.tobytes()
                
                # Yield the frame in MJPEG format
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + f"{len(frame_bytes)}".encode() + b'\r\n\r\n' + 
                       frame_bytes + b'\r\n')
                
                # Add a slightly longer delay to reduce browser CPU usage
                # Adjust this value to trade between smoothness and CPU usage
                time.sleep(1.0/max_fps)
                
            except Exception as e:
                logger.error(f"Error in stream generation: {str(e)}")
                time.sleep(1.0)
                
    except Exception as e:
        logger.error(f"Stream thread exception: {str(e)}")
    finally:
        # Decrement active streams counter when a client disconnects
        active_streams -= 1
        logger.info(f"Stream disconnected. Active streams: {active_streams}")

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    """Route to serve the video feed"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def render_template_string(template_string):
    """Simple function to replace Flask's render_template_string"""
    # Replace the url_for function call with the actual URL
    return template_string.replace("{{ url_for('video_feed') }}", "/video_feed")

def main():
    """Main function to start the server"""
    logger.info("Starting video streaming server")
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Video Streaming Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on")
    parser.add_argument("--fps", type=int, default=15, help="Maximum FPS")
    args = parser.parse_args()
    
    global max_fps
    max_fps = args.fps
    
    # Start the frame capture thread
    frame_thread = threading.Thread(target=capture_frames, daemon=True)
    frame_thread.start()
    
    # Start the Flask server
    logger.info(f"Starting video streaming server on http://{args.host}:{args.port}/")
    try:
        # Use a production-ready WSGI server if available
        try:
            from waitress import serve
            logger.info("Using Waitress WSGI server")
            serve(app, host=args.host, port=args.port, threads=4)
        except ImportError:
            # Fall back to Flask's built-in server
            logger.info("Using Flask's built-in server (production use not recommended)")
            app.run(host=args.host, port=args.port, threaded=True, debug=False)
    except Exception as e:
        logger.error(f"Server exception: {str(e)}")
    finally:
        # Ensure cleanup on exit
        cleanup_resources()

if __name__ == "__main__":
    # First, make sure required packages are installed
    required_packages = ["opencv-python", "flask"]
    try:
        for package in required_packages:
            __import__(package)
    except ImportError:
        logger.info("Required packages not found. Installing...")
        os.system("pip3 install opencv-python flask waitress")
        logger.info("Installation complete. Running server...")
    
    # Start the server
    main()
