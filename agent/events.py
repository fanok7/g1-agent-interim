import json, base64, asyncio
import sounddevice as sd
import numpy as np
from robot.audio import play_audio, find_microphone
from robot.hardware import get_audio_client
from tools.registry import call as call_tool

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
            await ws.send(json.dumps({
                'type': 'input_audio_buffer.append',
                'audio': base64.b64encode(chunk).decode()
            }))


async def receive_events_loop(ws):
    audio_buf  = bytearray()
    text_buf   = ''
    tool_id    = None
    tool_name  = None
    tool_args  = ''
    responding = False

    async for raw in ws:
        e = json.loads(raw)
        t = e.get('type', '')

        if t == 'input_audio_buffer.speech_started':
            print('[Toi] Parle...')
            if responding:
                get_audio_client().PlayStop('chat')
                audio_buf.clear()
                responding = False

        elif t == 'conversation.item.input_audio_transcription.completed':
            print(f'[Toi] {e.get("transcript", "")}')

        elif t == 'response.output_audio.delta':
            audio_buf.extend(base64.b64decode(e['delta']))
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

            await ws.send(json.dumps({
                'type': 'conversation.item.create',
                'item': {'type': 'function_call_output', 'call_id': tool_id, 'output': result}
            }))
            await ws.send(json.dumps({'type': 'response.create'}))
            tool_id = tool_name = None
            tool_args = ''

        elif t == 'error':
            print(f'[ERREUR] {e.get("error", {})}')
