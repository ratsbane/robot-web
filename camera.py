import cv2
import time
import multiprocessing
import numpy as np  # No shared_memory import

class CameraProcess:
    def __init__(self, active_buffer_index, frame_data_list, frame_shape, lock): # Add lock parameter
        self.active_buffer_index = active_buffer_index  # multiprocessing.Value
        self.frame_data_list = frame_data_list  # List of two shared bytearrays
        self.frame_shape = frame_shape
        self.camera = None
        self.running = True
        self.process = None
        self.lock = lock  # Add lock attribute


    def _camera_loop(self):
        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            print("Error: Could not open camera in CameraProcess")
            return

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_shape[1])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_shape[0])
        # self.camera.set(cv2.CAP_PROP_FPS, 15)

        current_buffer = 0

        while self.running:
            success, frame = self.camera.read()
            if success:
                frame = cv2.resize(frame, (self.frame_shape[1], self.frame_shape[0]))
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                if ret:
                    encoded_frame = buffer.tobytes()

                    # Use the provided lock
                    with self.lock:
                        # Check size *before* copying
                        if len(encoded_frame) <= len(self.frame_data_list[current_buffer]):
                            self.frame_data_list[current_buffer][:len(encoded_frame)] = encoded_frame
                            self.active_buffer_index.value = current_buffer  # Signal ready
                        else:
                            print(f"Warning: Frame too large for buffer {current_buffer}. Dropping.")

                    # Switch to the *other* buffer for the next frame
                    current_buffer = (current_buffer + 1) % 2

                else:
                    print("Encoding failed.")
                    break
            else:
                print("Error reading from camera")
                break

        if self.camera:
            self.camera.release()
        print("Camera process exiting.")

    def start(self):
        self.process = multiprocessing.Process(target=self._camera_loop)
        self.process.daemon = True
        self.process.start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.join(timeout=2)
            if self.process.is_alive():
                print("Terminating camera process")
                self.process.terminate()
                self.process.join()
