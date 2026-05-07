import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import torch
from torchvision import models, transforms


MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def build_transform(image_size: int = 224):
    return transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])


def build_model(checkpoint_path: Path, device: torch.device):
    model = models.squeezenet1_1(weights=None)
    model.classifier[1] = torch.nn.Conv2d(512, 2, kernel_size=1)
    model.num_classes = 2
    try:
        checkpoint = torch.load(checkpoint_path, map_location=device)
    except RuntimeError as exc:
        exc_text = str(exc or '')
        if device.type != 'cpu' and ('device_count() is 0' in exc_text or 'Attempting to deserialize object on CUDA device' in exc_text):
            device = torch.device('cpu')
            checkpoint = torch.load(checkpoint_path, map_location=device)
        else:
            raise
    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)
    model.eval()
    return model


def resolve_device() -> torch.device:
    force_cpu = str(os.environ.get('MIND_ECHO_FORCE_CPU', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    hidden_cuda = str(os.environ.get('CUDA_VISIBLE_DEVICES', '') or '').strip() == '' and 'CUDA_VISIBLE_DEVICES' in os.environ
    if force_cpu or hidden_cuda:
        return torch.device('cpu')
    try:
        if torch.cuda.is_available() and int(torch.cuda.device_count()) > 0:
            return torch.device('cuda')
    except Exception:
        pass
    return torch.device('cpu')


def hz_to_mel(value_hz: float) -> float:
    return 2595.0 * math.log10(1.0 + float(value_hz) / 700.0)


def mel_to_hz(value_mel: float) -> float:
    return 700.0 * (10.0 ** (float(value_mel) / 2595.0) - 1.0)


def build_mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 128, fmin: float = 30.0, fmax: float | None = None):
    upper_hz = float(fmax if fmax is not None else sample_rate * 0.5)
    mel_points = np.linspace(hz_to_mel(fmin), hz_to_mel(upper_hz), n_mels + 2, dtype=np.float32)
    hz_points = np.asarray([mel_to_hz(float(item)) for item in mel_points], dtype=np.float32)
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


def build_mel_image(signal: np.ndarray, sample_rate: int):
    n_fft = 1024
    hop_length = 256
    win_length = 1024
    waveform = torch.as_tensor(np.asarray(signal, dtype=np.float32).reshape(-1))
    if waveform.numel() < win_length:
        waveform = torch.nn.functional.pad(waveform, (0, win_length - waveform.numel()))
    window = torch.hann_window(win_length)
    stft = torch.stft(
        waveform,
        n_fft=n_fft,
        hop_length=hop_length,
        win_length=win_length,
        window=window,
        center=True,
        return_complex=True,
    )
    power = stft.abs().pow(2.0)
    mel_filter = build_mel_filterbank(sample_rate=sample_rate, n_fft=n_fft)
    mel_spec = torch.matmul(mel_filter, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if mel_spec.numel() else 0.0
    if peak > 0.0:
        mel_spec = mel_spec / peak
    mel_np = mel_spec.cpu().numpy().astype(np.float32)
    return np.stack([mel_np, mel_np, mel_np], axis=-1)


def build_batch_from_windows(windows: np.ndarray, sample_rate: int, image_size: int):
    transform = build_transform(image_size)
    tensors = []
    for window in windows:
        rgb = build_mel_image(window, sample_rate=sample_rate)
        tensors.append(transform(rgb))
    return torch.stack(tensors)


@torch.no_grad()
def predict_windows(model, batch: torch.Tensor, device: torch.device):
    probs = []
    for start_idx in range(0, batch.size(0), 24):
        sub = batch[start_idx:start_idx + 24].to(device)
        logits = model(sub)
        sub_probs = torch.softmax(logits, dim=1).cpu().numpy().tolist()
        probs.extend(sub_probs)
    return [
        {
            'chest_prob': float(item[0]),
            'falsetto_prob': float(item[1]),
        }
        for item in probs
    ]


def main():
    parser = argparse.ArgumentParser(description='Batch inference for SqueezeNet chest/falsetto windows.')
    parser.add_argument('--input-npz', required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--image-size', type=int, default=224)
    args = parser.parse_args()

    payload = np.load(args.input_npz)
    windows = np.asarray(payload['windows'], dtype=np.float32)
    sample_rate = int(np.asarray(payload['sample_rate']).reshape(-1)[0])

    device = resolve_device()
    model = build_model(Path(args.checkpoint), device)
    batch = build_batch_from_windows(windows, sample_rate=sample_rate, image_size=args.image_size)
    result = predict_windows(model, batch, device)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()