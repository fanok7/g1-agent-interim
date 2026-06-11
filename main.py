"""
G1 Agent Interim — point d'entrée.

python3.8 main.py
"""

import sys
sys.path.insert(0, '/home/unitree/g1_agent_interim')

import asyncio
import os
import threading
import subprocess
import robot.hardware as hardware
from robot.gestures import execute_gesture

# Chargement des tools — l'import suffit à les enregistrer dans le registry
import tools.web_search       # noqa: F401
import tools.database         # noqa: F401
import tools.gesture_tool     # noqa: F401
import tools.gmail            # noqa: F401
import tools.airlabs_tools    # noqa: F401
import tools.transport_tools  # noqa: F401
import tools.googlemaps_tools # noqa: F401
import tools.face_id_tool     # noqa: F401
import tools.vision_tool      # noqa: F401
import tools.pointing_tool    # noqa: F401
import tools.rps_tool         # noqa: F401

from agent.session import connect
from agent.events import send_audio_loop, receive_events_loop, face_greeting_loop, rps_result_loop

MINICONDA_PYTHON    = "/home/unitree/miniconda3/bin/python3"
PYTHON38            = "/usr/bin/python3.8"
FACE_ID_SCRIPT      = "/home/unitree/g1_agent_interim/vision/face_id/face_id.py"
VISION_SRV_SCRIPT   = "/home/unitree/g1_agent_interim/vision/vision_server.py"
GESTURE_POSE_SCRIPT = "/home/unitree/g1_agent_interim/vision/gesture_pose.py"
GESTURE_CMD_FILE    = "/tmp/gesture_cmd"


def _start_subprocess(script: str, tag: str, python: str = MINICONDA_PYTHON) -> subprocess.Popen:
    proc = subprocess.Popen(
        [python, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"[G1] {tag} démarré (PID {proc.pid})")
    return proc


async def _pipe_logs(proc: subprocess.Popen) -> None:
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        print(line.decode(errors="replace").rstrip())


async def _gesture_cmd_loop() -> None:
    """Surveille /tmp/gesture_cmd et exécute les gestes détectés par gesture_pose."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(0.1)
        if not os.path.exists(GESTURE_CMD_FILE):
            continue
        try:
            with open(GESTURE_CMD_FILE) as f:
                geste = f.read().strip()
            os.remove(GESTURE_CMD_FILE)
            if geste:
                threading.Thread(target=execute_gesture, args=(geste,), daemon=True).start()
        except Exception as e:
            print(f"[GESTURE] Erreur lecture cmd : {e}")


async def run():
    for f in ['/tmp/vision_state.json', '/tmp/face_id_state.json']:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    vision_proc = _start_subprocess(VISION_SRV_SCRIPT, "vision_server", python=PYTHON38)
    hardware.init()
    ws = await connect()
    print('[G1] Prêt. Parle pour commencer. (Ctrl+C pour quitter)')
    try:
        await asyncio.gather(
            send_audio_loop(ws),
            receive_events_loop(ws),
            face_greeting_loop(ws),
            rps_result_loop(ws),
            _pipe_logs(vision_proc),
            _gesture_cmd_loop(),
        )
    finally:
        await ws.close()
        vision_proc.terminate()


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('\n[G1] Au revoir !')
