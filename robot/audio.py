import sys, os, tempfile, subprocess, time
sys.path.insert(0, '/home/unitree/unitree_sdk2_python/example/g1/audio')

import sounddevice as sd
import numpy as np
from wav import read_wav, play_pcm_stream
from config import VOLUME_BOOST
import robot.hardware as hardware


def find_microphone():
    devices = sd.query_devices()
    # Priorité : USB MIC (Cubilux)
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and 'MIC' in d['name'].upper():
            sr = int(d['default_samplerate'])
            print(f'[MICRO] {d["name"]} index={i} sr={sr}')
            return i, sr
    # Fallback : premier périphérique USB avec entrée
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and 'USB' in d['name'].upper():
            sr = int(d['default_samplerate'])
            print(f'[MICRO] fallback {d["name"]} index={i} sr={sr}')
            return i, sr
    sr = int(sd.query_devices(0)['default_samplerate'])
    print(f'[MICRO] fallback index=0 sr={sr}')
    return 0, sr


def play_audio(pcm_bytes):
    audio_client = hardware.get_audio_client()
    if not pcm_bytes:
        return
    # Un seul pipeline ffmpeg : PCM 24kHz → WAV 16kHz + volume boost
    with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as f:
        tmp_raw = f.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_wav = f.name
    try:
        with open(tmp_raw, 'wb') as f:
            f.write(pcm_bytes)
        ret = subprocess.run(
            ['ffmpeg', '-y',
             '-f', 's16le', '-ar', '24000', '-ac', '1', '-i', tmp_raw,
             '-ar', '16000', '-ac', '1', '-af', f'volume={VOLUME_BOOST}',
             tmp_wav],
            capture_output=True
        )
        if ret.returncode != 0:
            print(f'[AUDIO] ffmpeg erreur : {ret.stderr[-200:]}')
            return
        pcm, sr, ch, ok = read_wav(tmp_wav)
        if ok:
            play_pcm_stream(audio_client, pcm, 'chat')
            time.sleep(len(pcm) / (sr * ch * 2) + 0.3)
        audio_client.PlayStop('chat')
        time.sleep(0.3)
    finally:
        for f in [tmp_raw, tmp_wav]:
            try:
                os.unlink(f)
            except OSError:
                pass
