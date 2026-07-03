"""Main detection loop with two independent AlertManagers (fire + smoke)."""
from __future__ import annotations  # G1 : annotations 3.10 sous python3.8

import logging

import cv2

from .alert import AlertManager, build_handler
from .camera import BaseCamera
from .model import ALERT_CLASSES, FireDetectionModel

logger = logging.getLogger(__name__)


def build_alert_manager(cfg: dict, label: str) -> AlertManager:
    sub = cfg["alert"][label]
    return AlertManager(
        handler=build_handler(sub),
        min_trigger_frames=sub["min_trigger_frames"],
        cooldown_seconds=sub["cooldown_seconds"],
    )


def run_detection(cfg: dict, camera: BaseCamera, model: FireDetectionModel) -> None:
    fire_manager = build_alert_manager(cfg, "fire")
    smoke_manager = build_alert_manager(cfg, "smoke")

    show = cfg["display"]["show_window"]
    title = cfg["display"]["window_title"]

    try:
        while True:
            frame = camera.read()
            if frame is None:
                logger.warning("Camera read failed — attempting reconnect")
                camera.reconnect()
                continue

            detections = model.predict(frame)
            alert_dets = [d for d in detections if d.label in ALERT_CLASSES]
            labels_detected = {d.label for d in alert_dets}

            # Frame transmise au handler = preuve sauvegardée. On l'annote (boîte +
            # label + score) quand un feu/fumée est détecté pour que le screenshot
            # envoyé par email montre la confiance de la détection.
            alert_frame = model.annotate(frame, alert_dets) if alert_dets else frame

            fire_manager.update("fire", "fire" in labels_detected, alert_frame)
            smoke_manager.update("smoke", "smoke" in labels_detected, alert_frame)

            for d in detections:
                if d.label not in ALERT_CLASSES:
                    logger.debug("other: %s %.2f", d.label, d.confidence)

            if show:
                annotated = model.annotate(frame, detections)
                cv2.imshow(title, annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        if show:
            cv2.destroyAllWindows()
