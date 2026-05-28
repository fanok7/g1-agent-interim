import sys, os, tempfile, subprocess, time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python/example/g1/audio')

import sounddevice as sd
import numpy as np
from wav import read_wav, play_pcm_stream
from config import VOLUME_BOOST
import robot.hardware as hardware


def find_microphone():
    for i, d in enumerate(sd.query_devices()):
        if 'USB' in d['name'] and d['max_input_channels'] > 0:
            sr = int(d['default_samplerate'])
            print(f'[MICRO] {d["name"]} index={i} sr={sr}')
            return i, sr
    print('[MICRO] USB non trouvé, device par défaut')
    return None, 48000


def play_audio(pcm_bytes):
    audio_client = hardware.get_audio_client()
    tmp_raw = tempfile.mktemp(suffix='.raw')
    tmp_wav = tempfile.mktemp(suffix='.wav')
    tmp_16k = tempfile.mktemp(suffix='_16k.wav')
    try:
        with open(tmp_raw, 'wb') as f:
            f.write(pcm_bytes)
        subprocess.run(
            ['ffmpeg', '-f', 's16le', '-ar', '24000', '-ac', '1', '-i', tmp_raw, tmp_wav, '-y'],
            capture_output=True
        )
        subprocess.run(
            ['ffmpeg', '-i', tmp_wav, '-ar', '16000', '-ac', '1', '-af', f'volume={VOLUME_BOOST}', tmp_16k, '-y'],
            capture_output=True
        )
        pcm, sr, ch, ok = read_wav(tmp_16k)
        if ok:
            play_pcm_stream(audio_client, pcm, 'chat')
            time.sleep(len(pcm) / 32000 + 0.5)
        audio_client.PlayStop('chat')
    finally:
        for f in [tmp_raw, tmp_wav, tmp_16k]:
            if os.path.exists(f):
                os.unlink(f)
