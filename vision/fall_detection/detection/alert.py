"""Alert system: handlers and AlertManager with sliding window + cooldown."""
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Deque, Optional
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AlertHandler(ABC):
    @abstractmethod
    def send(self, frame: np.ndarray) -> None:
        """Fire an alert, optionally using the triggering frame."""


class ConsoleAlertHandler(AlertHandler):
    def __init__(self, save_image: bool, save_dir: str) -> None:
        self._save_image = save_image
        self._save_dir = Path(save_dir)

    def send(self, frame: np.ndarray) -> None:
        logger.warning("FALL DETECTED")
        print("[ALERT] Fall detected!")
        if self._save_image:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            filename = self._save_dir / f"fall_{int(time.time())}.jpg"
            cv2.imwrite(str(filename), frame)
            logger.info("Saved alert image to %s", filename)


class WebhookAlertHandler(AlertHandler):
    def send(self, frame: np.ndarray) -> None:
        raise NotImplementedError("WebhookAlertHandler not yet implemented")


class AgentToolHandler(AlertHandler):
    """Point d'intégration agent G1 : écrit le fichier IPC `state_file`
    (/tmp/fall_state.json) de façon atomique. La boucle `fall_alert_loop` de
    agent/events.py le consomme (lecture + suppression) et fait réagir le robot
    vocalement. Optionnellement sauvegarde la frame déclencheuse comme preuve."""

    def __init__(self, state_file: str, save_image: bool, save_dir: str) -> None:
        self._state_file = Path(state_file)
        self._save_image = save_image
        self._save_dir = Path(save_dir)

    def send(self, frame: np.ndarray) -> None:
        image_path: Optional[str] = None
        if self._save_image:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            image_path = str(self._save_dir / f"fall_{int(time.time())}.jpg")
            cv2.imwrite(image_path, frame)
        payload = {"event": "fall", "ts": time.time(), "image": image_path}
        tmp = str(self._state_file) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, self._state_file)
        logger.warning("Fall alert written to %s", self._state_file)
        print("[ALERT] Fall detected!", flush=True)


class AlertManager:
    """Sliding window over recent frames; fires handler when fall is confirmed."""

    def __init__(self, handler: AlertHandler, min_fall_frames: int, cooldown_seconds: float) -> None:
        self._handler = handler
        self._min_fall_frames = min_fall_frames
        self._cooldown = cooldown_seconds
        self._window: Deque[bool] = deque(maxlen=min_fall_frames)
        self._last_alert: float = 0.0

    def update(self, is_fallen: bool, frame: np.ndarray) -> bool:
        """Push latest detection; returns True if alert fired this frame."""
        self._window.append(is_fallen)
        if (
            len(self._window) == self._min_fall_frames
            and all(self._window)
            and (time.monotonic() - self._last_alert) >= self._cooldown
        ):
            self._last_alert = time.monotonic()
            self._handler.send(frame)
            return True
        return False


def build_alert_manager(cfg: dict) -> AlertManager:
    a = cfg["alert"]
    handler_name = a["handler"]

    if handler_name == "console":
        handler = ConsoleAlertHandler(a["save_image"], a["save_dir"])
    elif handler_name == "webhook":
        handler = WebhookAlertHandler()
    elif handler_name == "agent":
        handler = AgentToolHandler(a["state_file"], a["save_image"], a["save_dir"])
    else:
        raise ValueError(f"Unknown alert handler: {handler_name!r}")

    return AlertManager(handler, a["min_fall_frames"], a["cooldown_seconds"])
