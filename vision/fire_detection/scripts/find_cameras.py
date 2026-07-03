"""Scan cv2 indexes 0-9 and print which open successfully."""
import cv2


def find_cameras(max_index: int = 9) -> None:
    print("Scanning camera indexes 0 to", max_index)
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"  index {i}: OK ({int(w)}x{int(h)})")
            cap.release()
        else:
            print(f"  index {i}: not available")


if __name__ == "__main__":
    find_cameras()
