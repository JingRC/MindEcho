---
name: audio-ml-eval
description: >
  MindEcho 音频处理与 ML 模型评估：跑音高检测对比测试、ML 模型推理验证、
  可视化输出检查、降噪效果对比。
  Triggers: "测试音高检测", "评估模型", "ML 验证", "可视化对比", "降噪测试", "audio test"
user-invocable: true
argument-hint: "[pitch|ml|noise|vis|all] [--model chest_falsetto|gtsinger] [--audio <file>]"
allowed-tools: Bash(python *), Read, Glob, Write
---

# Audio & ML Evaluation for MindEcho

## 音高检测评估

对比 YIN / 自相关 / FFT 三种算法的准确性：

```bash
# 使用测试音频跑三种算法对比
python -c "
from src.analysis.pitch_detection import PitchDetector
import numpy as np
import scipy.io.wavfile as wav

# 加载测试音频
sr, data = wav.read('test_recordings/test_tone_440hz.wav')
if data.ndim > 1:
    data = data.mean(axis=1)

detector = PitchDetector(sample_rate=sr)
# YIN
yin_result = detector.detect_pitch_yin(data[:4096], sr)
# Autocorrelation
ac_result = detector.detect_pitch_autocorrelation(data[:4096], sr)
# FFT
fft_result = detector.detect_pitch_fft(data[:4096], sr)

print(f'YIN: {yin_result:.1f}Hz')
print(f'Autocorr: {ac_result:.1f}Hz')
print(f'FFT: {fft_result:.1f}Hz')
"
```

## ML 模型评估

```bash
# Chest/Falsetto 模型在测试集上评估
python ml_dl_models/chest_falsetto/evaluation/evaluate.py 2>/dev/null || \
  echo "评估脚本路径可能不同，请检查 ml_dl_models/chest_falsetto/evaluation/"

# GTSinger Multi-tech 模型评估
python ml_dl_models/gtsinger_multitech/evaluation/evaluate.py 2>/dev/null || \
  echo "评估脚本路径可能不同，请检查 ml_dl_models/gtsinger_multitech/evaluation/"

# 列出所有可用的评估脚本
find ml_dl_models/ -name "evaluate*.py" -o -name "eval*.py"
```

## 降噪效果对比

```bash
# 运行降噪前后对比
python -c "
from src.audio_processing.noise_reduction import NoiseReductionProcessor
import numpy as np
import scipy.io.wavfile as wav

sr, data = wav.read('test_recordings/noisy_sample.wav')
if data.ndim > 1:
    data = data.mean(axis=1)

processor = NoiseReductionProcessor(sample_rate=sr)
cleaned = processor.process(data)

# 保存对比
wav.write('test_recordings/noisy_sample_cleaned.wav', sr, cleaned.astype(np.int16))
print(f'SNR improvement: {processor.get_snr_improvement():.1f}dB')
"
```

## 可视化输出验证

```bash
# 测试可视化渲染（无头模式）
python -c "
import matplotlib
matplotlib.use('Agg')  # 无头模式
from src.analysis.staff_visualizer import StaffRenderer
# 渲染测试
renderer = StaffRenderer()
renderer.test_render('test_output/staff_test.png')
print('Staff notation render saved')
"
```
