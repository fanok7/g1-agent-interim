"""Scan cv2 indexes 0-9, print which open and their device name."""
import platform
import subprocess
from pathlib import Path

import cv2


def _device_names() -> "dict[int, str]":
    """Return a mapping of cv2 index → device name where available."""
    system = platform.system()

    if system == "Linux":
        names = {}
        for i in range(10):
            p = Path(f"/sys/class/video4linux/video{i}/name")
            if p.exists():
                names[i] = p.read_text().strip()
        return names

    if system == "Windows":
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-PnpDevice -Class Camera | Select-Object -ExpandProperty FriendlyName"],
                capture_output=True, text=True, timeout=5,
            )
            names_list = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            # PowerShell returns names in detection order, matching cv2 index order
            return dict(enumerate(names_list))
        except Exception:
            pass

    return {}


def find_cameras() -> None:
    names = _device_names()
    found = []
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            found.append((i, w, h, names.get(i, "unknown")))
            cap.release()

    if not found:
        print("No cameras found.")
    else:
        for idx, w, h, name in found:
            print(f"  [{idx}] {w}x{h}  -  {name}")


if __name__ == "__main__":
    find_cameras()
