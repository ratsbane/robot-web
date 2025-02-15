import cv2

# VERY IMPORTANT: Start with index 0. We'll change this if needed.
camera_index = 0

cap = cv2.VideoCapture(camera_index)

if not cap.isOpened():
    print(f"ERROR: Cannot open camera at index {camera_index}")
    exit()

print(f"Camera opened successfully at index {camera_index}")

while True:
    ret, frame = cap.read()

    if not ret:
        print("ERROR: Can't receive frame (stream end?). Exiting ...")
        break

    cv2.imshow('Camera Feed', frame)

    # Wait for 'q' key to be pressed to exit
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print("Camera test finished.")

