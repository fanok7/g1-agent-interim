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
import robot.spotify_player as spotify_player
from robot import hand_idle
from robot.gestures import execute_gesture

# Chargement des tools — l'import suffit à les enregistrer dans le registry
<<<<<<< HEAD
import tools.web_search    # noqa: F401
import tools.database      # noqa: F401
import tools.gesture_tool  # noqa: F401
import tools.gmail         # noqa: F401
import tools.airlabs_tools   # noqa: F401
import tools.transport_tools   # noqa: F401
import tools.googlemaps_tools  # noqa: F401
=======
import tools.web_search       # noqa: F401
#import tools.database         # noqa: F401
import tools.gesture_tool     # noqa: F401
import tools.gmail            # noqa: F401
import tools.airlabs_tools    # noqa: F401
import tools.transport_tools  # noqa: F401
import tools.googlemaps_tools # noqa: F401
import tools.face_id_tool     # noqa: F401
import tools.shake_hand_tool
#import tools.vision_tool      # noqa: F401
#import tools.rps_tool         # noqa: F401
#import tools.spotify_tool     # noqa: F401
import tools.datetime_tool    # noqa: F401
#import tools.screenshot_tool  # noqa: F401
import tools.calendar_tool    # noqa: F401
#import tools.qr_tool          # noqa: F401
from tools.screenshot_tool import SCREENSHOT_DIR
>>>>>>> vision_dev

from agent.parler_client import send_emotion
from agent.session import connect
from agent.events import (send_audio_loop, receive_events_loop, face_greeting_loop,
                          rps_result_loop, qr_alert_loop)



MINICONDA_PYTHON    = "/home/unitree/miniconda3/bin/python3"
PYTHON38            = "/usr/bin/python3.8"
FACE_ID_SCRIPT      = "/home/unitree/g1_agent_interim/vision/face_id/face_id.py"
VISION_SRV_SCRIPT   = "/home/unitree/g1_agent_interim/vision/vision_server.py"
GESTURE_POSE_SCRIPT = "/home/unitree/g1_agent_interim/vision/gesture_pose.py"
VISION_FALL_SCRIPT  = "/home/unitree/g1_agent_interim/vision/fall_detection/main.py"
VISION_FALL_CONFIG  = "/home/unitree/g1_agent_interim/vision/fall_detection/config/g1.yaml"
VISION_FIRE_SCRIPT  = "/home/unitree/g1_agent_interim/vision/fire_detection/main.py"
VISION_FIRE_CONFIG  = "/home/unitree/g1_agent_interim/vision/fire_detection/config/g1.yaml"
GESTURE_CMD_FILE    = "/tmp/gesture_cmd"

send_emotion("content")

def _start_subprocess(script: str, tag: str, python: str = MINICONDA_PYTHON,
                      args=None) -> subprocess.Popen:
    proc = subprocess.Popen(
        [python, script, *(args or [])],
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


async def _supervise(script: str, tag: str, python: str, args=None) -> None:
    """Lance, pipe les logs, et redémarre automatiquement si le subprocess crash."""
    while True:
        proc = _start_subprocess(script, tag, python, args)
        await _pipe_logs(proc)
        proc.poll()
        rc = proc.returncode
        print(f"[G1] {tag} terminé (code {rc}) — redémarrage dans 3s")
        await asyncio.sleep(3)


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
    # Nettoyage de tous les fichiers IPC — un résidu de crash bloque sinon le
    # micro (agent_responding), la caméra (vision_pause) ou rejoue un geste.
    for f in ['/tmp/vision_state.json', '/tmp/face_id_state.json',
              '/tmp/agent_responding', '/tmp/vision_pause', '/tmp/rps_go',
              '/tmp/rps_result.json', '/tmp/gesture_cmd', '/tmp/fall_state.json',
              '/tmp/fire_state.json', '/tmp/qr_state.json',
              ]:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    # Vide le dossier des screenshots à chaque lancement : on repart d'une session
    # propre. Les photos de feu/chute sont conservées PENDANT la session (preuve +
    # email), puis effacées au prochain démarrage de main.py.
    if os.path.isdir(SCREENSHOT_DIR):
        for name in os.listdir(SCREENSHOT_DIR):
            path = os.path.join(SCREENSHOT_DIR, name)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    hardware.init()
    from robot.led_manager import led
    from robot.hardware import get_audio_client
    led.init(get_audio_client())   
    led.idle()
    spotify_player.start()
    threading.Thread(target=hand_idle.start, daemon=True).start()
    ws = await connect()
    print('[G1] Prêt. Parle pour commencer. (Ctrl+C pour quitter)')
    try:
        await asyncio.gather(
            send_audio_loop(ws),
<<<<<<< HEAD
            receive_events_loop(ws)
=======
            receive_events_loop(ws),
            face_greeting_loop(ws),
            rps_result_loop(ws),
            #fall_alert_loop(ws),
            #fire_alert_loop(ws),
            qr_alert_loop(ws),
            _supervise(VISION_SRV_SCRIPT,  "vision_server", PYTHON38),
            _supervise(FACE_ID_SCRIPT,     "face_id",       MINICONDA_PYTHON),
            #_supervise(VISION_FALL_SCRIPT, "fall_detection", PYTHON38,
            #           ["-c", VISION_FALL_CONFIG]),
            #_supervise(VISION_FIRE_SCRIPT, "fire_detection", PYTHON38,
            #           ["-c", VISION_FIRE_CONFIG]),
            _gesture_cmd_loop(),
>>>>>>> vision_dev
        )
    finally:
        await ws.close()


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('\n[G1] Au revoir !')
