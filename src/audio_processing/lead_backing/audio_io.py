from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Tuple


def find_ffmpeg_executable() -> str:
    import shutil

    ff = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
    if ff:
        return str(ff)
    try:
        project_root = Path(__file__).resolve().parents[3]
        candidates = [
            project_root / 'tools' / 'ffmpeg' / 'bin' / 'ffmpeg.exe',
            project_root / 'tools' / 'ffmpeg' / 'bin' / 'ffmpeg',
        ]
        for cand in candidates:
            if cand.exists():
                return str(cand)
    except Exception:
        pass
    return ''


def read_wave_pcm(path: str) -> Tuple[object, int]:
    import numpy as np
    import wave

    with wave.open(path, 'rb') as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(n)

    if sw == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f'unsupported WAV bit depth: {sw * 8}')

    if ch > 1:
        arr = arr.reshape(-1, ch)
    else:
        arr = arr.reshape(-1, 1)
    return arr.astype(np.float32), int(sr)


def load_audio(path: str):
    import numpy as np

    try:
        import soundfile as sf

        data, sr = sf.read(path, always_2d=True)
        return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        pass

    try:
        import torchaudio

        wav, sr = torchaudio.load(path)
        arr = wav.numpy()
        if arr.ndim == 1:
            arr = arr[None, :]
        return arr.T.astype(np.float32), int(sr)
    except Exception:
        pass

    try:
        import librosa

        y, sr = librosa.load(path, sr=None, mono=False)
        if y.ndim == 1:
            data = y[:, None]
        else:
            data = y.T
        return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        pass

    try:
        ff = find_ffmpeg_executable()
        if ff:
            tmpdir = Path(tempfile.mkdtemp(prefix='lead_backing_decode_'))
            wav_path = tmpdir / 'decoded.wav'
            try:
                cmd = [ff, '-y', '-i', str(path), '-ac', '2', '-ar', '44100', '-f', 'wav', str(wav_path)]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return read_wave_pcm(str(wav_path))
            finally:
                try:
                    for p in tmpdir.glob('*'):
                        p.unlink(missing_ok=True)
                    tmpdir.rmdir()
                except Exception:
                    pass
    except Exception:
        pass

    return read_wave_pcm(path)


def load_audio_mono(path: str):
    import numpy as np

    data, sr = load_audio(path)
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 2 and arr.shape[1] > 1:
        arr = arr.mean(axis=1)
    else:
        arr = arr.squeeze()
    return np.asarray(arr, dtype=np.float32), int(sr)