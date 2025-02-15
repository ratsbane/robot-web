from flask import Flask, render_template, Response
import cv2
import time
#import socketio

app = Flask(__name__)

camera = cv2.VideoCapture(0)  # Use the correct index!
if not camera.isOpened():
    print("Error: Could not open camera in app_camera_test.py")
    camera = None

def generate_frames():
    while True:
        if camera:
            success, frame = camera.read()
            if not success:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
          yield (b'--frame\r\n'
                 b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')  # Empty frame
          time.sleep(1)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return "<html><body><h1>Camera Test</h1><img src='/video_feed'></body></html>"

if __name__ == '__main__':
    #app.run(debug=False, host='0.0.0.0', port=5000) # Debug mode for testing ONLY
    #socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False) # Use app.run

