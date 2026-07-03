import time
import threading
import robot.hardware as hardware

try:
    from robot import hand_idle
    _HAND_IDLE_AVAILABLE = True
except Exception:
    _HAND_IDLE_AVAILABLE = False

_release_event = threading.Event()

ACTION_MAP = {
    'saluer':            25,
    'serrer_main':       27,
    'tope_la':           18,
    'calin':             19,
    'grande_salutation': 26,
    'applaudir':         17,
    'bisou_gauche':      12,
    'bisou_droit':       13,
    'bisou_deux_mains':  11,
    'coeur':             20,
    'coeur_droit':       21,
    'mains_levees':      15,
    'main_droite_levee': 23,
    'rayons_x':          24,
    'refus':             22,
}

RESET_CODE = 99


def relacher_bras():
    _release_event.set()


def execute_gesture(geste: str):
    geste = geste.lower().strip()
    arm_client = hardware.get_arm_client()
    if geste not in ACTION_MAP:
        print(f'[GESTE] Inconnu : {geste}')
        return
    # Ne jamais lancer un geste haut niveau pendant qu'arm_sdk tient une pose
    # (jeu RPS, pointage) — les deux contrôleurs se disputeraient les bras
    import robot.arm_sdk as arm_sdk
    if arm_sdk.is_holding():
        print(f'[GESTE] {geste} ignoré — arm_sdk tient une pose (jeu en cours)')
        return
    code = ACTION_MAP[geste]
    print(f'[GESTE] {geste} → code {code}')
    # Les gestes hauts niveau (ExecuteAction) pilotent aussi les mains — le
    # mouvement naturel en tâche de fond (hand_idle) doit se taire le temps
    # du geste, sinon les deux se disputent le même actionneur.
    if _HAND_IDLE_AVAILABLE:
        hand_idle.stop()
    try:
        if geste == 'mains_levees':
            _release_event.clear()
        arm_client.ExecuteAction(code)
        if geste == 'mains_levees':
            print('[GESTE] En attente de relacher_bras()...')
            _release_event.wait(timeout=60)
        else:
            time.sleep(2)
        arm_client.ExecuteAction(RESET_CODE)
    except Exception as e:
        print(f'[GESTE] Erreur : {e}')
    finally:
        if _HAND_IDLE_AVAILABLE:
            hand_idle.start()
