"""Export best.pt to best.engine for TensorRT inference on Jetson. Run once."""
from huggingface_hub import hf_hub_download
from ultralytics import YOLO


def export(repo_id: str, filename: str) -> None:
    path = hf_hub_download(repo_id=repo_id, filename=filename)
    model = YOLO(path)
    model.export(format="engine")
    print(f"Exported: {path.replace('.pt', '.engine')}")


if __name__ == "__main__":
    export("melihuzunoglu/human-fall-detection", "best.pt")
