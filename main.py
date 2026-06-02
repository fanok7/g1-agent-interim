"""
main.py — point d'entrée G1 Agent Interim (version avec vision + gestes)

Lancer depuis :
    cd /home/unitree/unitree_sdk2_python
    python3.8 /home/unitree/g1_agent_interim/main.py

Prérequis :
    Terminal 1 : /home/unitree/miniconda3/bin/python3 /home/unitree/g1_agent_interim/vision/vision_server.py
    Terminal 2 : /home/unitree/miniconda3/bin/python3 /home/unitree/gesture_multi.py
    Terminal 3 : python3.8 /home/unitree/robot_controller.py eth0
    Terminal 4 : python3.8 /home/unitree/g1_agent_interim/main.py  ← ce fichier
"""

import sys
sys.path.insert(0, '/home/unitree/g1_agent_interim')

import asyncio
import robot.hardware as hardware

# ── Chargement des tools ───────────────────────────────────────────────────
# L'import suffit à enregistrer chaque tool dans le registry agent.
import tools.web_search    # noqa: F401
import tools.database      # noqa: F401
import tools.gesture_tool  # noqa: F401
import tools.vision_tool   # noqa: F401  ← NOUVEAU : tool "voir"

# ── Démarrage du listener gestes ──────────────────────────────────────────
import agent.gesture_listener as gesture_listener
gesture_listener.start()   # ← NOUVEAU : écoute port 9998

from agent.session import connect
from agent.events import send_audio_loop, receive_events_loop


async def run():
    hardware.init()
    ws = await connect()
    print('[G1] Prêt. Parle pour commencer. (Ctrl+C pour quitter)')
    await asyncio.gather(
        send_audio_loop(ws),
        receive_events_loop(ws)
    )


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('\n[G1] Au revoir !')
