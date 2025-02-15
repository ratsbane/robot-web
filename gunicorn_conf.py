import multiprocessing
import os
import sys

# Add /var/www/robot to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Global variables to hold shared resources
frame_ready = None
frame_data_list = None
frame_shape = None
camera_process = None
lock = None  # Add a global lock variable

def on_starting(server):
    """Gunicorn hook - runs in the master process before forking workers."""
    global frame_ready, frame_data_list, frame_shape, lock

    print("Gunicorn on_starting hook (master process)")

    # --- Shared Data Setup (Using Manager) ---
    frame_width = 640
    frame_height = 480
    channels = 3
    frame_shape = (frame_height, frame_width, channels)
    max_frame_size = frame_width * frame_height * channels

    manager = multiprocessing.Manager()  # Create a Manager
    frame_ready = manager.Value('i', 0)  # Shared Value
    # Create a *list* of two shared bytearrays
    frame_data_list = manager.list([manager.list(range(max_frame_size)), manager.list(range(max_frame_size))])
    lock = manager.Lock() # Create the lock here

def when_ready(server):
    """Gunicorn hook - runs in each worker process after forking."""
    global frame_ready, frame_data_list, frame_shape, camera_process, lock

    print(f"Gunicorn when_ready hook (worker process {os.getpid()})")

    # --- Camera Process Initialization (INSIDE the worker) ---
    from camera import CameraProcess  # Import *inside* the hook
    camera_process = CameraProcess(frame_ready, frame_data_list, frame_shape, lock)  # Pass lock
    camera_process.start()

def worker_exit(worker, reason):
    global camera_process  # No shms to close
    print(f"Worker process exiting. Cleaning resources.")
    if camera_process:
        camera_process.stop()


def on_exit(server):
    # No need to clean up shared memory when using a Manager
    print("Cleaning up resources on Gunicorn exit...")
