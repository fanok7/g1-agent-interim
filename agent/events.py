import json, base64, asyncio, os, time, threading
import sounddevice as sd
import numpy as np
from robot.audio import play_audio, find_microphone
from robot.hardware import get_audio_client
from robot.gestures import execute_gesture
from tools.registry import call as call_tool

_RESPONDING_FLAG  = "/tmp/agent_responding"
_FACE_STATE_FILE  = "/tmp/face_id_state.json"
_FACE_STALE_SECS  = 5.0

# Tools qui nécessitent une instruction forcée dans response.create
_TOOL_INSTRUCTIONS = {
    'demarrer_pfc': 'Dis exactement et uniquement ce texte, mot pour mot, avec enthousiasme : "3 ! 2 ! 1 ! Go !"',
}

def _response_create(tool_name=None):
    msg = {'type': 'response.create'}
    if tool_name and tool_name in _TOOL_INSTRUCTIONS:
        msg['response'] = {'instructions': _TOOL_INSTRUCTIONS[tool_name]}
    return msg

def _set_responding(state: bool):
    if state:
        open(_RESPONDING_FLAG, 'w').close()
    else:
        try:
            os.remove(_RESPONDING_FLAG)
        except FileNotFoundError:
            pass

MICRO_INDEX, MICRO_SR = find_microphone()


async def send_audio_loop(ws):
    loop = asyncio.get_event_loop()
    q = asyncio.Queue()

    def cb(indata, frames, t, status):
        data = indata[::2] if MICRO_SR == 48000 else indata
        pcm = (data * 32767).astype(np.int16).tobytes()
        loop.call_soon_threadsafe(q.put_nowait, pcm)

    with sd.InputStream(samplerate=MICRO_SR, channels=1, dtype='float32',
                        device=MICRO_INDEX, blocksize=int(MICRO_SR * 0.02),
                        callback=cb):
        while True:
            chunk = await q.get()
            # Muet pendant la lecture du robot + 500 ms après (anti-écho)
            if os.path.exists(_RESPONDING_FLAG):
                continue
            await ws.send(json.dumps({
                'type': 'input_audio_buffer.append',
                'audio': base64.b64encode(chunk).decode()
            }))


async def receive_events_loop(ws):
    audio_buf           = bytearray()
    text_buf            = ''
    tool_id             = None
    tool_name           = None
    tool_args           = ''
    responding          = False
    pending_tool_output = None   # (tool_id, result) à envoyer après response.done
    pending_tool_name   = None

    async for raw in ws:
        e = json.loads(raw)
        t = e.get('type', '')

        if t == 'input_audio_buffer.speech_started':
            print('[Toi] Parle...')
            if responding:
                get_audio_client().PlayStop('chat')
                audio_buf.clear()
                responding = False
                _set_responding(False)

        elif t == 'conversation.item.input_audio_transcription.completed':
            print(f'[Toi] {e.get("transcript", "")}')

        elif t == 'response.output_audio.delta':
            audio_buf.extend(base64.b64decode(e['delta']))
            if not responding:
                print('[G1] Parle...')
                _set_responding(True)
            responding = True

        elif t == 'response.output_audio_transcript.delta':
            text_buf += e.get('delta', '')

        elif t == 'response.output_audio.done':
            if audio_buf:
                print(f'[G1] {text_buf}')
                play_audio(bytes(audio_buf))
                audio_buf.clear()
                text_buf = ''
                responding = False
                _set_responding(False)
                print('[G1] Écoute...')

        elif t == 'response.done':
            responding = False
            _set_responding(False)
            if pending_tool_output:
                tid, result   = pending_tool_output
                tname         = pending_tool_name
                pending_tool_output = None
                pending_tool_name   = None
                await ws.send(json.dumps({
                    'type': 'conversation.item.create',
                    'item': {'type': 'function_call_output', 'call_id': tid, 'output': result}
                }))
                await ws.send(json.dumps(_response_create(tname)))

        elif t == 'response.output_item.added':
            item = e.get('item', {})
            if item.get('type') == 'function_call':
                tool_id   = item.get('call_id')
                tool_name = item.get('name')
                tool_args = ''
                print(f'[TOOL] Appel : {tool_name}')

        elif t == 'response.function_call_arguments.delta':
            tool_args += e.get('delta', '')

        elif t == 'response.function_call_arguments.done':
            try:
                args = json.loads(tool_args)
                print(f'[TOOL] Args : {args}')
                result = call_tool(tool_name, args)
            except Exception as ex:
                print(f'[TOOL] Erreur : {ex}')
                result = str(ex)

            if responding:
                pending_tool_output = (tool_id, result)
                pending_tool_name   = tool_name
            else:
                await ws.send(json.dumps({
                    'type': 'conversation.item.create',
                    'item': {'type': 'function_call_output', 'call_id': tool_id, 'output': result}
                }))
                await ws.send(json.dumps(_response_create(tool_name)))
            tool_id = tool_name = None
            tool_args = ''

        elif t == 'error':
            print(f'[ERREUR] {e.get("error", {})}')


async def rps_result_loop(ws):
    """Injecte le résultat RPS dans la conversation dès que la partie se termine."""
    _RPS_RESULT = '/tmp/rps_result.json'
    while True:
        await asyncio.sleep(1)
        if not os.path.exists(_RPS_RESULT):
            continue
        try:
            with open(_RPS_RESULT) as f:
                result = json.load(f)
            os.remove(_RPS_RESULT)
        except Exception:
            continue

        r      = result.get('result', 'rate')
        player = result.get('player') or 'inconnu'
        robot  = result.get('robot', '?')
        sp     = result.get('score_player', 0)
        sr     = result.get('score_robot', 0)

        if r == 'rate':
            msg = (f'[RPS] Geste du joueur non détecté. '
                   f'Le robot avait joué {robot}. '
                   f'Annonce que tu n\'as pas vu son geste et propose de rejouer.')
        else:
            msg = (f'[RPS] Résultat : robot={robot}, joueur={player}, résultat={r}. '
                   f'Score : joueur {sp} — robot {sr}. '
                   f'Annonce le résultat de façon enthousiaste et propose une revanche.')

        await ws.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type':    'message',
                'role':    'user',
                'content': [{'type': 'input_text', 'text': msg}],
            }
        }))
        await ws.send(json.dumps({'type': 'response.create'}))


async def face_greeting_loop(ws):
    """Salue automatiquement les visages connus reconnus pour la première fois."""
    greeted = set()

    # Attendre que vision_server soit prêt (poll fichier)
    for _ in range(30):
        if os.path.exists(_FACE_STATE_FILE):
            break
        await asyncio.sleep(1)
    else:
        await asyncio.sleep(5)

    while True:
        await asyncio.sleep(2)
        try:
            with open(_FACE_STATE_FILE) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        if time.time() - state.get('ts', 0) > _FACE_STALE_SECS:
            continue

        for face in state.get('faces', []):
            name = face.get('name', 'Inconnu')
            if name == 'Inconnu' or name in greeted:
                continue

            greeted.add(name)
            print(f'[FACE] Nouvelle personne reconnue : {name} → salutation')

            # Geste saluer en parallèle de la voix
            threading.Thread(target=execute_gesture, args=('saluer',), daemon=True).start()

            # Injecter un déclencheur discret dans la conversation
            await ws.send(json.dumps({
                'type': 'conversation.item.create',
                'item': {
                    'type': 'message',
                    'role': 'user',
                    'content': [{'type': 'input_text',
                                 'text': f'[SYSTÈME] La caméra vient de détecter {name}. Salue-le chaleureusement par son prénom.'}]
                }
            }))
            await ws.send(json.dumps({'type': 'response.create'}))
            # Attendre que le robot finisse de parler avant de chercher le prochain visage
            await asyncio.sleep(5)
