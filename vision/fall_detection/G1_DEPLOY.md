# Deploying Fall Detection on Unitree G1 EDU (Jetson Orin NX)

## Prerequisites

- Jetson Orin NX flashed with JetPack 6.x
- USB webcam mounted on robot head
- `uv` installed on the Jetson
- Network access to HuggingFace (first run only)

---

## Steps

### 1. Clone the repo on the Jetson

```bash
git clone <repo-url> fall_detection
cd fall_detection
uv sync
```

### 2. Find the camera index

```bash
uv run python scripts/find_cameras.py
```

Output example:
```
  [0] 640x480  -  Intel(R) AVStream Camera
  [1] 640x480  -  UGREEN Camera
```

Note the index next to your USB webcam name (e.g. UGREEN), update `config/g1.yaml`:

```yaml
camera:
  source: <index>
```

### 3. Export the model to TensorRT (run once)

```bash
uv run python scripts/export_tensorrt.py
```

This downloads `best.pt` and produces `best.engine` in the same cache directory. Takes a few minutes.

### 4. Point the config to the TensorRT engine

In `config/g1.yaml`, update the model filename:

```yaml
model:
  filename: best.engine
```

### 5. Run

```bash
uv run python main.py -c config/g1.yaml
```

No window will open (headless). Alerts print to stdout and logs.

---

## Notes

- `*.pt` and `*.engine` are gitignored — the model is always downloaded at runtime from HuggingFace and cached in `~/.cache/huggingface/`
- To test with a display connected: `uv run python main.py -c config/g1.yaml --no-display` overrides headless if needed (add `show_window: true` temporarily in g1.yaml)
- Alert handler is currently `console` — swap to `agent` in `config/g1.yaml` when the `AgentToolHandler` is wired up
