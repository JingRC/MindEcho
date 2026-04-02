import argparse
import json
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple

import librosa
import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms


CLASS_NAMES = ['chest', 'falsetto']
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def build_transform(image_size: int = 224):
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=MEAN, std=STD),
    ])


def build_model(checkpoint_path: Path, device: torch.device):
    model = models.squeezenet1_1(weights=None)
    model.classifier[1] = torch.nn.Conv2d(512, 2, kernel_size=1)
    model.num_classes = 2
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)
    model.eval()
    return model


def mel_image_from_wav(wav_path: Path, sr: int = 22050) -> Image.Image:
    audio, _ = librosa.load(str(wav_path), sr=sr, mono=True)
    mel = librosa.feature.melspectrogram(y=audio, sr=sr)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_norm = mel_db - mel_db.min()
    if mel_norm.max() > 0:
        mel_norm = mel_norm / mel_norm.max()
    array = (mel_norm * 255.0).clip(0, 255).astype(np.uint8)
    image = Image.fromarray(array).convert('RGB')
    return image


def load_image(path: Path) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix == '.wav':
        return mel_image_from_wav(path)
    return Image.open(path).convert('RGB')


@torch.no_grad()
def predict_file(model, path: Path, device: torch.device, image_size: int = 224) -> Dict[str, float | str]:
    image = load_image(path)
    tensor = build_transform(image_size)(image).unsqueeze(0).to(device)
    logits = model(tensor)
    probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy().tolist()
    best_idx = int(np.argmax(probs))
    return {
        'label': CLASS_NAMES[best_idx],
        'chest_prob': float(probs[0]),
        'falsetto_prob': float(probs[1]),
    }


def main():
    parser = argparse.ArgumentParser(description='Run inference with the lightweight SqueezeNet chest/falsetto model.')
    parser.add_argument('input_path', help='Path to a wav or jpg file.')
    parser.add_argument('--checkpoint', default=r'd:\-MindEcho-main\ml_dl_models\chest_falsetto\squeezenet_binary\artifacts\best_squeezenet_binary.pt')
    parser.add_argument('--image-size', type=int, default=224)
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = build_model(Path(args.checkpoint), device)
    result = predict_file(model, Path(args.input_path), device, image_size=args.image_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()