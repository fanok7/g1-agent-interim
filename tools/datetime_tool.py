"""tools/datetime_tool.py — date et heure courantes (heure locale française).

Le fuseau horaire du Jetson est souvent faux (réglé sur Asia/Shanghai après un
reboot). On force donc Europe/Paris via pytz pour que l'agent donne toujours
l'heure française correcte, quelle que soit la config système — du moment que
l'horloge UTC du robot est juste.
"""

from datetime import datetime

import pytz

from tools.registry import register

_PARIS = pytz.timezone('Europe/Paris')
_JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
_MOIS  = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
          'août', 'septembre', 'octobre', 'novembre', 'décembre']


def maintenant_paris() -> datetime:
    """datetime courant en heure de Paris (gère l'heure d'été automatiquement)."""
    return datetime.now(_PARIS)


def date_heure_fr() -> str:
    """Phrase naturelle et lisible à voix haute (la synthèse bute sur '10h15',
    donc on écrit 'dix heures quinze' en toutes lettres approchées) :
    'lundi 15 juin 2026, il est 10 heures 09'."""
    now  = maintenant_paris()
    jour = _JOURS[now.weekday()]
    mois = _MOIS[now.month - 1]
    if now.minute == 0:
        heure = f"{now.hour} heures"
    else:
        heure = f"{now.hour} heures {now.minute}"
    return f"{jour} {now.day} {mois} {now.year}, il est {heure}"


def _handler(**_kwargs) -> str:
    return date_heure_fr()


register(
    {
        'name': 'date_heure_actuelle',
        'description': (
            "Donne la date et l'heure actuelles en heure locale française. "
            "Appelle ce tool dès qu'on te demande l'heure, le jour, la date, "
            "'on est quel jour ?', 'quelle heure est-il ?'. "
            "Ne donne JAMAIS l'heure ou la date de mémoire — appelle toujours ce tool."
        ),
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
    _handler,
)
