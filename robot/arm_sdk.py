"""
Contrôle articulaire des bras via rt/arm_sdk (DDS).
Fonctionne en parallèle du locomotion controller — jambes non affectées.
S'initialise paresseusement après hardware.init().
"""
import math
import time
import threading

from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC

# Ordre des joints dans les vecteurs de pose (17 valeurs)
# [L_ShPitch, L_ShRoll, L_ShYaw, L_Elbow, L_WRoll, L_WPitch, L_WYaw,
#  R_ShPitch, R_ShRoll, R_ShYaw, R_Elbow, R_WRoll, R_WPitch, R_WYaw,
#  WaistYaw, WaistRoll, WaistPitch]
_ARM_JOINTS  = [15, 16, 17, 18, 19, 20, 21,
                22, 23, 24, 25, 26, 27, 28,
                12, 13, 14]
_ENABLE_SLOT = 29   # motor_cmd[29].q = 1 active arm_sdk

_PI2 = math.pi / 2        # 90°
_80D = math.radians(80)   # 80°

# Poses calibrées sur le robot (valeurs mesurées)
# Index : 0=L_ShPitch, 1=L_ShRoll, 3=L_Elbow, 7=R_ShPitch, 8=R_ShRoll, 10=R_Elbow
POSES = {
    'gauche': [0, _PI2, 0, 0,   0, 0, 0,
               0, 0,    0, 0,   0, 0, 0,
               0, 0, 0],

    'droite': [0, 0,    0, 0,   0, 0, 0,
               0, -_PI2,0, _PI2,0, 0, 0,
               0, 0, 0],

    'devant': [0, 0,    0, 0,   0, 0, 0,
               -_80D, 0, 0, _PI2, 0, 0, 0,
               0, 0, 0],

    'devant_gauche': [_80D, 0, 0, _PI2, 0, 0, 0,
                      0, 0,  0, 0,    0, 0, 0,
                      0, 0, 0],

    'rps': [0.] * 17,   # bras droit à zéro = coude naturellement plié
}

_NEUTRAL     = [0.] * 17
_RIGHT_ONLY  = frozenset(range(7, 14))   # indices bras droit dans le vecteur 17
_ARMS_ONLY   = frozenset(range(0, 14))   # les 2 bras — jamais la taille (14-16),
                                         # réservée au contrôleur d'équilibre
_KP       = 60.0   # valeurs de l'exemple officiel g1_arm7_sdk_dds_example
_KD       = 1.5
_CTRL_DT  = 0.02   # 50 Hz
_RAMP_DUR = 1.5    # secondes d'interpolation
_FADE_DUR = 1.0    # secondes de rampe weight 1→0 pour rendre la main au loco


class _Controller:
    def __init__(self):
        self._low_state  = None
        self._state_lock = threading.Lock()
        self._exec_lock  = threading.Lock()
        self._crc        = CRC()
        self._pub        = None
        self._ready      = False

    def _init_once(self):
        if self._ready:
            return
        self._pub = ChannelPublisher("rt/arm_sdk", LowCmd_)
        self._pub.Init()
        sub = ChannelSubscriber("rt/lowstate", LowState_)
        sub.Init(self._on_state, 10)
        for _ in range(50):
            if self._low_state is not None:
                break
            time.sleep(0.1)
        self._ready = True

    def _on_state(self, msg: LowState_):
        with self._state_lock:
            self._low_state = msg

    def _current_q(self):
        with self._state_lock:
            if self._low_state is None:
                return list(_NEUTRAL)
            return [self._low_state.motor_state[j].q for j in _ARM_JOINTS]

    def _write(self, q_list, weight=1.0):
        """Tous les joints sont commandés avec KP plein — jamais kp=0 tant que
        arm_sdk est actif, sinon le joint devient mou (taille → perte d'équilibre).
        Le blending avec le contrôleur loco se fait uniquement via weight."""
        cmd = unitree_hg_msg_dds__LowCmd_()
        cmd.motor_cmd[_ENABLE_SLOT].q = weight
        for i, joint in enumerate(_ARM_JOINTS):
            cmd.motor_cmd[joint].tau = 0.
            cmd.motor_cmd[joint].q   = q_list[i]
            cmd.motor_cmd[joint].dq  = 0.
            cmd.motor_cmd[joint].kp  = _KP
            cmd.motor_cmd[joint].kd  = _KD
        cmd.crc = self._crc.Crc(cmd)
        self._pub.Write(cmd)

    def _ramp(self, from_q, to_q, duration):
        t0 = time.time()
        while True:
            r = min((time.time() - t0) / duration, 1.0)
            q = [from_q[i] + r * (to_q[i] - from_q[i]) for i in range(17)]
            self._write(q)
            if r >= 1.0:
                break
            time.sleep(_CTRL_DT)

    def _fade_out(self, base_q):
        """Rampe weight 1→0 : rend progressivement la main au contrôleur loco."""
        t0 = time.time()
        while True:
            r = min((time.time() - t0) / _FADE_DUR, 1.0)
            self._write(base_q, weight=1.0 - r)
            if r >= 1.0:
                break
            time.sleep(_CTRL_DT)

    def _build_target(self, direction, base_q, active_set):
        """Joints actifs → pose demandée ; les autres (dont la taille, toujours)
        restent figés à leur position mesurée au départ."""
        pose = POSES[direction]
        return [pose[i] if i in active_set else base_q[i] for i in range(17)]

    def hold_until_release(self, direction: str, event: threading.Event,
                           active_set=_ARMS_ONLY):
        if direction not in POSES:
            print(f'[ARM_SDK] Direction inconnue: {direction}')
            return
        with self._exec_lock:
            self._init_once()
            base_q = self._current_q()
            target = self._build_target(direction, base_q, active_set)
            print(f'[ARM_SDK] ↑ {direction} (hold)')
            self._ramp(base_q, target, _RAMP_DUR)
            while not event.wait(timeout=_CTRL_DT):
                self._write(target)
            self._ramp(target, base_q, _RAMP_DUR)
            self._fade_out(base_q)
            print(f'[ARM_SDK] ↓ {direction} relâché')

    def execute(self, direction: str, hold_secs: float = 2.0):
        if direction not in POSES:
            print(f'[ARM_SDK] Direction inconnue: {direction}')
            return
        with self._exec_lock:
            self._init_once()
            base_q = self._current_q()
            target = self._build_target(direction, base_q, _ARMS_ONLY)
            print(f'[ARM_SDK] → {direction}')
            self._ramp(base_q, target, _RAMP_DUR)
            t0 = time.time()
            while time.time() - t0 < hold_secs:
                self._write(target)
                time.sleep(_CTRL_DT)
            self._ramp(target, base_q, _RAMP_DUR)
            self._fade_out(base_q)
            print(f'[ARM_SDK] {direction} terminé')


_ctrl = _Controller()
_hold_event = threading.Event()
_hold_thread = None


def execute_direction(direction: str, hold_secs: float = 2.0):
    _ctrl.execute(direction, hold_secs)


def hold_pose(direction: str, right_only: bool = False):
    """Maintient la pose jusqu'à release_pose(). right_only=True : seul le bras
    droit bouge, le gauche reste figé à sa position courante (KP plein)."""
    global _hold_thread
    active = _RIGHT_ONLY if right_only else _ARMS_ONLY
    _hold_event.clear()
    _hold_thread = threading.Thread(target=_ctrl.hold_until_release,
                                    args=(direction, _hold_event, active),
                                    daemon=True)
    _hold_thread.start()


def release_pose(wait: bool = False, timeout: float = 6.0):
    """Relâche la pose tenue par hold_pose(). wait=True : bloque jusqu'à la fin
    des rampes de relâchement (~2.5s) — à utiliser avant un ExecuteAction."""
    _hold_event.set()
    t = _hold_thread
    if wait and t is not None and t.is_alive():
        t.join(timeout=timeout)


def is_holding() -> bool:
    """True si une pose est tenue : les gestes haut niveau (ExecuteAction)
    doivent attendre, sinon les deux contrôleurs se disputent les bras."""
    t = _hold_thread
    return t is not None and t.is_alive()
