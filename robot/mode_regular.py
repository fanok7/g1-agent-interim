# robot/mode_regular.py
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

print("[Mode] Regular (3 DoF Waist)...")
client.SetFsmId(501)
time.sleep(1)
print("[Mode] Regular OK")