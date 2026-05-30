"""
Chest/Falsetto 分类器端到端评估脚本

在 ccmusic-database 的 1,280 个 WAV 文件上运行完整的推理管线
（从 raw audio → mel spectrogram → SqueezeNet → prediction），
计算各维度准确率指标。
"""
import json
import math
import os
import sys
import time
import zipfile
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torchvision import models, transforms

# --- 配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIO_ZIP = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'dataset' / 'data' / 'audio.zip'
CHECKPOINT_PATH = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts_mel_safe_v2' / 'best_squeezenet_binary.pt'
CHECKPOINT_PATH_4CLASS = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts_mel_safe_v2' / 'best_squeezenet_fourclass.pt'
OUTPUT_DIR = Path(__file__).resolve().parent / 'results'
IMAGE_SIZE = 224
BATCH_SIZE = 32
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

FOUR_CLASS_LABELS = ('m_chest', 'f_chest', 'm_falsetto', 'f_falsetto')
FOUR_TO_BINARY = {'m_chest': 'chest', 'f_chest': 'chest', 'm_falsetto': 'falsetto', 'f_falsetto': 'falsetto'}
FOUR_TO_GENDER = {'m_chest': 'male', 'f_chest': 'female', 'm_falsetto': 'male', 'f_falsetto': 'female'}
# 从文件名提取性别简称 (m/f)
def get_gender_short(four_class: str) -> str:
    return four_class.split('_')[0]  # 'm' or 'f'


def resolve_device() -> torch.device:
    force_cpu = str(os.environ.get('MIND_ECHO_FORCE_CPU', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if force_cpu:
        return torch.device('cpu')
    try:
        if torch.cuda.is_available() and int(torch.cuda.device_count()) > 0:
            return torch.device('cuda')
    except Exception:
        pass
    return torch.device('cpu')


def build_transform():
    """与 infer_squeezenet_binary.py 一致 — 输入为 PIL Image"""
    return transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])


def build_model(checkpoint_path: Path, device: torch.device):
    try:
        checkpoint = torch.load(checkpoint_path, map_location=device)
    except RuntimeError as exc:
        if device.type != 'cpu' and 'device_count() is 0' in str(exc):
            checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))
        else:
            raise
    state_dict = checkpoint.get('model_state_dict', checkpoint) if isinstance(checkpoint, dict) else checkpoint
    # Auto-detect num_classes from classifier output layer
    num_classes = 2
    for key, tensor in state_dict.items():
        if 'classifier.1.weight' in key:
            num_classes = int(tensor.shape[0])
            break
    model = models.squeezenet1_1(weights=None)
    model.classifier[1] = torch.nn.Conv2d(512, num_classes, kernel_size=1)
    model.num_classes = num_classes
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model, num_classes


def build_mel_image(signal: np.ndarray, sample_rate: int) -> np.ndarray:
    """使用与训练完全一致的预处理管线：
    librosa mel → power_to_db → plt.imsave(JPG) → PIL读取 → RGB array

    训练时的 mel.zip 图像由 data.py:audio2img 生成，关键步骤：
    1. librosa.feature.melspectrogram
    2. librosa.power_to_db
    3. plt.imsave (应用 viridis colormap + JPG 压缩)
    """
    import io
    import librosa
    from PIL import Image as PILImage
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    mel = librosa.feature.melspectrogram(y=signal.astype(np.float32), sr=sample_rate)
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # 通过 JPG round-trip 模拟训练管线的 JPG 压缩
    buf_jpg = io.BytesIO()
    plt.imsave(buf_jpg, mel_db, format='jpg')
    buf_jpg.seek(0)
    plt.close('all')

    image = PILImage.open(buf_jpg).convert('RGB')
    return image


def parse_label(filename: str) -> Tuple[str, str, str]:
    """从文件名解析标签: audio/0001_m_chest.wav → (m_chest, chest, male)"""
    base = os.path.basename(filename).lower().replace('.wav', '')
    parts = base.split('_')
    # pattern: NNNN_GENDER_METHOD → parts = ['NNNN', 'm', 'chest']
    if len(parts) >= 3:
        gender = parts[1]   # m or f
        method = parts[2]   # chest or falsetto
    elif len(parts) == 2:
        gender = parts[0]
        method = parts[1]
    else:
        return 'unknown', 'unknown', 'unknown'
    four_class = f"{gender}_{method}"
    return four_class, FOUR_TO_BINARY.get(four_class, 'unknown'), FOUR_TO_GENDER.get(four_class, 'unknown')


def load_wav_from_zip(zf: zipfile.ZipFile, entry_name: str, target_sr: int = 22050) -> np.ndarray:
    """从 zip 读取 WAV 并重采样到 target_sr。使用 librosa 以确保与训练时完全一致。"""
    import io
    import librosa
    data = zf.read(entry_name)
    samples, sr = librosa.load(io.BytesIO(data), sr=target_sr, mono=True)
    return np.asarray(samples, dtype=np.float32)


@torch.no_grad()
def predict_batch(model, batch: torch.Tensor, device: torch.device) -> List[Dict[str, float]]:
    probs = []
    for start_idx in range(0, batch.size(0), BATCH_SIZE):
        sub = batch[start_idx:start_idx + BATCH_SIZE].to(device)
        logits = model(sub)
        sub_probs = torch.softmax(logits, dim=1).cpu().numpy().tolist()
        probs.extend(sub_probs)
    return [{'chest_prob': float(p[0]), 'falsetto_prob': float(p[1])} for p in probs]


def apply_context_priors(chest_prob: float, falsetto_prob: float,
                         voice_type: str = 'unspecified') -> Tuple[float, float]:
    """模拟 _apply_voice_type_context_priors 的核心逻辑"""
    is_female = voice_type.lower() in {'soprano', 'mezzo_soprano', 'contralto'}
    cp = chest_prob
    fp = falsetto_prob

    # 声部偏置: 女声增加假声先验
    if is_female:
        cp -= 0.04
        fp += 0.04
    # Clip and renormalize
    cp = max(0.0, min(1.0, cp))
    fp = max(0.0, min(1.0, fp))
    total = cp + fp
    if total > 0:
        cp /= total
        fp /= total
    return cp, fp


def compute_metrics(y_true: List[str], y_pred: List[str], labels: List[str]) -> dict:
    """手动计算 precision, recall, f1"""
    metrics = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        metrics[label] = {'precision': round(precision, 4), 'recall': round(recall, 4),
                          'f1': round(f1, 4), 'support': tp + fn}
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(len(y_true), 1)
    metrics['accuracy'] = round(acc, 4)
    return metrics


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    device = resolve_device()
    # 优先使用 4-class checkpoint，否则回退 binary
    if CHECKPOINT_PATH_4CLASS.exists():
        effective_checkpoint = CHECKPOINT_PATH_4CLASS
    elif CHECKPOINT_PATH.exists():
        effective_checkpoint = CHECKPOINT_PATH
    else:
        print(f"[eval] ERROR: No checkpoint found")
        sys.exit(1)
    print(f"[eval] Device: {device}")
    print(f"[eval] Model: {effective_checkpoint}")

    if not AUDIO_ZIP.exists():
        print(f"[eval] ERROR: Audio zip not found at {AUDIO_ZIP}")
        sys.exit(1)

    # 加载模型
    model, num_classes = build_model(effective_checkpoint, device)
    use_four_class = num_classes == 4
    print(f"[eval] num_classes={num_classes}, use_four_class={use_four_class}")
    transform = build_transform()

    # 收集 WAV 条目
    with zipfile.ZipFile(AUDIO_ZIP, 'r') as zf:
        wav_entries = [n for n in zf.namelist() if n.lower().endswith('.wav')]
    print(f"[eval] Found {len(wav_entries)} WAV files in audio.zip")

    # 按 4 类标签分组
    groups = defaultdict(list)
    for entry in wav_entries:
        four_class, _, _ = parse_label(entry)
        groups[four_class].append(entry)
    print(f"[eval] Class distribution: { {k: len(v) for k, v in sorted(groups.items())} }")

    # 逐条推理
    all_results = []
    start_time = time.time()

    with zipfile.ZipFile(AUDIO_ZIP, 'r') as zf:
        for i, entry in enumerate(wav_entries):
            four_class, binary_label, gender = parse_label(entry)
            try:
                audio = load_wav_from_zip(zf, entry, target_sr=22050)
                mel_rgb = build_mel_image(audio, 22050)
                tensor = transform(mel_rgb).unsqueeze(0).to(device)
                with torch.no_grad():
                    logits = model(tensor)
                    probs = torch.softmax(logits, dim=1).squeeze(0).detach().cpu().numpy()
                if use_four_class:
                    m_chest_prob = float(probs[0])
                    f_chest_prob = float(probs[1])
                    m_falsetto_prob = float(probs[2])
                    f_falsetto_prob = float(probs[3])
                    chest_prob = m_chest_prob + f_chest_prob
                    falsetto_prob = m_falsetto_prob + f_falsetto_prob
                    auto_female = (f_chest_prob + f_falsetto_prob) > (m_chest_prob + m_falsetto_prob)
                    pred_4class_direct_idx = int(np.argmax(probs))
                    pred_4class_direct = FOUR_CLASS_LABELS[pred_4class_direct_idx]
                    auto_gender = 'female' if auto_female else 'male'
                else:
                    chest_prob = float(probs[0])
                    falsetto_prob = float(probs[1])
                    m_chest_prob = 0.0; f_chest_prob = 0.0
                    m_falsetto_prob = 0.0; f_falsetto_prob = 0.0
                    pred_4class_direct = ''
                    auto_gender = ''
            except Exception as e:
                print(f"  [WARN] Failed on {entry}: {e}")
                continue

            pred_binary = 'chest' if chest_prob >= falsetto_prob else 'falsetto'
            cp_adj, fp_adj = apply_context_priors(chest_prob, falsetto_prob, voice_type='unspecified')
            pred_with_priors = 'chest' if cp_adj >= fp_adj else 'falsetto'

            # 如果是女声，用女声声部测试
            if gender == 'female':
                cp_female, fp_female = apply_context_priors(chest_prob, falsetto_prob, voice_type='soprano')
                pred_female_priors = 'chest' if cp_female >= fp_female else 'falsetto'
            else:
                cp_female, fp_female = cp_adj, fp_adj
                pred_female_priors = pred_with_priors

            gender_short = get_gender_short(four_class)
            pred_4class = f"{gender_short}_{pred_binary}"
            pred_4class_priors = f"{gender_short}_{pred_with_priors}"

            all_results.append({
                'entry': entry,
                'four_class': four_class,
                'binary_label': binary_label,
                'gender': gender,
                'gender_short': gender_short,
                'chest_prob': chest_prob,
                'falsetto_prob': falsetto_prob,
                'pred_binary': pred_binary,
                'pred_4class': pred_4class,
                'pred_with_priors': pred_with_priors,
                'pred_4class_priors': pred_4class_priors,
                'm_chest_prob': m_chest_prob,
                'f_chest_prob': f_chest_prob,
                'm_falsetto_prob': m_falsetto_prob,
                'f_falsetto_prob': f_falsetto_prob,
                'pred_4class_direct': pred_4class_direct,
                'auto_gender': auto_gender,
            })

            if (i + 1) % 200 == 0:
                elapsed = time.time() - start_time
                print(f"  Progress: {i + 1}/{len(wav_entries)} ({elapsed:.1f}s)")

    total_time = time.time() - start_time
    print(f"[eval] Inference completed in {total_time:.1f}s ({len(all_results) / total_time:.1f} samples/s)")

    # --- 评估 ---
    y_true_4class = [r['four_class'] for r in all_results]
    y_pred_4class_raw = [r['pred_4class'] for r in all_results]
    y_pred_4class_priors = [r['pred_4class_priors'] for r in all_results]

    y_true_binary = [r['binary_label'] for r in all_results]
    y_pred_binary_raw = [r['pred_binary'] for r in all_results]
    y_pred_binary_priors = [r['pred_with_priors'] for r in all_results]

    # 混淆矩阵 (4-class)
    cm_4class = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true_4class, y_pred_4class_raw):
        cm_4class[t][p] += 1

    results = {
        'total_samples': len(all_results),
        'inference_time_s': round(total_time, 1),
        'samples_per_second': round(len(all_results) / total_time, 1),
        'device': str(device),
        'checkpoint': str(effective_checkpoint),
        'num_classes': num_classes,
        'use_four_class': use_four_class,

        # 4-class metrics (raw model)
        'four_class_raw': compute_metrics(y_true_4class, y_pred_4class_raw, list(FOUR_CLASS_LABELS)),
        # 4-class metrics (with priors)
        'four_class_with_priors': compute_metrics(y_true_4class, y_pred_4class_priors, list(FOUR_CLASS_LABELS)),
        # 4-class direct (only meaningful with 4-class model)
        'four_class_direct': compute_metrics(
            [r['four_class'] for r in all_results],
            [r['pred_4class_direct'] for r in all_results],
            list(FOUR_CLASS_LABELS)
        ) if use_four_class else {},
        # Binary metrics (raw model)
        'binary_raw': compute_metrics(y_true_binary, y_pred_binary_raw, ['chest', 'falsetto']),
        # Binary metrics (with priors)
        'binary_with_priors': compute_metrics(y_true_binary, y_pred_binary_priors, ['chest', 'falsetto']),

        # Per-gender binary metrics
        'male_binary_raw': compute_metrics(
            [r['binary_label'] for r in all_results if r['gender'] == 'male'],
            [r['pred_binary'] for r in all_results if r['gender'] == 'male'],
            ['chest', 'falsetto']
        ),
        'female_binary_raw': compute_metrics(
            [r['binary_label'] for r in all_results if r['gender'] == 'female'],
            [r['pred_binary'] for r in all_results if r['gender'] == 'female'],
            ['chest', 'falsetto']
        ),

        # 混淆矩阵
        'confusion_matrix_4class': {k: dict(v) for k, v in cm_4class.items()},

        # 错误案例分析
        'errors': [
            {
                'entry': r['entry'],
                'true': r['four_class'],
                'pred': r['pred_4class'],
                'chest_prob': round(r['chest_prob'], 4),
                'falsetto_prob': round(r['falsetto_prob'], 4),
            }
            for r in all_results if r['four_class'] != r['pred_4class']
        ],
    }

    # 输出结果
    output_path = OUTPUT_DIR / 'chest_falsetto_eval.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print("\n" + "=" * 70)
    print("CHEST/FALSETTO EVALUATION RESULTS")
    print("=" * 70)

    print(f"\n  Total samples: {results['total_samples']}")
    print(f"  Device: {results['device']}")
    print(f"  Inference time: {results['inference_time_s']}s ({results['samples_per_second']} samples/s)")

    print(f"\n  Binary Accuracy (raw model):    {results['binary_raw']['accuracy']:.2%}")
    print(f"  Binary Accuracy (with priors):  {results['binary_with_priors']['accuracy']:.2%}")

    if use_four_class:
        print(f"\n  --- 4-Class Direct Accuracy ---")
        fd = results.get('four_class_direct', {})
        print(f"  Direct model output:  {fd.get('accuracy', 0):.2%}")
        if fd:
            print(f"  Per-class (direct):")
            for label in FOUR_CLASS_LABELS:
                m = fd.get(label, {})
                if m:
                    print(f"    {label:16s}  P:{m.get('precision', 0):.3f}  R:{m.get('recall', 0):.3f}  F1:{m.get('f1', 0):.3f}  N:{m.get('support', 0)}")

    print(f"\n  --- Per-Gender Binary Accuracy ---")
    print(f"  Male (raw):     {results['male_binary_raw']['accuracy']:.2%}")
    print(f"  Female (raw):   {results['female_binary_raw']['accuracy']:.2%}")

    print(f"\n  --- 4-Class Accuracy ---")
    print(f"  Raw model:      {results['four_class_raw']['accuracy']:.2%}")
    print(f"  With priors:    {results['four_class_with_priors']['accuracy']:.2%}")

    print(f"\n  --- 4-Class Per-Class Metrics (Raw) ---")
    for label in FOUR_CLASS_LABELS:
        m = results['four_class_raw'].get(label, {})
        if m:
            print(f"  {label:16s}  P:{m.get('precision', 0):.3f}  R:{m.get('recall', 0):.3f}  F1:{m.get('f1', 0):.3f}  N:{m.get('support', 0)}")

    print(f"\n  --- Binary Per-Class Metrics (Raw) ---")
    for label in ['chest', 'falsetto']:
        m = results['binary_raw'].get(label, {})
        if m:
            print(f"  {label:10s}  P:{m.get('precision', 0):.3f}  R:{m.get('recall', 0):.3f}  F1:{m.get('f1', 0):.3f}  N:{m.get('support', 0)}")

    print(f"\n  --- Confusion Matrix (4-Class) ---")
    header = f"  {'':14s}" + "".join(f"{l:>10s}" for l in FOUR_CLASS_LABELS)
    print(header)
    for tl in FOUR_CLASS_LABELS:
        row = f"  {tl:14s}"
        for pl in FOUR_CLASS_LABELS:
            row += f"{cm_4class[tl][pl]:>10d}"
        print(row)

    error_count = len(results['errors'])
    print(f"\n  Total errors: {error_count} ({error_count / max(len(all_results), 1):.2%})")

    print(f"\n  Full results saved to: {output_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
