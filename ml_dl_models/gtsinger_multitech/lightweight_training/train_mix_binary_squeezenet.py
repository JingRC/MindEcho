import argparse
import csv
import json
import random
import time
import wave
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from PIL import Image
from scipy import signal
from scipy.io import wavfile
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms


SEED = 42
NON_MIX_LABEL = 0
MIX_LABEL = 1
EVAL_WINDOW_AGGREGATIONS = (
    'mean',
    'mean_minus_std',
    'median',
    'trimmed_mean',
    'support_gate',
    'support_gate_conservative',
    'support_gate_dual',
)
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
VALIDATION_GROUPS = (
    'Mixed_Voice_Group',
    'Control_Group',
    'Breathy_Group',
    'Falsetto_Group',
)
VALIDATION_BINARY_ROLES = (
    'positive_mix',
    'control_negative',
    'breathy_group',
    'falsetto_group',
)
SUPPORTED_BACKBONES = (
    'squeezenet11',
    'mobilenet_v3_small',
    'efficientnet_b0',
)


def compute_row_focus_multiplier(
    row: dict,
    *,
    head_mix_boost: float,
    breathy_mix_boost: float,
    control_negative_boost: float,
    falsetto_negative_boost: float,
    breathy_negative_boost: float,
    other_negative_boost: float,
) -> float:
    label = MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL
    if label == MIX_LABEL:
        mix_variant = str(row.get('mix_variant', '') or '')
        if mix_variant == 'head_mix':
            return float(head_mix_boost)
        if mix_variant == 'breathy_mix':
            return float(breathy_mix_boost)
        return 1.0

    group_name = str(row.get('group_name', '') or '')
    if group_name == 'Control_Group':
        return float(control_negative_boost)
    if group_name == 'Breathy_Group':
        return float(breathy_negative_boost)
    if group_name == 'Falsetto_Group':
        return float(falsetto_negative_boost)
    return float(other_negative_boost)


def get_row_multiplier(row: dict, field_name: str, default: float = 1.0) -> float:
    try:
        value = float(row.get(field_name, default) or default)
    except Exception:
        value = float(default)
    if not np.isfinite(value):
        return float(default)
    return max(0.0, float(value))


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_manifest(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def _select_window_bounds(total_length: int, target_length: int, train: bool, anchor_ratio: float | None = None) -> tuple[int, int]:
    total = max(0, int(total_length))
    target = max(1, int(target_length))
    if total <= target:
        return 0, total
    if anchor_ratio is not None:
        clamped = min(1.0, max(0.0, float(anchor_ratio)))
        start = int(round((total - target) * clamped))
        return start, start + target
    if train:
        start = random.randint(0, total - target)
    else:
        start = (total - target) // 2
    return start, start + target


def build_eval_anchor_ratios(window_count: int) -> tuple[float, ...]:
    count = max(1, int(window_count))
    if count <= 1:
        return (0.5,)
    return tuple(float(item) for item in np.linspace(0.0, 1.0, count, dtype=np.float32).tolist())


def _required_source_length(source_sr: int, target_sr: int, target_length: int | None) -> int | None:
    if target_length is None or target_length <= 0:
        return None
    if int(source_sr) == int(target_sr):
        return int(target_length)
    return max(1, int(np.ceil(float(target_length) * float(source_sr) / float(target_sr))))


def _read_audio_with_wave_fallback(
    path: Path,
    *,
    target_sr: int,
    target_length: int | None,
    train: bool,
    anchor_ratio: float | None = None,
) -> tuple[int, np.ndarray]:
    with wave.open(str(path), 'rb') as handle:
        sample_rate = int(handle.getframerate())
        channels = int(handle.getnchannels())
        sample_width = int(handle.getsampwidth())
        frame_count = int(handle.getnframes())
        source_length = _required_source_length(sample_rate, target_sr, target_length)
        if source_length is not None:
            start, end = _select_window_bounds(frame_count, source_length, train, anchor_ratio=anchor_ratio)
            handle.setpos(start)
            raw_frames = handle.readframes(end - start)
        else:
            raw_frames = handle.readframes(frame_count)

    if sample_width == 1:
        audio = np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw_frames, dtype='<i2').astype(np.float32) / 32768.0
    elif sample_width == 3:
        packed = np.frombuffer(raw_frames, dtype=np.uint8)
        packed = packed.reshape(-1, 3)
        values = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        sign_mask = 1 << 23
        values = (values ^ sign_mask) - sign_mask
        audio = values.astype(np.float32) / float(sign_mask)
    elif sample_width == 4:
        audio = np.frombuffer(raw_frames, dtype='<i4').astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f'Unsupported PCM sample width: {sample_width}')

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return sample_rate, audio


def read_audio(path: Path, target_sr: int, *, target_length: int | None = None, train: bool = False, anchor_ratio: float | None = None) -> np.ndarray:
    try:
        sample_rate, audio = wavfile.read(path, mmap=True)
    except Exception as exc:
        try:
            sample_rate, audio = _read_audio_with_wave_fallback(
                path,
                target_sr=target_sr,
                target_length=target_length,
                train=train,
                anchor_ratio=anchor_ratio,
            )
        except Exception:
            raise exc
    source_length = _required_source_length(sample_rate, target_sr, target_length)
    if source_length is not None:
        start, end = _select_window_bounds(len(audio), source_length, train, anchor_ratio=anchor_ratio)
        audio = audio[start:end]
    if audio.ndim > 1:
        audio = np.asarray(audio, dtype=np.float32).mean(axis=1)
    if np.issubdtype(audio.dtype, np.integer):
        max_val = float(np.iinfo(audio.dtype).max)
        audio = np.asarray(audio, dtype=np.float32)
        audio /= max_val
    else:
        audio = np.asarray(audio, dtype=np.float32)
    if sample_rate != target_sr:
        audio = signal.resample_poly(audio, target_sr, sample_rate).astype(np.float32)
    if target_length is not None:
        audio = crop_or_pad(audio, target_length, train=False)
    return audio


def crop_or_pad(audio: np.ndarray, target_length: int, train: bool) -> np.ndarray:
    if len(audio) >= target_length:
        if train:
            start = random.randint(0, len(audio) - target_length)
        else:
            start = (len(audio) - target_length) // 2
        return audio[start:start + target_length]
    padded = np.zeros(target_length, dtype=np.float32)
    start = 0 if train else (target_length - len(audio)) // 2
    padded[start:start + len(audio)] = audio
    return padded


def build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 128, fmin: float = 30.0, fmax: float | None = None) -> torch.Tensor:
    upper_hz = float(fmax if fmax is not None else sample_rate * 0.5)
    mel_low = 2595.0 * np.log10(1.0 + float(fmin) / 700.0)
    mel_high = 2595.0 * np.log10(1.0 + upper_hz / 700.0)
    mel_points = np.linspace(mel_low, mel_high, n_mels + 2, dtype=np.float32)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bins = np.floor((n_fft + 1) * hz_points / float(sample_rate)).astype(np.int32)
    bins = np.clip(bins, 0, n_fft // 2)
    filterbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for mel_idx in range(1, n_mels + 1):
        left = int(bins[mel_idx - 1])
        center = int(bins[mel_idx])
        right = int(bins[mel_idx + 1])
        if center <= left:
            center = min(left + 1, n_fft // 2)
        if right <= center:
            right = min(center + 1, n_fft // 2)
        if center > left:
            filterbank[mel_idx - 1, left:center] = np.linspace(0.0, 1.0, max(center - left, 1), endpoint=False, dtype=np.float32)
        if right > center:
            filterbank[mel_idx - 1, center:right] = np.linspace(1.0, 0.0, max(right - center, 1), endpoint=False, dtype=np.float32)
    return torch.from_numpy(filterbank)


def mel_image_from_audio(audio: np.ndarray, sample_rate: int, image_size: int, n_fft: int, hop_length: int, n_mels: int) -> Image.Image:
    waveform = torch.as_tensor(np.asarray(audio, dtype=np.float32).reshape(-1))
    if waveform.numel() < n_fft:
        waveform = torch.nn.functional.pad(waveform, (0, n_fft - waveform.numel()))
    window = torch.hann_window(n_fft)
    stft = torch.stft(
        waveform,
        n_fft=n_fft,
        hop_length=hop_length,
        win_length=n_fft,
        window=window,
        center=True,
        return_complex=True,
    )
    power = stft.abs().pow(2.0)
    mel_filter = build_mel_filterbank(sample_rate=sample_rate, n_fft=n_fft, n_mels=n_mels)
    mel_spec = torch.matmul(mel_filter, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if mel_spec.numel() else 0.0
    if peak > 0.0:
        mel_spec = mel_spec / peak
    image = (mel_spec.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(image).convert('RGB').resize((image_size, image_size), Image.BILINEAR)


def build_transforms(image_size: int, augment_profile: str = 'safe'):
    train_ops = [transforms.Resize((image_size, image_size))]
    if augment_profile == 'safe':
        train_ops.extend([
            transforms.RandomApply([transforms.ColorJitter(brightness=0.06, contrast=0.08)], p=0.20),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.45))], p=0.12),
            transforms.RandomAffine(degrees=0, translate=(0.02, 0.02), scale=(0.98, 1.02)),
        ])
    elif augment_profile == 'aggressive':
        train_ops.extend([
            transforms.RandomApply([transforms.ColorJitter(brightness=0.12, contrast=0.12)], p=0.35),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.8))], p=0.20),
            transforms.RandomAffine(degrees=0, translate=(0.03, 0.03), scale=(0.96, 1.04)),
            transforms.RandomHorizontalFlip(p=0.5),
        ])
    else:
        raise ValueError(f'Unsupported augment_profile: {augment_profile}')
    train_ops.extend([
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])
    if augment_profile == 'aggressive':
        train_ops.append(transforms.RandomErasing(p=0.18, scale=(0.02, 0.08), ratio=(0.5, 1.8), value='random'))
    else:
        train_ops.append(transforms.RandomErasing(p=0.06, scale=(0.02, 0.05), ratio=(0.8, 1.25), value='random'))
    train_tf = transforms.Compose(train_ops)
    eval_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])
    return train_tf, eval_tf


class MixBinaryAudioDataset(Dataset):
    def __init__(
        self,
        rows: Sequence[dict],
        *,
        sample_rate: int,
        sample_secs: float,
        image_size: int,
        n_fft: int,
        hop_length: int,
        n_mels: int,
        transform,
        train: bool,
        loss_weight_mode: str = 'none',
        loss_weight_config: dict | None = None,
        eval_anchor_ratios: Sequence[float] | None = None,
    ):
        self.rows = list(rows)
        self.sample_rate = sample_rate
        self.target_length = int(round(sample_rate * sample_secs))
        self.image_size = image_size
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.transform = transform
        self.train = train
        self.loss_weight_mode = str(loss_weight_mode)
        self.loss_weight_config = dict(loss_weight_config or {})
        self.eval_anchor_ratios = tuple(float(item) for item in (eval_anchor_ratios or (0.5,)))
        self.use_loss_weight_output = bool(self.train) and (
            self.loss_weight_mode != 'none'
            or any(abs(get_row_multiplier(row, 'loss_weight_multiplier', 1.0) - 1.0) > 1e-12 for row in self.rows)
        )

    def __len__(self) -> int:
        return len(self.rows)

    def _load_image(self, row: dict, anchor_ratio: float | None = None):
        audio = read_audio(
            Path(row['wav_path']),
            self.sample_rate,
            target_length=self.target_length,
            train=self.train,
            anchor_ratio=anchor_ratio,
        )
        image = mel_image_from_audio(audio, self.sample_rate, self.image_size, self.n_fft, self.hop_length, self.n_mels)
        if self.transform is not None:
            image = self.transform(image)
        return image

    def __getitem__(self, index: int):
        row = self.rows[index]
        if (not self.train) and len(self.eval_anchor_ratios) > 1:
            image = torch.stack([self._load_image(row, anchor_ratio=item) for item in self.eval_anchor_ratios], dim=0)
        else:
            anchor_ratio = None if self.train else self.eval_anchor_ratios[0]
            image = self._load_image(row, anchor_ratio=anchor_ratio)
        label = MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL
        if self.train and self.use_loss_weight_output:
            loss_weight = 1.0
            if self.loss_weight_mode != 'none':
                if self.loss_weight_mode == 'technique_focus':
                    loss_weight *= compute_row_focus_multiplier(row, **self.loss_weight_config)
                else:
                    raise ValueError(f'Unsupported loss_weight_mode: {self.loss_weight_mode}')
            loss_weight *= get_row_multiplier(row, 'loss_weight_multiplier', 1.0)
            return image, label, float(loss_weight)
        return image, label


@dataclass
class TrainConfig:
    train_manifest: Path
    validation_manifest: Path
    test_manifest: Path
    output_dir: Path
    init_checkpoint: Path | None = None
    backbone_name: str = 'squeezenet11'
    augment_profile: str = 'safe'
    batch_size: int = 32
    head_epochs: int = 6
    finetune_epochs: int = 8
    head_lr: float = 1e-3
    finetune_lr: float = 2e-4
    weight_decay: float = 1e-4
    image_size: int = 224
    sample_rate: int = 22050
    sample_secs: float = 2.4
    eval_window_count: int = 1
    eval_window_aggregation: str = 'mean'
    eval_window_consistency_penalty: float = 0.0
    eval_window_support_threshold: float = 0.40
    eval_window_min_support_windows: int = 2
    eval_window_high_support_threshold: float = 0.55
    eval_window_min_high_support_windows: int = 1
    n_fft: int = 1024
    hop_length: int = 256
    n_mels: int = 128
    num_workers: int = 0
    seed: int = SEED
    label_smoothing: float = 0.03
    class_weight_mode: str = 'none'
    weighted_sampler: bool = False
    sample_weight_mode: str = 'class_balanced'
    head_mix_boost: float = 1.0
    breathy_mix_boost: float = 1.0
    control_negative_boost: float = 1.0
    falsetto_negative_boost: float = 1.0
    breathy_negative_boost: float = 1.0
    other_negative_boost: float = 1.0
    loss_weight_mode: str = 'none'
    head_mix_loss_boost: float = 1.0
    breathy_mix_loss_boost: float = 1.0
    control_negative_loss_boost: float = 1.0
    falsetto_negative_loss_boost: float = 1.0
    breathy_negative_loss_boost: float = 1.0
    other_negative_loss_boost: float = 1.0
    selection_metric: str = 'balanced_acc'
    threshold_min: float = 0.25
    threshold_max: float = 0.70
    threshold_step: float = 0.025
    min_positive_mix_rate: float = 0.0
    max_control_negative_rate: float = 1.0
    max_breathy_negative_rate: float = 1.0
    max_falsetto_negative_rate: float = 1.0
    product_proxy_positive_weight: float = 0.35
    product_proxy_control_penalty: float = 0.30
    product_proxy_breathy_penalty: float = 0.20
    product_proxy_falsetto_penalty: float = 0.15


def build_model(backbone_name: str = 'squeezenet11') -> nn.Module:
    name = str(backbone_name or 'squeezenet11').strip().lower()
    if name == 'squeezenet11':
        try:
            weights = models.SqueezeNet1_1_Weights.DEFAULT
            model = models.squeezenet1_1(weights=weights)
        except Exception:
            model = models.squeezenet1_1(weights=None)
        model.classifier[1] = nn.Conv2d(512, 2, kernel_size=1)
        model.num_classes = 2
    elif name == 'mobilenet_v3_small':
        try:
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
            model = models.mobilenet_v3_small(weights=weights)
        except Exception:
            model = models.mobilenet_v3_small(weights=None)
        in_features = int(model.classifier[-1].in_features)
        model.classifier[-1] = nn.Linear(in_features, 2)
    elif name == 'efficientnet_b0':
        try:
            weights = models.EfficientNet_B0_Weights.DEFAULT
            model = models.efficientnet_b0(weights=weights)
        except Exception:
            model = models.efficientnet_b0(weights=None)
        in_features = int(model.classifier[-1].in_features)
        model.classifier[-1] = nn.Linear(in_features, 2)
    else:
        raise ValueError(f'Unsupported backbone_name: {backbone_name}')
    setattr(model, '_mix_backbone_name', name)
    return model


def load_checkpoint_state_dict(checkpoint_path: Path, device: torch.device) -> Dict[str, torch.Tensor]:
    try:
        checkpoint = torch.load(str(checkpoint_path), map_location=device)
    except TypeError:
        checkpoint = torch.load(str(checkpoint_path), map_location=device, weights_only=False)
    except Exception as exc:
        if 'weights_only' not in str(exc or ''):
            raise
        checkpoint = torch.load(str(checkpoint_path), map_location=device, weights_only=False)
    state_dict = checkpoint.get('model_state_dict', checkpoint) if isinstance(checkpoint, dict) else checkpoint
    if not isinstance(state_dict, dict):
        raise RuntimeError(f'Unsupported checkpoint format: {checkpoint_path}')
    return state_dict


def model_backbone_name(model: nn.Module) -> str:
    return str(getattr(model, '_mix_backbone_name', 'squeezenet11') or 'squeezenet11').strip().lower()


def get_model_embedding_dim(model: nn.Module) -> int:
    name = model_backbone_name(model)
    if name == 'squeezenet11':
        return 512
    if name == 'mobilenet_v3_small':
        return 576
    if name == 'efficientnet_b0':
        return 1280
    raise ValueError(f'Unsupported backbone_name: {name}')


def extract_model_embeddings(model: nn.Module, images: torch.Tensor) -> torch.Tensor:
    name = model_backbone_name(model)
    if name in {'squeezenet11', 'mobilenet_v3_small', 'efficientnet_b0'}:
        features = model.features(images)
        return torch.nn.functional.adaptive_avg_pool2d(features, (1, 1)).flatten(1)
    raise ValueError(f'Unsupported backbone_name: {name}')


def aggregate_window_logits(
    window_logits: torch.Tensor,
    *,
    aggregation: str = 'mean',
    consistency_penalty: float = 0.0,
    support_threshold: float = 0.40,
    min_support_windows: int = 2,
    high_support_threshold: float = 0.55,
    min_high_support_windows: int = 1,
) -> torch.Tensor:
    if window_logits.ndim != 3:
        raise ValueError(f'Expected window logits rank 3, got shape={tuple(window_logits.shape)}')
    if int(window_logits.shape[-1]) != 2:
        return window_logits.mean(dim=1)
    mode = str(aggregation or 'mean').strip().lower()
    margins = window_logits[:, :, MIX_LABEL] - window_logits[:, :, NON_MIX_LABEL]
    if mode == 'mean':
        aggregated_margin = margins.mean(dim=1)
    elif mode == 'mean_minus_std':
        aggregated_margin = margins.mean(dim=1) - max(0.0, float(consistency_penalty)) * margins.std(dim=1, unbiased=False)
    elif mode == 'median':
        aggregated_margin = margins.median(dim=1).values
    elif mode == 'trimmed_mean':
        if int(margins.shape[1]) <= 2:
            aggregated_margin = margins.mean(dim=1)
        else:
            aggregated_margin = margins.sort(dim=1).values[:, 1:-1].mean(dim=1)
    elif mode == 'support_gate':
        weak_support_threshold = min(0.95, max(0.05, float(support_threshold)))
        required_windows = max(1, int(min_support_windows))
        window_probs = torch.softmax(window_logits, dim=2)[:, :, MIX_LABEL]
        support_mask = window_probs >= weak_support_threshold
        support_counts = support_mask.sum(dim=1)
        gated_mean = margins.mean(dim=1)
        fallback_margin = margins.median(dim=1).values
        aggregated_margin = torch.where(support_counts >= required_windows, gated_mean, fallback_margin)
    elif mode == 'support_gate_conservative':
        weak_support_threshold = min(0.95, max(0.05, float(support_threshold)))
        required_windows = max(1, int(min_support_windows))
        window_probs = torch.softmax(window_logits, dim=2)[:, :, MIX_LABEL]
        support_mask = window_probs >= weak_support_threshold
        support_counts = support_mask.sum(dim=1)
        support_weights = support_mask.to(dtype=margins.dtype)
        support_mean = (margins * support_weights).sum(dim=1) / support_counts.clamp(min=1).to(dtype=margins.dtype)
        gated_mean = torch.minimum(margins.mean(dim=1), support_mean)
        fallback_margin = margins.median(dim=1).values
        aggregated_margin = torch.where(support_counts >= required_windows, gated_mean, fallback_margin)
    elif mode == 'support_gate_dual':
        weak_support_threshold = min(0.95, max(0.05, float(support_threshold)))
        required_windows = max(1, int(min_support_windows))
        strong_support_threshold = min(0.99, max(weak_support_threshold, float(high_support_threshold)))
        required_high_windows = max(1, int(min_high_support_windows))
        window_probs = torch.softmax(window_logits, dim=2)[:, :, MIX_LABEL]
        support_mask = window_probs >= weak_support_threshold
        high_support_mask = window_probs >= strong_support_threshold
        support_counts = support_mask.sum(dim=1)
        high_support_counts = high_support_mask.sum(dim=1)
        gate_mask = (support_counts >= required_windows) & (high_support_counts >= required_high_windows)
        gated_mean = margins.mean(dim=1)
        fallback_margin = margins.median(dim=1).values
        aggregated_margin = torch.where(gate_mask, gated_mean, fallback_margin)
    else:
        raise ValueError(f'Unsupported eval window aggregation: {aggregation}')
    return torch.stack((-0.5 * aggregated_margin, 0.5 * aggregated_margin), dim=1)


def forward_with_window_average(
    model: nn.Module,
    images: torch.Tensor,
    *,
    aggregation: str = 'mean',
    consistency_penalty: float = 0.0,
    support_threshold: float = 0.40,
    min_support_windows: int = 2,
    high_support_threshold: float = 0.55,
    min_high_support_windows: int = 1,
) -> torch.Tensor:
    if images.ndim == 4:
        return model(images)
    if images.ndim != 5:
        raise ValueError(f'Expected image batch rank 4 or 5, got shape={tuple(images.shape)}')
    batch_size, window_count, channels, height, width = images.shape
    flat_images = images.reshape(batch_size * window_count, channels, height, width)
    flat_logits = model(flat_images)
    return aggregate_window_logits(
        flat_logits.reshape(batch_size, window_count, -1),
        aggregation=aggregation,
        consistency_penalty=consistency_penalty,
        support_threshold=support_threshold,
        min_support_windows=min_support_windows,
        high_support_threshold=high_support_threshold,
        min_high_support_windows=min_high_support_windows,
    )


def set_feature_trainable(model: nn.Module, trainable: bool) -> None:
    for param in model.features.parameters():
        param.requires_grad = trainable


def summarize_rows(rows: Sequence[dict]) -> Dict[str, Dict[str, int] | int]:
    labels = [MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL for row in rows]
    roles = Counter(str(row.get('binary_role', '') or '') for row in rows)
    groups = Counter(str(row.get('group_name', '') or '') for row in rows)
    return {
        'items': len(rows),
        'labels': {str(key): int(value) for key, value in Counter(labels).items()},
        'binary_roles': {str(key): int(value) for key, value in roles.items()},
        'groups': {str(key): int(value) for key, value in groups.items()},
    }


def build_class_weights(rows: Sequence[dict], mode: str) -> torch.Tensor | None:
    if mode == 'none':
        return None
    counts = Counter(MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL for row in rows)
    total = max(1, sum(counts.values()))
    weights = np.ones((2,), dtype=np.float32)
    if mode == 'inverse_freq':
        for label_index in (NON_MIX_LABEL, MIX_LABEL):
            count = max(1, int(counts.get(label_index, 0)))
            weights[label_index] = float(total) / float(2 * count)
    elif mode == 'inverse_sqrt':
        for label_index in (NON_MIX_LABEL, MIX_LABEL):
            count = max(1, int(counts.get(label_index, 0)))
            weights[label_index] = float(np.sqrt(float(total) / float(2 * count)))
    else:
        raise ValueError(f'Unsupported class_weight_mode: {mode}')
    return torch.tensor(weights, dtype=torch.float32)


def build_weighted_sampler(rows: Sequence[dict], cfg: TrainConfig) -> WeightedRandomSampler:
    counts = Counter(MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL for row in rows)
    sample_weights = []
    for row in rows:
        label = MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else NON_MIX_LABEL
        base_weight = 1.0 / max(1, int(counts.get(label, 0)))
        if cfg.sample_weight_mode == 'class_balanced':
            weight = base_weight
        elif cfg.sample_weight_mode == 'technique_focus':
            weight = base_weight * compute_row_focus_multiplier(
                row,
                head_mix_boost=cfg.head_mix_boost,
                breathy_mix_boost=cfg.breathy_mix_boost,
                control_negative_boost=cfg.control_negative_boost,
                falsetto_negative_boost=cfg.falsetto_negative_boost,
                breathy_negative_boost=cfg.breathy_negative_boost,
                other_negative_boost=cfg.other_negative_boost,
            )
        else:
            raise ValueError(f'Unsupported sample_weight_mode: {cfg.sample_weight_mode}')
        weight *= get_row_multiplier(row, 'sample_weight_multiplier', 1.0)
        sample_weights.append(weight)
    weights = torch.tensor(sample_weights, dtype=torch.double)
    return WeightedRandomSampler(weights=weights, num_samples=len(sample_weights), replacement=True)


def summarize_group_positive_rates(rows: Sequence[dict], preds: Sequence[int]) -> Dict[str, float]:
    preds_np = np.asarray(list(preds), dtype=np.int32)
    rates: Dict[str, float] = {}
    for group_name in VALIDATION_GROUPS:
        indices = [index for index, row in enumerate(rows) if str(row.get('group_name', '') or '') == group_name]
        if not indices:
            continue
        rates[group_name] = float(preds_np[indices].mean()) if len(indices) else 0.0
    return rates


def summarize_binary_role_positive_rates(rows: Sequence[dict], preds: Sequence[int]) -> Dict[str, float]:
    preds_np = np.asarray(list(preds), dtype=np.int32)
    rates: Dict[str, float] = {}
    for role_name in VALIDATION_BINARY_ROLES:
        indices = [index for index, row in enumerate(rows) if str(row.get('binary_role', '') or '') == role_name]
        if not indices:
            continue
        rates[role_name] = float(preds_np[indices].mean()) if len(indices) else 0.0
    return rates


def threshold_constraints_satisfied(role_rates: Dict[str, float], cfg: TrainConfig) -> bool:
    positive_mix_rate = float(role_rates.get('positive_mix', 0.0))
    control_negative_rate = float(role_rates.get('control_negative', 0.0))
    breathy_negative_rate = float(role_rates.get('breathy_group', 0.0))
    falsetto_negative_rate = float(role_rates.get('falsetto_group', 0.0))
    if positive_mix_rate + 1e-12 < float(cfg.min_positive_mix_rate):
        return False
    if control_negative_rate - 1e-12 > float(cfg.max_control_negative_rate):
        return False
    if breathy_negative_rate - 1e-12 > float(cfg.max_breathy_negative_rate):
        return False
    if falsetto_negative_rate - 1e-12 > float(cfg.max_falsetto_negative_rate):
        return False
    return True


def compute_binary_metrics(targets: Sequence[int], preds: Sequence[int]) -> Dict[str, float]:
    targets_np = np.asarray(list(targets), dtype=np.int32)
    preds_np = np.asarray(list(preds), dtype=np.int32)
    return {
        'acc': float(accuracy_score(targets_np, preds_np)),
        'balanced_acc': float(balanced_accuracy_score(targets_np, preds_np)),
        'macro_f1': float(f1_score(targets_np, preds_np, average='macro', zero_division=0)),
        'mix_f1': float(f1_score(targets_np, preds_np, pos_label=MIX_LABEL, zero_division=0)),
        'mix_precision': float(precision_score(targets_np, preds_np, pos_label=MIX_LABEL, zero_division=0)),
        'mix_recall': float(recall_score(targets_np, preds_np, pos_label=MIX_LABEL, zero_division=0)),
    }


def compute_selection_score(metrics: Dict[str, float], role_rates: Dict[str, float], cfg: TrainConfig) -> float:
    if cfg.selection_metric != 'product_proxy':
        return float(metrics.get(cfg.selection_metric, metrics['mix_f1']))
    positive_mix_rate = float(role_rates.get('positive_mix', 0.0))
    control_negative_rate = float(role_rates.get('control_negative', 0.0))
    breathy_negative_rate = float(role_rates.get('breathy_group', 0.0))
    falsetto_negative_rate = float(role_rates.get('falsetto_group', 0.0))
    return (
        float(metrics.get('balanced_acc', 0.0))
        + float(cfg.product_proxy_positive_weight) * positive_mix_rate
        - float(cfg.product_proxy_control_penalty) * control_negative_rate
        - float(cfg.product_proxy_breathy_penalty) * breathy_negative_rate
        - float(cfg.product_proxy_falsetto_penalty) * falsetto_negative_rate
    )


def find_best_threshold(targets: Sequence[int], mix_probs: Sequence[float], cfg: TrainConfig, rows: Sequence[dict] | None = None) -> tuple[float, Dict[str, float], Dict[str, float], Dict[str, float], bool]:
    targets_np = np.asarray(list(targets), dtype=np.int32)
    probs_np = np.asarray(list(mix_probs), dtype=np.float32)
    default_preds = (probs_np >= 0.5).astype(np.int32)
    default_group_rates = summarize_group_positive_rates(rows or [], default_preds) if rows is not None else {}
    default_role_rates = summarize_binary_role_positive_rates(rows or [], default_preds) if rows is not None else {}
    best_threshold = 0.5
    best_metrics = compute_binary_metrics(targets_np, default_preds)
    best_group_rates = default_group_rates
    best_role_rates = default_role_rates
    best_score = compute_selection_score(best_metrics, best_role_rates, cfg)
    best_constraints_ok = threshold_constraints_satisfied(default_role_rates, cfg) if rows is not None else True

    constrained_threshold = None
    constrained_metrics = None
    constrained_group_rates = None
    constrained_role_rates = None
    constrained_score = None
    candidates = np.arange(cfg.threshold_min, cfg.threshold_max + 1e-9, cfg.threshold_step, dtype=np.float32)
    for candidate in candidates:
        preds = (probs_np >= candidate).astype(np.int32)
        metrics = compute_binary_metrics(targets_np, preds)
        group_rates = summarize_group_positive_rates(rows or [], preds) if rows is not None else {}
        role_rates = summarize_binary_role_positive_rates(rows or [], preds) if rows is not None else {}
        score = compute_selection_score(metrics, role_rates, cfg)
        if score > best_score + 1e-12:
            best_score = score
            best_threshold = float(candidate)
            best_metrics = metrics
            best_group_rates = group_rates
            best_role_rates = role_rates
            best_constraints_ok = threshold_constraints_satisfied(role_rates, cfg) if rows is not None else True
        if rows is not None and threshold_constraints_satisfied(role_rates, cfg):
            if constrained_score is None or score > float(constrained_score) + 1e-12:
                constrained_threshold = float(candidate)
                constrained_metrics = metrics
                constrained_group_rates = group_rates
                constrained_role_rates = role_rates
                constrained_score = score

    if constrained_threshold is not None:
        return constrained_threshold, constrained_metrics or best_metrics, constrained_group_rates or {}, constrained_role_rates or {}, True
    return best_threshold, best_metrics, best_group_rates, best_role_rates, best_constraints_ok


def build_dataloaders(cfg: TrainConfig):
    train_rows = load_manifest(cfg.train_manifest)
    valid_rows = load_manifest(cfg.validation_manifest)
    test_rows = load_manifest(cfg.test_manifest)
    eval_anchor_ratios = build_eval_anchor_ratios(cfg.eval_window_count)
    train_tf, eval_tf = build_transforms(cfg.image_size, cfg.augment_profile)
    train_ds = MixBinaryAudioDataset(
        train_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=train_tf,
        train=True,
        loss_weight_mode=cfg.loss_weight_mode,
        loss_weight_config={
            'head_mix_boost': cfg.head_mix_loss_boost,
            'breathy_mix_boost': cfg.breathy_mix_loss_boost,
            'control_negative_boost': cfg.control_negative_loss_boost,
            'falsetto_negative_boost': cfg.falsetto_negative_loss_boost,
            'breathy_negative_boost': cfg.breathy_negative_loss_boost,
            'other_negative_boost': cfg.other_negative_loss_boost,
        },
    )
    valid_ds = MixBinaryAudioDataset(
        valid_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=eval_tf,
        train=False,
        eval_anchor_ratios=eval_anchor_ratios,
    )
    test_ds = MixBinaryAudioDataset(
        test_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=eval_tf,
        train=False,
        eval_anchor_ratios=eval_anchor_ratios,
    )
    sampler = build_weighted_sampler(train_rows, cfg) if cfg.weighted_sampler else None
    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=sampler is None,
        sampler=sampler,
        num_workers=cfg.num_workers,
    )
    valid_loader = DataLoader(valid_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    test_loader = DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    split_summary = {
        'train': summarize_rows(train_rows),
        'validation': summarize_rows(valid_rows),
        'test': summarize_rows(test_rows),
    }
    return train_loader, valid_loader, test_loader, split_summary, train_rows, valid_rows


def train_one_epoch(
    model,
    loader,
    optimizer,
    criterion,
    device,
    *,
    eval_window_aggregation: str = 'mean',
    eval_window_consistency_penalty: float = 0.0,
    eval_window_support_threshold: float = 0.40,
    eval_window_min_support_windows: int = 2,
    eval_window_high_support_threshold: float = 0.55,
    eval_window_min_high_support_windows: int = 1,
):
    model.train()
    total_loss = 0.0
    all_preds: List[int] = []
    all_targets: List[int] = []
    for batch in loader:
        if len(batch) == 3:
            images, labels, loss_weights = batch
            loss_weights = loss_weights.to(device=device, dtype=torch.float32)
        else:
            images, labels = batch
            loss_weights = None
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        outputs = forward_with_window_average(
            model,
            images,
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        loss_values = criterion(outputs, labels)
        if getattr(loss_values, 'ndim', 0) == 0:
            loss = loss_values
        else:
            if loss_weights is not None:
                loss_values = loss_values * loss_weights
            loss = loss_values.mean()
        loss.backward()
        optimizer.step()
        total_loss += float(loss.item()) * int(labels.size(0))
        preds = outputs.argmax(dim=1)
        all_preds.extend(preds.detach().cpu().tolist())
        all_targets.extend(labels.detach().cpu().tolist())
    avg_loss = total_loss / max(1, len(loader.dataset))
    acc = accuracy_score(all_targets, all_preds)
    return avg_loss, acc


@torch.no_grad()
def evaluate(
    model,
    loader,
    criterion,
    device,
    threshold: float = 0.5,
    *,
    eval_window_aggregation: str = 'mean',
    eval_window_consistency_penalty: float = 0.0,
    eval_window_support_threshold: float = 0.40,
    eval_window_min_support_windows: int = 2,
    eval_window_high_support_threshold: float = 0.55,
    eval_window_min_high_support_windows: int = 1,
):
    model.eval()
    total_loss = 0.0
    all_preds: List[int] = []
    all_targets: List[int] = []
    all_probs: List[List[float]] = []
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        outputs = forward_with_window_average(
            model,
            images,
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        loss = criterion(outputs, labels)
        probs = torch.softmax(outputs, dim=1)
        total_loss += float(loss.item()) * int(labels.size(0))
        preds = (probs[:, MIX_LABEL] >= float(threshold)).to(dtype=torch.int64)
        all_preds.extend(preds.detach().cpu().tolist())
        all_targets.extend(labels.detach().cpu().tolist())
        all_probs.extend(probs.detach().cpu().tolist())
    avg_loss = total_loss / max(1, len(loader.dataset))
    acc = accuracy_score(all_targets, all_preds)
    return avg_loss, acc, all_targets, all_preds, all_probs


def write_history_csv(path: Path, history: List[Dict[str, float]]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)


def run_training(cfg: TrainConfig) -> Path:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    set_seed(cfg.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    train_loader, valid_loader, test_loader, split_summary, train_rows, valid_rows = build_dataloaders(cfg)
    model = build_model(cfg.backbone_name).to(device)
    init_checkpoint_text = ''
    if cfg.init_checkpoint is not None:
        init_checkpoint_path = Path(cfg.init_checkpoint)
        if not init_checkpoint_path.exists():
            raise FileNotFoundError(f'init checkpoint not found: {init_checkpoint_path}')
        model.load_state_dict(load_checkpoint_state_dict(init_checkpoint_path, device))
        init_checkpoint_text = str(init_checkpoint_path.resolve())
    class_weights = build_class_weights(train_rows, cfg.class_weight_mode)
    train_criterion = nn.CrossEntropyLoss(
        weight=class_weights.to(device) if class_weights is not None else None,
        label_smoothing=cfg.label_smoothing,
        reduction='none',
    )
    eval_criterion = nn.CrossEntropyLoss(
        weight=class_weights.to(device) if class_weights is not None else None,
        label_smoothing=cfg.label_smoothing,
    )
    history: List[Dict[str, float]] = []
    best_state = None
    final_state = None
    best_val_score = -1.0
    best_epoch = -1
    best_threshold = 0.5
    best_path = cfg.output_dir / 'best_mix_binary_squeezenet.pt'
    final_path = cfg.output_dir / 'last_mix_binary_squeezenet.pt'
    stage_schedule = [
        ('head', cfg.head_epochs, cfg.head_lr, False),
        ('finetune', cfg.finetune_epochs, cfg.finetune_lr, True),
    ]

    start_time = time.time()
    epoch_cursor = 0
    for stage_name, epochs, lr, feature_trainable in stage_schedule:
        if epochs <= 0:
            continue
        set_feature_trainable(model, feature_trainable)
        params = [param for param in model.parameters() if param.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=cfg.weight_decay)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
        for _ in range(epochs):
            epoch_cursor += 1
            train_loss, train_acc = train_one_epoch(
                model,
                train_loader,
                optimizer,
                train_criterion,
                device,
                eval_window_aggregation=cfg.eval_window_aggregation,
                eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
                eval_window_support_threshold=cfg.eval_window_support_threshold,
                eval_window_min_support_windows=cfg.eval_window_min_support_windows,
                eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
                eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
            )
            val_loss_raw, _, val_targets, _, val_probs = evaluate(
                model,
                valid_loader,
                eval_criterion,
                device,
                threshold=0.5,
                eval_window_aggregation=cfg.eval_window_aggregation,
                eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
                eval_window_support_threshold=cfg.eval_window_support_threshold,
                eval_window_min_support_windows=cfg.eval_window_min_support_windows,
                eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
                eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
            )
            val_mix_probs = [float(item[MIX_LABEL]) for item in val_probs]
            val_threshold, val_metrics, val_group_rates, val_role_rates, val_constraints_ok = find_best_threshold(val_targets, val_mix_probs, cfg, rows=valid_rows)
            val_selection_score = compute_selection_score(val_metrics, val_role_rates, cfg)
            row = {
                'epoch': epoch_cursor,
                'stage': stage_name,
                'train_loss': round(train_loss, 6),
                'train_acc': round(train_acc, 6),
                'val_loss': round(val_loss_raw, 6),
                'val_acc': round(val_metrics['acc'], 6),
                'val_balanced_acc': round(val_metrics['balanced_acc'], 6),
                'val_macro_f1': round(val_metrics['macro_f1'], 6),
                'val_mix_f1': round(val_metrics['mix_f1'], 6),
                'val_mix_precision': round(val_metrics['mix_precision'], 6),
                'val_mix_recall': round(val_metrics['mix_recall'], 6),
                'val_mixed_group_positive_rate': round(float(val_group_rates.get('Mixed_Voice_Group', 0.0)), 6),
                'val_control_group_positive_rate': round(float(val_group_rates.get('Control_Group', 0.0)), 6),
                'val_breathy_group_positive_rate': round(float(val_group_rates.get('Breathy_Group', 0.0)), 6),
                'val_falsetto_group_positive_rate': round(float(val_group_rates.get('Falsetto_Group', 0.0)), 6),
                'val_positive_mix_rate': round(float(val_role_rates.get('positive_mix', 0.0)), 6),
                'val_control_negative_rate': round(float(val_role_rates.get('control_negative', 0.0)), 6),
                'val_breathy_negative_rate': round(float(val_role_rates.get('breathy_group', 0.0)), 6),
                'val_falsetto_negative_rate': round(float(val_role_rates.get('falsetto_group', 0.0)), 6),
                'val_selection_score': round(float(val_selection_score), 6),
                'val_threshold_constraints_ok': bool(val_constraints_ok),
                'val_threshold': round(val_threshold, 4),
                'lr': round(float(optimizer.param_groups[0]['lr']), 8),
            }
            history.append(row)
            write_history_csv(cfg.output_dir / 'history.csv', history)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            final_threshold = float(val_threshold)
            final_state = {
                'model_state_dict': model.state_dict(),
                'val_score': float(val_selection_score),
                'val_metrics': dict(val_metrics),
                'val_group_rates': dict(val_group_rates),
                'val_role_rates': dict(val_role_rates),
                'val_selection_score': float(val_selection_score),
                'val_threshold_constraints_ok': bool(val_constraints_ok),
                'threshold': final_threshold,
                'epoch': epoch_cursor,
                'stage': stage_name,
                'class_to_idx': {'non_mix': NON_MIX_LABEL, 'mix': MIX_LABEL},
                'config': cfg.__dict__,
            }
            current_score = float(val_selection_score)
            if current_score > best_val_score:
                best_val_score = current_score
                best_epoch = epoch_cursor
                best_threshold = float(val_threshold)
                best_state = {
                    'model_state_dict': model.state_dict(),
                    'val_score': current_score,
                    'val_metrics': val_metrics,
                    'val_group_rates': val_group_rates,
                    'val_role_rates': val_role_rates,
                    'val_selection_score': val_selection_score,
                    'val_threshold_constraints_ok': bool(val_constraints_ok),
                    'threshold': best_threshold,
                    'epoch': epoch_cursor,
                    'stage': stage_name,
                    'class_to_idx': {'non_mix': NON_MIX_LABEL, 'mix': MIX_LABEL},
                    'config': cfg.__dict__,
                }
                torch.save(best_state, best_path)
            scheduler.step()

    if best_state is None:
        raise RuntimeError('Training did not produce a valid checkpoint.')
    if final_state is None:
        raise RuntimeError('Training did not produce a final checkpoint state.')

    torch.save(final_state, final_path)

    model.load_state_dict(best_state['model_state_dict'])
    test_loss, test_acc, test_targets, test_preds, test_probs = evaluate(
        model,
        test_loader,
        eval_criterion,
        device,
        threshold=best_threshold,
        eval_window_aggregation=cfg.eval_window_aggregation,
        eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
        eval_window_support_threshold=cfg.eval_window_support_threshold,
        eval_window_min_support_windows=cfg.eval_window_min_support_windows,
        eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
        eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
    )
    duration_sec = time.time() - start_time
    test_metrics = compute_binary_metrics(test_targets, test_preds)
    report = classification_report(
        test_targets,
        test_preds,
        target_names=['non_mix', 'mix'],
        output_dict=True,
        zero_division=0,
    )
    mix_probs = [float(item[MIX_LABEL]) for item in test_probs]
    summary = {
        'device': str(device),
        'task': 'mix_binary_crossentropy',
        'init_checkpoint': init_checkpoint_text,
        'backbone_name': str(cfg.backbone_name),
        'augment_profile': cfg.augment_profile,
        'image_size': int(cfg.image_size),
        'sample_rate': int(cfg.sample_rate),
        'sample_secs': cfg.sample_secs,
        'eval_window_count': int(cfg.eval_window_count),
        'eval_window_aggregation': str(cfg.eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(cfg.eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(cfg.eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(cfg.eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(cfg.eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(cfg.eval_window_min_high_support_windows),
        'n_fft': int(cfg.n_fft),
        'hop_length': int(cfg.hop_length),
        'n_mels': cfg.n_mels,
        'best_epoch': best_epoch,
        'class_weight_mode': cfg.class_weight_mode,
        'weighted_sampler': bool(cfg.weighted_sampler),
        'sample_weight_mode': cfg.sample_weight_mode,
        'loss_weight_mode': cfg.loss_weight_mode,
        'selection_metric': cfg.selection_metric,
        'best_threshold': round(float(best_threshold), 6),
        'best_val_score': round(float(best_val_score), 6),
        'best_val_selection_score': round(float(best_state.get('val_selection_score', best_val_score)), 6),
        'best_val_metrics': {key: round(float(value), 6) for key, value in best_state.get('val_metrics', {}).items()},
        'best_val_group_rates': {
            key: round(float(value), 6)
            for key, value in best_state.get('val_group_rates', {}).items()
        },
        'best_val_binary_role_rates': {
            key: round(float(value), 6)
            for key, value in best_state.get('val_role_rates', {}).items()
        },
        'best_val_threshold_constraints_ok': bool(best_state.get('val_threshold_constraints_ok', True)),
        'validation_threshold_constraints': {
            'min_positive_mix_rate': round(float(cfg.min_positive_mix_rate), 6),
            'max_control_negative_rate': round(float(cfg.max_control_negative_rate), 6),
            'max_breathy_negative_rate': round(float(cfg.max_breathy_negative_rate), 6),
            'max_falsetto_negative_rate': round(float(cfg.max_falsetto_negative_rate), 6),
        },
        'best_val_acc': round(float(best_state.get('val_metrics', {}).get('acc', 0.0)), 6),
        'final_epoch': int(final_state.get('epoch', -1)),
        'final_stage': str(final_state.get('stage', '') or ''),
        'final_threshold': round(float(final_state.get('threshold', 0.5)), 6),
        'final_val_score': round(float(final_state.get('val_selection_score', 0.0)), 6),
        'final_val_metrics': {key: round(float(value), 6) for key, value in final_state.get('val_metrics', {}).items()},
        'final_val_binary_role_rates': {
            key: round(float(value), 6)
            for key, value in final_state.get('val_role_rates', {}).items()
        },
        'test_acc': round(float(test_acc), 6),
        'test_loss': round(float(test_loss), 6),
        'test_metrics': {key: round(float(value), 6) for key, value in test_metrics.items()},
        'duration_sec': round(float(duration_sec), 3),
        'split_summary': split_summary,
        'confusion_matrix': confusion_matrix(test_targets, test_preds).tolist(),
        'classification_report': report,
        'test_mix_probability': {
            'mean': round(float(np.mean(mix_probs)) if mix_probs else 0.0, 6),
            'min': round(float(np.min(mix_probs)) if mix_probs else 0.0, 6),
            'max': round(float(np.max(mix_probs)) if mix_probs else 0.0, 6),
        },
        'history': history,
        'checkpoint': str(best_path),
        'final_checkpoint': str(final_path),
    }
    (cfg.output_dir / 'training_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (cfg.output_dir / 'label_map.json').write_text(json.dumps({'labels': ['non_mix', 'mix']}, ensure_ascii=False, indent=2), encoding='utf-8')
    if history:
        write_history_csv(cfg.output_dir / 'history.csv', history)
    print(json.dumps({
        'best_val_score': summary['best_val_score'],
        'best_threshold': summary['best_threshold'],
        'test_acc': summary['test_acc'],
        'test_metrics': summary['test_metrics'],
        'checkpoint': summary['checkpoint'],
        'duration_sec': summary['duration_sec'],
    }, ensure_ascii=False, indent=2), flush=True)
    return best_path


def main() -> None:
    parser = argparse.ArgumentParser(description='Train a dedicated CrossEntropy SqueezeNet mix binary classifier.')
    parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\train_manifest.csv')
    parser.add_argument('--validation-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\validation_manifest.csv')
    parser.add_argument('--test-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\test_manifest.csv')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_ce_v2_calibrated_gpu')
    parser.add_argument('--init-checkpoint', default='', help='Optional checkpoint path to warm-start from before training.')
    parser.add_argument('--backbone-name', choices=list(SUPPORTED_BACKBONES), default='squeezenet11')
    parser.add_argument('--augment-profile', choices=['safe', 'aggressive'], default='safe')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--head-epochs', type=int, default=6)
    parser.add_argument('--finetune-epochs', type=int, default=8)
    parser.add_argument('--head-lr', type=float, default=1e-3)
    parser.add_argument('--finetune-lr', type=float, default=2e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-4)
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--sample-rate', type=int, default=22050)
    parser.add_argument('--sample-secs', type=float, default=2.4)
    parser.add_argument('--eval-window-count', type=int, default=1)
    parser.add_argument('--eval-window-aggregation', choices=list(EVAL_WINDOW_AGGREGATIONS), default='mean')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=0.0)
    parser.add_argument('--eval-window-support-threshold', type=float, default=0.40)
    parser.add_argument('--eval-window-min-support-windows', type=int, default=2)
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=0.55)
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=1)
    parser.add_argument('--n-fft', type=int, default=1024)
    parser.add_argument('--hop-length', type=int, default=256)
    parser.add_argument('--n-mels', type=int, default=128)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--label-smoothing', type=float, default=0.03)
    parser.add_argument('--class-weight-mode', choices=['none', 'inverse_freq', 'inverse_sqrt'], default='none')
    parser.add_argument('--weighted-sampler', action='store_true', default=False)
    parser.add_argument('--no-weighted-sampler', dest='weighted_sampler', action='store_false')
    parser.add_argument('--sample-weight-mode', choices=['class_balanced', 'technique_focus'], default='class_balanced')
    parser.add_argument('--head-mix-boost', type=float, default=1.0)
    parser.add_argument('--breathy-mix-boost', type=float, default=1.0)
    parser.add_argument('--control-negative-boost', type=float, default=1.0)
    parser.add_argument('--falsetto-negative-boost', type=float, default=1.0)
    parser.add_argument('--breathy-negative-boost', type=float, default=1.0)
    parser.add_argument('--other-negative-boost', type=float, default=1.0)
    parser.add_argument('--loss-weight-mode', choices=['none', 'technique_focus'], default='none')
    parser.add_argument('--head-mix-loss-boost', type=float, default=1.0)
    parser.add_argument('--breathy-mix-loss-boost', type=float, default=1.0)
    parser.add_argument('--control-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--falsetto-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--breathy-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--other-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--selection-metric', choices=['acc', 'balanced_acc', 'macro_f1', 'mix_f1', 'mix_precision', 'mix_recall', 'product_proxy'], default='balanced_acc')
    parser.add_argument('--threshold-min', type=float, default=0.25)
    parser.add_argument('--threshold-max', type=float, default=0.70)
    parser.add_argument('--threshold-step', type=float, default=0.025)
    parser.add_argument('--min-positive-mix-rate', type=float, default=0.0)
    parser.add_argument('--max-control-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-breathy-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-falsetto-negative-rate', type=float, default=1.0)
    parser.add_argument('--product-proxy-positive-weight', type=float, default=0.35)
    parser.add_argument('--product-proxy-control-penalty', type=float, default=0.30)
    parser.add_argument('--product-proxy-breathy-penalty', type=float, default=0.20)
    parser.add_argument('--product-proxy-falsetto-penalty', type=float, default=0.15)
    args = parser.parse_args()

    cfg = TrainConfig(
        train_manifest=Path(args.train_manifest),
        validation_manifest=Path(args.validation_manifest),
        test_manifest=Path(args.test_manifest),
        output_dir=Path(args.output_dir),
        init_checkpoint=Path(args.init_checkpoint) if str(args.init_checkpoint or '').strip() else None,
        backbone_name=args.backbone_name,
        augment_profile=args.augment_profile,
        batch_size=args.batch_size,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        head_lr=args.head_lr,
        finetune_lr=args.finetune_lr,
        weight_decay=args.weight_decay,
        image_size=args.image_size,
        sample_rate=args.sample_rate,
        sample_secs=args.sample_secs,
        eval_window_count=args.eval_window_count,
        eval_window_aggregation=args.eval_window_aggregation,
        eval_window_consistency_penalty=args.eval_window_consistency_penalty,
        eval_window_support_threshold=args.eval_window_support_threshold,
        eval_window_min_support_windows=args.eval_window_min_support_windows,
        eval_window_high_support_threshold=args.eval_window_high_support_threshold,
        eval_window_min_high_support_windows=args.eval_window_min_high_support_windows,
        n_fft=args.n_fft,
        hop_length=args.hop_length,
        n_mels=args.n_mels,
        num_workers=args.num_workers,
        seed=args.seed,
        label_smoothing=args.label_smoothing,
        class_weight_mode=args.class_weight_mode,
        weighted_sampler=bool(args.weighted_sampler),
        sample_weight_mode=args.sample_weight_mode,
        head_mix_boost=args.head_mix_boost,
        breathy_mix_boost=args.breathy_mix_boost,
        control_negative_boost=args.control_negative_boost,
        falsetto_negative_boost=args.falsetto_negative_boost,
        breathy_negative_boost=args.breathy_negative_boost,
        other_negative_boost=args.other_negative_boost,
        loss_weight_mode=args.loss_weight_mode,
        head_mix_loss_boost=args.head_mix_loss_boost,
        breathy_mix_loss_boost=args.breathy_mix_loss_boost,
        control_negative_loss_boost=args.control_negative_loss_boost,
        falsetto_negative_loss_boost=args.falsetto_negative_loss_boost,
        breathy_negative_loss_boost=args.breathy_negative_loss_boost,
        other_negative_loss_boost=args.other_negative_loss_boost,
        selection_metric=args.selection_metric,
        threshold_min=args.threshold_min,
        threshold_max=args.threshold_max,
        threshold_step=args.threshold_step,
        min_positive_mix_rate=args.min_positive_mix_rate,
        max_control_negative_rate=args.max_control_negative_rate,
        max_breathy_negative_rate=args.max_breathy_negative_rate,
        max_falsetto_negative_rate=args.max_falsetto_negative_rate,
        product_proxy_positive_weight=args.product_proxy_positive_weight,
        product_proxy_control_penalty=args.product_proxy_control_penalty,
        product_proxy_breathy_penalty=args.product_proxy_breathy_penalty,
        product_proxy_falsetto_penalty=args.product_proxy_falsetto_penalty,
    )
    best_path = run_training(cfg)
    print(f'best_checkpoint={best_path}')


if __name__ == '__main__':
    main()