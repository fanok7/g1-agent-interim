"""Alert system: handlers and sliding-window AlertManager."""
from __future__ import annotations  # G1 : annotations 3.10 sous python3.8

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AlertHandler(ABC):
    @abstractmethod
    def trigger(self, label: str, frame: np.ndarray | None) -> None:
        pass


class ConsoleAlertHandler(AlertHandler):
    def __init__(self, save_image: bool, save_dir: str):
        self._save_image = save_image
        self._save_dir = Path(save_dir)

    def trigger(self, label: str, frame: np.ndarray | None) -> None:
        print(f"[ALERT] {label.upper()} DETECTED")
        if self._save_image and frame is not None:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = self._save_dir / f"{label}_{ts}.jpg"
            cv2.imwrite(str(path), frame)
            logger.info("Saved alert image: %s", path)


class WebhookAlertHandler(AlertHandler):
    def trigger(self, label: str, frame: np.ndarray | None) -> None:
        raise NotImplementedError("WebhookAlertHandler not yet implemented")


class AgentToolHandler(AlertHandler):
    """Point d'intégration agent G1 : écrit le fichier IPC `state_file`
    (/tmp/fire_state.json) de façon atomique. La boucle `fire_alert_loop` de
    agent/events.py le consomme (lecture + suppression) et fait crier le robot
    « Au feu ! ». Sauvegarde optionnellement la frame déclencheuse (annotée) comme
    preuve, envoyée par email."""

    def __init__(self, state_file: str, save_image: bool, save_dir: str):
        self._state_file = Path(state_file)
        self._save_image = save_image
        self._save_dir = Path(save_dir)

    def trigger(self, label: str, frame: np.ndarray | None) -> None:
        image_path = None
        if self._save_image and frame is not None:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            image_path = str(self._save_dir / f"{label}_{int(time.time())}.jpg")
            cv2.imwrite(image_path, frame)
        payload = {"event": label, "ts": time.time(), "image": image_path}
        tmp = str(self._state_file) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, self._state_file)
        logger.warning("%s alert written to %s", label, self._state_file)
        print(f"[ALERT] {label.upper()} detected!", flush=True)


def build_handler(cfg: dict) -> AlertHandler:
    kind = cfg.get("handler", "console")
    if kind == "console":
        return ConsoleAlertHandler(cfg.get("save_image", False), cfg.get("save_dir", "alerts/"))
    if kind == "webhook":
        return WebhookAlertHandler()
    if kind == "agent":
        return AgentToolHandler(
            cfg.get("state_file", "/tmp/fire_state.json"),
            cfg.get("save_image", True),
            cfg.get("save_dir", "/home/unitree/g1_agent_interim/vision/Screenshot"),
        )
    raise ValueError(f"Unknown handler: {kind}")


class AlertManager:
    """Generic sliding-window alert manager — label-agnostic."""

    def __init__(self, handler: AlertHandler, min_trigger_frames: int, cooldown_seconds: float):
        self._handler = handler
        self._min_trigger_frames = min_trigger_frames
        self._cooldown = cooldown_seconds
        self._window: deque[bool] = deque(maxlen=min_trigger_frames)
        self._last_alert: float = 0.0

    def update(self, label: str, detected: bool, frame: np.ndarray | None = None) -> None:
        self._window.append(detected)
        if (
            len(self._window) == self._min_trigger_frames
            and all(self._window)
            and (time.time() - self._last_alert) >= self._cooldown
        ):
            self._last_alert = time.time()
            self._handler.trigger(label, frame)
