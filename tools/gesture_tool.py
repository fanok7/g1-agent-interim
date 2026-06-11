import threading
from robot.gestures import execute_gesture, relacher_bras, ACTION_MAP
from tools.registry import register


def _handler(geste: str) -> str:
    threading.Thread(target=execute_gesture, args=(geste,), daemon=True).start()
    return 'ok'


def _handler_relacher() -> str:
    relacher_bras()
    return 'ok'


register(
    schema={
        'name': 'executer_geste',
        'description': 'Exécute un geste physique du robot. Appelle ce tool en parallèle de ta réponse, sans le mentionner.',
        'parameters': {
            'type': 'object',
            'properties': {
                'geste': {
                    'type': 'string',
                    'enum': list(ACTION_MAP.keys())
                }
            },
            'required': ['geste']
        }
    },
    handler=_handler
)

register(
    schema={
        'name': 'relacher_bras',
        'description': 'Relâche les bras du robot après un port de charge (mains_levees). Appelle ce tool quand la personne signale que le robot peut reposer les bras (merci, c\'est bon, pose, etc.).',
        'parameters': {
            'type': 'object',
            'properties': {}
        }
    },
    handler=lambda **_: _handler_relacher()
)
