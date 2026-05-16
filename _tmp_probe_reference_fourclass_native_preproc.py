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

import matplotlib

matplotlib.use('Agg')

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent
REFERENCE_FOUR_CLASS_CHECKPOINT = (
    PROJECT_ROOT
    / 'ml_dl_models'
    / 'chest_falsetto'
    / 'reference_model'
    / 'squeezenet1_1_mel_2024-07-30_15-40-44'
    / 'save.pt'
)
DATASET_AUDIO_ZIP = PROJECT_ROOT / 'ml_dl_models' / 'chest_falsetto' / 'dataset' / 'data' / 'audio.zip'

TARGET_SR = 22050
IMAGE_SIZE = 224
SEG_LEN_S = 0.4961451247165533
MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

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

TARGET_SAMPLES = {
    'female_lead_libai': PROJECT_ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '单依纯 - 李白 (Live)_人声_lead.wav',
    'male_lead_wuju': PROJECT_ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '林俊杰 - 无拘_人声_lead.wav',
    'dry_mic_phrase': PROJECT_ROOT / 'recordings' / 'recording_20260202_113327.wav',
    'dry_mic_short': PROJECT_ROOT / 'recordings' / 'recording_20260202_104455.wav',
}


class Fire(torch.nn.Module):
    def __init__(self, inplanes: int, squeeze_planes: int, expand1x1_planes: int, expand3x3_planes: int):
        super().__init__()
        self.squeeze = torch.nn.Conv2d(inplanes, squeeze_planes, kernel_size=1)
        self.squeeze_activation = torch.nn.ReLU(inplace=True)
        self.expand1x1 = torch.nn.Conv2d(squeeze_planes, expand1x1_planes, kernel_size=1)
        self.expand1x1_activation = torch.nn.ReLU(inplace=True)
        self.expand3x3 = torch.nn.Conv2d(squeeze_planes, expand3x3_planes, kernel_size=3, padding=1)
        self.expand3x3_activation = torch.nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.squeeze_activation(self.squeeze(x))
        return torch.cat(
            [
                self.expand1x1_activation(self.expand1x1(x)),
                self.expand3x3_activation(self.expand3x3(x)),
            ],
            1,
        )


class ReferenceSqueezeNet(torch.nn.Module):
    def __init__(self, num_classes: int = 4):
        super().__init__()
        self.num_classes = num_classes
        self.features = torch.nn.Sequential(
            torch.nn.Conv2d(3, 64, kernel_size=3, stride=2),
            torch.nn.ReLU(inplace=True),
            torch.nn.MaxPool2d(kernel_size=3, stride=2, ceil_mode=True),
            Fire(64, 16, 64, 64),
            Fire(128, 16, 64, 64),
            torch.nn.MaxPool2d(kernel_size=3, stride=2, ceil_mode=True),
            Fire(128, 32, 128, 128),
            Fire(256, 32, 128, 128),
            torch.nn.MaxPool2d(kernel_size=3, stride=2, ceil_mode=True),
            Fire(256, 48, 192, 192),
            Fire(384, 48, 192, 192),
            Fire(384, 64, 256, 256),
            Fire(512, 64, 256, 256),
        )
        self.classifier = torch.nn.Sequential(
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

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.classifier(x)
        return x


def load_reference_model(checkpoint_path: Path) -> ReferenceSqueezeNet:
    model = ReferenceSqueezeNet(num_classes=4)
    state_dict = torch.load(str(checkpoint_path), map_location='cpu')
    model.load_state_dict(state_dict)
    model.eval()
    return model


def parse_label_from_name(name: str) -> Optional[str]:
    lower_name = str(name or '').lower()
    for label in FOUR_CLASS_LABELS:
        if label in lower_name:
            return label
    return None


def pick_evenly(items: List[str], count: int) -> List[str]:
    if len(items) <= count:
        return list(items)
    indices = np.linspace(0, len(items) - 1, count, dtype=int)
    return [items[int(idx)] for idx in indices]


def collect_dataset_members(zip_path: Path, per_class: int) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    with zipfile.ZipFile(str(zip_path), 'r') as zip_file:
        for member in zip_file.namelist():
            if not member.lower().endswith('.wav'):
                continue
            label = parse_label_from_name(Path(member).name)
            if label:
                grouped[label].append(member)
    return {label: pick_evenly(sorted(grouped.get(label, [])), per_class) for label in FOUR_CLASS_LABELS}


def decode_pcm_frames(frames: bytes, *, sampwidth: int, channels: int) -> np.ndarray:
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


def load_audio_from_path(path: Path) -> Tuple[np.ndarray, int]:
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
        audio = decode_pcm_frames(frames, sampwidth=sampwidth, channels=channels)
        return audio, sample_rate


def load_audio_from_zip(zip_file: zipfile.ZipFile, member: str) -> Tuple[np.ndarray, int]:
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
        audio = decode_pcm_frames(frames, sampwidth=sampwidth, channels=channels)
        return audio, sample_rate


def to_mono_float32(audio: np.ndarray) -> np.ndarray:
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    return np.nan_to_num(y.reshape(-1), nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def build_native_mel_segments(audio: np.ndarray, sample_rate: int, width: float = SEG_LEN_S) -> List[np.ndarray]:
    y = to_mono_float32(audio)
    if int(sample_rate) != TARGET_SR:
        y = librosa.resample(y, orig_sr=int(sample_rate), target_sr=TARGET_SR)
        sample_rate = TARGET_SR
    mel_spec = librosa.feature.melspectrogram(y=y, sr=sample_rate)
    log_mel_spec = librosa.power_to_db(mel_spec, ref=np.max)
    duration = librosa.get_duration(y=y, sr=sample_rate)
    total_frames = int(log_mel_spec.shape[1])
    if total_frames <= 0 or duration <= 0.0:
        return []
    step = int(width * total_frames / duration)
    step = max(1, step)
    count = max(1, int(total_frames / step))
    begin = max(0, int(0.5 * (total_frames - count * step)))
    end = min(total_frames, begin + step * count)
    segments: List[np.ndarray] = []
    for frame_idx in range(begin, end, step):
        segment = log_mel_spec[:, frame_idx : min(frame_idx + step, total_frames)]
        if segment.size <= 0:
            continue
        segments.append(np.asarray(segment, dtype=np.float32))
    return segments


def render_native_segment(segment: np.ndarray) -> np.ndarray:
    figure = plt.figure()
    axis = figure.add_subplot(111)
    librosa.display.specshow(segment, ax=axis)
    axis.axis('off')
    buffer = io.BytesIO()
    figure.savefig(buffer, format='png', bbox_inches='tight', pad_inches=0.0)
    plt.close(figure)
    buffer.seek(0)
    image = Image.open(buffer).convert('RGB')
    image = image.resize((IMAGE_SIZE, IMAGE_SIZE), Image.BILINEAR)
    array = np.asarray(image, dtype=np.float32) / 255.0
    chw = np.transpose(array, (2, 0, 1))
    chw = (chw - MEAN) / STD
    return np.asarray(chw, dtype=np.float32)


def predict_segment_probs(model: ReferenceSqueezeNet, segments: List[np.ndarray]) -> np.ndarray:
    if not segments:
        return np.zeros((0, len(FOUR_CLASS_LABELS)), dtype=np.float32)
    tensors = [torch.from_numpy(render_native_segment(segment)) for segment in segments]
    probabilities: List[np.ndarray] = []
    with torch.no_grad():
        for start_idx in range(0, len(tensors), 16):
            batch = torch.stack(tensors[start_idx : start_idx + 16], dim=0)
            logits = model(batch)
            probabilities.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.concatenate(probabilities, axis=0) if probabilities else np.zeros((0, len(FOUR_CLASS_LABELS)), dtype=np.float32)


def collapse_four_probs(probabilities: np.ndarray) -> Dict[str, float]:
    return {
        'chest': float(probabilities[0] + probabilities[1]),
        'falsetto': float(probabilities[2] + probabilities[3]),
        'male': float(probabilities[0] + probabilities[2]),
        'female': float(probabilities[1] + probabilities[3]),
    }


def summarize_probability_matrix(probabilities: np.ndarray) -> Dict[str, Any]:
    mean_probs = np.mean(probabilities, axis=0) if probabilities.size else np.zeros(4, dtype=np.float32)
    predicted_four = FOUR_CLASS_LABELS[int(np.argmax(mean_probs))] if probabilities.size else ''
    segment_top_labels = [FOUR_CLASS_LABELS[int(idx)] for idx in np.argmax(probabilities, axis=1)] if probabilities.size else []
    return {
        'mean_probs': {label: float(mean_probs[idx]) for idx, label in enumerate(FOUR_CLASS_LABELS)},
        'collapsed_probs': collapse_four_probs(mean_probs),
        'predicted_four': predicted_four,
        'predicted_binary': FOUR_TO_BINARY.get(predicted_four, ''),
        'predicted_gender': FOUR_TO_GENDER.get(predicted_four, ''),
        'segment_top_class_counts': dict(Counter(segment_top_labels)),
    }


def evaluate_audio(
    *,
    sample_name: str,
    audio: np.ndarray,
    sample_rate: int,
    model: ReferenceSqueezeNet,
    ground_truth: Optional[str] = None,
) -> Dict[str, Any]:
    segments = build_native_mel_segments(audio, sample_rate)
    probabilities = predict_segment_probs(model, segments)
    top_falsetto_summary: Dict[str, Any] = {}
    if probabilities.size:
        falsetto_scores = probabilities[:, 2] + probabilities[:, 3]
        top_k = max(8, int(round(probabilities.shape[0] * 0.10)))
        top_k = min(int(probabilities.shape[0]), top_k)
        top_indices = np.argsort(falsetto_scores)[-top_k:]
        top_probs = probabilities[top_indices]
        top_falsetto_summary = summarize_probability_matrix(top_probs)
        top_falsetto_summary['selected_segments'] = int(top_k)
    result: Dict[str, Any] = {
        'sample_name': sample_name,
        'segment_count': len(segments),
        'reference_native_preproc': summarize_probability_matrix(probabilities),
    }
    if top_falsetto_summary:
        result['reference_native_preproc']['top_falsetto_focus'] = top_falsetto_summary
    if ground_truth:
        result['ground_truth_four'] = ground_truth
        result['ground_truth_binary'] = FOUR_TO_BINARY[ground_truth]
        result['ground_truth_gender'] = FOUR_TO_GENDER[ground_truth]
        result['matches'] = {
            'reference_binary_correct': bool(result['reference_native_preproc'].get('predicted_binary', '') == FOUR_TO_BINARY[ground_truth]),
            'reference_gender_correct': bool(result['reference_native_preproc'].get('predicted_gender', '') == FOUR_TO_GENDER[ground_truth]),
            'reference_four_correct': bool(result['reference_native_preproc'].get('predicted_four', '') == ground_truth),
        }
    return result


def summarize_labeled(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    summary = {
        'sample_count': total,
        'reference_binary_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_binary_correct')) / total) if total else 0.0,
        'reference_gender_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_gender_correct')) / total) if total else 0.0,
        'reference_four_class_accuracy': float(sum(1 for item in results if item.get('matches', {}).get('reference_four_correct')) / total) if total else 0.0,
        'per_class': {},
    }
    per_class: Dict[str, Dict[str, int]] = {}
    for label in FOUR_CLASS_LABELS:
        subset = [item for item in results if item.get('ground_truth_four') == label]
        per_class[label] = {
            'count': len(subset),
            'reference_binary_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_binary_correct')),
            'reference_gender_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_gender_correct')),
            'reference_four_correct': sum(1 for item in subset if item.get('matches', {}).get('reference_four_correct')),
        }
    summary['per_class'] = per_class
    return summary


def print_labeled_summary(summary: Dict[str, Any]) -> None:
    print('[native_labeled] sample_count=', summary.get('sample_count', 0))
    print('  reference_binary_accuracy=', round(float(summary.get('reference_binary_accuracy', 0.0)), 4))
    print('  reference_gender_accuracy=', round(float(summary.get('reference_gender_accuracy', 0.0)), 4))
    print('  reference_four_class_accuracy=', round(float(summary.get('reference_four_class_accuracy', 0.0)), 4))
    for label, payload in dict(summary.get('per_class', {}) or {}).items():
        print(
            f"  {label}: count={payload.get('count', 0)} ref_bin={payload.get('reference_binary_correct', 0)} ref_gender={payload.get('reference_gender_correct', 0)} ref_four={payload.get('reference_four_correct', 0)}"
        )


def print_target_results(results: Dict[str, Dict[str, Any]]) -> None:
    print('[targets]')
    for sample_name, payload in results.items():
        if bool(payload.get('missing')):
            print(f"  {sample_name}: skipped ({payload.get('reason', 'missing_audio')})")
            continue
        native = payload.get('reference_native_preproc', {})
        collapsed = native.get('collapsed_probs', {})
        falsetto_focus = native.get('top_falsetto_focus', {})
        falsetto_focus_collapsed = falsetto_focus.get('collapsed_probs', {}) if isinstance(falsetto_focus, dict) else {}
        print(
            f"  {sample_name}: pred_four={native.get('predicted_four')} gender={native.get('predicted_gender')} chest={collapsed.get('chest', 0.0):.3f} falsetto={collapsed.get('falsetto', 0.0):.3f} male={collapsed.get('male', 0.0):.3f} female={collapsed.get('female', 0.0):.3f} segments={payload.get('segment_count', 0)}"
        )
        if falsetto_focus:
            print(
                f"    top_falsetto_focus: pred_four={falsetto_focus.get('predicted_four')} gender={falsetto_focus.get('predicted_gender')} chest={falsetto_focus_collapsed.get('chest', 0.0):.3f} falsetto={falsetto_focus_collapsed.get('falsetto', 0.0):.3f} selected={falsetto_focus.get('selected_segments', 0)}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description='Native-preprocessing offline probe for the four-class chest/falsetto reference model.')
    parser.add_argument('--dataset-per-class', type=int, default=8)
    parser.add_argument('--output', default='_tmp_reference_fourclass_native_preproc_probe.json')
    args = parser.parse_args()

    if not REFERENCE_FOUR_CLASS_CHECKPOINT.exists():
        raise FileNotFoundError(f'Missing reference checkpoint: {REFERENCE_FOUR_CLASS_CHECKPOINT}')
    if not DATASET_AUDIO_ZIP.exists():
        raise FileNotFoundError(f'Missing dataset zip: {DATASET_AUDIO_ZIP}')

    model = load_reference_model(REFERENCE_FOUR_CLASS_CHECKPOINT)

    labeled_results: List[Dict[str, Any]] = []
    selected_members = collect_dataset_members(DATASET_AUDIO_ZIP, per_class=max(1, int(args.dataset_per_class)))
    with zipfile.ZipFile(str(DATASET_AUDIO_ZIP), 'r') as zip_file:
        for label in FOUR_CLASS_LABELS:
            for member in selected_members.get(label, []):
                audio, sample_rate = load_audio_from_zip(zip_file, member)
                labeled_results.append(
                    evaluate_audio(
                        sample_name=member,
                        audio=audio,
                        sample_rate=sample_rate,
                        model=model,
                        ground_truth=label,
                    )
                )

    labeled_summary = summarize_labeled(labeled_results)

    target_results: Dict[str, Dict[str, Any]] = {}
    for sample_name, path in TARGET_SAMPLES.items():
        if not path.exists():
            target_results[sample_name] = {'missing': True, 'path': str(path), 'reason': 'file_missing'}
            continue
        try:
            audio, sample_rate = load_audio_from_path(path)
            target_results[sample_name] = evaluate_audio(
                sample_name=sample_name,
                audio=audio,
                sample_rate=sample_rate,
                model=model,
                ground_truth=None,
            )
        except Exception as exc:
            target_results[sample_name] = {'missing': True, 'path': str(path), 'reason': str(exc)}

    payload = {
        'model_checkpoint': str(REFERENCE_FOUR_CLASS_CHECKPOINT),
        'config': {
            'target_sample_rate': TARGET_SR,
            'seg_len_s': SEG_LEN_S,
            'dataset_per_class': int(args.dataset_per_class),
            'frontend': 'librosa_melspectrogram + power_to_db + specshow + savefig + resize224',
        },
        'labeled_summary': labeled_summary,
        'labeled_results': labeled_results,
        'target_results': target_results,
    }

    output_path = PROJECT_ROOT / str(args.output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print('[model] checkpoint=', REFERENCE_FOUR_CLASS_CHECKPOINT)
    print_labeled_summary(labeled_summary)
    print_target_results(target_results)
    print('json_report=', output_path)


if __name__ == '__main__':
    main()