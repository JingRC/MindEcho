"""Calibrate temporal smoothing: measure FN rescue vs FP cost on core_CN test set."""
import csv, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import torch

PROJECT = Path(r'd:\-MindEcho-main')
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training'))
from train_mix_binary_squeezenet_latefusion import (
    read_audio, mel_tensor_from_audio, compute_spectral_features,
    build_transforms, SqueezeNetLateFusion,
)

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
TARGET_SR = 22050
TARGET_LEN = int(round(TARGET_SR * 2.4))
_, eval_tf = build_transforms(image_size=224, augment_profile='safe')

V6_CKPT = PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt'
TEST_CSV = PROJECT / 'ml_dl_models/gtsinger_multitech/dataset/curated/mix_binary_core/test_manifest.csv'

# Load model
ckpt = torch.load(str(V6_CKPT), map_location=DEVICE, weights_only=False)
sd = ckpt.get('model_state_dict', ckpt)
sd2 = ckpt.get('spectral_dim', 16) or 16
do = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
model = SqueezeNetLateFusion(spectral_dim=int(sd2), dropout=do).to(DEVICE)
model.eval()

FEMALE_THRESHOLD = 0.225
MALE_THRESHOLD = 0.275


@torch.no_grad()
def predict_one(row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(DEVICE)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(DEVICE)
    logits = model(mel, sp)
    return float(torch.softmax(logits, dim=1)[0, 1].cpu())


def is_female_singer(singer):
    return any(kw in str(singer) for kw in ['Alto', 'Soprano', 'Mezzo'])


def apply_temporal_smoothing(records, half_window=3):
    """In-place temporal smoothing of mix_prob. Only boosts UP."""
    n = len(records)
    if n < 3:
        return records
    for i in range(n):
        cur_prob = records[i]['mix_prob']
        cur_thr = records[i]['mix_threshold']
        if cur_prob >= cur_thr:
            continue
        neighbor_probs = []
        above_count = 0
        for j in range(max(0, i - half_window), min(n, i + half_window + 1)):
            if j == i:
                continue
            p = records[j]['mix_prob']
            t = records[j]['mix_threshold']
            if p > 0:
                neighbor_probs.append(p)
                if p >= t:
                    above_count += 1
        if len(neighbor_probs) < 2 or above_count < 2:
            continue
        neighbor_mean = sum(neighbor_probs) / len(neighbor_probs)
        if neighbor_mean <= cur_prob:
            continue
        if neighbor_mean > cur_thr + 0.05:
            blend = 0.65
        elif neighbor_mean > cur_thr:
            blend = 0.55
        else:
            blend = 0.40
        records[i]['mix_prob'] = cur_prob + blend * (neighbor_mean - cur_prob)
    return records


# Load manifest
with open(TEST_CSV, 'r', encoding='utf-8-sig', newline='') as f:
    manifest = list(csv.DictReader(f))

print(f"Running inference on {len(manifest)} samples...")
results = []
for i, row in enumerate(manifest):
    try:
        prob = predict_one(row)
        label = int(float(row.get('mix', 0) or 0))
        parts = row['item_name'].split('#')
        singer = parts[1]
        female = is_female_singer(singer)
        threshold = FEMALE_THRESHOLD if female else MALE_THRESHOLD
        results.append({
            'item_name': row['item_name'],
            'singer': singer,
            'song': parts[3],
            'group': parts[4],
            'clip': parts[5],
            'label': label,
            'mix_prob': prob,
            'mix_threshold': threshold,
            'female': female,
        })
    except Exception:
        pass
    if (i + 1) % 100 == 0:
        print(f"  {i + 1}/{len(manifest)}")

# ── Baseline (gender-aware threshold only, no smoothing) ──
print(f"\n{'='*70}")
print("BASELINE: Gender-aware threshold (no temporal smoothing)")
print(f"{'='*70}")
y_true = [r['label'] for r in results]
y_prob = [r['mix_prob'] for r in results]
y_thr = [r['mix_threshold'] for r in results]
y_pred_baseline = [1 if p >= t else 0 for p, t in zip(y_prob, y_thr)]

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix


def report(name, y_pred):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    cm = confusion_matrix(y_true, y_pred)
    fn_count = cm[1][0]
    fp_count = cm[0][1]
    tp_count = cm[1][1]
    print(f"  {name}: Acc={acc:.4f} F1={f1:.4f} Prec={prec:.4f} Rec={rec:.4f} FN={fn_count} FP={fp_count} TP={tp_count}")
    return {'acc': acc, 'f1': f1, 'precision': prec, 'recall': rec, 'fn': fn_count, 'fp': fp_count, 'tp': tp_count}


baseline_metrics = report("Baseline", y_pred_baseline)

# ── Temporal smoothing: simulate frame-ordered stream ──
# Group by (singer, song) — within each song, sort by clip ID (temporal order)
# and apply smoothing
print(f"\n{'='*70}")
print("TEMPORAL SMOOTHING: Simulated on (singer, song) groups")
print(f"{'='*70}")

smoothed_by_key = {}
groups = defaultdict(list)
for r in results:
    groups[(r['singer'], r['song'])].append(r)

for (singer, song), group_records in groups.items():
    if len(group_records) < 2:
        for r in group_records:
            smoothed_by_key[r['item_name']] = r
        continue
    group_records.sort(key=lambda r: int(r['clip']))
    apply_temporal_smoothing(group_records)
    for r in group_records:
        smoothed_by_key[r['item_name']] = r
smoothed_aligned = [smoothed_by_key[r['item_name']] for r in results]

y_prob_smoothed = [r['mix_prob'] for r in smoothed_aligned]
y_pred_smoothed = [1 if p >= t else 0 for p, t in zip(y_prob_smoothed, y_thr)]
smoothed_metrics = report("Smoothed", y_pred_smoothed)

# ── Per-singer breakdown ──
print(f"\n{'='*70}")
print("PER-SINGER BREAKDOWN")
print(f"{'='*70}")

singers = sorted(set(r['singer'] for r in results))
for singer in singers:
    singer_results = [r for r in results if r['singer'] == singer]
    singer_smoothed = [smoothed_by_key[r['item_name']] for r in singer_results]
    s_true = [r['label'] for r in singer_results]
    s_prob = [r['mix_prob'] for r in singer_results]
    s_thr = [r['mix_threshold'] for r in singer_results]
    s_prob_s = [r['mix_prob'] for r in singer_smoothed]

    s_pred_base = [1 if p >= t else 0 for p, t in zip(s_prob, s_thr)]
    s_pred_smooth = [1 if p >= t else 0 for p, t in zip(s_prob_s, s_thr)]

    cm_base = confusion_matrix(s_true, s_pred_base)
    cm_smooth = confusion_matrix(s_true, s_pred_smooth)

    fn_base, fp_base = cm_base[1][0], cm_base[0][1]
    fn_s, fp_s = cm_smooth[1][0], cm_smooth[0][1]
    delta_fn = fn_base - fn_s
    delta_fp = fp_s - fp_base

    rec_base = recall_score(s_true, s_pred_base, pos_label=1, zero_division=0)
    rec_s = recall_score(s_true, s_pred_smooth, pos_label=1, zero_division=0)

    print(f"  {singer}: FN {fn_base}→{fn_s} ({delta_fn:+d}), FP {fp_base}→{fp_s} ({delta_fp:+d}), "
          f"Recall {rec_base:.3f}→{rec_s:.3f}")

# ── Summary ──
print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
delta_fn = baseline_metrics['fn'] - smoothed_metrics['fn']
delta_fp = smoothed_metrics['fp'] - baseline_metrics['fp']
print(f"FN: {baseline_metrics['fn']} → {smoothed_metrics['fn']} (rescued {delta_fn})")
print(f"FP: {baseline_metrics['fp']} → {smoothed_metrics['fp']} (added {delta_fp})")
print(f"Recall: {baseline_metrics['recall']:.4f} → {smoothed_metrics['recall']:.4f}")
print(f"F1: {baseline_metrics['f1']:.4f} → {smoothed_metrics['f1']:.4f}")
print("\nDone.")
