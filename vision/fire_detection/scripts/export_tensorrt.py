"""Export best.pt to best.engine for TensorRT inference on Jetson. Run once.

    cd /home/unitree/g1_agent_interim/vision/fire_detection
    python3.8 scripts/export_tensorrt.py

Génère best.engine à côté du best.pt dans le cache HuggingFace (l'engine n'existe
pas sur le remote HF — model.py::_resolve_weights pointe ce frère local)."""
from huggingface_hub import hf_hub_download
from ultralytics import YOLO


def export(repo_id: str, filename: str) -> None:
    path = hf_hub_download(repo_id=repo_id, filename=filename)
    model = YOLO(path)
    model.export(format="engine")
    print(f"Exported: {path.replace('.pt', '.engine')}")


if __name__ == "__main__":
    export("SalahALHaismawi/yolov26-fire-detection", "best.pt")
