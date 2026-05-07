import argparse
import csv
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
from PIL import Image
from scipy import signal
from scipy.io import wavfile
from sklearn.metrics import f1_score, precision_score, recall_score
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


DEFAULT_LABELS = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_manifest(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def read_audio(path: Path, target_sr: int) -> np.ndarray:
    sample_rate, audio = wavfile.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if np.issubdtype(audio.dtype, np.integer):
        max_val = float(np.iinfo(audio.dtype).max)
        audio = audio.astype(np.float32) / max_val
    else:
        audio = audio.astype(np.float32)
    if sample_rate != target_sr:
        audio = signal.resample_poly(audio, target_sr, sample_rate).astype(np.float32)
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


def spectrogram_image(audio: np.ndarray, sample_rate: int, image_size: int, n_fft: int, hop_length: int) -> Image.Image:
    _, _, spec = signal.stft(
        audio,
        fs=sample_rate,
        nperseg=n_fft,
        noverlap=max(0, n_fft - hop_length),
        padded=False,
        boundary=None,
    )
    spec = np.abs(spec)
    spec = np.log1p(spec)
    spec -= spec.min()
    if spec.max() > 0:
        spec = spec / spec.max()
    image = (spec * 255.0).clip(0, 255).astype(np.uint8)
    pil_image = Image.fromarray(image).convert('RGB')
    return pil_image.resize((image_size, image_size), Image.BILINEAR)


def build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int, fmin: float = 30.0, fmax: float | None = None) -> np.ndarray:
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
    return filterbank


def mel_spectrogram_image(audio: np.ndarray, sample_rate: int, image_size: int, n_fft: int, hop_length: int, n_mels: int) -> Image.Image:
    _, _, spec = signal.stft(
        audio,
        fs=sample_rate,
        nperseg=n_fft,
        noverlap=max(0, n_fft - hop_length),
        padded=False,
        boundary=None,
    )
    power = np.abs(spec).astype(np.float32) ** 2.0
    mel_filter = build_mel_filterbank(sample_rate=sample_rate, n_fft=n_fft, n_mels=n_mels)
    mel_spec = np.matmul(mel_filter, power)
    mel_spec = np.log10(np.clip(mel_spec, 1e-10, None))
    mel_spec -= mel_spec.min()
    if mel_spec.max() > 0:
        mel_spec = mel_spec / mel_spec.max()
    image = (mel_spec * 255.0).clip(0, 255).astype(np.uint8)
    pil_image = Image.fromarray(image).convert('RGB')
    return pil_image.resize((image_size, image_size), Image.BILINEAR)


class MultiLabelAudioDataset(Dataset):
    def __init__(self, rows: List[dict], label_names: List[str], sample_rate: int, sample_secs: float, image_size: int, n_fft: int, hop_length: int, n_mels: int, frontend: str, train: bool):
        self.rows = rows
        self.label_names = label_names
        self.sample_rate = sample_rate
        self.target_length = int(sample_rate * sample_secs)
        self.image_size = image_size
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.frontend = frontend
        self.train = train
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=MEAN, std=STD),
        ])

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        audio = read_audio(Path(row['wav_path']), self.sample_rate)
        audio = crop_or_pad(audio, self.target_length, train=self.train)
        if self.frontend == 'mel':
            image = mel_spectrogram_image(audio, self.sample_rate, self.image_size, self.n_fft, self.hop_length, self.n_mels)
        else:
            image = spectrogram_image(audio, self.sample_rate, self.image_size, self.n_fft, self.hop_length)
        tensor = self.transform(image)
        labels = np.array([float(row[name]) for name in self.label_names], dtype=np.float32)
        return tensor, torch.from_numpy(labels)


@dataclass
class TrainConfig:
    train_manifest: Path
    validation_manifest: Path
    test_manifest: Path
    output_dir: Path
    label_names: List[str]
    batch_size: int = 24
    head_epochs: int = 4
    finetune_epochs: int = 6
    head_lr: float = 1e-3
    finetune_lr: float = 2e-4
    weight_decay: float = 1e-4
    sample_rate: int = 22050
    sample_secs: float = 2.8
    image_size: int = 224
    n_fft: int = 1024
    hop_length: int = 256
    n_mels: int = 128
    frontend: str = 'stft'
    num_workers: int = 0
    seed: int = 42
    pos_weight_cap: float = 4.0
    threshold_min: float = 0.25
    threshold_max: float = 0.85
    threshold_step: float = 0.05


def build_model(num_labels: int) -> nn.Module:
    try:
        weights = models.SqueezeNet1_1_Weights.DEFAULT
        model = models.squeezenet1_1(weights=weights)
    except Exception:
        model = models.squeezenet1_1(weights=None)
    model.classifier[1] = nn.Conv2d(512, num_labels, kernel_size=1)
    model.num_classes = num_labels
    return model


def set_feature_trainable(model: nn.Module, trainable: bool) -> None:
    for param in model.features.parameters():
        param.requires_grad = trainable


def build_pos_weight(rows: List[dict], label_names: List[str], cap: float) -> torch.Tensor:
    positives = np.array([sum(float(row[name]) for row in rows) for name in label_names], dtype=np.float32)
    negatives = max(1, len(rows)) - positives
    weights = negatives / np.maximum(positives, 1.0)
    weights = np.clip(weights, 1.0, float(cap))
    return torch.tensor(weights, dtype=torch.float32)


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        logits = torch.flatten(logits, 1)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += float(loss.item()) * int(images.size(0))
    return total_loss / max(1, len(loader.dataset))


def _compute_metrics(targets: np.ndarray, probs: np.ndarray, thresholds: np.ndarray) -> Tuple[Dict[str, float], Dict[int, Dict[str, float]]]:
    preds = (probs >= thresholds[None, :]).astype(np.int32)
    metrics = {
        'macro_f1': float(f1_score(targets, preds, average='macro', zero_division=0)),
        'macro_precision': float(precision_score(targets, preds, average='macro', zero_division=0)),
        'macro_recall': float(recall_score(targets, preds, average='macro', zero_division=0)),
    }
    per_label = {}
    for index in range(targets.shape[1]):
        per_label[index] = {
            'f1': float(f1_score(targets[:, index], preds[:, index], zero_division=0)),
            'precision': float(precision_score(targets[:, index], preds[:, index], zero_division=0)),
            'recall': float(recall_score(targets[:, index], preds[:, index], zero_division=0)),
            'positive_rate': float(targets[:, index].mean()),
            'predicted_positive_rate': float(preds[:, index].mean()),
            'threshold': float(thresholds[index]),
        }
    return metrics, per_label


def find_best_thresholds(targets: np.ndarray, probs: np.ndarray, cfg: TrainConfig) -> np.ndarray:
    candidates = np.arange(cfg.threshold_min, cfg.threshold_max + 1e-9, cfg.threshold_step, dtype=np.float32)
    thresholds = np.full((targets.shape[1],), 0.5, dtype=np.float32)
    for index in range(targets.shape[1]):
        best_threshold = 0.5
        best_f1 = -1.0
        for candidate in candidates:
            preds = (probs[:, index] >= candidate).astype(np.int32)
            score = f1_score(targets[:, index], preds, zero_division=0)
            if score > best_f1:
                best_f1 = score
                best_threshold = float(candidate)
        thresholds[index] = best_threshold
    return thresholds


@torch.no_grad()
def evaluate(model, loader, criterion, device, thresholds: np.ndarray | None = None, cfg: TrainConfig | None = None):
    model.eval()
    total_loss = 0.0
    all_targets: List[np.ndarray] = []
    all_probs: List[np.ndarray] = []
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        logits = torch.flatten(logits, 1)
        loss = criterion(logits, labels)
        probs = torch.sigmoid(logits)
        total_loss += float(loss.item()) * int(images.size(0))
        all_targets.append(labels.cpu().numpy())
        all_probs.append(probs.cpu().numpy())
    targets = np.concatenate(all_targets, axis=0)
    probs = np.concatenate(all_probs, axis=0)
    if thresholds is None:
        if cfg is None:
            raise ValueError('cfg is required when thresholds is None')
        thresholds = find_best_thresholds(targets, probs, cfg)
    metrics, per_label = _compute_metrics(targets, probs, thresholds)
    metrics['loss'] = total_loss / max(1, len(loader.dataset))
    return metrics, per_label


def run_training(cfg: TrainConfig) -> Path:
    set_seed(cfg.seed)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    train_rows = load_manifest(cfg.train_manifest)
    valid_rows = load_manifest(cfg.validation_manifest)
    test_rows = load_manifest(cfg.test_manifest)

    train_ds = MultiLabelAudioDataset(train_rows, cfg.label_names, cfg.sample_rate, cfg.sample_secs, cfg.image_size, cfg.n_fft, cfg.hop_length, cfg.n_mels, cfg.frontend, train=True)
    valid_ds = MultiLabelAudioDataset(valid_rows, cfg.label_names, cfg.sample_rate, cfg.sample_secs, cfg.image_size, cfg.n_fft, cfg.hop_length, cfg.n_mels, cfg.frontend, train=False)
    test_ds = MultiLabelAudioDataset(test_rows, cfg.label_names, cfg.sample_rate, cfg.sample_secs, cfg.image_size, cfg.n_fft, cfg.hop_length, cfg.n_mels, cfg.frontend, train=False)

    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers)
    valid_loader = DataLoader(valid_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    test_loader = DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = build_model(len(cfg.label_names)).to(device)
    pos_weight = build_pos_weight(train_rows, cfg.label_names, cap=cfg.pos_weight_cap).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    history = []
    best_path = cfg.output_dir / 'best_multitech_squeezenet.pt'
    best_valid_f1 = -1.0
    best_thresholds = np.full((len(cfg.label_names),), 0.5, dtype=np.float32)

    set_feature_trainable(model, trainable=False)
    head_params = [param for param in model.parameters() if param.requires_grad]
    optimizer = torch.optim.AdamW(head_params, lr=cfg.head_lr, weight_decay=cfg.weight_decay)

    for stage_name, epochs, lr in (
        ('head', cfg.head_epochs, cfg.head_lr),
        ('finetune', cfg.finetune_epochs, cfg.finetune_lr),
    ):
        if stage_name == 'finetune':
            set_feature_trainable(model, trainable=True)
            optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=cfg.weight_decay)
        for epoch in range(1, epochs + 1):
            start_time = time.time()
            train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
            valid_metrics, valid_per_label = evaluate(model, valid_loader, criterion, device, thresholds=None, cfg=cfg)
            elapsed = time.time() - start_time
            row = {
                'stage': stage_name,
                'epoch': epoch,
                'train_loss': round(train_loss, 6),
                'valid_loss': round(valid_metrics['loss'], 6),
                'valid_macro_f1': round(valid_metrics['macro_f1'], 6),
                'valid_macro_precision': round(valid_metrics['macro_precision'], 6),
                'valid_macro_recall': round(valid_metrics['macro_recall'], 6),
                'elapsed_sec': round(elapsed, 2),
            }
            row['valid_thresholds'] = {
                cfg.label_names[index]: round(valid_per_label[index]['threshold'], 3)
                for index in range(len(cfg.label_names))
            }
            history.append(row)
            if valid_metrics['macro_f1'] > best_valid_f1:
                best_valid_f1 = valid_metrics['macro_f1']
                best_thresholds = np.array([valid_per_label[index]['threshold'] for index in range(len(cfg.label_names))], dtype=np.float32)
                torch.save(
                    {
                        'model_state_dict': model.state_dict(),
                        'label_names': cfg.label_names,
                        'config': cfg.__dict__,
                        'best_valid_macro_f1': best_valid_f1,
                        'best_thresholds': best_thresholds.tolist(),
                    },
                    best_path,
                )
            print(json.dumps(row, ensure_ascii=False), flush=True)

    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])
    checkpoint_thresholds = np.array(checkpoint.get('best_thresholds', best_thresholds.tolist()), dtype=np.float32)
    test_metrics, test_per_label = evaluate(model, test_loader, criterion, device, thresholds=checkpoint_thresholds, cfg=cfg)

    summary = {
        'label_names': cfg.label_names,
        'train_items': len(train_rows),
        'validation_items': len(valid_rows),
        'test_items': len(test_rows),
        'device': str(device),
        'frontend': cfg.frontend,
        'pos_weight_cap': cfg.pos_weight_cap,
        'best_valid_macro_f1': best_valid_f1,
        'best_thresholds': {cfg.label_names[index]: float(checkpoint_thresholds[index]) for index in range(len(cfg.label_names))},
        'test_metrics': test_metrics,
        'test_per_label': {cfg.label_names[index]: metrics for index, metrics in test_per_label.items()},
        'history': history,
    }
    (cfg.output_dir / 'training_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (cfg.output_dir / 'label_map.json').write_text(json.dumps({'labels': cfg.label_names}, ensure_ascii=False, indent=2), encoding='utf-8')
    return best_path


def main() -> None:
    parser = argparse.ArgumentParser(description='Train a lightweight multi-label GTSinger technique model.')
    parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_core\train_manifest.csv')
    parser.add_argument('--validation-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_core\validation_manifest.csv')
    parser.add_argument('--test-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_core\test_manifest.csv')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\multitech_squeezenet')
    parser.add_argument('--labels', default=','.join(DEFAULT_LABELS))
    parser.add_argument('--batch-size', type=int, default=24)
    parser.add_argument('--head-epochs', type=int, default=4)
    parser.add_argument('--finetune-epochs', type=int, default=6)
    parser.add_argument('--sample-secs', type=float, default=2.8)
    parser.add_argument('--frontend', choices=['stft', 'mel'], default='stft')
    parser.add_argument('--n-mels', type=int, default=128)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--pos-weight-cap', type=float, default=4.0)
    parser.add_argument('--threshold-min', type=float, default=0.25)
    parser.add_argument('--threshold-max', type=float, default=0.85)
    parser.add_argument('--threshold-step', type=float, default=0.05)
    args = parser.parse_args()

    cfg = TrainConfig(
        train_manifest=Path(args.train_manifest),
        validation_manifest=Path(args.validation_manifest),
        test_manifest=Path(args.test_manifest),
        output_dir=Path(args.output_dir),
        label_names=[label.strip() for label in args.labels.split(',') if label.strip()],
        batch_size=args.batch_size,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        sample_secs=args.sample_secs,
        frontend=args.frontend,
        n_mels=args.n_mels,
        num_workers=args.num_workers,
        seed=args.seed,
        pos_weight_cap=args.pos_weight_cap,
        threshold_min=args.threshold_min,
        threshold_max=args.threshold_max,
        threshold_step=args.threshold_step,
    )
    best_path = run_training(cfg)
    print(f'best_checkpoint={best_path}')


if __name__ == '__main__':
    main()