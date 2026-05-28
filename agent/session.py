import json
import websockets
from config import REALTIME_URL, OPENAI_API_KEY, VOICE, SYSTEM_PROMPT
from tools.registry import get_schemas


async def connect():
    headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
    print('[AGENT] Connexion OpenAI Realtime...')
    ws = await websockets.connect(REALTIME_URL, extra_headers=headers)
    print('[AGENT] Connecté.')

    await ws.send(json.dumps({
        'type': 'session.update',
        'session': {
            'type': 'realtime',
            'instructions': SYSTEM_PROMPT,
            'output_modalities': ['audio'],
            'audio': {
                'input': {
                    'format': {'type': 'audio/pcm', 'rate': 24000},
                    'transcription': {'model': 'gpt-4o-mini-transcribe'},
                    'turn_detection': {
                        'type': 'semantic_vad',
                        'interrupt_response': True
                    }
                },
                'output': {
                    'format': {'type': 'audio/pcm', 'rate': 24000},
                    'voice': VOICE
                }
            },
            'tools': get_schemas(),
            'tool_choice': 'auto',
        }
    }))
    print(f'[AGENT] Session configurée — {len(get_schemas())} tool(s) actif(s)')
    return ws
