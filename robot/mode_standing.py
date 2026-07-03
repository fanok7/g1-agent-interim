# robot/mode_standing.py
import sys
import time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')
sys.path.insert(0, '/home/unitree/g1_agent_interim')

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from config import ROBOT_INTERFACE, ROBOT_NETWORK_ID

ChannelFactoryInitialize(ROBOT_NETWORK_ID, ROBOT_INTERFACE)
client = LocoClient()
client.SetTimeout(10.0)
client.Init()

print("[Mode] Mise en Damp...")
client.Damp()         # FSM 1 — sécurité, fonctionne depuis Seating et Damp
time.sleep(2)         # laisse le temps au robot de s'affaisser si besoin

print("[Mode] Locked Standing en cours (7s)...")
client.SetFsmId(4)    # FSM 4 — le robot se relève
time.sleep(7)         # temps nécessaire pour se lever complètement

print("[Mode] Start...")
client.Start()        # FSM 500 — prêt à bouger
time.sleep(1)

print("[Mode] Locked Standing OK")