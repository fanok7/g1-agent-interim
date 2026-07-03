# G1 Robot Migration Guide — Jetson Orin NX

Step-by-step instructions for deploying the fire detection module on the **Unitree G1 EDU** robot's onboard Jetson Orin NX compute unit.

---

## Hardware overview

| Component | Spec |
|-----------|------|
| SoC | NVIDIA Jetson Orin NX (16 GB) |
| GPU | 1024-core Ampere, 32 TOPS |
| OS | Ubuntu 20.04 (JetPack 6.x) |
| Camera | USB webcam mounted on the G1 head, index `2` |
| Connectivity | SSH over robot's internal LAN (`192.168.123.x`) |

---

## 1. SSH into the Jetson

```bash
ssh user@192.168.123.18   # adjust IP to your G1's Jetson address
```

---

## 2. Install system dependencies

```bash
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    libopencv-dev \
    v4l-utils          # to confirm camera device nodes
```

Confirm the USB webcam is visible:
```bash
v4l2-ctl --list-devices
# expect something like /dev/video2 for the head cam
```

---

## 3. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

---

## 4. Clone the repo onto the Jetson

```bash
git clone <your-repo-url> ~/fire_detection
cd ~/fire_detection
```

---

## 5. Install Python dependencies

Standard dependencies (same as laptop):
```bash
uv sync
```

`pyrealsense2` is **not needed** unless you swap the webcam for a RealSense — skip it.

---

## 6. Install PyTorch for Jetson (JetPack wheels)

The standard PyPI `torch` wheel does **not** support the Jetson GPU. Install NVIDIA's JetPack-compatible wheel instead:

```bash
# For JetPack 6.x / Python 3.11
pip install --no-cache \
  https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.3.0+nv24.7-cp311-cp311-linux_aarch64.whl
```

> Check the [NVIDIA PyTorch for Jetson page](https://developer.nvidia.com/embedded/downloads) for the latest wheel matching your JetPack version.

Verify GPU is reachable:
```bash
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# expected: True  Orin
```

---

## 7. (Optional but recommended) Export to TensorRT

Running YOLO with TensorRT on the Jetson gives ~3–5× faster inference vs. plain PyTorch.

First run on the laptop to download weights:
```bash
uv run main.py --no-display   # downloads best.pt to HF cache, then quit
```

Copy the weights to the Jetson:
```bash
scp ~/.cache/huggingface/hub/models--SalahALHaismawi--yolov26-fire-detection/snapshots/*/best.pt \
    user@192.168.123.18:~/fire_detection/
```

Then on the Jetson, export to a TensorRT engine:
```bash
cd ~/fire_detection
uv run scripts/export_tensorrt.py   # produces best.engine
```

`scripts/export_tensorrt.py` content for reference:
```python
from ultralytics import YOLO
model = YOLO("best.pt")
model.export(format="engine", device=0, half=True)   # FP16, maximises throughput
```

Once exported, point the config at the engine:
```yaml
# config/g1.yaml
model:
  filename: best.engine
```

---

## 8. Verify camera index

```bash
uv run scripts/find_cameras.py
```

The G1 head USB webcam is expected at index `2` (already set in `config/g1.yaml`). If the index differs, update `config/g1.yaml`:
```yaml
camera:
  source: <correct-index>
```

---

## 9. Run headless on the Jetson

```bash
cd ~/fire_detection
uv run main.py -c config/g1.yaml
```

`g1.yaml` enforces:
- `display.show_window: false` — no GUI
- `model.device: cuda` — uses Jetson GPU
- `camera.source: 2` — head webcam
- `logging.level: WARNING` — minimal output

---

## 10. Run as a systemd service (production)

Create `/etc/systemd/system/fire-detection.service`:

```ini
[Unit]
Description=G.E.R.O Fire & Smoke Detection
After=network.target

[Service]
User=user
WorkingDirectory=/home/user/fire_detection
ExecStart=/home/user/.local/bin/uv run main.py -c config/g1.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fire-detection
sudo systemctl start fire-detection
sudo journalctl -u fire-detection -f   # follow logs
```

---

## 11. Wire up the AgentToolHandler

When the G1 agent layer is ready, implement `AgentToolHandler.trigger()` in `detection/alert.py`:

```python
class AgentToolHandler(AlertHandler):
    def trigger(self, label: str, frame: np.ndarray | None) -> None:
        # call the G1 agent tool here
        # e.g. post to an internal message bus, call a ROS2 topic, or invoke an MCP tool
        pass
```

Then switch the config:
```yaml
alert:
  fire:
    handler: agent
  smoke:
    handler: agent
```

No other code changes needed — the rest of the pipeline is already wired for this.

---

## Performance targets (Jetson Orin NX, FP16 TensorRT)

| Mode | Approx. FPS |
|------|-------------|
| PyTorch CPU (laptop) | ~5–8 fps |
| PyTorch CUDA (Jetson) | ~20–30 fps |
| TensorRT FP16 (Jetson) | ~50–80 fps |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `torch.cuda.is_available()` returns False | Wrong torch wheel installed | Reinstall NVIDIA JetPack wheel (step 6) |
| Camera not found at index 2 | USB enumeration order changed | Run `find_cameras.py`, update `g1.yaml` |
| `best.engine` load fails | Engine built on different JetPack/TRT version | Re-export on the Jetson (step 7) |
| High latency on first frame | TensorRT warm-up | Normal — subsequent frames are fast |
| `pyrealsense2` import error | Lazy import triggered by wrong backend | Ensure `camera.backend: opencv` in config |
