import numpy as np
from time import time

try:
    from src.audio_processing.pitch_service import PitchDetectionService
except Exception as e:
    print(f"ImportError: {e}")
    raise


def gen_sine(f, sr=44100, dur=1.0):
    t = np.arange(int(sr*dur)) / sr
    return 0.1*np.sin(2*np.pi*f*t)


def run_once(f, sr=44100):
    service = PitchDetectionService(sample_rate=sr, min_frequency=80, max_frequency=1200, yin_threshold=0.15, mode_name='HIGH')
    # frame ~ 2.5 cycles @ min_f
    min_f = 80.0
    frame = int(sr * (2.5/min_f))
    hop = max(192, frame//7)
    x = gen_sine(f, sr, dur=0.8)
    n = len(x)
    t0 = time()
    count = 0
    f_hits = []
    for i in range(0, n-frame, hop):
        f0, c = service.detect(x[i:i+frame])
        count += 1
        f_hits.append(f0)
    el = time() - t0
    fps = count/el if el>0 else 0
    print(f"freq={f}Hz frames={count} time={el:.3f}s FPS~{fps:.1f} median_f0={np.median([v for v in f_hits if v>0]) if any(v>0 for v in f_hits) else 0:.1f}")


if __name__ == '__main__':
    for f in [110, 220, 440, 523.25, 659.26]:
        run_once(f)
    # quiet high voice amplitude
    sr=44100
    t = np.arange(int(sr*0.6))/sr
    x = 0.01*np.sin(2*np.pi*880*t)
    service = PitchDetectionService(sample_rate=sr, min_frequency=80, max_frequency=1200, yin_threshold=0.15, mode_name='BALANCED')
    frame = int(sr*(2.5/80.0))
    hop = max(192, frame//7)
    hits = []
    for i in range(0, len(x)-frame, hop):
        f0, _ = service.detect(x[i:i+frame])
        hits.append(f0)
    med = np.median([v for v in hits if v>0]) if any(v>0 for v in hits) else 0
    print(f"quiet-880Hz median_f0={med:.1f}")
