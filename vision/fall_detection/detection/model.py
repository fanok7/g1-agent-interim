"""Model loading, inference, and frame annotation."""
import logging
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import EntryNotFoundError
from ultralytics import YOLO

logger = logging.getLogger(__name__)

FALLEN = "fallen"
_BOX_COLORS = {FALLEN: (0, 0, 255), "sitting": (0, 165, 255), "standing": (0, 255, 0)}


class FallDetectionModel:
    def __init__(self, repo_id: str, filename: str, confidence: float, device: str) -> None:
        path = self._resolve_weights(repo_id, filename)
        logger.info("Loaded model from %s", path)
        self._model = YOLO(path)
        self._conf = confidence
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

    def predict(self, frame: np.ndarray) -> List[Dict]:
        """Run inference and return list of detections: {label, confidence, box}."""
        results = self._model.predict(frame, conf=self._conf, device=self._device, verbose=False)
        detections = []
        for r in results:
            for box in (r.boxes or []):
                label = r.names[int(box.cls)]
                detections.append({
                    "label": label,
                    "confidence": float(box.conf),
                    "box": [int(v) for v in box.xyxy[0].tolist()],
                })
        return detections

    def annotate(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Draw bounding boxes and labels onto a copy of frame."""
        out = frame.copy()
        for d in detections:
            x1, y1, x2, y2 = d["box"]
            color = _BOX_COLORS.get(d["label"], (200, 200, 200))
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            text = f"{d['label']} {d['confidence']:.2f}"
            cv2.putText(out, text, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return out


def build_model(cfg: dict) -> FallDetectionModel:
    m = cfg["model"]
    return FallDetectionModel(m["repo_id"], m["filename"], m["confidence"], m["device"])
