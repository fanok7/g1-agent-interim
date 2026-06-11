"""
Script de calibration des bras via arm_sdk.
Lance depuis /home/unitree/unitree_sdk2_python :
  python3.8 /home/unitree/g1_agent_interim/robot/arm_calibrate.py eth0

Commandes interactives :
  q <index> <angle_deg>   -- bouge un joint à l'angle donné (en degrés)
  pose <n1,n2,...>         -- pose complète : 17 angles en degrés (séparés par virgules)
  print                   -- affiche la position actuelle de tous les bras
  reset                   -- retourne à zéro (bras bas)
  release                 -- relâche arm_sdk
  exit                    -- quitte

Joints bras (index) :
  15 = L_ShoulderPitch   16 = L_ShoulderRoll   17 = L_ShoulderYaw
  18 = L_Elbow           19 = L_WristRoll       20 = L_WristPitch   21 = L_WristYaw
  22 = R_ShoulderPitch   23 = R_ShoulderRoll    24 = R_ShoulderYaw
  25 = R_Elbow           26 = R_WristRoll       27 = R_WristPitch   28 = R_WristYaw
  12 = WaistYaw          13 = WaistRoll         14 = WaistPitch
"""
import sys
import math
import time
import threading

sys.path.insert(0, '/home/unitree/unitree_sdk2_python')
sys.path.insert(0, '/home/unitree/g1_agent_interim')

from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC

ARM_JOINTS = [15, 16, 17, 18, 19, 20, 21,
              22, 23, 24, 25, 26, 27, 28,
              12, 13, 14]
ENABLE_SLOT = 29
KP = 60.0
KD = 1.5
CTRL_DT = 0.02

low_state   = None
state_lock  = threading.Lock()
crc         = CRC()
publisher   = None
target_q    = [0.0] * 17   # angles cibles courants (index = position dans ARM_JOINTS)
enabled     = False


def on_state(msg: LowState_):
    global low_state
    with state_lock:
        low_state = msg


def current_q():
    with state_lock:
        if low_state is None:
            return [0.0] * 17
        return [low_state.motor_state[j].q for j in ARM_JOINTS]


def publish_once(q_list, enable_w=1.0):
    cmd = unitree_hg_msg_dds__LowCmd_()
    cmd.motor_cmd[ENABLE_SLOT].q = enable_w
    for i, joint in enumerate(ARM_JOINTS):
        cmd.motor_cmd[joint].tau = 0.
        cmd.motor_cmd[joint].q   = q_list[i]
        cmd.motor_cmd[joint].dq  = 0.
        cmd.motor_cmd[joint].kp  = KP * enable_w
        cmd.motor_cmd[joint].kd  = KD
    cmd.crc = crc.Crc(cmd)
    publisher.Write(cmd)


def move_to(q_target, duration=1.5):
    """Interpolation lisse vers q_target."""
    start = current_q()
    t0 = time.time()
    while True:
        elapsed = time.time() - t0
        r = min(elapsed / duration, 1.0)
        q = [start[i] + r * (q_target[i] - start[i]) for i in range(17)]
        publish_once(q)
        if r >= 1.0:
            break
        time.sleep(CTRL_DT)


def release():
    t0 = time.time()
    dur = 0.5
    while True:
        elapsed = time.time() - t0
        r = min(elapsed / dur, 1.0)
        publish_once([0.0] * 17, enable_w=1.0 - r)
        if r >= 1.0:
            break
        time.sleep(CTRL_DT)
    print('[CAL] arm_sdk relâché')


def print_state():
    q = current_q()
    names = [
        'L_ShPitch(15)', 'L_ShRoll(16)', 'L_ShYaw(17)', 'L_Elbow(18)',
        'L_WRoll(19)',   'L_WPitch(20)', 'L_WYaw(21)',
        'R_ShPitch(22)', 'R_ShRoll(23)', 'R_ShYaw(24)', 'R_Elbow(25)',
        'R_WRoll(26)',   'R_WPitch(27)', 'R_WYaw(28)',
        'WaistYaw(12)',  'WaistRoll(13)','WaistPitch(14)',
    ]
    for i, (name, angle) in enumerate(zip(names, q)):
        print(f'  {name:20s} = {math.degrees(angle):7.1f}°  ({angle:.3f} rad)')


if __name__ == '__main__':
    iface = sys.argv[1] if len(sys.argv) > 1 else 'eth0'
    ChannelFactoryInitialize(0, iface)

    publisher = ChannelPublisher("rt/arm_sdk", LowCmd_)
    publisher.Init()
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_state, 10)

    print('[CAL] Attente lowstate...')
    for _ in range(50):
        if low_state is not None:
            break
        time.sleep(0.1)
    print('[CAL] Prêt. Tape "help" pour la liste des commandes.\n')

    # Active arm_sdk
    move_to([0.0] * 17, duration=0.5)
    enabled = True

    while True:
        try:
            line = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            release()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ('exit', 'quit'):
            release()
            break

        elif cmd == 'help':
            print(__doc__)

        elif cmd == 'print':
            print_state()

        elif cmd == 'reset':
            move_to([0.0] * 17)
            target_q[:] = [0.0] * 17
            print('[CAL] Reset à zéro')

        elif cmd == 'release':
            release()
            enabled = False

        elif cmd == 'q' and len(parts) == 3:
            try:
                joint_idx = int(parts[1])
                angle_deg = float(parts[2])
                angle_rad = math.radians(angle_deg)
                if joint_idx not in ARM_JOINTS:
                    print(f'[CAL] Index {joint_idx} non valide. Valides: {ARM_JOINTS}')
                    continue
                pos = ARM_JOINTS.index(joint_idx)
                new_q = list(target_q)
                new_q[pos] = angle_rad
                move_to(new_q)
                target_q[:] = new_q
                print(f'[CAL] Joint {joint_idx} → {angle_deg}° ({angle_rad:.3f} rad)')
            except ValueError:
                print('[CAL] Usage: q <index> <angle_deg>')

        elif cmd == 'pose' and len(parts) == 2:
            try:
                angles_deg = [float(x) for x in parts[1].split(',')]
                if len(angles_deg) != 17:
                    print(f'[CAL] Besoin de 17 angles, reçu {len(angles_deg)}')
                    continue
                new_q = [math.radians(a) for a in angles_deg]
                move_to(new_q)
                target_q[:] = new_q
                print(f'[CAL] Pose appliquée')
            except ValueError:
                print('[CAL] Usage: pose 0,90,0,0,0,0,0, 0,-90,0,0,0,0,0, 0,0,0')

        else:
            print(f'[CAL] Commande inconnue: {line}. Tape "help".')
