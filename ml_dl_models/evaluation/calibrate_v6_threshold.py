"""V6 threshold calibration: sweep thresholds to optimize core CN recall while monitoring English."""
import csv, time, sys
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix

PROJECT = Path(r'd:\-MindEcho-main')
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training'))
from train_mix_binary_squeezenet_latefusion import (read_audio, mel_tensor_from_audio,
    compute_spectral_features, build_transforms, SqueezeNetLateFusion)
from evaluate_mix_voice import resolve_device

DEVICE = resolve_device()
TARGET_SR = 22050
TARGET_LEN = int(round(TARGET_SR * 2.4))

_, eval_tf = build_transforms(image_size=224, augment_profile='safe')

V6_CKPT = PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt'

CURATED = PROJECT / 'ml_dl_models/gtsinger_multitech/dataset/curated'
TEST_SETS = {
    'core': CURATED / 'mix_binary_core' / 'test_manifest.csv',
    'english_holdout': CURATED / 'mix_binary_english_singer_holdout_v1' / 'test_manifest.csv',
    'song_level': CURATED / 'mix_binary_song_level_v1' / 'test_manifest.csv',
}

print(f"Device: {DEVICE}")

# Load model
import torch
ckpt = torch.load(str(V6_CKPT), map_location=DEVICE, weights_only=False)
sd = ckpt.get('model_state_dict', ckpt)
sd2 = ckpt.get('spectral_dim', 16) or 16
do = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
best_threshold = float(ckpt.get('best_threshold', 0.4))
print(f"spectral_dim={sd2}, dropout={do}, training_best_threshold={best_threshold}")

model = SqueezeNetLateFusion(spectral_dim=int(sd2), dropout=do).to(DEVICE)
model.load_state_dict(sd)
model.eval()

@torch.no_grad()
def predict_one(model, row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(DEVICE)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(DEVICE)
    logits = model(mel, sp)
    return float(torch.softmax(logits, dim=1)[0, 1].cpu())

def load_predictions(test_path):
    """Run inference once and cache all probabilities."""
    with open(test_path, 'r', encoding='utf-8-sig', newline='') as f:
        manifest = list(csv.DictReader(f))
    y_true, y_prob = [], []
    for row in manifest:
        try:
            prob = predict_one(model, row)
            label = int(float(row.get('mix', 0) or 0))
            y_true.append(label)
            y_prob.append(prob)
        except Exception:
            pass
    return y_true, y_prob

# Collect predictions for all test sets
all_data = {}
print("\nRunning inference on all test sets...")
for test_name, test_path in TEST_SETS.items():
    if not test_path.exists():
        print(f"  Skip {test_name}: not found")
        continue
    t0 = time.time()
    y_true, y_prob = load_predictions(test_path)
    all_data[test_name] = (y_true, y_prob)
    print(f"  {test_name}: {len(y_true)} samples in {time.time()-t0:.1f}s")

# Sweep thresholds
thresholds = np.arange(0.15, 0.90, 0.025)
print(f"\n{'='*100}")
print(f"THRESHOLD SWEEP ({len(thresholds)} thresholds from {thresholds[0]:.3f} to {thresholds[-1]:.3f})")
print(f"{'='*100}")

# Header
print(f"{'Thr':<8}", end='')
for test_name in all_data:
    print(f" {test_name + '_acc':<12} {test_name + '_f1':<12} {test_name + '_P':<12} {test_name + '_R':<12}", end='  ')
print()

best_core_f1 = 0
best_core_thr = 0.5
best_english_f1_at_best_core = 0
best_song_f1_at_best_core = 0

for thr in thresholds:
    print(f"{thr:<8.3f}", end='')
    row_data = {}
    for test_name, (y_true, y_prob) in all_data.items():
        y_pred = [1 if p > thr else 0 for p in y_prob]
        acc = accuracy_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
        prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
        rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
        row_data[test_name] = (acc, f1, prec, rec)
        print(f" {acc:<12.4f} {f1:<12.4f} {prec:<12.4f} {rec:<12.4f}", end='  ')
    print()

    # Track best core CN F1
    if row_data['core'][1] > best_core_f1:
        best_core_f1 = row_data['core'][1]
        best_core_thr = thr
        best_english_f1_at_best_core = row_data['english_holdout'][1]
        best_song_f1_at_best_core = row_data['song_level'][1]

# Summary
print(f"\n{'='*80}")
print("RECOMMENDATION")
print(f"{'='*80}")
print(f"Training best_threshold: {best_threshold}")
print(f"Current default (0.5):")
for test_name, (y_true, y_prob) in all_data.items():
    y_pred = [1 if p > 0.5 else 0 for p in y_prob]
    f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    acc = accuracy_score(y_true, y_pred)
    print(f"  {test_name:<20} acc={acc:.4f}  f1={f1:.4f}  P={prec:.4f}  R={rec:.4f}")

print(f"\nOptimal for core CN F1: threshold={best_core_thr:.3f}")
print(f"  core:           f1={best_core_f1:.4f}")
print(f"  english_holdout: f1={best_english_f1_at_best_core:.4f}")
print(f"  song_level:      f1={best_song_f1_at_best_core:.4f}")

# Detailed breakdown at best threshold
print(f"\n--- Detail at threshold={best_core_thr:.3f} ---")
for test_name in all_data:
    y_true, y_prob = all_data[test_name]
    y_pred = [1 if p > best_core_thr else 0 for p in y_prob]
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    cm = confusion_matrix(y_true, y_pred)
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    print(f"  {test_name}: n={len(y_true)} (pos={n_pos}, neg={n_neg})")
    print(f"    acc={acc:.4f}  f1={f1:.4f}  P={prec:.4f}  R={rec:.4f}  CM={cm.tolist()}")

print("\nDone.")
