"""Config loading: base.yaml merged with optional override YAML + CLI args."""
import argparse
from pathlib import Path
from typing import List, Optional

import yaml


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _nested_set(d: dict, dotted_key: str, value) -> None:
    keys = dotted_key.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def load_config(argv: Optional[List[str]] = None) -> dict:
    """Load and return merged config dict from YAML files and CLI flags."""
    parser = argparse.ArgumentParser(description="Fall detection")
    parser.add_argument("-c", "--config", default=None, help="Override YAML (e.g. config/g1.yaml)")
    parser.add_argument("--source", default=None, help="Camera source (index, path, or URL)")
    parser.add_argument("--no-display", action="store_true", help="Disable cv2 window")
    args = parser.parse_args(argv)

    base_path = Path(__file__).parent / "base.yaml"
    cfg = _load_yaml(base_path)

    if args.config:
        override = _load_yaml(Path(args.config))
        cfg = _deep_merge(cfg, override)

    if args.source is not None:
        source = int(args.source) if args.source.isdigit() else args.source
        _nested_set(cfg, "camera.source", source)

    if args.no_display:
        _nested_set(cfg, "display.show_window", False)

    return cfg
