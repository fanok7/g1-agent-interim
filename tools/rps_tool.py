import sys
sys.path.insert(0, '/home/unitree/g1_agent_interim')

from tools.registry import register
import vision.rps.rps_game_runner as runner


def _handler_setup(**_kwargs):
    """Phase 1 — prépare le coup secret du robot."""
    if runner.is_busy():
        return 'Une partie est déjà en cours.'
    runner.prepare()
    return (
        'Coup choisi en secret. '
        'INTERDIT de révéler ou laisser deviner ton coup avant le compte à rebours. '
        'Dis uniquement : "C\'est bon, je suis prêt ! Tu es prêt ?" '
        'puis appelle demarrer_pfc dès qu\'il dit oui.'
    )


def _handler_start(**_kwargs):
    """Phase 2 — lance le compte à rebours et la révélation."""
    if not runner.is_ready():
        return 'Lance d\'abord jouer_pfc pour préparer la partie.'
    if runner.is_busy():
        return 'Partie déjà en cours.'
    runner.countdown()
    # Retourne un token opaque — le texte à dire est imposé par _TOOL_INSTRUCTIONS
    # dans events.py, pas ici, pour éviter que le LLM le lise et le répète directement
    # sans avoir appelé le tool.
    return 'COUNTDOWN_OK'


_SCHEMA_SETUP = {
    'name': 'jouer_pfc',
    'description': (
        'Démarre une partie de Pierre Feuille Ciseaux : le robot choisit son coup en secret. '
        'Appelle ce tool dès que quelqu\'un propose de jouer. '
        'Après l\'appel, demande au joueur s\'il est prêt puis appelle demarrer_pfc.'
    ),
    'parameters': {'type': 'object', 'properties': {}, 'required': []},
}

_SCHEMA_START = {
    'name': 'demarrer_pfc',
    'description': (
        'Lance le compte à rebours Pierre Feuille Ciseaux. '
        'Appelle UNIQUEMENT après jouer_pfc et quand le joueur a dit qu\'il est prêt. '
        'Le robot révèle sa main en synchronisation avec le compte à rebours, '
        'puis détecte le geste du joueur à la caméra. '
        'Le résultat sera annoncé automatiquement.'
    ),
    'parameters': {'type': 'object', 'properties': {}, 'required': []},
}

register(_SCHEMA_SETUP, _handler_setup)
register(_SCHEMA_START, _handler_start)
