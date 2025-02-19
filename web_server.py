import os
import sys
import time
import cv2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio

# --- Set working directory and sys.path ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
sys.path.insert(0, current_dir)

app = FastAPI()

# Mount the "oemplates" directory as a static directory
app.mount("/templates", StaticFiles(directory="templates"), name="templates")


# --- Camera Setup ---
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Error: Could not open camera")
    camera = None

async def generate_frames():
    while True:
        if camera:
            success, frame = camera.read()
            if not success:
                await asyncio.sleep(0.1)
                continue
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if not ret:
                await asyncio.sleep(0.1)
                continue
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            await asyncio.sleep(1)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')


@app.get("/")
async def read_root():
    with open("templates/robot.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/simple")
async def read_root():
    #with open("templates/robot.html", "r") as f:
    with open("templates/video_feed.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
