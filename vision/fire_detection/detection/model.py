"""Model loading via HuggingFace Hub and inference with annotation."""
from __future__ import annotations  # G1 : annotations 3.10 sous python3.8

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import EntryNotFoundError
from ultralytics import YOLO

logger = logging.getLogger(__name__)

ALERT_CLASSES = {"fire", "smoke"}


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2


class FireDetectionModel:
    def __init__(self, repo_id: str, filename: str, confidence: float, device: str):
        path = self._resolve_weights(repo_id, filename)
        logger.info("Loaded model from %s", path)
        self._model = YOLO(path)
        self._confidence = confidence
        self._device = device

    @staticmethod
    def _resolve_weights(repo_id: str, filename: str) -> str:
        """Localise les poids. Un .engine TensorRT est généré localement par
        scripts/export_tensorrt.py et n'existe PAS sur le remote HF : on télécharge
        d'abord le .pt (pour situer le dossier de cache), puis on pointe le .engine
        frère. Pour un .pt, comportement inchangé (téléchargement direct)."""
        try:
            return hf_hub_download(repo_id=repo_id, filename=filename)
        except EntryNotFoundError:
            base = Path(filename).with_suffix(".pt").name
            cached = Path(hf_hub_download(repo_id=repo_id, filename=base))
            local = cached.with_name(filename)
            if not local.exists():
                raise FileNotFoundError(
                    f"{filename} absent du cache HF — lance d'abord "
                    f"scripts/export_tensorrt.py sur le Jetson")
            return str(local)

    def predict(self, frame: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            frame,
            conf=self._confidence,
            device=self._device,
            verbose=False,
        )
        detections: list[Detection] = []
        for r in results:
            for box in r.boxes:
                label = r.names[int(box.cls)]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(Detection(label, float(box.conf), (x1, y1, x2, y2)))
        return detections

    def annotate(self, frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        colors = {"fire": (0, 0, 255), "smoke": (0, 165, 255)}
        annotated = frame.copy()
        for d in detections:
            color = colors.get(d.label, (200, 200, 200))
            x1, y1, x2, y2 = d.box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f"{d.label} {d.confidence:.2f}", (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return annotated
