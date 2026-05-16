from __future__ import annotations

import argparse
import io
import json
import math
import wave
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms


PROJECT_ROOT = Path(__file__).resolve().parent

CURRENT_BINARY_CHECKPOINT_CANDIDATES = (
    PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts_mel_safe_v2' / 'best_squeezenet_binary.pt',
    PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'squeezenet_binary' / 'artifacts' / 'best_squeezenet_binary.pt',
)
REFERENCE_FOUR_CLASS_CHECKPOINT = (
    PROJECT_ROOT
    / 'ml_dl_models'
    / 'chest_falsetto'
    / 'reference_model'
    / 'squeezenet1_1_mel_2024-07-30_15-40-44'
    / 'save.pt'
)
DATASET_AUDIO_ZIP = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'dataset' / 'data' / 'audio.zip'
EXAMPLE_DIR = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'reference_model' / 'examples'

TARGET_SR = 22050
WINDOW_S = 0.64
HOP_S = 0.16
IMAGE_SIZE = 224
BATCH_SIZE = 24
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

FOUR_CLASS_LABELS = ('m_chest', 'f_chest', 'm_falsetto', 'f_falsetto')
FOUR_TO_BINARY = {
    'm_chest': 'chest',
    'f_chest': 'chest',
    'm_falsetto': 'falsetto',
    'f_falsetto': 'falsetto',
}
FOUR_TO_GENDER = {
    'm_chest': 'male',
    'm_falsetto': 'male',
    'f_chest': 'female',
    'f_falsetto': 'female',
}

UNLABELED_SAMPLES = {
    'female_lead_libai': PROJECT_ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '单依纯 - 李白 (Live)_人声_lead.wav',
    'male_lead_wuju': PROJECT_ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '林俊杰 - 无拘_人声_lead.wav',
    'dry_mic_phrase': PROJECT_ROOT / 'recordings' / 'recording_20260202_113327.wav',
    'dry_mic_short': PROJECT_ROOT / 'recordings' / 'recording_20260202_104455.wav',
}


def _build_transform() -> Any:
    return transforms.Compose(
        [
            transforms.ToPILImage(),
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(mean=MEAN, std=STD),
        ]
    )


def _find_existing_path(candidates: Iterable[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f'No existing checkpoint found in: {list(candidates)}')


def _build_squeezenet(num_classes: int, *, reference_four_class_head: bool = False) -> Any:
    model = models.squeezenet1_1(weights=None)
    if reference_four_class_head:
        model.classifier = torch.nn.Sequential(
            torch.nn.Dropout(p=0.5),
            torch.nn.Conv2d(512, 144, kernel_size=1),
            torch.nn.ReLU(inplace=True),
            torch.nn.AdaptiveAvgPool2d((1, 1)),
            torch.nn.Flatten(),
            torch.nn.Linear(144, 43),
            torch.nn.ReLU(inplace=True),
            torch.nn.Dropout(p=0.2),
            torch.nn.Linear(43, 13),
            torch.nn.ReLU(inplace=True),
            torch.nn.Linear(13, num_classes),
        )
    else:
        model.classifier[1] = torch.nn.Conv2d(512, num_classes, kernel_size=1)
    model.num_classes = num_classes
    return model


def _load_model(checkpoint_path: Path, num_classes: int, *, reference_four_class_head: bool = False) -> Any:
    model = _build_squeezenet(num_classes=num_classes, reference_four_class_head=reference_four_class_head)
    checkpoint = torch.load(str(checkpoint_path), map_location='cpu')
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        state_dict = checkpoint['model_state_dict']
    else:
        state_dict = checkpoint
    model.load_state_dict(state_dict)
    model.eval()
    return model


def _resample_audio(audio: np.ndarray, sample_rate: int, target_sample_rate: int) -> np.ndarray:
    y = np.asarray(audio, dtype=np.float32).reshape(-1)
    if y.size <= 1 or int(sample_rate) == int(target_sample_rate):
        return y.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly  # type: ignore

        gcd = math.gcd(int(sample_rate), int(target_sample_rate))
        up = int(target_sample_rate) // max(1, gcd)
        down = int(sample_rate) // max(1, gcd)
        return np.asarray(resample_poly(y, up, down), dtype=np.float32)
    except Exception:
        old_n = int(y.size)
        new_n = max(1, int(round(old_n * float(target_sample_rate) / float(sample_rate))))
        if old_n <= 1 or new_n <= 1:
            return y.astype(np.float32, copy=False)
        t_old = np.linspace(0.0, 1.0, old_n, endpoint=False, dtype=np.float32)
        t_new = np.linspace(0.0, 1.0, new_n, endpoint=False, dtype=np.float32)
        return np.asarray(np.interp(t_new, t_old, y), dtype=np.float32)


def _load_audio_from_path(path: Path) -> Tuple[np.ndarray, int]:
    try:
        if path.stat().st_size <= 512:
            prefix = path.read_text(encoding='utf-8', errors='ignore')
            if prefix.startswith('version https://git-lfs.github.com/spec/v1'):
                raise ValueError(f'git_lfs_pointer:{path}')
    except ValueError:
        raise
    except Exception:
        pass
    try:
        import soundfile as sf  # type: ignore

        audio, sample_rate = sf.read(str(path), dtype='float32')
        return np.asarray(audio, dtype=np.float32), int(sample_rate)
    except Exception:
        with wave.open(str(path), 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            sample_rate = int(wav_file.getframerate())
            channels = int(wav_file.getnchannels())
            sampwidth = int(wav_file.getsampwidth())
        audio = _decode_pcm_frames(frames, sampwidth=sampwidth, channels=channels)
        return audio, sample_rate


def _load_audio_from_zip(zip_file: zipfile.ZipFile, member: str) -> Tuple[np.ndarray, int]:
    raw = zip_file.read(member)
    try:
        import soundfile as sf  # type: ignore

        audio, sample_rate = sf.read(io.BytesIO(raw), dtype='float32')
        return np.asarray(audio, dtype=np.float32), int(sample_rate)
    except Exception:
        with wave.open(io.BytesIO(raw), 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            sample_rate = int(wav_file.getframerate())
            channels = int(wav_file.getnchannels())
            sampwidth = int(wav_file.getsampwidth())
        audio = _decode_pcm_frames(frames, sampwidth=sampwidth, channels=channels)
        return audio, sample_rate


def _decode_pcm_frames(frames: bytes, *, sampwidth: int, channels: int) -> np.ndarray:
    if sampwidth == 1:
        data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sampwidth == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        signed = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        sign_mask = signed & 0x800000
        signed = signed - (sign_mask << 1)
        data = signed.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f'Unsupported PCM sample width: {sampwidth}')
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return np.asarray(data, dtype=np.float32)


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = np.nan_to_num(y.reshape(-1), nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1.0:
        y = y / peak
    return y.astype(np.float32, copy=False)


def _make_windows(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    y = _normalize_audio(audio)
    if int(sample_rate) != TARGET_SR:
        y = _resample_audio(y, int(sample_rate), TARGET_SR)
    if y.size <= 0:
        return np.zeros((0, int(round(WINDOW_S * TARGET_SR))), dtype=np.float32)
    window_samples = max(1, int(round(WINDOW_S * TARGET_SR)))
    hop_samples = max(1, int(round(HOP_S * TARGET_SR)))
    if y.size < window_samples:
        padded = np.zeros(window_samples, dtype=np.float32)
        padded[: y.size] = y
        return padded.reshape(1, -1)
    max_start = max(0, int(y.size) - window_samples)
    starts = list(range(0, max_start + 1, hop_samples))
    if starts[-1] != max_start:
        starts.append(max_start)
    windows = []
    for start in starts:
        end = start + window_samples
        windows.append(np.asarray(y[start:end], dtype=np.float32))
    return np.stack(windows, axis=0).astype(np.float32)


def _hz_to_mel(value_hz: float) -> float:
    return 2595.0 * math.log10(1.0 + float(value_hz) / 700.0)


def _mel_to_hz(value_mel: float) -> float:
    return 700.0 * (10.0 ** (float(value_mel) / 2595.0) - 1.0)


def _build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 128) -> torch.Tensor:
    upper_hz = float(sample_rate) * 0.5
    mel_points = np.linspace(_hz_to_mel(30.0), _hz_to_mel(upper_hz), n_mels + 2, dtype=np.float32)
    hz_points = np.asarray([_mel_to_hz(float(item)) for item in mel_points], dtype=np.float32)
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


def _build_mel_image(signal: np.ndarray, sample_rate: int, mel_filter: torch.Tensor) -> np.ndarray:
    n_fft = 1024
    hop_length = 256
    waveform = torch.as_tensor(np.asarray(signal, dtype=np.float32).reshape(-1))
    if int(waveform.numel()) < n_fft:
        waveform = torch.nn.functional.pad(waveform, (0, n_fft - int(waveform.numel())))
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
    mel_spec = torch.matmul(mel_filter, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if int(mel_spec.numel()) > 0 else 0.0
    if peak > 0.0:
        mel_spec = mel_spec / peak
    mel_np = np.asarray(mel_spec.cpu().numpy(), dtype=np.float32)
    return np.stack([mel_np, mel_np, mel_np], axis=-1)


def _build_batch(windows: np.ndarray, transform: Any, mel_filter: torch.Tensor) -> torch.Tensor:
    tensors = []
    for window in windows:
        rgb = _build_mel_image(window, sample_rate=TARGET_SR, mel_filter=mel_filter)
        tensors.append(transform(rgb))
    return torch.stack(tensors, dim=0)


def _predict_probabilities(model: Any, batch: torch.Tensor) -> np.ndarray:
    probs = []
    with torch.no_grad():
        for start_idx in range(0, int(batch.size(0)), BATCH_SIZE):
            logits = model(batch[start_idx : start_idx + BATCH_SIZE])
            probs.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.concatenate(probs, axis=0) if probs else np.zeros((0, int(model.num_classes)), dtype=np.float32)


def _collapse_four_class_probabilities(probabilities: np.ndarray) -> Dict[str, float]:
    return {
        'chest': float(probabilities[0] + probabilities[1]),
        'falsetto': float(probabilities[2] + probabilities[3]),
        'male': float(probabilities[0] + probabilities[2]),
        'female': float(probabilities[1] + probabilities[3]),
    }


def _parse_four_class_label(file_name: str) -> Optional[str]:
    lower = str(file_name or '').lower()
    for label in FOUR_CLASS_LABELS:
        if label in lower:
            return label
    return None


def _pick_evenly(items: List[str], count: int) -> List[str]:
    if len(items) <= count:
        return list(items)
    indices = np.linspace(0, len(items) - 1, count, dtype=int)
    return [items[int(idx)] for idx in indices]


def _collect_dataset_members(zip_path: Path, per_class: int) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    with zipfile.ZipFile(str(zip_path), 'r') as zip_file:
        for member in zip_file.namelist():
            if not member.lower().endswith('.wav'):
                continue
            label = _parse_four_class_label(Path(member).name)
            if label:
                grouped[label].append(member)
    return {label: _pick_evenly(sorted(grouped.get(label, [])), per_class) for label in FOUR_CLASS_LABELS}


def _collect_eval_mel_members(zip_path: Path, per_class: int) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    with zipfile.ZipFile(str(zip_path), 'r') as zip_file:
        for member in zip_file.namelist():
            if '/mel/' not in member or not member.lower().endswith('.jpg'):
                continue
            label = _parse_four_class_label(Path(member).name)
            if label:
                grouped[label].append(member)
    return {label: _pick_evenly(sorted(grouped.get(label, [])), per_class) for label in FOUR_CLASS_LABELS}


def _evaluate_clip(
    *,
    sample_name: str,
    audio: np.ndarray,
    sample_rate: int,
    binary_model: Any,
    four_model: Any,
    transform: Any,
    mel_filter: torch.Tensor,
    ground_truth: Optional[str] = None,
) -> Dict[str, Any]:
    windows = _make_windows(audio, sample_rate)
    batch = _build_batch(windows, transform=transform, mel_filter=mel_filter)
    binary_probs = _predict_probabilities(binary_model, batch)
    four_probs = _predict_probabilities(four_model, batch)
    binary_mean = np.mean(binary_probs, axis=0) if binary_probs.size else np.zeros(2, dtype=np.float32)
    four_mean = np.mean(four_probs, axis=0) if four_probs.size else np.zeros(4, dtype=np.float32)
    top_window_labels = [FOUR_CLASS_LABELS[int(idx)] for idx in np.argmax(four_probs, axis=1)] if four_probs.size else []
    collapsed = _collapse_four_class_probabilities(four_mean)
    predicted_four = FOUR_CLASS_LABELS[int(np.argmax(four_mean))] if four_probs.size else ''
    predicted_binary_from_four = FOUR_TO_BINARY.get(predicted_four, '')
    predicted_gender = FOUR_TO_GENDER.get(predicted_four, '')
    predicted_binary_current = 'chest' if float(binary_mean[0]) >= float(binary_mean[1]) else 'falsetto'

    result = {
        'sample_name': sample_name,
        'window_count': int(windows.shape[0]),
        'duration_s': float(len(_normalize_audio(audio)) / float(sample_rate)) if int(sample_rate) > 0 else 0.0,
        'ground_truth_four': ground_truth,
        'ground_truth_binary': FOUR_TO_BINARY.get(ground_truth or '', ''),
        'ground_truth_gender': FOUR_TO_GENDER.get(ground_truth or '', ''),
        'current_binary': {
            'chest_prob': float(binary_mean[0]),
            'falsetto_prob': float(binary_mean[1]),
            'predicted_binary': predicted_binary_current,
        },
        'reference_four_class': {
            'mean_probs': {label: float(four_mean[idx]) for idx, label in enumerate(FOUR_CLASS_LABELS)},
            'collapsed_probs': collapsed,
            'predicted_four': predicted_four,
            'predicted_binary': predicted_binary_from_four,
            'predicted_gender': predicted_gender,
            'window_top_class_counts': dict(Counter(top_window_labels)),
        },
    }
    if ground_truth:
        result['matches'] = {
            'current_binary_correct': bool(predicted_binary_current == FOUR_TO_BINARY[ground_truth]),
            'reference_binary_correct': bool(predicted_binary_from_four == FOUR_TO_BINARY[ground_truth]),
            'reference_gender_correct': bool(predicted_gender == FOUR_TO_GENDER[ground_truth]),
            'reference_four_correct': bool(predicted_four == ground_truth),
        }
    return result


def _summarize_labeled(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    current_binary_hits = sum(1 for item in results if item.get('matches', {}).get('current_binary_correct'))
    reference_binary_hits = sum(1 for item in results if item.get('matches', {}).get('reference_binary_correct'))
    reference_gender_hits = sum(1 for item in results if item.get('matches', {}).get('reference_gender_correct'))
    reference_four_hits = sum(1 for item in results if item.get('matches', {}).get('reference_four_correct'))
    per_class: Dict[str, Dict[str, int]] = {}
    for label in FOUR_CLASS_LABELS:
        subset = [item for item in results if item.get('ground_truth_four') == label]
        per_class[label] = {
            'count': len(subset),
            'current_binary_correct': sum(1 for item in subset if item.get('matches', {}).get('current_binary_correct')),
            'reference_binary_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_binary_correct')),
            'reference_gender_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_gender_correct')),
            'reference_four_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_four_correct')),
        }
    return {
        'sample_count': total,
        'current_binary_accuracy': float(current_binary_hits / total) if total else 0.0,
        'reference_binary_accuracy': float(reference_binary_hits / total) if total else 0.0,
        'reference_gender_accuracy': float(reference_gender_hits / total) if total else 0.0,
        'reference_four_class_accuracy': float(reference_four_hits / total) if total else 0.0,
        'per_class': per_class,
    }


def _print_labeled_summary(summary: Dict[str, Any]) -> None:
    print('[labeled] sample_count=', summary.get('sample_count', 0))
    print('  current_binary_accuracy=', round(float(summary.get('current_binary_accuracy', 0.0)), 4))
    print('  reference_binary_accuracy=', round(float(summary.get('reference_binary_accuracy', 0.0)), 4))
    print('  reference_gender_accuracy=', round(float(summary.get('reference_gender_accuracy', 0.0)), 4))
    print('  reference_four_class_accuracy=', round(float(summary.get('reference_four_class_accuracy', 0.0)), 4))
    for label, payload in dict(summary.get('per_class', {}) or {}).items():
        print(
            f"  {label}: count={payload.get('count', 0)} cur_bin={payload.get('current_binary_correct', 0)} ref_bin={payload.get('reference_binary_correct', 0)} ref_gender={payload.get('reference_gender_correct', 0)} ref_four={payload.get('reference_four_correct', 0)}"
        )


def _print_unlabeled(results: Dict[str, Dict[str, Any]]) -> None:
    print('[unlabeled]')
    for sample_name, payload in results.items():
        if bool(payload.get('missing')):
            print(f"  {sample_name}: skipped ({payload.get('reason', 'missing_audio')})")
            continue
        current_binary = payload.get('current_binary', {})
        reference_four = payload.get('reference_four_class', {})
        collapsed = reference_four.get('collapsed_probs', {})
        print(
            f"  {sample_name}: cur_bin=({current_binary.get('predicted_binary')}, chest={current_binary.get('chest_prob', 0.0):.3f}, falsetto={current_binary.get('falsetto_prob', 0.0):.3f}) ref_four=({reference_four.get('predicted_four')}, gender={reference_four.get('predicted_gender')}, chest={collapsed.get('chest', 0.0):.3f}, falsetto={collapsed.get('falsetto', 0.0):.3f}, male={collapsed.get('male', 0.0):.3f}, female={collapsed.get('female', 0.0):.3f})"
        )


def _evaluate_reference_native_mel(
    *,
    zip_path: Path,
    four_model: Any,
    transform: Any,
    per_class: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    selected = _collect_eval_mel_members(zip_path, per_class=per_class)
    results: List[Dict[str, Any]] = []
    with zipfile.ZipFile(str(zip_path), 'r') as zip_file:
        for label in FOUR_CLASS_LABELS:
            for member in selected.get(label, []):
                image = Image.open(io.BytesIO(zip_file.read(member))).convert('RGB')
                batch = transform(np.asarray(image, dtype=np.uint8)).unsqueeze(0)
                probs = _predict_probabilities(four_model, batch)[0]
                predicted_four = FOUR_CLASS_LABELS[int(np.argmax(probs))]
                collapsed = _collapse_four_class_probabilities(probs)
                results.append(
                    {
                        'sample_name': member,
                        'ground_truth_four': label,
                        'ground_truth_binary': FOUR_TO_BINARY[label],
                        'ground_truth_gender': FOUR_TO_GENDER[label],
                        'reference_four_class': {
                            'mean_probs': {name: float(probs[idx]) for idx, name in enumerate(FOUR_CLASS_LABELS)},
                            'collapsed_probs': collapsed,
                            'predicted_four': predicted_four,
                            'predicted_binary': FOUR_TO_BINARY[predicted_four],
                            'predicted_gender': FOUR_TO_GENDER[predicted_four],
                        },
                        'matches': {
                            'reference_binary_correct': bool(FOUR_TO_BINARY[predicted_four] == FOUR_TO_BINARY[label]),
                            'reference_gender_correct': bool(FOUR_TO_GENDER[predicted_four] == FOUR_TO_GENDER[label]),
                            'reference_four_correct': bool(predicted_four == label),
                        },
                    }
                )
    total = len(results)
    summary = {
        'sample_count': total,
        'reference_binary_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_binary_correct')) / total) if total else 0.0,
        'reference_gender_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_gender_correct')) / total) if total else 0.0,
        'reference_four_class_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_four_correct')) / total) if total else 0.0,
    }
    return summary, results


def main() -> None:
    parser = argparse.ArgumentParser(description='Compare current binary chest/falsetto model against the four-class reference model.')
    parser.add_argument('--dataset-per-class', type=int, default=12, help='How many labeled dataset samples to evaluate per four-class label.')
    parser.add_argument('--output', default='_tmp_chest_falsetto_model_compare.json')
    args = parser.parse_args()

    transform = _build_transform()
    mel_filter = _build_mel_filterbank(sample_rate=TARGET_SR, n_fft=1024)

    binary_checkpoint = _find_existing_path(CURRENT_BINARY_CHECKPOINT_CANDIDATES)
    if not REFERENCE_FOUR_CLASS_CHECKPOINT.exists():
        raise FileNotFoundError(f'Missing reference checkpoint: {REFERENCE_FOUR_CLASS_CHECKPOINT}')

    binary_model = _load_model(binary_checkpoint, num_classes=2)
    four_model = _load_model(REFERENCE_FOUR_CLASS_CHECKPOINT, num_classes=4, reference_four_class_head=True)

    dataset_members = _collect_dataset_members(DATASET_AUDIO_ZIP, per_class=max(1, int(args.dataset_per_class)))
    labeled_results: List[Dict[str, Any]] = []
    with zipfile.ZipFile(str(DATASET_AUDIO_ZIP), 'r') as zip_file:
        for label in FOUR_CLASS_LABELS:
            for member in dataset_members.get(label, []):
                audio, sample_rate = _load_audio_from_zip(zip_file, member)
                labeled_results.append(
                    _evaluate_clip(
                        sample_name=member,
                        audio=audio,
                        sample_rate=sample_rate,
                        binary_model=binary_model,
                        four_model=four_model,
                        transform=transform,
                        mel_filter=mel_filter,
                        ground_truth=label,
                    )
                )

    example_results: List[Dict[str, Any]] = []
    skipped_examples: List[Dict[str, str]] = []
    for file_path in sorted(EXAMPLE_DIR.glob('*.wav')):
        label = _parse_four_class_label(file_path.name)
        if not label:
            continue
        try:
            audio, sample_rate = _load_audio_from_path(file_path)
            example_results.append(
                _evaluate_clip(
                    sample_name=str(file_path.relative_to(PROJECT_ROOT)),
                    audio=audio,
                    sample_rate=sample_rate,
                    binary_model=binary_model,
                    four_model=four_model,
                    transform=transform,
                    mel_filter=mel_filter,
                    ground_truth=label,
                )
            )
        except Exception as exc:
            skipped_examples.append({'path': str(file_path.relative_to(PROJECT_ROOT)), 'reason': str(exc)})

    unlabeled_results: Dict[str, Dict[str, Any]] = {}
    for sample_name, file_path in UNLABELED_SAMPLES.items():
        if not file_path.exists():
            unlabeled_results[sample_name] = {'missing': True, 'path': str(file_path)}
            continue
        try:
            audio, sample_rate = _load_audio_from_path(file_path)
            unlabeled_results[sample_name] = _evaluate_clip(
                sample_name=sample_name,
                audio=audio,
                sample_rate=sample_rate,
                binary_model=binary_model,
                four_model=four_model,
                transform=transform,
                mel_filter=mel_filter,
                ground_truth=None,
            )
        except Exception as exc:
            unlabeled_results[sample_name] = {
                'missing': True,
                'path': str(file_path),
                'reason': str(exc),
            }

    labeled_summary = _summarize_labeled(labeled_results)
    example_summary = _summarize_labeled(example_results)
    native_mel_summary, native_mel_results = _evaluate_reference_native_mel(
        zip_path=PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'dataset' / 'data' / 'eval.zip',
        four_model=four_model,
        transform=transform,
        per_class=max(1, int(args.dataset_per_class)),
    )
    payload = {
        'models': {
            'current_binary_checkpoint': str(binary_checkpoint),
            'reference_four_class_checkpoint': str(REFERENCE_FOUR_CLASS_CHECKPOINT),
        },
        'config': {
            'target_sample_rate': TARGET_SR,
            'window_s': WINDOW_S,
            'hop_s': HOP_S,
            'dataset_per_class': int(args.dataset_per_class),
        },
        'labeled_dataset_summary': labeled_summary,
        'labeled_dataset_results': labeled_results,
        'example_summary': example_summary,
        'example_results': example_results,
        'skipped_examples': skipped_examples,
        'reference_native_mel_summary': native_mel_summary,
        'reference_native_mel_results': native_mel_results,
        'unlabeled_results': unlabeled_results,
    }
    output_path = PROJECT_ROOT / str(args.output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print('[models]')
    print('  current_binary_checkpoint=', binary_checkpoint)
    print('  reference_four_class_checkpoint=', REFERENCE_FOUR_CLASS_CHECKPOINT)
    _print_labeled_summary(labeled_summary)
    print('[examples]')
    _print_labeled_summary(example_summary)
    print('[reference_native_mel]')
    print('  sample_count=', native_mel_summary.get('sample_count', 0))
    print('  reference_binary_accuracy=', round(float(native_mel_summary.get('reference_binary_accuracy', 0.0)), 4))
    print('  reference_gender_accuracy=', round(float(native_mel_summary.get('reference_gender_accuracy', 0.0)), 4))
    print('  reference_four_class_accuracy=', round(float(native_mel_summary.get('reference_four_class_accuracy', 0.0)), 4))
    _print_unlabeled(unlabeled_results)
    print('json_report=', output_path)


if __name__ == '__main__':
    main()