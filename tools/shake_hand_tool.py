"""
tools/shake_hand_tool.py — Tool GPT : poignée de main

Enregistre le tool 'serrer_main' dans le registry.
GPT l'appelle quand quelqu'un demande de serrer la main.

Flux :
  GPT → serrer_main()
      → thread → main.shake_hand.run_shake_hand()
          → SDK lève bras (27)
          → capteur paume attend contact
          → Modbus ferme doigts
          → capteur paume détecte relâchement
          → Modbus ouvre doigts
          → SDK baisse bras (99)
      → event_queue ← 'handshake_start' / 'handshake_end'
          → agent/shake_hand_loop.py → GPT dit quelque chose
"""

import threading
import queue
import logging

from tools.registry import register

log = logging.getLogger(__name__)

# Queue consommée par agent/shake_hand_loop.py
event_queue: queue.Queue = queue.Queue()

# Verrou pour éviter deux poignées simultanées
_running = threading.Event()


def _handler(side: str = 'left') -> str:
    if _running.is_set():
        return 'Je suis déjà en train de serrer une main.'

    def _run():
        _running.set()
        try:
            from main.shake_hand import run_shake_hand
            run_shake_hand(
                side=side,
                on_event=lambda evt: event_queue.put(evt)
            )
        except Exception as exc:
            log.error('[SHAKE_TOOL] Erreur : %s', exc)
        finally:
            _running.clear()

    threading.Thread(target=_run, daemon=True, name='shake_hand').start()
    return 'ok'


register(
    schema={
        'name': 'serrer_main',
        'description': (
            'Serre la main d\'une personne physiquement. '
            'Le robot lève le bras, attend que la personne mette sa main '
            'dans la sienne via le capteur tactile de paume, serre les '
            'doigts, puis baisse le bras quand la personne retire sa main. '
            'Appelle ce tool dès que quelqu\'un dit "serre-moi la main", '
            '"shake hands", "donne-moi ta main" ou formule similaire. '
            'Ne mentionne pas le tool dans ta réponse vocale.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'side': {
                    'type': 'string',
                    'enum': ['left', 'right'],
                    'description': 'Main à utiliser. Défaut : left.'
                }
            },
            'required': []
        }
    },
    handler=lambda side='left', **_: _handler(side)
)
