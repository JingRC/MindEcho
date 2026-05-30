"""Fast evaluation of V6 on the song-level test set only."""
import csv, json, time, math, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import models, transforms
from torch.utils.data import DataLoader, Dataset

PROJECT_ROOT = Path(r'd:\-MindEcho-main')
V6_CKPT = PROJECT_ROOT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt'
SONG_TEST = PROJECT_ROOT / 'ml_dl_models/gtsinger_multitech/dataset/curated/mix_binary_song_level_v1/test_manifest.csv'
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
TARGET_SR = 22050
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 128

def hz_to_mel(hz): return 2595.0 * math.log10(1.0 + hz / 700.0)
def mel_to_hz(mel): return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def build_mel_filterbank(sr, n_fft, n_mels=128, fmin=30.0, fmax=None):
    upper = fmax if fmax is not None else sr * 0.5
    mel_points = np.linspace(hz_to_mel(fmin), hz_to_mel(upper), n_mels + 2, dtype=np.float32)
    hz_points = np.array([mel_to_hz(m) for m in mel_points], dtype=np.float32)
    bins = np.floor((n_fft + 1) * hz_points / sr).astype(np.int32)
    bins = np.clip(bins, 0, n_fft // 2)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(1, n_mels + 1):
        l, c, r = int(bins[i-1]), int(bins[i]), int(bins[i+1])
        if c <= l: c = min(l + 1, n_fft // 2)
        if r <= c: r = min(c + 1, n_fft // 2)
        if c > l: fb[i-1, l:c] = np.linspace(0., 1., max(c-l, 1), endpoint=False, dtype=np.float32)
        if r > c: fb[i-1, c:r] = np.linspace(1., 0., max(r-c, 1), endpoint=False, dtype=np.float32)
    return torch.from_numpy(fb)

MEL_FILTER = build_mel_filterbank(TARGET_SR, N_FFT, N_MELS)

# ── Models (same as evaluate_mix_voice.py) ──
class SpectralEncoder(torch.nn.Module):
    def __init__(self, input_dim=3, hidden_dim=16):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(input_dim, hidden_dim), torch.nn.ReLU(inplace=True))
    def forward(self, x): return self.net(x)

class FusionHead(torch.nn.Module):
    def __init__(self, backbone_dim=512, spectral_dim=16, dropout=0.3):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(backbone_dim + spectral_dim, 128), torch.nn.ReLU(inplace=True), torch.nn.Dropout(dropout),
            torch.nn.Linear(128, 32), torch.nn.ReLU(inplace=True),
            torch.nn.Linear(32, 2))
    def forward(self, bb, sp): return self.net(torch.cat([bb, sp], dim=1))

class SqueezeNetLF(torch.nn.Module):
    def __init__(self, spectral_dim=16, dropout=0.3):
        super().__init__()
        self.backbone = models.squeezenet1_1(weights=None)
        self.backbone.classifier[1] = torch.nn.Identity()
        self.spectral_encoder = SpectralEncoder(3, spectral_dim)
        self.fusion_head = FusionHead(512, spectral_dim, dropout)
        self._is_latefusion = True
    def forward(self, mel, sp): return self.fusion_head(self.backbone.features(mel).mean([2,3]), self.spectral_encoder(sp))

# ── Audio processing ──
def compute_spectral(audio):
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    n = len(x)
    if n < 64: return np.array([0., 1., 1.], dtype=np.float32)
    sr = float(TARGET_SR)
    spec = np.fft.rfft(x); mag = np.abs(spec) + 1e-12
    freqs = np.fft.rfftfreq(n, 1./sr)
    valid = freqs > 0
    if np.sum(valid) > 4:
        mag_db = 20.*np.log10(mag[valid])
        log2_f = np.log2(freqs[valid])
        slope, _ = np.polyfit(log2_f, mag_db, 1)
        tilt = float(slope)
    else: tilt = 0.
    mid_mask = (freqs >= 300) & (freqs <= 3000)
    high_mask = freqs > 3000
    me = float(np.mean(mag[mid_mask])) if np.any(mid_mask) else 0.
    he = float(np.mean(mag[high_mask])) if np.any(high_mask) else 1e-12
    mhr = (me+1e-9)/(he+1e-9)
    hm = (freqs >= 2000) & (freqs <= 6000)
    hh = freqs > 6000
    ehm = float(np.mean(mag[hm])) if np.any(hm) else 1e-12
    ehh = float(np.mean(mag[hh])) if np.any(hh) else 1e-12
    hmohh = (ehm+1e-9)/(ehh+1e-9)
    return np.array([tilt, hmohh, mhr], dtype=np.float32)

def build_mel_tensor(sig, sr):
    wf = torch.as_tensor(np.asarray(sig, dtype=np.float32).reshape(-1))
    if wf.numel() < N_FFT: wf = F.pad(wf, (0, N_FFT - wf.numel()))
    win = torch.hann_window(N_FFT)
    stft = torch.stft(wf, n_fft=N_FFT, hop_length=HOP_LENGTH, win_length=N_FFT, window=win, center=True, return_complex=True)
    power = stft.abs().pow(2.)
    mel_spec = torch.matmul(MEL_FILTER, power)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))
    mel_spec = mel_spec - mel_spec.amin()
    peak = float(mel_spec.amax()) if mel_spec.numel() else 0.
    if peak > 0.: mel_spec = mel_spec / peak
    rgb = torch.stack([mel_spec]*3, dim=0).float()
    rgb = F.interpolate(rgb.unsqueeze(0), size=(224,224), mode='bilinear', align_corners=False).squeeze(0)
    return transforms.Normalize(mean=MEAN, std=STD)(rgb)

# ── Load data ──
def load_manifest(p):
    with open(p, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

print("Loading V6 checkpoint...")
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

ckpt = torch.load(str(V6_CKPT), map_location=device, weights_only=False)
sd = ckpt.get('model_state_dict', ckpt)
spectral_dim = int(ckpt.get('spectral_dim', 16) or 16)
dropout = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
print(f"spectral_dim={spectral_dim}, dropout={dropout}")

model = SqueezeNetLF(spectral_dim=spectral_dim, dropout=dropout).to(device)
model.load_state_dict(sd)
model.eval()

manifest = load_manifest(SONG_TEST)
print(f"Test entries: {len(manifest)}")

y_true, y_pred, y_prob = [], [], []
t0 = time.time()
BATCH = 32
spec_batch, mel_batch = [], []
batch_rows = []

@torch.no_grad()
def flush():
    global spec_batch, mel_batch, batch_rows
    if not batch_rows: return
    mels = torch.stack(mel_batch).to(device)
    specs = torch.stack(spec_batch).to(device)
    logits = model(mels, specs)
    probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
    for row, p in zip(batch_rows, probs):
        y_true.append(int(float(row.get('mix', 0) or 0)))
        y_pred.append(1 if p > 0.5 else 0)
        y_prob.append(float(p))
    spec_batch, mel_batch, batch_rows = [], [], []

import soundfile as sf
for i, row in enumerate(manifest):
    if i % 200 == 0: print(f"  {i}/{len(manifest)}...")
    try:
        audio, sr = sf.read(str(Path(row['wav_path'])))
        if len(audio.shape) > 1: audio = audio.mean(axis=1)
        audio = np.asarray(audio, dtype=np.float32)
        mel_batch.append(build_mel_tensor(audio, int(sr)))
        spec_batch.append(torch.from_numpy(compute_spectral(audio)))
        batch_rows.append(row)
        if len(batch_rows) >= BATCH: flush()
    except Exception as e:
        pass
flush()

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix
acc = accuracy_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
cm = confusion_matrix(y_true, y_pred)

# Per-group breakdown
groups = {'Mixed_Voice_Group': [], 'Control_Group': [], 'Falsetto_Group': [], 'Breathy_Group': []}
for row, pred, prob in zip(manifest, y_pred, y_prob):
    g = row.get('group_name', '')
    if g in groups:
        groups[g].append((int(float(row.get('mix', 0) or 0)), pred, prob))

print(f"\n{'='*60}")
print(f"V6 SONG-LEVEL TEST RESULTS (unseen songs)")
print(f"{'='*60}")
print(f"Samples: {len(y_true)} (mix={sum(y_true)}, non_mix={len(y_true)-sum(y_true)})")
print(f"Accuracy: {acc:.4f}")
print(f"Mix F1: {f1:.4f}  Precision: {prec:.4f}  Recall: {rec:.4f}")
print(f"Confusion: {cm.tolist()}")
avg_pos = np.mean([p for p, t in zip(y_prob, y_true) if t == 1])
avg_neg = np.mean([p for p, t in zip(y_prob, y_true) if t == 0])
print(f"Avg prob (mix): {avg_pos:.4f}  Avg prob (non_mix): {avg_neg:.4f}")
print(f"\nPer-Group Accuracy:")
for g, items in groups.items():
    if items:
        g_acc = sum(p == t for t, p, _ in items) / len(items)
        print(f"  {g:<25} n={len(items):<5} acc={g_acc:.4f}")
print(f"Time: {time.time()-t0:.1f}s")
