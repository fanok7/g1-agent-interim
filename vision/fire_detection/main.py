"""Entrypoint: load config, build camera + model, run detection loop."""
import argparse
import logging

from detection.camera import create_camera
from detection.config import load_config
from detection.detector import run_detection
from detection.model import FireDetectionModel


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time fire & smoke detection")
    p.add_argument("-c", "--config", default=None, help="Override YAML (e.g. config/g1.yaml)")
    p.add_argument("--source", default=None, help="Camera source override (index or URL)")
    p.add_argument("--no-display", action="store_true", help="Disable cv2.imshow")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)

    if args.source is not None:
        src = int(args.source) if args.source.isdigit() else args.source
        cfg["camera"]["source"] = src
    if args.no_display:
        cfg["display"]["show_window"] = False

    logging.basicConfig(level=getattr(logging, cfg["logging"]["level"]))

    model_cfg = cfg["model"]
    model = FireDetectionModel(
        repo_id=model_cfg["repo_id"],
        filename=model_cfg["filename"],
        confidence=model_cfg["confidence"],
        device=model_cfg["device"],
    )
    camera = create_camera(cfg)
    run_detection(cfg, camera, model)


if __name__ == "__main__":
    main()
