"""Deep analysis of Chinese FN: extract acoustic features and compare vs TP."""
import csv, json, sys
from pathlib import Path
from collections import Counter
import numpy as np
import torch

PROJECT = Path(r'd:\-MindEcho-main')
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training'))
from train_mix_binary_squeezenet_latefusion import (read_audio, mel_tensor_from_audio,
    compute_spectral_features, build_transforms, SqueezeNetLateFusion)

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
model.load_state_dict(sd)
model.eval()

THRESHOLD = 0.275

@torch.no_grad()
def predict_one(model, row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(DEVICE)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(DEVICE)
    logits = model(mel, sp)
    prob = float(torch.softmax(logits, dim=1)[0, 1].cpu())
    return prob, spectral

print(f"Threshold: {THRESHOLD}")

# Load test manifest
with open(TEST_CSV, 'r', encoding='utf-8-sig', newline='') as f:
    manifest = list(csv.DictReader(f))

# Run inference and collect features
print(f"Running inference on {len(manifest)} samples...")
results = []
for i, row in enumerate(manifest):
    try:
        prob, spectral = predict_one(model, row)
        label = int(float(row.get('mix', 0) or 0))
        item_name = row['item_name']

        # Parse item_name for metadata
        parts = item_name.split('#')

        results.append({
            'item_name': item_name,
            'language': parts[0],
            'singer': parts[1],
            'tech_folder': parts[2],
            'song': parts[3],
            'group': parts[4],
            'clip': parts[5],
            'label': label,
            'prob': prob,
            'spectral_tilt': float(spectral[0]),
            'hm_over_hh': float(spectral[1]),
            'mid_high_ratio': float(spectral[2]),
        })
    except Exception as e:
        pass
    if (i+1) % 100 == 0:
        print(f"  {i+1}/{len(manifest)}")

# Categorize
tp = [r for r in results if r['label'] == 1 and r['prob'] >= THRESHOLD]  # True Positive
fn = [r for r in results if r['label'] == 1 and r['prob'] < THRESHOLD]   # False Negative
fp = [r for r in results if r['label'] == 0 and r['prob'] >= THRESHOLD]  # False Positive
tn = [r for r in results if r['label'] == 0 and r['prob'] < THRESHOLD]   # True Negative

print(f"\n{'='*80}")
print(f"RESULTS @ threshold={THRESHOLD}")
print(f"  TP: {len(tp)}, FN: {len(fn)}, FP: {len(fp)}, TN: {len(tn)}")

# ==============================
# ANALYSIS 1: FN vs TP - spectral features
# ==============================
print(f"\n{'='*80}")
print("SPECTRAL FEATURES: TP vs FN vs FP")
print(f"{'='*80}")

for name, group in [('TP (correctly caught mix)', tp), ('FN (missed mix)', fn), ('FP (false alarm)', fp)]:
    if not group:
        continue
    tilts = [r['spectral_tilt'] for r in group]
    hms = [r['hm_over_hh'] for r in group]
    mhrs = [r['mid_high_ratio'] for r in group]
    probs = [r['prob'] for r in group]
    print(f"\n{name} (n={len(group)}):")
    print(f"  spectral_tilt:   mean={np.mean(tilts):.2f}, std={np.std(tilts):.2f}, min={np.min(tilts):.2f}, max={np.max(tilts):.2f}")
    print(f"  hm_over_hh:      mean={np.mean(hms):.3f}, std={np.std(hms):.3f}, min={np.min(hms):.3f}, max={np.max(hms):.3f}")
    print(f"  mid_high_ratio:  mean={np.mean(mhrs):.3f}, std={np.std(mhrs):.3f}, min={np.min(mhrs):.3f}, max={np.max(mhrs):.3f}")
    print(f"  model_prob:      mean={np.mean(probs):.4f}, std={np.std(probs):.4f}, min={np.min(probs):.4f}, max={np.max(probs):.4f}")

# ==============================
# ANALYSIS 2: FN by group_name
# ==============================
print(f"\n{'='*80}")
print("FN BREAKDOWN BY GROUP")
print(f"{'='*80}")

fn_groups = Counter(r['group'] for r in fn)
print(f"  Groups: {dict(fn_groups)}")

fn_songs = Counter(r['song'] for r in fn)
print(f"  Songs (top 15): {dict(fn_songs.most_common(15))}")

fn_singers = Counter(r['singer'] for r in fn)
print(f"  Singers: {dict(fn_singers)}")

# ==============================
# ANALYSIS 3: FN by group + technique
# ==============================
print(f"\n{'='*80}")
print("FN DETAIL: each sample")
print(f"{'='*80}")

# Sort FN by prob ascending (most confident wrong first)
fn_sorted = sorted(fn, key=lambda r: r['prob'])
for r in fn_sorted:
    print(f"  prob={r['prob']:.4f} | tilt={r['spectral_tilt']:.1f} hm_hh={r['hm_over_hh']:.3f} mhr={r['mid_high_ratio']:.3f} | {r['singer']}/{r['song']}/{r['group']}/{r['clip']}")

# ==============================
# ANALYSIS 4: FN spectral_tilt distribution buckets
# ==============================
print(f"\n{'='*80}")
print("FN SPECTRAL TILT DISTRIBUTION")
print(f"{'='*80}")

buckets = [(-30, -18), (-18, -12), (-12, -8), (-8, -4), (-4, 0), (0, 10)]
for lo, hi in buckets:
    in_range = [r for r in fn if lo <= r['spectral_tilt'] < hi]
    tp_in_range = [r for r in tp if lo <= r['spectral_tilt'] < hi]
    print(f"  tilt [{lo:>4}, {hi:>4}): FN={len(in_range):>3}, TP={len(tp_in_range):>3}")

# ==============================
# ANALYSIS 5: Per-song FN detail - songs with most FN
# ==============================
print(f"\n{'='*80}")
print("PER-SONG FN ANALYSIS")
print(f"{'='*80}")

fn_by_song = {}
for r in fn:
    key = f"{r['singer']}/{r['song']}"
    fn_by_song.setdefault(key, []).append(r)

tp_by_song = {}
for r in tp:
    key = f"{r['singer']}/{r['song']}"
    tp_by_song.setdefault(key, []).append(r)

for song_key in sorted(fn_by_song.keys(), key=lambda k: len(fn_by_song[k]), reverse=True):
    fn_list = fn_by_song[song_key]
    tp_list = tp_by_song.get(song_key, [])
    fn_tilts = [r['spectral_tilt'] for r in fn_list]
    fn_probs = [r['prob'] for r in fn_list]
    tp_tilts = [r['spectral_tilt'] for r in tp_list] if tp_list else []
    tp_probs = [r['prob'] for r in tp_list] if tp_list else []

    groups = Counter(r['group'] for r in fn_list)
    print(f"\n  {song_key}: {len(fn_list)} FN, {len(tp_list)} TP")
    print(f"    FN groups: {dict(groups)}")
    print(f"    FN tilt: mean={np.mean(fn_tilts):.1f}, prob mean={np.mean(fn_probs):.3f}")
    if tp_list:
        print(f"    TP tilt: mean={np.mean(tp_tilts):.1f}, prob mean={np.mean(tp_probs):.3f}")

# ==============================
# ANALYSIS 6: Compare Falsetto_Group FN vs Mixed_Voice_Group FN
# ==============================
print(f"\n{'='*80}")
print("FN: FALSETTO_GROUP vs MIXED_VOICE_GROUP")
print(f"{'='*80}")

for group_name in ['Falsetto_Group', 'Mixed_Voice_Group', 'Control_Group', 'Breathy_Group']:
    fn_g = [r for r in fn if r['group'] == group_name]
    tp_g = [r for r in tp if r['group'] == group_name]
    if fn_g:
        fn_tilts = [r['spectral_tilt'] for r in fn_g]
        fn_hms = [r['hm_over_hh'] for r in fn_g]
        fn_probs = [r['prob'] for r in fn_g]
        print(f"\n  {group_name}: {len(fn_g)} FN / {len(tp_g)} TP")
        print(f"    FN: tilt={np.mean(fn_tilts):.1f}±{np.std(fn_tilts):.1f}, hm_hh={np.mean(fn_hms):.3f}±{np.std(fn_hms):.3f}, prob={np.mean(fn_probs):.3f}±{np.std(fn_probs):.3f}")
        if tp_g:
            tp_tilts = [r['spectral_tilt'] for r in tp_g]
            tp_hms = [r['hm_over_hh'] for r in tp_g]
            tp_probs = [r['prob'] for r in tp_g]
            print(f"    TP: tilt={np.mean(tp_tilts):.1f}±{np.std(tp_tilts):.1f}, hm_hh={np.mean(tp_hms):.3f}±{np.std(tp_hms):.3f}, prob={np.mean(tp_probs):.3f}±{np.std(tp_probs):.3f}")

print("\nDone.")
