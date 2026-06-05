import time
import threading
import robot.hardware as hardware

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
    code = ACTION_MAP[geste]
    print(f'[GESTE] {geste} → code {code}')
    try:
        if geste == 'mains_levees':
            _release_event.clear()
        arm_client.ExecuteAction(code)
        if geste == 'mains_levees':
            print('[GESTE] En attente de relacher_bras()...')
            _release_event.wait()
        else:
            time.sleep(2)
        arm_client.ExecuteAction(RESET_CODE)
    except Exception as e:
        print(f'[GESTE] Erreur : {e}')
