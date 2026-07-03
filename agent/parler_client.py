# agent/parler_client.py
import socket
import json

LAUNCH_HOST = "127.0.0.1"
LAUNCH_PORT = 9876

def send_emotion(emotion: str):
    """Envoie une émotion à launch.py qui la transmet à l'ESP32."""
    try:
        with socket.create_connection((LAUNCH_HOST, LAUNCH_PORT), timeout=0.5) as s:
            s.sendall(json.dumps({"emotion": emotion}).encode())
    except Exception:
        pass  # silencieux — si launch.py n'est pas là, on ignore