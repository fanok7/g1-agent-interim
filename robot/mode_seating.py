# robot/mode_seating.py
import sys
sys.path.insert(0, '/home/unitree/unitree_sdk2_python')
sys.path.insert(0, '/home/unitree/g1_agent_interim')

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from config import ROBOT_INTERFACE, ROBOT_NETWORK_ID

ChannelFactoryInitialize(ROBOT_NETWORK_ID, ROBOT_INTERFACE)
client = LocoClient()
client.Init()
client.Sit()
print("[Mode] Seating OK")