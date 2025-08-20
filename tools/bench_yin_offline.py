# -*- coding: utf-8 -*-
"""
离线基准：测 PitchDetectionService 的YIN热路径帧率与准确性。
运行方式：python tools/bench_yin_offline.py
"""
import time
import numpy as np
import sys
import os
from types import SimpleNamespace

# 将 src 加入路径
ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))

try:
    from src.audio_processing.pitch_service import PitchDetectionService
except Exception as e:
    print("导入失败: ", e)
    sys.exit(1)


def run_once(sample_rate=48000, freq=440.0, dur_s=1.0, win=2048, hop=256, mode='BALANCED'):
    cfg = SimpleNamespace(
        sample_rate=sample_rate,
        min_frequency=80.0,
        max_frequency=1047.0,
        yin_threshold=0.20,
        mode_name=mode,
    )
    svc = PitchDetectionService(cfg)

    t = np.arange(int(sample_rate * dur_s)) / sample_rate
    x = np.sin(2*np.pi*freq*t).astype(np.float64)

    cnt = 0
    hits = 0
    f_sum = 0.0
    t0 = time.time()
    for i in range(0, len(x)-win, hop):
        f0, conf = svc.detect(x[i:i+win])
        cnt += 1
        if f0 > 0:
            hits += 1
            f_sum += f0
    t1 = time.time()

    fps = cnt / max(1e-6, (t1 - t0))
    f_avg = f_sum / max(1, hits)
    return {
        'frames': cnt,
        'fps': fps,
        'hits': hits,
        'avg_freq': f_avg,
        'mode': mode,
        'win': win,
        'hop': hop,
    }


def main():
    print("🎯 离线YIN基准 (PitchDetectionService)")
    for mode in ['QUIET', 'BALANCED', 'HIGH_PERFORMANCE']:
        res = run_once(mode=mode)
        print(f"- 模式={mode:16s} | 帧数={res['frames']:4d} | FPS={res['fps']:.1f} | 命中={res['hits']:3d} | 平均频率≈{res['avg_freq']:.1f}Hz | win={res['win']} hop={res['hop']}")


if __name__ == '__main__':
    main()
