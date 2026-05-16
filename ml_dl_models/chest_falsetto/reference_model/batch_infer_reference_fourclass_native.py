import argparse
import io
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image


TARGET_SR = 22050
SEGMENT_S = 0.4961451247165533
IMAGE_SIZE = 224
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


def build_model(checkpoint_path: Path, device: torch.device) -> ReferenceSqueezeNet:
    model = ReferenceSqueezeNet(num_classes=4)
    try:
        checkpoint = torch.load(str(checkpoint_path), map_location=device)
    except RuntimeError as exc:
        exc_text = str(exc or '')
        if device.type != 'cpu' and ('device_count() is 0' in exc_text or 'Attempting to deserialize object on CUDA device' in exc_text):
            device = torch.device('cpu')
            checkpoint = torch.load(str(checkpoint_path), map_location=device)
        else:
            raise
    state_dict = checkpoint.get('model_state_dict', checkpoint) if isinstance(checkpoint, dict) else checkpoint
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def collapse_four_probs(probabilities: np.ndarray) -> dict:
    return {
        'chest': float(probabilities[0] + probabilities[1]),
        'falsetto': float(probabilities[2] + probabilities[3]),
        'male': float(probabilities[0] + probabilities[2]),
        'female': float(probabilities[1] + probabilities[3]),
    }


def prepare_window_audio(window: np.ndarray, sample_rate: int) -> np.ndarray:
    y = np.asarray(window, dtype=np.float32).reshape(-1)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    if int(sample_rate) != TARGET_SR:
        y = librosa.resample(y, orig_sr=int(sample_rate), target_sr=TARGET_SR)
    target_samples = max(1, int(round(SEGMENT_S * TARGET_SR)))
    if y.size < target_samples:
        pad_total = int(target_samples - y.size)
        pad_left = int(pad_total // 2)
        pad_right = int(pad_total - pad_left)
        y = np.pad(y, (pad_left, pad_right), mode='constant')
    elif y.size > target_samples:
        start = max(0, int((y.size - target_samples) // 2))
        y = y[start:start + target_samples]
    return np.asarray(y, dtype=np.float32)


def render_native_window(window: np.ndarray, sample_rate: int) -> np.ndarray:
    y = prepare_window_audio(window, sample_rate)
    mel_spec = librosa.feature.melspectrogram(y=y, sr=TARGET_SR)
    log_mel_spec = librosa.power_to_db(mel_spec, ref=np.max)
    figure = plt.figure()
    axis = figure.add_subplot(111)
    librosa.display.specshow(log_mel_spec, ax=axis)
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


def build_batch_from_windows(windows: np.ndarray, sample_rate: int) -> torch.Tensor:
    tensors = [torch.from_numpy(render_native_window(window, sample_rate)) for window in windows]
    return torch.stack(tensors, dim=0)


@torch.no_grad()
def predict_windows(model: ReferenceSqueezeNet, batch: torch.Tensor, device: torch.device) -> list:
    outputs = []
    for start_idx in range(0, int(batch.size(0)), 16):
        sub_batch = batch[start_idx:start_idx + 16].to(device)
        probs = torch.softmax(model(sub_batch), dim=1).cpu().numpy()
        for prob in probs:
            predicted_idx = int(np.argmax(prob))
            predicted_four = FOUR_CLASS_LABELS[predicted_idx]
            collapsed = collapse_four_probs(np.asarray(prob, dtype=np.float32))
            outputs.append({
                'm_chest_prob': float(prob[0]),
                'f_chest_prob': float(prob[1]),
                'm_falsetto_prob': float(prob[2]),
                'f_falsetto_prob': float(prob[3]),
                'predicted_four': predicted_four,
                'predicted_binary': FOUR_TO_BINARY.get(predicted_four, ''),
                'predicted_gender': FOUR_TO_GENDER.get(predicted_four, ''),
                'collapsed_probs': collapsed,
            })
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description='Batch inference for native-preproc four-class chest/falsetto reference windows.')
    parser.add_argument('--input-npz', required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--checkpoint', required=True)
    args = parser.parse_args()

    payload = np.load(args.input_npz)
    windows = np.asarray(payload['windows'], dtype=np.float32)
    sample_rate = int(np.asarray(payload['sample_rate']).reshape(-1)[0])

    device = resolve_device()
    model = build_model(Path(args.checkpoint), device)
    batch = build_batch_from_windows(windows, sample_rate=sample_rate)
    result = predict_windows(model, batch, device)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()