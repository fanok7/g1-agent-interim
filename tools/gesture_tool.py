import threading
from robot.gestures import execute_gesture, ACTION_MAP
from tools.registry import register


def _handler(geste: str) -> str:
    threading.Thread(target=execute_gesture, args=(geste,), daemon=True).start()
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
