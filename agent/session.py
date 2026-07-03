import json
import websockets
from config import REALTIME_URL, OPENAI_API_KEY, VOICE, SYSTEM_PROMPT
from tools.registry import get_schemas
from tools.datetime_tool import date_heure_fr


async def connect():
    headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
    print('[AGENT] Connexion OpenAI Realtime...')
    ws = await websockets.connect(REALTIME_URL, extra_headers=headers)
    print('[AGENT] Connecté.')

    # Injecte la date/heure réelle (Paris) au démarrage de la session.
    import pytz
    from datetime import timedelta
    _paris = pytz.timezone("Europe/Paris")
    _now   = __import__("datetime").datetime.now(_paris)
    _demain = _now + timedelta(days=1)
    _apres  = _now + timedelta(days=2)
    instructions = (
        f"CONTEXTE TEMPOREL (heure de Paris au démarrage) :\n"
        f"  Aujourd'hui  : {date_heure_fr()}  — date ISO : {_now.strftime('%Y-%m-%d')}\n"
        f"  Demain       : {_demain.strftime('%A %d/%m/%Y').lower()} — date ISO : {_demain.strftime('%Y-%m-%d')}\n"
        f"  Après-demain : {_apres.strftime('%A %d/%m/%Y').lower()} — date ISO : {_apres.strftime('%Y-%m-%d')}\n"
        f"Pour l'heure exacte EN COURS DE CONVERSATION, appelle le tool date_heure_actuelle.\n"
        f"Pour l'agenda d'un jour précis, passe le paramètre date au format YYYY-MM-DD à agenda_du_jour.\n\n"
        + SYSTEM_PROMPT
    )

    schemas = get_schemas()
    await ws.send(json.dumps({
        'type': 'session.update',
        'session': {
            'type': 'realtime',
            'instructions': instructions,
            'output_modalities': ['audio'],
            'audio': {
                'input': {
                    'format': {'type': 'audio/pcm', 'rate': 24000},
                    'transcription': {
                        'model': 'gpt-4o-mini-transcribe',
                        # Pas de 'language' forcé : auto-détection → le robot comprend
                        # et répond dans la langue de l'interlocuteur (FR, EN, ES...).
                    },
                    'turn_detection': {
                        'type': 'semantic_vad',
                        'interrupt_response': True,
                        'create_response': True,
                        'eagerness': 'medium',
                    },
                },
                'output': {
                    'format': {'type': 'audio/pcm', 'rate': 24000},
                    'voice': VOICE,
                },
            },
            'tools': schemas,
            'tool_choice': 'auto',
        }
    }))
    print(f'[AGENT] Session configurée — {len(schemas)} tool(s) actif(s)')
    return ws
