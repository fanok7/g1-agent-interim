"""Camera backends: OpenCVCamera, RealSenseCamera (lazy import), SharedFrameCamera,
and create_camera factory."""
from __future__ import annotations  # G1 : annotations 3.10 (X | None) sous python3.8

import logging
import os
import time
from abc import ABC, abstractmethod

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class BaseCamera(ABC):
    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Return BGR frame or None on failure."""

    @abstractmethod
    def reconnect(self) -> bool:
        """Attempt to reconnect. Return True on success."""

    @abstractmethod
    def release(self) -> None:
        pass


class OpenCVCamera(BaseCamera):
    def __init__(self, source: int | str, width: int, height: int, fps: int):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self._cap: cv2.VideoCapture | None = None
        self._open()

    def _open(self) -> None:
        self._cap = cv2.VideoCapture(self.source)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)

    def read(self) -> np.ndarray | None:
        if self._cap is None or not self._cap.isOpened():
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def reconnect(self) -> bool:
        logger.warning("Reconnecting camera source=%s", self.source)
        if self._cap:
            self._cap.release()
        self._open()
        return self._cap.isOpened()

    def release(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None


class RealSenseCamera(BaseCamera):
    """Intel RealSense D435i — pyrealsense2 is lazy so non-Jetson machines are unaffected."""

    def __init__(self, width: int, height: int, fps: int):
        import pyrealsense2 as rs  # noqa: PLC0415

        self._pipeline = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        self._pipeline.start(cfg)

    def read(self) -> np.ndarray | None:
        frames = self._pipeline.wait_for_frames(timeout_ms=5000)
        color = frames.get_color_frame()
        return np.asanyarray(color.get_data()) if color else None

    def reconnect(self) -> bool:
        logger.warning("Restarting RealSense pipeline")
        try:
            self._pipeline.stop()
            self._pipeline.start()
            return True
        except Exception:
            return False

    def release(self) -> None:
        self._pipeline.stop()


class SharedFrameCamera(BaseCamera):
    """Lit la frame partagée écrite par un autre process (face_id.py écrit
    /tmp/latest_ugreen.jpg sur le G1). Aucune ouverture de /dev/video* — évite le
    conflit avec face_id qui possède /dev/video0 en exclusivité (et avec vision_server
    + fall_detection qui lisent la même frame). Le débit est cadencé sur `fps` pour
    borner la charge GPU (inutile de relire plus vite que face_id n'écrit)."""

    def __init__(self, path: str, fps: int):
        self._path = path
        self._min_dt = 1.0 / fps if fps and fps > 0 else 0.0
        self._last = 0.0

    def read(self) -> np.ndarray | None:
        dt = time.monotonic() - self._last
        if dt < self._min_dt:
            time.sleep(self._min_dt - dt)
        self._last = time.monotonic()
        if not os.path.exists(self._path):
            return None
        return cv2.imread(self._path)  # None si fichier en cours d'écriture

    def reconnect(self) -> bool:
        time.sleep(0.5)  # source fichier : rien à rouvrir, on attend la prochaine frame
        return True

    def release(self) -> None:
        pass


def create_camera(cfg: dict) -> BaseCamera:
    cam = cfg["camera"]
    if cam["backend"] == "shared_frame":
        return SharedFrameCamera(cam["path"], cam["fps"])
    w, h, fps = cam["width"], cam["height"], cam["fps"]
    if cam["backend"] == "realsense":
        return RealSenseCamera(w, h, fps)
    return OpenCVCamera(cam["source"], w, h, fps)
