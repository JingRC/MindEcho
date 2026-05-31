"""Train LateFusion SqueezeNet for breath binary classification (2.4s windows).

Reuses the same mel+spectral pipeline as mix binary V6.
Target: breath column from breath_binary_core manifest.
"""

import argparse
import csv
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                              classification_report, confusion_matrix,
                              f1_score, precision_score, recall_score)
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

SEED = 42
BREATH_LABEL = 1
NON_BREATH_LABEL = 0
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
SUPPORTED_BACKBONES = ('squeezenet11', 'mobilenet_v3_small', 'efficientnet_b0')


# ── Utilities (copied from train_mix_binary_squeezenet_latefusion.py) ────

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_manifest(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def compute_spectral_features(audio: np.ndarray, sample_rate: int) -> np.ndarray:
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


def build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 128,
                         fmin: float = 30.0, fmax: float | None = None) -> torch.Tensor:
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
            filterbank[mel_idx - 1, left:center] = np.linspace(
                0.0, 1.0, max(center - left, 1), endpoint=False, dtype=np.float32)
        if right > center:
            filterbank[mel_idx - 1, center:right] = np.linspace(
                1.0, 0.0, max(right - center, 1), endpoint=False, dtype=np.float32)
    return torch.from_numpy(filterbank)


def mel_tensor_from_audio(audio: np.ndarray, sample_rate: int, image_size: int,
                          n_fft: int, hop_length: int, n_mels: int) -> torch.Tensor:
    waveform = torch.as_tensor(np.asarray(audio, dtype=np.float32).reshape(-1))
    if waveform.numel() < n_fft:
        waveform = torch.nn.functional.pad(waveform, (0, n_fft - waveform.numel()))
    window = torch.hann_window(n_fft)
    stft = torch.stft(
        waveform, n_fft=n_fft, hop_length=hop_length, win_length=n_fft,
        window=window, center=True, return_complex=True,
    )
    power = stft.abs().pow(2.0)
    mel_filter = build_mel_filterbank(sample_rate=sample_rate, n_fft=n_fft, n_mels=n_mels)
    mel_spec = torch.matmul(mel_filter, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if mel_spec.numel() else 0.0
    if peak > 0.0:
        mel_spec = mel_spec / peak
    rgb = torch.stack((mel_spec, mel_spec, mel_spec), dim=0).to(dtype=torch.float32)
    rgb = torch.nn.functional.interpolate(rgb.unsqueeze(0), size=(image_size, image_size),
                                           mode='bilinear', align_corners=False).squeeze(0)
    return rgb


# ── Audio loading ───────────────────────────────────────────────────────

def _select_window_bounds(total_length: int, target_length: int, train: bool,
                          anchor_ratio: float | None = None) -> tuple:
    total = max(0, int(total_length))
    target = max(1, int(target_length))
    if total <= target:
        return 0, total
    if anchor_ratio is not None:
        start = int(round((total - target) * min(1.0, max(0.0, float(anchor_ratio)))))
        return start, start + target
    if train:
        start = random.randint(0, total - target)
    else:
        start = (total - target) // 2
    return start, start + target


def read_audio(path: Path, target_sr: int, *, target_length: int | None = None,
               train: bool = False, anchor_ratio: float | None = None) -> np.ndarray:
    import wave
    from scipy.io import wavfile
    from scipy import signal as scipy_signal
    try:
        sample_rate, audio = wavfile.read(str(path), mmap=False)
    except Exception:
        with wave.open(str(path), 'rb') as h:
            sample_rate = int(h.getframerate())
            channels = int(h.getnchannels())
            sample_width = int(h.getsampwidth())
            frame_count = int(h.getnframes())
            if target_length is not None:
                src_len = max(1, int(np.ceil(float(target_length) * float(sample_rate) / float(target_sr))))
                start, end = _select_window_bounds(frame_count, src_len, train,
                                                    anchor_ratio=anchor_ratio)
                h.setpos(start)
                raw = h.readframes(end - start)
            else:
                raw = h.readframes(frame_count)
            if sample_width == 1:
                audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                audio = (audio - 128.0) / 128.0
            elif sample_width == 2:
                audio = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
            elif sample_width == 3:
                packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
                values = (packed[:, 0].astype(np.int32)
                          | (packed[:, 1].astype(np.int32) << 8)
                          | (packed[:, 2].astype(np.int32) << 16))
                sign_mask = 1 << 23
                values = (values ^ sign_mask) - sign_mask
                audio = values.astype(np.float32) / float(sign_mask)
            elif sample_width == 4:
                audio = np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f'Unsupported sample width: {sample_width}')
    if audio.ndim > 1:
        audio = np.asarray(audio, dtype=np.float32).mean(axis=1)
    if np.issubdtype(audio.dtype, np.integer):
        audio = np.asarray(audio, dtype=np.float32) / float(np.iinfo(audio.dtype).max)
    if sample_rate != target_sr:
        audio = scipy_signal.resample_poly(audio, target_sr, sample_rate).astype(np.float32)
    if target_length is not None:
        if len(audio) >= target_length:
            if train:
                start = random.randint(0, len(audio) - target_length)
            else:
                start = (len(audio) - target_length) // 2
            audio = audio[start:start + target_length]
        else:
            padded = np.zeros(target_length, dtype=np.float32)
            start_pad = 0 if train else (target_length - len(audio)) // 2
            padded[start_pad:start_pad + len(audio)] = audio
            audio = padded
    return np.asarray(audio, dtype=np.float32)


# ── Dataset ──────────────────────────────────────────────────────────────

class BreathBinaryLateFusionDataset(Dataset):
    def __init__(self, rows, *, sample_rate, sample_secs, image_size,
                 n_fft, hop_length, n_mels, transform, train,
                 eval_anchor_ratios=None):
        self.rows = list(rows)
        self.sample_rate = sample_rate
        self.target_length = int(round(sample_rate * sample_secs))
        self.image_size = image_size
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.transform = transform
        self.train = train
        self.eval_anchor_ratios = tuple(float(r) for r in (eval_anchor_ratios or (0.5,)))

    def __len__(self):
        return len(self.rows)

    def _load_item(self, row, anchor_ratio=None):
        audio = read_audio(Path(row['wav_path']), self.sample_rate,
                           target_length=self.target_length, train=self.train,
                           anchor_ratio=anchor_ratio)
        mel = mel_tensor_from_audio(audio, self.sample_rate, self.image_size,
                                     self.n_fft, self.hop_length, self.n_mels)
        spectral = compute_spectral_features(audio, self.sample_rate)
        spectral_t = torch.from_numpy(spectral)
        if self.transform is not None:
            mel = self.transform(mel)
        return mel, spectral_t

    def __getitem__(self, index):
        row = self.rows[index]
        if (not self.train) and len(self.eval_anchor_ratios) > 1:
            mels, specs = [], []
            for r in self.eval_anchor_ratios:
                m, s = self._load_item(row, anchor_ratio=r)
                mels.append(m)
                specs.append(s)
            return torch.stack(mels, dim=0), torch.stack(specs, dim=0), int(float(row.get('breath', 0) or 0))
        anchor = None if self.train else self.eval_anchor_ratios[0]
        mel, spec = self._load_item(row, anchor_ratio=anchor)
        return mel, spec, int(float(row.get('breath', 0) or 0))


# ── Model ────────────────────────────────────────────────────────────────

class SpectralEncoder(nn.Module):
    def __init__(self, input_dim=3, output_dim=16):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, output_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class LateFusionSqueezeNet(nn.Module):
    def __init__(self, num_classes=2, backbone_name='squeezenet11',
                 spectral_dim=16, fusion_dropout=0.3):
        super().__init__()
        self.backbone_name = str(backbone_name or 'squeezenet11').strip().lower()
        if self.backbone_name == 'squeezenet11':
            try:
                weights = models.SqueezeNet1_1_Weights.DEFAULT
                self.backbone = models.squeezenet1_1(weights=weights)
            except Exception:
                self.backbone = models.squeezenet1_1(weights=None)
            self.backbone.classifier[1] = nn.Identity()
            self._backbone_dim = 512
        elif self.backbone_name == 'mobilenet_v3_small':
            try:
                weights = models.MobileNet_V3_Small_Weights.DEFAULT
                self.backbone = models.mobilenet_v3_small(weights=weights)
            except Exception:
                self.backbone = models.mobilenet_v3_small(weights=None)
            self._backbone_dim = 576
        elif self.backbone_name == 'efficientnet_b0':
            try:
                weights = models.EfficientNet_B0_Weights.DEFAULT
                self.backbone = models.efficientnet_b0(weights=weights)
            except Exception:
                self.backbone = models.efficientnet_b0(weights=None)
            self._backbone_dim = 1280
        else:
            raise ValueError(f'Unknown backbone: {backbone_name}')
        self.num_classes = num_classes
        self.spectral_encoder = SpectralEncoder(input_dim=3, output_dim=spectral_dim)
        fusion_input = self._backbone_dim + spectral_dim
        self.fusion_head = nn.Sequential(
            nn.Linear(fusion_input, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(fusion_dropout),
            nn.Linear(128, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, num_classes),
        )
        self._backbone_name = self.backbone_name
        setattr(self, '_is_latefusion', True)

    def forward_features(self, x):
        features = self.backbone.features(x)
        return torch.nn.functional.adaptive_avg_pool2d(features, (1, 1)).flatten(1)

    def forward(self, mel_images, spectral_features):
        if mel_images.dim() == 5:
            B, W, C, H, W_img = mel_images.shape
            mel_flat = mel_images.view(B * W, C, H, W_img)
            spec_flat = spectral_features.view(B * W, -1) if spectral_features.dim() == 3 else spectral_features
            backbone_emb = self.forward_features(mel_flat)
            spec_emb = self.spectral_encoder(spec_flat)
            fused = torch.cat([backbone_emb, spec_emb], dim=1)
            logits = self.fusion_head(fused)
            return logits.view(B, W, -1)
        backbone_emb = self.forward_features(mel_images)
        spec_emb = self.spectral_encoder(spectral_features)
        fused = torch.cat([backbone_emb, spec_emb], dim=1)
        return self.fusion_head(fused)


# ── Training ─────────────────────────────────────────────────────────────

def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for mel, spec, labels in loader:
        mel = mel.to(device)
        spec = spec.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        logits = model(mel, spec)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * labels.size(0)
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += labels.size(0)
    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_probs, all_labels = [], []
    for mel, spec, labels in loader:
        mel = mel.to(device)
        spec = spec.to(device)
        labels = labels.to(device)
        logits = model(mel, spec)
        loss = criterion(logits, labels)
        total_loss += loss.item() * labels.size(0)
        probs = F.softmax(logits, dim=1)
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += labels.size(0)
        all_probs.append(probs[:, BREATH_LABEL].cpu().numpy())
        all_labels.append(labels.cpu().numpy())
    y_prob = np.concatenate(all_probs)
    y_true = np.concatenate(all_labels)
    return total_loss / total, correct / total, y_true, y_prob


def find_best_threshold(y_true, y_prob):
    """Find threshold that maximizes balanced accuracy."""
    best_ba, best_thr = 0.0, 0.5
    for thr in np.arange(0.10, 0.85, 0.025):
        y_pred = (y_prob >= thr).astype(int)
        ba = balanced_accuracy_score(y_true, y_pred)
        if ba > best_ba:
            best_ba, best_thr = ba, float(thr)
    return best_thr, best_ba


@dataclass
class TrainConfig:
    train_manifest: Path
    validation_manifest: Path
    test_manifest: Path
    output_dir: Path
    backbone_name: str = 'squeezenet11'
    batch_size: int = 32
    head_epochs: int = 10
    finetune_epochs: int = 15
    head_lr: float = 1e-3
    finetune_lr: float = 2e-4
    weight_decay: float = 1e-4
    image_size: int = 224
    sample_rate: int = 22050
    sample_secs: float = 2.4
    spectral_dim: int = 16
    fusion_dropout: float = 0.3
    eval_window_count: int = 1
    n_fft: int = 1024
    hop_length: int = 256
    n_mels: int = 128
    num_workers: int = 0
    seed: int = SEED


def run_training(cfg: TrainConfig) -> Path:
    set_seed(cfg.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Device: {device}')

    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    train_rows = load_manifest(cfg.train_manifest)
    val_rows = load_manifest(cfg.validation_manifest)
    test_rows = load_manifest(cfg.test_manifest)

    train_labels = [int(float(r.get('breath', 0) or 0)) for r in train_rows]
    val_labels = [int(float(r.get('breath', 0) or 0)) for r in val_rows]
    test_labels = [int(float(r.get('breath', 0) or 0)) for r in test_rows]

    print(f'Train: {len(train_rows)} (breath={sum(train_labels)}, non-breath={len(train_rows)-sum(train_labels)})')
    print(f'Val:   {len(val_rows)} (breath={sum(val_labels)}, non-breath={len(val_rows)-sum(val_labels)})')
    print(f'Test:  {len(test_rows)} (breath={sum(test_labels)}, non-breath={len(test_rows)-sum(test_labels)})')

    eval_anchors = tuple(float(r) for r in np.linspace(0.0, 1.0, cfg.eval_window_count, dtype=np.float32).tolist())

    transform = transforms.Compose([
        transforms.Normalize(mean=MEAN, std=STD),
    ])

    ds_kwargs = dict(sample_rate=cfg.sample_rate, sample_secs=cfg.sample_secs,
                     image_size=cfg.image_size, n_fft=cfg.n_fft,
                     hop_length=cfg.hop_length, n_mels=cfg.n_mels)
    train_ds = BreathBinaryLateFusionDataset(train_rows, transform=transform, train=True, **ds_kwargs)
    val_ds = BreathBinaryLateFusionDataset(val_rows, transform=transform, train=False,
                                            eval_anchor_ratios=eval_anchors, **ds_kwargs)
    test_ds = BreathBinaryLateFusionDataset(test_rows, transform=transform, train=False,
                                             eval_anchor_ratios=eval_anchors, **ds_kwargs)

    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True,
                              num_workers=cfg.num_workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False,
                            num_workers=cfg.num_workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False,
                             num_workers=cfg.num_workers, pin_memory=True)

    model = LateFusionSqueezeNet(num_classes=2, backbone_name=cfg.backbone_name,
                                  spectral_dim=cfg.spectral_dim, fusion_dropout=cfg.fusion_dropout)
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    history: List[dict] = []
    best_val_score = -1.0
    best_epoch = 0
    best_state = None

    start_time = time.time()

    # ── Stage 1: Head-only training (frozen backbone) ──
    print('\n=== Stage 1: Head training (frozen backbone) ===')
    for name, param in model.named_parameters():
        if 'backbone' in name:
            param.requires_grad = False
        else:
            param.requires_grad = True
    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad],
        lr=cfg.head_lr, weight_decay=cfg.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.head_epochs)

    for epoch in range(1, cfg.head_epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, y_true, y_prob = evaluate(model, val_loader, criterion, device)
        thr, ba = find_best_threshold(y_true, y_prob)
        f1 = f1_score(y_true, (y_prob >= thr).astype(int))
        scheduler.step()
        lr = optimizer.param_groups[0]['lr']
        history.append({'epoch': epoch, 'stage': 'head', 'train_loss': train_loss,
                        'train_acc': train_acc, 'val_loss': val_loss,
                        'val_acc': val_acc, 'val_balanced_acc': ba,
                        'val_f1': f1, 'val_threshold': thr, 'lr': lr})
        print(f'  Epoch {epoch}: train_loss={train_loss:.4f} train_acc={train_acc:.4f} '
              f'val_loss={val_loss:.4f} val_acc={val_acc:.4f} val_ba={ba:.4f} '
              f'val_f1={f1:.4f} thr={thr:.3f} lr={lr:.6f}')
        if ba > best_val_score:
            best_val_score = ba
            best_epoch = epoch
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # ── Stage 2: Finetune (unfrozen backbone) ──
    print('\n=== Stage 2: Finetune (unfrozen backbone) ===')
    for param in model.parameters():
        param.requires_grad = True
    # Reload best head state before finetuning
    if best_state is not None:
        model.load_state_dict(best_state)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.finetune_lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.finetune_epochs)
    best_val_score = -1.0  # Reset for finetune stage

    for epoch in range(1, cfg.finetune_epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, y_true, y_prob = evaluate(model, val_loader, criterion, device)
        thr, ba = find_best_threshold(y_true, y_prob)
        f1 = f1_score(y_true, (y_prob >= thr).astype(int))
        scheduler.step()
        lr = optimizer.param_groups[0]['lr']
        history.append({'epoch': epoch, 'stage': 'finetune', 'train_loss': train_loss,
                        'train_acc': train_acc, 'val_loss': val_loss,
                        'val_acc': val_acc, 'val_balanced_acc': ba,
                        'val_f1': f1, 'val_threshold': thr, 'lr': lr})
        print(f'  Epoch {epoch}: train_loss={train_loss:.4f} train_acc={train_acc:.4f} '
              f'val_loss={val_loss:.4f} val_acc={val_acc:.4f} val_ba={ba:.4f} '
              f'val_f1={f1:.4f} thr={thr:.3f} lr={lr:.6f}')
        if ba > best_val_score:
            best_val_score = ba
            best_epoch = epoch
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            best_thr = thr

    duration = time.time() - start_time

    # ── Final evaluation on test set ──
    model.load_state_dict(best_state)
    test_loss, test_acc, y_true, y_prob = evaluate(model, test_loader, criterion, device)
    y_pred = (y_prob >= best_thr).astype(int)
    report = classification_report(y_true, y_pred,
                                    target_names=['non_breath', 'breath'],
                                    output_dict=True)
    cm = confusion_matrix(y_true, y_pred)

    print(f'\n=== Test Results ===')
    print(f'Threshold: {best_thr:.3f}')
    print(f'Accuracy: {test_acc:.4f}')
    print(f'F1 (breath): {report["breath"]["f1-score"]:.4f}')
    print(f'Precision (breath): {report["breath"]["precision"]:.4f}')
    print(f'Recall (breath): {report["breath"]["recall"]:.4f}')
    print(f'Confusion matrix:\n{cm}')

    # ── Save checkpoint ──
    checkpoint = {
        'model_state_dict': best_state,
        'threshold': best_thr,
        'config': {k: str(v) if isinstance(v, Path) else v for k, v in vars(cfg).items()},
    }
    best_path = cfg.output_dir / 'best_breath_binary_latefusion.pt'
    torch.save(checkpoint, best_path)

    # Save history CSV
    history_path = cfg.output_dir / 'history.csv'
    with open(history_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)

    # Save training summary
    summary = {
        'device': str(device),
        'task': 'breath_binary_latefusion',
        'model_type': 'squeezenet_latefusion',
        'backbone_name': cfg.backbone_name,
        'image_size': cfg.image_size,
        'sample_rate': cfg.sample_rate,
        'sample_secs': cfg.sample_secs,
        'spectral_dim': cfg.spectral_dim,
        'fusion_dropout': cfg.fusion_dropout,
        'best_epoch': best_epoch,
        'best_threshold': best_thr,
        'best_val_score': best_val_score,
        'test_acc': test_acc,
        'test_loss': test_loss,
        'test_metrics': {
            'acc': test_acc,
            'balanced_acc': balanced_accuracy_score(y_true, y_pred),
            'f1': f1_score(y_true, y_pred),
            'precision': precision_score(y_true, y_pred),
            'recall': recall_score(y_true, y_pred),
        },
        'confusion_matrix': cm.tolist(),
        'classification_report': report,
        'duration_sec': duration,
        'history': history,
        'checkpoint': str(best_path),
    }
    summary_path = cfg.output_dir / 'training_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f'\nBest checkpoint: {best_path}')
    print(f'Duration: {duration:.1f}s')
    return best_path


def main():
    parser = argparse.ArgumentParser(description='Train LateFusion SqueezeNet for breath binary classification')
    parser.add_argument('--train-manifest',
                        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\breath_binary_core\train_manifest.csv')
    parser.add_argument('--validation-manifest',
                        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\breath_binary_core\validation_manifest.csv')
    parser.add_argument('--test-manifest',
                        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\breath_binary_core\test_manifest.csv')
    parser.add_argument('--output-dir',
                        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\breath_binary_latefusion_v1')
    parser.add_argument('--backbone-name', choices=list(SUPPORTED_BACKBONES), default='squeezenet11')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--head-epochs', type=int, default=10)
    parser.add_argument('--finetune-epochs', type=int, default=15)
    parser.add_argument('--head-lr', type=float, default=1e-3)
    parser.add_argument('--finetune-lr', type=float, default=2e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-4)
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--sample-rate', type=int, default=22050)
    parser.add_argument('--sample-secs', type=float, default=2.4)
    parser.add_argument('--spectral-dim', type=int, default=16)
    parser.add_argument('--fusion-dropout', type=float, default=0.3)
    parser.add_argument('--eval-window-count', type=int, default=1)
    parser.add_argument('--n-fft', type=int, default=1024)
    parser.add_argument('--hop-length', type=int, default=256)
    parser.add_argument('--n-mels', type=int, default=128)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args()

    cfg = TrainConfig(
        train_manifest=Path(args.train_manifest),
        validation_manifest=Path(args.validation_manifest),
        test_manifest=Path(args.test_manifest),
        output_dir=Path(args.output_dir),
        backbone_name=args.backbone_name,
        batch_size=args.batch_size,
        head_epochs=args.head_epochs, finetune_epochs=args.finetune_epochs,
        head_lr=args.head_lr, finetune_lr=args.finetune_lr,
        weight_decay=args.weight_decay,
        image_size=args.image_size, sample_rate=args.sample_rate, sample_secs=args.sample_secs,
        spectral_dim=args.spectral_dim, fusion_dropout=args.fusion_dropout,
        eval_window_count=args.eval_window_count,
        n_fft=args.n_fft, hop_length=args.hop_length, n_mels=args.n_mels,
        num_workers=args.num_workers, seed=args.seed,
    )
    best_path = run_training(cfg)
    print(f'best_checkpoint={best_path}')


if __name__ == '__main__':
    main()
