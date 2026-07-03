"""
main/shake_hand.py — Poignée de main réactive

  - SDK  → lève / baisse le bras (ExecuteAction 27 / 99)
  - Modbus → ferme / ouvre les doigts  (via HandControl)
  - Capteur paume → pilote tout le timing (zéro timer artificiel)

Lancement standalone :
    python3.8 -c "
    import sys; sys.path.insert(0, '/home/unitree/g1_agent_interim')
    import robot.hardware as hw; hw.init()
    from main.shake_hand import run_shake_hand
    run_shake_hand()
    "
"""

import time
import logging

from main.hand_control import HandControl

try:
    from robot import hand_idle
    _HAND_IDLE_AVAILABLE = True
except Exception:
    _HAND_IDLE_AVAILABLE = False

log = logging.getLogger(__name__)

# ── Paramètres serrage ─────────────────────────────────────────────────────
TARGET_GRIP = 500    # position cible (0–1000)
FORCE_MAX_G = 2000   # force max en grammes avant réduction
GRIP_STEP   = 30     # pas de fermeture par cycle
GRIP_FLOOR  = 200    # plancher de sécurité
SPEED       = 250    # vitesse fermeture

# ── SDK bras ───────────────────────────────────────────────────────────────
ACTION_SHAKE = 27   # lève le bras + geste poignée
ACTION_RESET = 99   # baisse le bras / reset

# ── Timeouts sécurité ──────────────────────────────────────────────────────
WAIT_CONTACT_TIMEOUT = 15.0   # secondes max en attente de contact paume
HOLD_TIMEOUT         = 30.0   # secondes max en état SERRAGE

# ── Fréquence boucle ───────────────────────────────────────────────────────
LOOP_DT = 0.05   # 20 Hz

# ── États ─────────────────────────────────────────────────────────────────
_WAITING   = 0
_CLOSING   = 1
_HOLDING   = 2
_RELEASING = 3
_STATE_NAMES = {
    _WAITING:   'EN ATTENTE',
    _CLOSING:   'FERMETURE',
    _HOLDING:   'SERRAGE',
    _RELEASING: 'RELACHEMENT',
}


def run_shake_hand(side: str = 'left', on_event=None):
    """
    Exécute un cycle complet de poignée de main.

    side      : 'left' | 'right'
    on_event  : callable(str) optionnel — reçoit 'handshake_start' et
                'handshake_end' pour notifier l'agent GPT
    """
    import robot.hardware as hardware

    log.info('[SHAKE] Démarrage (côté=%s)', side)

    # Le mouvement naturel en tâche de fond (hand_idle) écrit sur le même
    # registre Modbus que HandControl ci-dessous — suspendu le temps de la
    # poignée de main, repris dans le finally.
    if _HAND_IDLE_AVAILABLE:
        hand_idle.stop()

    hand = HandControl(side)
    if not hand.connect():
        log.error('[SHAKE] Connexion Modbus impossible.')
        if _HAND_IDLE_AVAILABLE:
            hand_idle.start()
        return

    arm_client = hardware.get_arm_client()

    # Init main
    hand.set_speed(SPEED)
    hand.open()
    time.sleep(0.3)

    # Lever le bras immédiatement via SDK
    log.info('[SHAKE] ExecuteAction(%d) — bras levé', ACTION_SHAKE)
    arm_client.ExecuteAction(ACTION_SHAKE)

    state      = _WAITING
    grip_value = 0
    t_state    = time.time()

    print(f'[SHAKE] {_STATE_NAMES[state]} — Tendez la main vers la paume...')

    try:
        while True:
            palm   = hand.read_palm()
            forces = hand.read_force()

            contact, nb_pts, total = hand.palm_contact(palm)
            released               = hand.palm_released(palm)
            avg_force = sum(forces[:5]) / 5 if forces else 0
            now = time.time()

            # ── Machine d'état ─────────────────────────────────────────────

            if state == _WAITING:
                if now - t_state > WAIT_CONTACT_TIMEOUT:
                    print('\n[SHAKE] Timeout — personne n\'a tendu la main.')
                    break

                if contact:
                    state      = _CLOSING
                    grip_value = 0
                    t_state    = now
                    _notify(on_event, 'handshake_start')
                    print(f'\n[SHAKE] {_STATE_NAMES[state]} '
                          f'(paume: {nb_pts} pts, total={total})')

            elif state == _CLOSING:
                grip_value = min(grip_value + GRIP_STEP, TARGET_GRIP)
                hand.close(grip_value)

                if grip_value >= TARGET_GRIP:
                    state   = _HOLDING
                    t_state = now
                    print(f'\n[SHAKE] {_STATE_NAMES[state]} (grip={grip_value})')

                # Paume retirée pendant fermeture
                if released:
                    state   = _RELEASING
                    t_state = now

            elif state == _HOLDING:
                # Sécurité force
                if forces and max(forces[:5]) > FORCE_MAX_G:
                    grip_value = max(grip_value - 50, GRIP_FLOOR)
                    hand.close(grip_value)

                # Timeout sécurité
                if now - t_state > HOLD_TIMEOUT:
                    log.warning('[SHAKE] Timeout SERRAGE — relâchement forcé.')
                    state = _RELEASING

                # Capteur paume → la personne retire sa main
                if released:
                    state   = _RELEASING
                    t_state = now
                    print(f'\n[SHAKE] {_STATE_NAMES[state]}')

            elif state == _RELEASING:
                hand.open()
                # Baisser le bras via SDK — déclenché par le capteur, pas un timer
                log.info('[SHAKE] ExecuteAction(%d) — bras baissé', ACTION_RESET)
                arm_client.ExecuteAction(ACTION_RESET)
                _notify(on_event, 'handshake_end')
                print('[SHAKE] Poignée terminée.')
                break

            # Affichage temps réel
            if state not in (_WAITING, _RELEASING):
                print(f'  paume={nb_pts:3d}pts  '
                      f'force_avg={avg_force:5.0f}g  '
                      f'grip={grip_value:4d}', end='\r')

            time.sleep(LOOP_DT)

    except KeyboardInterrupt:
        print('\n[SHAKE] Interruption clavier.')

    finally:
        hand.open()
        arm_client.ExecuteAction(ACTION_RESET)
        time.sleep(0.3)
        hand.disconnect()
        if _HAND_IDLE_AVAILABLE:
            hand_idle.start()
        log.info('[SHAKE] Nettoyage OK.')


# ── Helper ─────────────────────────────────────────────────────────────────

def _notify(on_event, event: str):
    if on_event:
        try:
            on_event(event)
        except Exception as exc:
            log.warning('[SHAKE] Erreur callback : %s', exc)
