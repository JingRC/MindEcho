"""
Mix Voice / Multi-Tech 评估脚本

在 GTSinger Multi-Tech 数据集上评估：
1. Mix binary 检测 (mix vs non-mix)
2. Falsetto 检测 (使用 chest/falsetto 模型)
3. 按 group (Control/Falsetto/Breathy/Mix) 和 variant 细粒度分析
"""
import csv
import io
import json
import math
import os
import sys
import time
import wave
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image as PILImage
from torchvision import models, transforms

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GTSINGER_ROOT = PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'raw'
GTSINGER_CURATED = PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated'

CHEST_FALSETTO_CKPTS = [
    PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts_mel_safe_v2' / 'best_squeezenet_fourclass.pt',
    PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts_mel_safe_v2' / 'best_squeezenet_binary.pt',
]
MIX_BINARY_CKPTS = [
    PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_latefusion_v6_song_level' / 'best_mix_binary_latefusion.pt',
    PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_latefusion_v2_core_plus_english' / 'best_mix_binary_latefusion.pt',
    PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_latefusion_v1' / 'best_mix_binary_latefusion.pt',
    PROJECT_ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_ce_v2_calibrated_gpu' / 'best_mix_binary_squeezenet.pt',
]

OUTPUT_DIR = Path(__file__).resolve().parent / 'results'

TARGET_SR = 22050
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


# ── Late Fusion model classes ─────────────────────────────────────────

class SpectralEncoder(nn.Module):
    def __init__(self, input_dim=3, hidden_dim=16):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.ReLU(inplace=True))

    def forward(self, x):
        return self.net(x)


class FusionHead(nn.Module):
    def __init__(self, backbone_dim, spectral_dim=16, dropout=0.3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(backbone_dim + spectral_dim, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(128, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 2),
        )

    def forward(self, backbone_emb, spectral_emb):
        return self.net(torch.cat([backbone_emb, spectral_emb], dim=1))


class SqueezeNetLateFusion(nn.Module):
    def __init__(self, backbone_name='squeezenet11', spectral_dim=16, dropout=0.3):
        super().__init__()
        self.backbone = models.squeezenet1_1(weights=None)
        self.backbone.classifier[1] = nn.Identity()
        self._backbone_dim = 512
        self.num_classes = 2
        self.spectral_encoder = SpectralEncoder(input_dim=3, hidden_dim=spectral_dim)
        self.fusion_head = FusionHead(backbone_dim=self._backbone_dim, spectral_dim=spectral_dim, dropout=dropout)
        self._is_latefusion = True

    def forward_features(self, x):
        features = self.backbone.features(x)
        return F.adaptive_avg_pool2d(features, (1, 1)).flatten(1)

    def forward(self, mel_images, spectral_features):
        backbone_emb = self.forward_features(mel_images)
        spectral_emb = self.spectral_encoder(spectral_features)
        return self.fusion_head(backbone_emb, spectral_emb)


def compute_spectral_features(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Compute [spectral_tilt, hm_over_hh, mid_high_ratio] from raw audio."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    n = len(x)
    if n < 64:
        return np.array([0.0, 1.0, 1.0], dtype=np.float32)
    sr = float(sample_rate)
    spec = np.fft.rfft(x)
    mag = np.abs(spec) + 1e-12
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    valid = freqs > 0
    if np.sum(valid) > 4:
        mag_db = 20.0 * np.log10(mag[valid])
        log2_f = np.log2(freqs[valid])
        slope, _ = np.polyfit(log2_f, mag_db, 1)
        spectral_tilt = float(slope)
    else:
        spectral_tilt = 0.0

    mid_mask = (freqs >= 300.0) & (freqs <= 3000.0)
    high_mask = freqs > 3000.0
    mid_energy = float(np.mean(mag[mid_mask])) if np.any(mid_mask) else 0.0
    high_energy = float(np.mean(mag[high_mask])) if np.any(high_mask) else 1e-12
    mid_high_ratio = (mid_energy + 1e-9) / (high_energy + 1e-9)

    hm_mask = (freqs >= 2000.0) & (freqs <= 6000.0)
    hh_mask = freqs > 6000.0
    e_hm = float(np.mean(mag[hm_mask])) if np.any(hm_mask) else 1e-12
    e_hh = float(np.mean(mag[hh_mask])) if np.any(hh_mask) else 1e-12
    hm_over_hh = (e_hm + 1e-9) / (e_hh + 1e-9)

    return np.array([spectral_tilt, hm_over_hh, mid_high_ratio], dtype=np.float32)


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


def load_manifest(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_wav(path: Path, target_sr: int = TARGET_SR) -> np.ndarray:
    with wave.open(str(path), 'rb') as wf:
        sr = wf.getframerate()
        width = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if width == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    elif width == 2:
        audio = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    elif width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = (packed[:, 0].astype(np.int32) | (packed[:, 1].astype(np.int32) << 8) | (packed[:, 2].astype(np.int32) << 16))
        sign_mask = 1 << 23
        values = (values ^ sign_mask) - sign_mask
        audio = values.astype(np.float32) / float(sign_mask)
    elif width == 4:
        audio = np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f'Unknown sample width: {width}')
    if sr != target_sr:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    return np.asarray(audio, dtype=np.float32)


# --- 两种不同的 mel 预处理 ---

def build_cf_mel_image(signal: np.ndarray, sample_rate: int) -> PILImage.Image:
    """Chest/Falsetto 模型: JPG colormap round-trip 管线 (与训练完全一致)"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import librosa
    mel = librosa.feature.melspectrogram(y=signal.astype(np.float32), sr=sample_rate)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    buf = io.BytesIO()
    plt.imsave(buf, mel_db, format='jpg')
    buf.seek(0)
    plt.close('all')
    return PILImage.open(buf).convert('RGB')


def build_mix_mel_tensor(signal: np.ndarray, sample_rate: int, image_size: int = 224) -> torch.Tensor:
    """Mix Binary model: float32 mel tensor matching training pipeline exactly."""
    n_fft = 1024
    hop_length = 256
    n_mels = 128

    waveform = torch.as_tensor(np.asarray(signal, dtype=np.float32).reshape(-1))
    if waveform.numel() < n_fft:
        waveform = torch.nn.functional.pad(waveform, (0, n_fft - waveform.numel()))
    window = torch.hann_window(n_fft)
    stft = torch.stft(waveform, n_fft=n_fft, hop_length=hop_length, win_length=n_fft,
                      window=window, center=True, return_complex=True)
    power = stft.abs().pow(2.0)
    mel_filter = build_mel_filterbank(sample_rate=sample_rate, n_fft=n_fft, n_mels=n_mels)
    mel_spec = torch.matmul(mel_filter, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if mel_spec.numel() else 0.0
    if peak > 0.0:
        mel_spec = mel_spec / peak
    rgb = torch.stack((mel_spec, mel_spec, mel_spec), dim=0).to(dtype=torch.float32)
    rgb = F.interpolate(rgb.unsqueeze(0), size=(image_size, image_size), mode='bilinear', align_corners=False).squeeze(0)
    return rgb


def build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 128):
    upper_hz = sample_rate * 0.5
    mel_low = 2595.0 * math.log10(1.0 + 30.0 / 700.0)
    mel_high = 2595.0 * math.log10(1.0 + upper_hz / 700.0)
    mel_points = np.linspace(mel_low, mel_high, n_mels + 2, dtype=np.float32)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bins = np.floor((n_fft + 1) * hz_points / float(sample_rate)).astype(np.int32)
    bins = np.clip(bins, 0, n_fft // 2)
    filterbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for mel_idx in range(1, n_mels + 1):
        left, center, right = int(bins[mel_idx - 1]), int(bins[mel_idx]), int(bins[mel_idx + 1])
        if center <= left: center = min(left + 1, n_fft // 2)
        if right <= center: right = min(center + 1, n_fft // 2)
        if center > left:
            filterbank[mel_idx - 1, left:center] = np.linspace(0.0, 1.0, center - left, endpoint=False, dtype=np.float32)
        if right > center:
            filterbank[mel_idx - 1, center:right] = np.linspace(1.0, 0.0, right - center, endpoint=False, dtype=np.float32)
    return torch.from_numpy(filterbank)


# --- 模型加载 ---
def build_cf_model(ckpt: Path, device: torch.device):
    checkpoint = torch.load(ckpt, map_location=device)
    state_dict = checkpoint.get('model_state_dict', checkpoint)
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
    return model


def build_mix_model(ckpt: Path, device: torch.device):
    checkpoint = torch.load(ckpt, map_location=device, weights_only=False)
    state_dict = checkpoint.get('model_state_dict', checkpoint)

    # Auto-detect model type from checkpoint metadata or state_dict keys
    model_type = str(checkpoint.get('model_type', '') or '')
    is_latefusion = model_type == 'squeezenet_latefusion' or any('spectral_encoder' in k or 'fusion_head' in k for k in state_dict.keys())

    if is_latefusion:
        spectral_dim = int(checkpoint.get('spectral_dim', 16) or 16)
        fusion_dropout = float(checkpoint.get('fusion_dropout', 0.3) or 0.3)
        model = SqueezeNetLateFusion(spectral_dim=spectral_dim, dropout=fusion_dropout).to(device)
        model.load_state_dict(state_dict)
        model.eval()
        return model

    # Plain SqueezeNet fallback
    model = models.squeezenet1_1(weights=None)
    model.classifier[1] = torch.nn.Conv2d(512, 2, kernel_size=1)
    model.num_classes = 2
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


# --- Transforms ---
def build_cf_transform():
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])


def build_mix_transform():
    """Normalization only — mel tensors are already resized via bilinear interpolation."""
    return transforms.Normalize(mean=MEAN, std=STD)


# --- 评估工具 ---
def compute_metrics(y_true: List[int], y_pred: List[int], label_names: List[str]) -> dict:
    metrics = {}
    for i, name in enumerate(label_names):
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == i and p == i)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != i and p == i)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == i and p != i)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        metrics[name] = {'precision': round(precision, 4), 'recall': round(recall, 4),
                         'f1': round(f1, 4), 'support': tp + fn}
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(len(y_true), 1)
    metrics['accuracy'] = round(acc, 4)
    return metrics


def evaluate_manifest(manifest: List[dict], cf_model, mix_model,
                      cf_transform, mix_transform, device,
                      manifest_name: str = 'unknown') -> dict:
    results = []
    missing_count = 0
    error_count = 0
    is_latefusion = bool(getattr(mix_model, '_is_latefusion', False))

    for i, row in enumerate(manifest):
        wav_path = Path(row['wav_path'])
        if not wav_path.exists():
            missing_count += 1
            continue

        try:
            audio = load_wav(wav_path)
        except Exception:
            error_count += 1
            continue

        # 截取中间 2.4s
        target_samples = int(2.4 * TARGET_SR)
        if len(audio) < target_samples:
            audio = np.pad(audio, (0, target_samples - len(audio)))
        elif len(audio) > target_samples:
            start = (len(audio) - target_samples) // 2
            audio = audio[start:start + target_samples]

        try:
            # Chest/Falsetto: colormap preprocessing
            cf_img = build_cf_mel_image(audio, TARGET_SR)
            cf_tensor = cf_transform(cf_img).unsqueeze(0).to(device)

            # Mix: float32 mel tensor (matches training pipeline exactly)
            mix_tensor = build_mix_mel_tensor(audio, TARGET_SR)
            mix_tensor = mix_transform(mix_tensor).unsqueeze(0).to(device)

            # Spectral features for late fusion models
            if is_latefusion:
                spectral = compute_spectral_features(audio, TARGET_SR)
                spectral_tensor = torch.from_numpy(spectral).unsqueeze(0).to(device)

            with torch.no_grad():
                cf_logits = cf_model(cf_tensor)
                cf_probs = torch.softmax(cf_logits, dim=1).squeeze(0).detach().cpu().numpy()
                cf_num_classes = int(getattr(cf_model, 'num_classes', 2) or 2)
                if cf_num_classes >= 4:
                    # 4-class: collapse to binary [chest=m_chest+f_chest, falsetto=m_falsetto+f_falsetto]
                    chest_prob = float(cf_probs[0] + cf_probs[1])
                    falsetto_prob = float(cf_probs[2] + cf_probs[3])
                else:
                    chest_prob = float(cf_probs[0])
                    falsetto_prob = float(cf_probs[1])

                if is_latefusion:
                    mix_logits = mix_model(mix_tensor, spectral_tensor)
                else:
                    mix_logits = mix_model(mix_tensor)
                mix_probs = torch.softmax(mix_logits, dim=1).squeeze(0).detach().cpu().numpy()
                non_mix_prob = float(mix_probs[0])
                mix_prob = float(mix_probs[1])
        except Exception as e:
            error_count += 1
            continue

        results.append({
            'item_name': row.get('item_name', ''),
            'singer': row.get('singer', ''),
            'song_name': row.get('song_name', ''),
            'group_name': row.get('group_name', ''),
            'mix_gt': int(float(row.get('mix', 0) or 0)),
            'falsetto_gt': int(float(row.get('falsetto', 0) or 0)),
            'breathy_gt': int(float(row.get('breathy', 0) or 0)),
            'vibrato_gt': int(float(row.get('vibrato', 0) or 0)),
            'glissando_gt': int(float(row.get('glissando', 0) or 0)),
            'pharyngeal_gt': int(float(row.get('pharyngeal', 0) or 0)),
            'any_tech': int(float(row.get('any_tech', 0) or 0)),
            'mix_variant': row.get('mix_variant', ''),
            'chest_prob': chest_prob,
            'falsetto_prob': falsetto_prob,
            'mix_prob': mix_prob,
            'non_mix_prob': non_mix_prob,
        })

        if (i + 1) % 500 == 0:
            print(f"  [{manifest_name}] Progress: {i + 1}/{len(manifest)}")

    print(f"  [{manifest_name}] Loaded: {len(results)}, missing: {missing_count}, errors: {error_count}")

    if not results:
        return {'error': 'no valid samples', 'missing': missing_count, 'errors': error_count}

    # Mix binary metrics
    mix_y_true = [r['mix_gt'] for r in results]
    mix_y_pred = [1 if r['mix_prob'] >= 0.5 else 0 for r in results]
    mix_metrics = compute_metrics(mix_y_true, mix_y_pred, ['non_mix', 'mix'])

    # Falsetto binary metrics
    fal_y_true = [r['falsetto_gt'] for r in results]
    fal_y_pred = [1 if r['falsetto_prob'] >= 0.5 else 0 for r in results]
    fal_metrics = compute_metrics(fal_y_true, fal_y_pred, ['non_falsetto', 'falsetto'])

    # Per-group breakdown
    group_metrics = {}
    for group_name in sorted(set(r['group_name'] for r in results)):
        grp = [r for r in results if r['group_name'] == group_name]
        if len(grp) < 5: continue
        grp_mix_y = [r['mix_gt'] for r in grp]
        grp_mix_p = [1 if r['mix_prob'] >= 0.5 else 0 for r in grp]
        grp_fal_y = [r['falsetto_gt'] for r in grp]
        grp_fal_p = [1 if r['falsetto_prob'] >= 0.5 else 0 for r in grp]
        group_metrics[group_name] = {
            'count': len(grp),
            'mix': compute_metrics(grp_mix_y, grp_mix_p, ['non_mix', 'mix']),
            'falsetto': compute_metrics(grp_fal_y, grp_fal_p, ['non_falsetto', 'falsetto']),
        }

    # Mix variant recall
    variant_metrics = {}
    for variant in sorted(set(r['mix_variant'] for r in results if r['mix_gt'] == 1)):
        var = [r for r in results if r['mix_variant'] == variant and r['mix_gt'] == 1]
        if len(var) < 3: continue
        var_p = [1 if r['mix_prob'] >= 0.5 else 0 for r in var]
        recall = sum(var_p) / max(len(var), 1)
        avg_prob = np.mean([r['mix_prob'] for r in var])
        variant_metrics[variant] = {'count': len(var), 'recall': round(recall, 4), 'avg_mix_prob': round(float(avg_prob), 4)}

    mix_pos = [r for r in results if r['mix_gt'] == 1]
    mix_neg = [r for r in results if r['mix_gt'] == 0]
    fal_pos = [r for r in results if r['falsetto_gt'] == 1]
    fal_neg = [r for r in results if r['falsetto_gt'] == 0]

    return {
        'manifest_name': manifest_name,
        'total': len(results),
        'missing': missing_count,
        'errors': error_count,
        'mix_binary': mix_metrics,
        'falsetto_binary': fal_metrics,
        'group_breakdown': group_metrics,
        'variant_breakdown': variant_metrics,
        'avg_mix_prob_mix_samples': round(float(np.mean([r['mix_prob'] for r in mix_pos])), 4) if mix_pos else 0,
        'avg_mix_prob_nonmix_samples': round(float(np.mean([r['mix_prob'] for r in mix_neg])), 4) if mix_neg else 0,
        'avg_falsetto_prob_falsetto_samples': round(float(np.mean([r['falsetto_prob'] for r in fal_pos])), 4) if fal_pos else 0,
        'avg_falsetto_prob_nonfalsetto_samples': round(float(np.mean([r['falsetto_prob'] for r in fal_neg])), 4) if fal_neg else 0,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    device = resolve_device()
    print(f"[eval] Device: {device}")

    cf_ckpt = None
    for candidate in CHEST_FALSETTO_CKPTS:
        if candidate.exists():
            cf_ckpt = candidate
            break
    if cf_ckpt is None:
        print(f"[eval] ERROR: No chest/falsetto checkpoint found. Tried: {[str(c) for c in CHEST_FALSETTO_CKPTS]}")
        sys.exit(1)

    # Find first available mix checkpoint
    mix_ckpt = None
    for candidate in MIX_BINARY_CKPTS:
        if candidate.exists():
            mix_ckpt = candidate
            break
    if mix_ckpt is None:
        print(f"[eval] ERROR: No mix binary checkpoint found. Tried: {[str(c) for c in MIX_BINARY_CKPTS]}")
        sys.exit(1)

    print(f"[eval] Loading models...")
    print(f"[eval] CF checkpoint: {cf_ckpt}")
    print(f"[eval] Mix checkpoint: {mix_ckpt}")
    cf_model = build_cf_model(cf_ckpt, device)
    mix_model = build_mix_model(mix_ckpt, device)
    model_type = 'latefusion' if getattr(mix_model, '_is_latefusion', False) else 'plain_squeezenet'
    print(f"[eval] Mix model type: {model_type}")
    cf_transform = build_cf_transform()
    mix_transform = build_mix_transform()

    manifest_candidates = [
        ('mix_binary_core', 'core'),
        ('mix_binary_controlhard_v1', 'controlhard'),
        ('mix_binary_confusable_cluster_v1', 'confusable'),
        ('mix_binary_controlstrata_v1', 'controlstrata'),
        ('mix_binary_english_singer_holdout_v1', 'english_holdout'),
        ('mix_binary_core_plus_english_singer_holdout_v1', 'core_plus_english'),
    ]

    all_results = {}
    for manifest_dir, tag in manifest_candidates:
        test_csv = GTSINGER_CURATED / manifest_dir / 'test_manifest.csv'
        if not test_csv.exists():
            print(f"  [SKIP] {manifest_dir}/test_manifest.csv not found")
            continue
        print(f"\n[eval] Evaluating: {manifest_dir}")
        manifest = load_manifest(test_csv)
        print(f"  Loaded {len(manifest)} entries")
        eval_result = evaluate_manifest(manifest, cf_model, mix_model,
                                        cf_transform, mix_transform, device,
                                        manifest_name=manifest_dir)
        eval_result['test_csv_path'] = str(test_csv)
        all_results[tag] = eval_result

    # 输出摘要
    print("\n" + "=" * 70)
    print("GTSINGER MIX VOICE / MULTI-TECH EVALUATION RESULTS")
    print("=" * 70)

    for tag, result in all_results.items():
        if 'error' in result:
            print(f"\n  [{tag}] ERROR: {result['error']}")
            continue
        print(f"\n  === [{tag}] {result['manifest_name']} ({result['total']} samples) ===")

        mix = result['mix_binary']
        fal = result['falsetto_binary']

        print(f"  --- Mix Binary ---")
        print(f"    Accuracy:     {mix['accuracy']:.2%}")
        print(f"    non_mix:      P:{mix['non_mix']['precision']:.3f}  R:{mix['non_mix']['recall']:.3f}  F1:{mix['non_mix']['f1']:.3f}")
        print(f"    mix:          P:{mix['mix']['precision']:.3f}  R:{mix['mix']['recall']:.3f}  F1:{mix['mix']['f1']:.3f}")
        print(f"    Avg mix prob (mix):     {result['avg_mix_prob_mix_samples']:.3f}")
        print(f"    Avg mix prob (non-mix): {result['avg_mix_prob_nonmix_samples']:.3f}")

        print(f"  --- Falsetto Binary ---")
        print(f"    Accuracy:     {fal['accuracy']:.2%}")
        print(f"    non_falsetto: P:{fal['non_falsetto']['precision']:.3f}  R:{fal['non_falsetto']['recall']:.3f}  F1:{fal['non_falsetto']['f1']:.3f}")
        print(f"    falsetto:     P:{fal['falsetto']['precision']:.3f}  R:{fal['falsetto']['recall']:.3f}  F1:{fal['falsetto']['f1']:.3f}")

        if result['group_breakdown']:
            print(f"  --- Per-Group Breakdown ---")
            for grp_name, grp_m in sorted(result['group_breakdown'].items()):
                print(f"    {grp_name:24s}  n={grp_m['count']:4d}  mix_acc={grp_m['mix']['accuracy']:.3f}  fal_acc={grp_m['falsetto']['accuracy']:.3f}")

        if result['variant_breakdown']:
            print(f"  --- Mix Variant Recall ---")
            for var_name, var_m in sorted(result['variant_breakdown'].items()):
                print(f"    {var_name:20s}  n={var_m['count']:3d}  recall={var_m['recall']:.3f}  avg_prob={var_m['avg_mix_prob']:.3f}")

    output_path = OUTPUT_DIR / 'gtsinger_mix_eval.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Full results saved to: {output_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
