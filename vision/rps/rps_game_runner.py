"""
rps_game_runner.py — Moteur Pierre Feuille Ciseaux pour l'agent G1

Deux phases :
  1. prepare()   → robot choisit son coup (secret), prêt à jouer
  2. countdown() → synchronisé avec le compte à rebours vocal du robot
                   révèle la main après ~4.5s (quand l'agent a fini "…1 2 3 !")
                   puis détecte le geste du joueur

IPC :
  /tmp/rps_result.json  → lu par rps_result_loop dans events.py
  /tmp/gesture_cmd      → lu par gesture_cmd_loop dans main.py
  /tmp/vision_pause     → mis en pause vision_server pour libérer la caméra
"""

import os
import sys
import json
import time
import random
import threading

_RPS_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(os.path.dirname(_RPS_DIR))
sys.path.insert(0, _RPS_DIR)
sys.path.insert(0, _ROOT_DIR)

from rps_game   import RPSGame, GESTES
from rps_vision import RPSVision
from rps_hand   import RPSHand

try:
    import robot.arm_sdk as arm_sdk
    _ARM_AVAILABLE = True
except Exception:
    _ARM_AVAILABLE = False

MODEL_PATH     = os.path.join(_RPS_DIR, 'yolo11-rps-detection.pt')
GESTURES_YAML  = os.path.join(_RPS_DIR, 'hand_gestures.yaml')
RESULT_FILE    = '/tmp/rps_result.json'
GESTURE_CMD    = '/tmp/gesture_cmd'
VISION_PAUSE   = '/tmp/vision_pause'

# Délai entre le retour du tool et la révélation de la main.
# L'agent dit "3 ! 2 ! 1 ! Geste !" → ~3s de TTS.
REVEAL_DELAY   = 3.0   # secondes
DETECT_TIMEOUT = 6.0   # fenêtre de détection après la révélation

REACTIONS = {
    'victoire': 'saluer',
    'defaite':  'refus',
    'egalite':  'applaudir',
}

# ── État global ───────────────────────────────────────────────────────────────
_state_lock       = threading.Lock()
_robot_gesture    = None
_game             = None
_countdown_active = False
_hand             = None
_vision           = None


def is_ready():
    """True si prepare() a été appelé et que le coup est prêt."""
    with _state_lock:
        return _robot_gesture is not None and not _countdown_active


def is_busy():
    with _state_lock:
        return _countdown_active


def prepare():
    """
    Phase 1 : robot choisit son coup en secret.
    Pré-charge le modèle YOLO et ouvre la connexion Modbus en background.
    """
    global _robot_gesture, _game, _hand, _vision
    with _state_lock:
        if _countdown_active:
            return None
        _game = RPSGame()
        _robot_gesture = random.choice(GESTES)

    _patch_yaml()
    _hand   = RPSHand(side='r')
    _vision = RPSVision(MODEL_PATH, source=0)
    threading.Thread(target=_vision.preload, daemon=True).start()

    print(f'[RPS] Coup secret choisi : {_robot_gesture}', flush=True)
    if _ARM_AVAILABLE:
        arm_sdk.hold_pose('rps', right_only=True)
    return _robot_gesture


def countdown():
    """
    Phase 2 : lance le compte à rebours en background.
    Le robot révèle sa main après REVEAL_DELAY secondes (synchronisé avec le TTS),
    puis détecte le geste du joueur.
    """
    global _countdown_active
    with _state_lock:
        if _robot_gesture is None or _countdown_active:
            return False
        _countdown_active = True
    threading.Thread(target=_reveal_and_detect, daemon=True).start()
    return True


# ── Pipeline interne ──────────────────────────────────────────────────────────
def _reveal_and_detect():
    global _robot_gesture, _countdown_active, _hand, _vision

    try:
        t_start = time.time()

        # Pauser vision_server pour libérer /dev/video0
        open(VISION_PAUSE, 'w').close()
        time.sleep(0.3)

        # Attendre que le modèle YOLO soit prêt (chargé dans prepare())
        if not _vision._model_ready.wait(timeout=10.0):
            print('[RPS] WARN modèle non prêt après 10s', flush=True)

        with _state_lock:
            gesture = _robot_gesture

        # Synchronisation précise avec le TTS : attendre exactement REVEAL_DELAY
        remaining = REVEAL_DELAY - (time.time() - t_start)
        if remaining > 0:
            print(f'[RPS] Attente révélation ({remaining:.1f}s restantes)...', flush=True)
            time.sleep(remaining)

        # Démarrer la caméra à l'instant de la révélation — zéro stale frames
        _vision.start()

        # ── RÉVÉLATION ── main du robot
        print(f'[RPS] Révèle : {gesture}', flush=True)
        _hand.play(gesture)   # 1.0s (doigts + pouce) — YOLO chauffe pendant ce temps

        # Détecter le geste du joueur
        print(f'[RPS] Détection joueur ({DETECT_TIMEOUT}s)...', flush=True)
        player_gesture = _vision.capture_gesture(timeout=DETECT_TIMEOUT)
        print(f'[RPS] Joueur → {player_gesture}', flush=True)

        # Arbitre
        with _state_lock:
            result = _game.play_round(player_gesture, gesture)
        print(f'[RPS] {result["message"]}', flush=True)

        # Résultat → rps_result_loop
        with open(RESULT_FILE, 'w') as f:
            json.dump(result, f, ensure_ascii=False)

        # Réaction gestuelle → gesture_cmd_loop
        reaction = REACTIONS.get(result['result'])
        if reaction:
            with open(GESTURE_CMD, 'w') as f:
                f.write(reaction)

        # Nettoyage mains
        time.sleep(1.5)
        _hand.open()
        _vision.stop()
        _hand.disconnect()

    finally:
        _hand   = None
        _vision = None
        _cleanup()
        with _state_lock:
            _robot_gesture    = None
            _countdown_active = False
        print('[RPS] Partie terminée', flush=True)


def _patch_yaml():
    import rps_hand as m
    m.GESTURES_FILE = GESTURES_YAML

def _cleanup():
    if _ARM_AVAILABLE:
        arm_sdk.release_pose()
    try:
        os.remove(VISION_PAUSE)
    except FileNotFoundError:
        pass
