# CLAUDE.md — Human Fall Detection System

## What this is
Real-time fall detection using YOLOv11 (`melihuzunoglu/human-fall-detection` on HuggingFace, 3 classes: `Fallen / Sitting / Standing`). Alerts fire on `Fallen` only.

Two deployment targets:
- **Phase 1 (now):** laptop + USB webcam, for testing
- **Phase 2 (next):** Unitree G1 EDU robot (Jetson Orin NX) + USB webcam on the robot's head

---

## Structure
```
fall-detection/
├── main.py                    # entrypoint: load config, run loop
├── config/
│   ├── base.yaml              # defaults (laptop + webcam)
│   └── g1.yaml                # robot overrides (headless, correct cam index)
├── detection/
│   ├── camera.py              # BaseCamera + OpenCVCamera + RealSenseCamera
│   ├── model.py               # model loading, inference, annotation
│   ├── alert.py               # AlertManager + pluggable handlers
│   └── detector.py            # main detection loop
└── scripts/
    ├── find_cameras.py        # scans cv2 indexes 0-9, prints which open
    └── export_tensorrt.py     # exports best.pt -> best.engine (run once on Jetson)
```

---

## Key decisions (non-negotiable)

**Config:** everything lives in YAML (`config/base.yaml`), overridden by `-c config/g1.yaml` and optional `--source`, `--no-display` CLI flags. Zero magic numbers in code.

**Model weights:** always loaded via `hf_hub_download(repo_id, filename)` at runtime. Never hardcoded paths, never committed to repo (add `*.pt`, `*.engine` to `.gitignore`).

**Camera backends:** `OpenCVCamera` (USB/RTSP/file via `cv2.VideoCapture`) and `RealSenseCamera` (D435i via `pyrealsense2`). The `pyrealsense2` import must be **lazy** (inside the class only) so the codebase works on non-Jetson machines. A `CameraFactory` picks the right one from config.

**Alert system:** `AlertManager` owns the sliding window (`deque(maxlen=N)`), the `min_fall_frames` threshold, and the cooldown. It calls a pluggable `AlertHandler`. Implement `ConsoleAlertHandler` (print + optional image save) now, and stub `WebhookAlertHandler` and `AgentToolHandler` (raise `NotImplementedError`) for later. **The `AgentToolHandler` stub is the future integration point for the AI agent tool call** — no other code should change when it gets wired up.

**Display:** `cv2.imshow` only when `display.show_window: true`. G1 config sets this to `false` (headless).

**On reconnect:** if `camera.read()` fails, log a warning and call `camera.reconnect()` — don't crash.

---

## Build order
1. Config loading (YAML merge + CLI args)
2. `camera.py` — `OpenCVCamera` first, `RealSenseCamera` second
3. `model.py`
4. `alert.py` — `ConsoleAlertHandler` + `AlertManager`
5. `detector.py` — main loop
6. `main.py` — entrypoint
7. `scripts/find_cameras.py`
8. Tests + `.gitignore`