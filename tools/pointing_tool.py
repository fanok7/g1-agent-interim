import threading
import robot.arm_sdk as arm_sdk
from tools.registry import register


def _handler(**kwargs):
    direction = kwargs.get('direction', 'devant')
    threading.Thread(
        target=arm_sdk.execute_direction,
        args=(direction,),
        daemon=True,
    ).start()
    labels = {'gauche': 'la gauche', 'droite': 'la droite', 'devant': 'devant'}
    return f'Pointage vers {labels.get(direction, direction)} lancé.'


_SCHEMA = {
    'name': 'pointer_direction',
    'description': (
        'Pointe physiquement le bras dans une direction pour indiquer un emplacement. '
        'Utilise quand quelqu\'un demande "où est X ?", "par où ?", "de quel côté ?". '
        'Ne jamais mentionner le geste dans la réponse parlée.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'direction': {
                'type': 'string',
                'enum': ['gauche', 'droite', 'devant'],
                'description': 'Direction vers laquelle pointer',
            },
        },
        'required': ['direction'],
    },
}

register(_SCHEMA, _handler)
