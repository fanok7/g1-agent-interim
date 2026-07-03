"""Entrypoint: load config and run detection loop."""
import logging

from config import load_config
from detection.detector import run


def main() -> None:
    cfg = load_config()
    logging.basicConfig(level=cfg["logging"]["level"])
    run(cfg)


if __name__ == "__main__":
    main()
