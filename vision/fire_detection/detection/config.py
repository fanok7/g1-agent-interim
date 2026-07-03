"""Config loading: merge base.yaml with optional override YAML, return nested dict."""
from __future__ import annotations  # G1 : annotations 3.10 (str | None) sous python3.8

import yaml
from pathlib import Path


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(override_path: str | None = None) -> dict:
    """Load base config, optionally deep-merged with an override file."""
    base = Path(__file__).parent.parent / "config" / "base.yaml"
    cfg = yaml.safe_load(base.read_text())
    if override_path:
        override = yaml.safe_load(Path(override_path).read_text())
        cfg = _deep_merge(cfg, override)
    return cfg
