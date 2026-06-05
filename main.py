"""
G1 Agent Interim — point d'entrée.

python3.8 main.py
"""

import sys
sys.path.insert(0, '/home/unitree/g1_agent_interim')

import asyncio
import robot.hardware as hardware

# Chargement des tools — l'import suffit à les enregistrer dans le registry
import tools.web_search    # noqa: F401
import tools.database      # noqa: F401
import tools.gesture_tool  # noqa: F401
import tools.gmail         # noqa: F401
import tools.airlabs_tools   # noqa: F401
import tools.transport_tools   # noqa: F401
import tools.googlemaps_tools  # noqa: F401

from agent.session import connect
from agent.events import send_audio_loop, receive_events_loop


async def run():
    hardware.init()
    ws = await connect()
    print('[G1] Prêt. Parle pour commencer. (Ctrl+C pour quitter)')
    try:
        await asyncio.gather(
            send_audio_loop(ws),
            receive_events_loop(ws)
        )
    finally:
        await ws.close()


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('\n[G1] Au revoir !')
