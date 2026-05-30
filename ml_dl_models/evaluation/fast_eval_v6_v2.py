"""Fast V6 eval using EXACT training pipeline (2.4s windows)."""
import csv, json, time, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import models, transforms
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix

PROJECT = Path(r'd:\-MindEcho-main')
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training'))
from train_mix_binary_squeezenet_latefusion import (read_audio, mel_tensor_from_audio,
    compute_spectral_features, build_transforms, build_eval_anchor_ratios,
    SqueezeNetLateFusion, MEAN, STD)
from evaluate_mix_voice import resolve_device

V6_CKPT = PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt'
SONG_TEST = PROJECT / 'ml_dl_models/gtsinger_multitech/dataset/curated/mix_binary_song_level_v1/test_manifest.csv'

device = resolve_device()
print(f"Device: {device}")

ckpt = torch.load(str(V6_CKPT), map_location=device, weights_only=False)
sd = ckpt.get('model_state_dict', ckpt)
spectral_dim = int(ckpt.get('spectral_dim', 16) or 16)
dropout = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
print(f"spectral_dim={spectral_dim}, dropout={dropout}")

model = SqueezeNetLateFusion(spectral_dim=spectral_dim, dropout=dropout).to(device)
model.load_state_dict(sd)
model.eval()

_, eval_tf = build_transforms(image_size=224, augment_profile='safe')
TARGET_SR = 22050
TARGET_LEN = int(round(TARGET_SR * 2.4))  # 52920

with open(SONG_TEST, 'r', encoding='utf-8-sig', newline='') as f:
    manifest = list(csv.DictReader(f))
print(f"Test entries: {len(manifest)}")

y_true, y_pred, y_prob = [], [], []
t0 = time.time()

@torch.no_grad()
def predict_one(row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(device)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(device)
    logits = model(mel, sp)
    prob = float(torch.softmax(logits, dim=1)[0, 1].cpu())
    return prob

BATCH = 48
for i in range(0, len(manifest), BATCH):
    batch = manifest[i:i+BATCH]
    if i % 480 == 0: print(f"  {i}/{len(manifest)}...")
    for row in batch:
        try:
            prob = predict_one(row)
            label = int(float(row.get('mix', 0) or 0))
            y_true.append(label)
            y_pred.append(1 if prob > 0.5 else 0)
            y_prob.append(prob)
        except Exception as e:
            pass

print(f"\nProcessed: {len(y_true)} samples in {time.time()-t0:.1f}s")

acc = accuracy_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
cm = confusion_matrix(y_true, y_pred)
avg_pos = np.mean([p for p, t in zip(y_prob, y_true) if t == 1]) if any(t==1 for t in y_true) else 0
avg_neg = np.mean([p for p, t in zip(y_prob, y_true) if t == 0]) if any(t==0 for t in y_true) else 0

print(f"Accuracy: {acc:.4f}")
print(f"Mix F1: {f1:.4f}  P: {prec:.4f}  R: {rec:.4f}")
print(f"CM: {cm.tolist()}")
print(f"Avg prob pos: {avg_pos:.4f}  neg: {avg_neg:.4f}")

# Per group
from collections import defaultdict
groups = defaultdict(list)
for row, p, t in zip(manifest, y_pred, y_true):
    g = row.get('group_name', '?')
    groups[g].append((t, p))
print("\nPer Group:")
for g, items in sorted(groups.items()):
    g_acc = sum(t == p for t, p in items) / len(items)
    n_pos = sum(t == 1 for t, _ in items)
    print(f"  {g:<30} n={len(items):<5} pos={n_pos:<5} acc={g_acc:.4f}")
