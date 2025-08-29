import math
import wave
import struct
from pathlib import Path

def gen_sine_mix(path: Path, sr: int = 44100, seconds: float = 2.0):
    n = int(sr * seconds)
    amp = 0.3
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sr)
        for i in range(n):
            t = i / sr
            # L: 440Hz + 880Hz, R: 220Hz
            l = amp * (math.sin(2*math.pi*440*t) + 0.5*math.sin(2*math.pi*880*t))
            r = amp * (math.sin(2*math.pi*220*t))
            # clamp and convert to int16
            li = max(-1.0, min(1.0, l))
            ri = max(-1.0, min(1.0, r))
            wf.writeframes(struct.pack('<hh', int(li*32767), int(ri*32767)))

if __name__ == '__main__':
    out = Path(__file__).with_name('test_tone.wav')
    gen_sine_mix(out)
    print(str(out))
