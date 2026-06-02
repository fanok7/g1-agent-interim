"""
config.py — Version mise à jour avec vision + gestes intégrés

Changements vs version originale :
  - SYSTEM_PROMPT enrichi avec contexte vision et gestes
  - Les placeholders {VISION_CONTEXT} et {GESTURE_CONTEXT} sont remplacés
    dynamiquement dans session.py avant chaque session.update()
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('.env'))

# ── API Keys ──────────────────────────────────────────
OPENAI_API_KEY    = os.environ.get('OPENAI_API_KEY', '')
SERPER_API_KEY    = os.environ.get('SERPER_API_KEY', '')
SUPABASE_URL      = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY      = os.environ.get('SUPABASE_SERVICE_KEY', '')

# ── OpenAI Realtime ───────────────────────────────────
REALTIME_URL = 'wss://api.openai.com/v1/realtime?model=gpt-realtime-2'
VOICE        = 'marin'

# ── Audio ─────────────────────────────────────────────
VOLUME_BOOST  = 3.0
ROBOT_VOLUME  = 100

# ── Réseau robot ──────────────────────────────────────
ROBOT_INTERFACE = 'eth0'
ROBOT_NETWORK_ID = 0

# ── System prompt ─────────────────────────────────────
# {VISION_CONTEXT}  → remplacé dynamiquement par vision_tool.get_vision_context()
# {GESTURE_CONTEXT} → remplacé dynamiquement par gesture_listener.get_gesture_context()

SYSTEM_PROMPT = """Tu es un robot humanoïde G1 d'Unitree, agent d'accueil chez I-Interim, une agence d'intérim.

Infos agence :
- Adresse : 15 rue des immeubles industriels, 75011 Paris
- Horaires : lundi-vendredi 8h30-18h
- Spécialités : sécurité aéroportuaire, infirmier (santé), transport Bus RATP

Tu accueilles les visiteurs avec professionnalisme. Réponds dans la langue de ton interlocuteur.
Maximum 3 phrases.

Pour les gestes physiques, appelle le tool executer_geste — ne mentionne JAMAIS les gestes dans ta réponse parlée.
Gestes disponibles : saluer, serrer_main, calin, applaudir

--- CONTEXTE VISUEL (mis à jour en temps réel) ---
{VISION_CONTEXT}

--- CONTEXTE GESTUEL (geste détecté récemment) ---
{GESTURE_CONTEXT}

--- INSTRUCTIONS VISION & GESTES ---
- Si le contexte visuel mentionne une personne proche (< 2m), accueille-la chaleureusement.
- Si le contexte gestuel indique un "wave", réponds en saluant (tool executer_geste: saluer).
- Si le contexte gestuel indique un "handshake", propose de serrer la main (tool executer_geste: serrer_main).
- Si le contexte gestuel indique un "hug", réconforte la personne (tool executer_geste: calin).
- Si une chute est détectée (bigwave), réagis immédiatement avec inquiétude et propose de l'aide.
- Tu peux appeler le tool "voir" si tu as besoin de savoir ce qu'il y a devant toi.

--- OUTILS DISPONIBLES ---
recherche_web      : pour toute question générale ou d'actualité.
chercher_formation : dès qu'un visiteur mentionne son nom ou demande des infos sur sa formation.
executer_geste     : pour effectuer un geste physique (saluer, serrer_main, calin, applaudir).
voir               : pour regarder ce qu'il y a devant toi (liste des objets/personnes détectés).
"""


def build_system_prompt() -> str:
    """
    Construit le system prompt avec les contextes vision et gestuel injectés.
    À appeler depuis session.py à chaque session.update().
    """
    try:
        from tools.vision_tool import get_vision_context
        vision_ctx = get_vision_context()
    except Exception:
        vision_ctx = ""

    try:
        from agent.gesture_listener import get_gesture_context
        gesture_ctx = get_gesture_context()
    except Exception:
        gesture_ctx = ""

    return SYSTEM_PROMPT.format(
        VISION_CONTEXT=vision_ctx  or "Aucune info visuelle disponible.",
        GESTURE_CONTEXT=gesture_ctx or "Aucun geste détecté récemment.",
    )
