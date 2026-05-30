"""Root cause analysis: prove 39 Chinese FN are labeling ambiguity, not model deficiency."""
import csv, json, sys
import numpy as np
from pathlib import Path
from collections import Counter
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
THRESHOLD = 0.275

# Load model
ckpt = torch.load(str(V6_CKPT), map_location=DEVICE, weights_only=False)
sd = ckpt.get('model_state_dict', ckpt)
sd2 = ckpt.get('spectral_dim', 16) or 16
do = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
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
    return float(torch.softmax(logits, dim=1)[0, 1].cpu()), spectral

# Load manifest
with open(TEST_CSV, 'r', encoding='utf-8-sig', newline='') as f:
    manifest = list(csv.DictReader(f))

print(f"Test manifest: {len(manifest)} rows")
print(f"Columns: {list(manifest[0].keys())}")

# Run inference and classify
fn_list = []
tp_list = []
for row in manifest:
    try:
        prob, spectral = predict_one(model, row)
        label = int(float(row.get('mix', 0) or 0))
        item_name = row['item_name']
        parts = item_name.split('#')

        entry = {
            'item_name': item_name,
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
            # From manifest CSV
            'mix_variant': row.get('mix_variant', '?'),
            'label_signature': row.get('label_signature', '?'),
            'falsetto': int(float(row.get('falsetto', 0) or 0)),
            'breathy': int(float(row.get('breathy', 0) or 0)),
            'vibrato': int(float(row.get('vibrato', 0) or 0)),
            'glissando': int(float(row.get('glissando', 0) or 0)),
            'pharyngeal': int(float(row.get('pharyngeal', 0) or 0)),
        }

        if label == 1 and prob < THRESHOLD:
            fn_list.append(entry)
        elif label == 1 and prob >= THRESHOLD:
            tp_list.append(entry)
    except Exception as e:
        pass

print(f"\nFN: {len(fn_list)}, TP: {len(tp_list)}")

# =============================================================
# ANALYSIS 1: mix_variant distribution (the KEY analysis)
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 1: mix_variant distribution - FN vs TP")
print(f"{'='*70}")

fn_variants = Counter(r['mix_variant'] for r in fn_list)
tp_variants = Counter(r['mix_variant'] for r in tp_list)
print(f"{'Variant':<20} {'FN':>8} {'TP':>8} {'FN%':>8}")
print(f"{'-'*44}")
for variant in ['head_mix', 'breathy_mix', 'clear_mix']:
    fn_n = fn_variants.get(variant, 0)
    tp_n = tp_variants.get(variant, 0)
    fn_pct = 100 * fn_n / (fn_n + tp_n) if (fn_n + tp_n) > 0 else 0
    print(f"  {variant:<18} {fn_n:>8} {tp_n:>8} {fn_pct:>7.1f}%")

# =============================================================
# ANALYSIS 2: label_signature (which techniques co-occur)
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 2: Label signature (6-bit technique flags)")
print(f"{'='*70}")
print("Format: [mix][falsetto][breathy][vibrato][glissando][pharyngeal]")

fn_sigs = Counter(r['label_signature'] for r in fn_list)
tp_sigs = Counter(r['label_signature'] for r in tp_list)

print(f"\nFN label signatures:")
for sig, cnt in fn_sigs.most_common():
    sig_desc = []
    names = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']
    for i, name in enumerate(names):
        if sig[i] == '1':
            sig_desc.append(name)
    print(f"  {sig} = {'+'.join(sig_desc) if sig_desc else 'none'}: {cnt}")

print(f"\nTP label signatures (top 10):")
for sig, cnt in tp_sigs.most_common(10):
    sig_desc = []
    names = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']
    for i, name in enumerate(names):
        if sig[i] == '1':
            sig_desc.append(name)
    print(f"  {sig} = {'+'.join(sig_desc) if sig_desc else 'none'}: {cnt}")

# =============================================================
# ANALYSIS 3: Try to read raw JSONs for FN samples
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 3: Raw JSON ph-level analysis")
print(f"{'='*70}")

# Build raw JSON path from item_name
# item_name: Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#演员#Mixed_Voice_Group#0014
raw_root = PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'raw'

ph_mix_density_fn = []
ph_mix_density_tp = []
ph_fal_density_fn = []
ph_fal_density_tp = []

for entry in fn_list[:10]:  # Check first 10 FN
    # Build path: language/singer/tech_folder/song/group/clip.json
    parts = entry['item_name'].split('#')
    rel_path = f"{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}/{parts[4]}/{parts[5]}.json"
    raw_path = raw_root / rel_path
    if raw_path.exists():
        try:
            data = json.loads(raw_path.read_text(encoding='utf-8'))
            total_ph = 0
            mix_ph = 0
            fal_ph = 0
            both_ph = 0
            for word in data:
                phs = word.get('ph', [])
                mix_flags = word.get('mix', ['0']*len(phs))
                fal_flags = word.get('falsetto', ['0']*len(phs))
                for i in range(len(phs)):
                    total_ph += 1
                    m = int(float(mix_flags[i])) if i < len(mix_flags) else 0
                    f = int(float(fal_flags[i])) if i < len(fal_flags) else 0
                    mix_ph += m
                    fal_ph += f
                    if m and f:
                        both_ph += 1
            mix_density = mix_ph / total_ph if total_ph > 0 else 0
            fal_density = fal_ph / total_ph if total_ph > 0 else 0
            ph_mix_density_fn.append(mix_density)
            ph_fal_density_fn.append(fal_density)
            print(f"  {entry['item_name'][:60]}... mix_density={mix_density:.2f} fal_density={fal_density:.2f} both={both_ph}/{total_ph}")
        except Exception as e:
            print(f"  {entry['item_name'][:60]}... ERROR: {e}")
    else:
        print(f"  {entry['item_name'][:60]}... raw JSON NOT FOUND at {rel_path}")

# Also check some TP for comparison
print(f"\nTP samples for comparison:")
for entry in tp_list[:5]:
    parts = entry['item_name'].split('#')
    rel_path = f"{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}/{parts[4]}/{parts[5]}.json"
    raw_path = raw_root / rel_path
    if raw_path.exists():
        try:
            data = json.loads(raw_path.read_text(encoding='utf-8'))
            total_ph = 0
            mix_ph = 0
            fal_ph = 0
            both_ph = 0
            for word in data:
                phs = word.get('ph', [])
                mix_flags = word.get('mix', ['0']*len(phs))
                fal_flags = word.get('falsetto', ['0']*len(phs))
                for i in range(len(phs)):
                    total_ph += 1
                    m = int(float(mix_flags[i])) if i < len(mix_flags) else 0
                    f = int(float(fal_flags[i])) if i < len(fal_flags) else 0
                    mix_ph += m
                    fal_ph += f
                    if m and f:
                        both_ph += 1
            mix_density = mix_ph / total_ph if total_ph > 0 else 0
            fal_density = fal_ph / total_ph if total_ph > 0 else 0
            ph_mix_density_tp.append(mix_density)
            ph_fal_density_tp.append(fal_density)
            print(f"  {entry['item_name'][:60]}... mix_density={mix_density:.2f} fal_density={fal_density:.2f} both={both_ph}/{total_ph}")
        except Exception as e:
            print(f"  {entry['item_name'][:60]}... ERROR: {e}")

# =============================================================
# ANALYSIS 4: Can we find an acoustic pattern via mel spectrogram?
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 4: Mel spectrogram energy distribution FN vs TP")
print(f"{'='*70}")

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Collect mel spectrograms for a few representative FN and TP
sample_fns = fn_list[:5]
sample_tps = tp_list[:5]

fig, axes = plt.subplots(2, 5, figsize=(25, 8))

for i, entry in enumerate(sample_fns):
    try:
        row = [r for r in manifest if r['item_name'] == entry['item_name']][0]
        audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
        mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
        axes[0][i].imshow(mel.squeeze().numpy(), origin='lower', aspect='auto', cmap='viridis')
        axes[0][i].set_title(f"FN: {entry['song'][:10]}\nprob={entry['prob']:.3f} {entry['mix_variant']}", fontsize=8)
        axes[0][i].axis('off')
    except Exception as e:
        axes[0][i].text(0.5, 0.5, f"ERROR\n{e}", ha='center', va='center', fontsize=6)

for i, entry in enumerate(sample_tps):
    try:
        row = [r for r in manifest if r['item_name'] == entry['item_name']][0]
        audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
        mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
        axes[1][i].imshow(mel.squeeze().numpy(), origin='lower', aspect='auto', cmap='viridis')
        axes[1][i].set_title(f"TP: {entry['song'][:10]}\nprob={entry['prob']:.3f} {entry['mix_variant']}", fontsize=8)
        axes[1][i].axis('off')
    except Exception as e:
        axes[1][i].text(0.5, 0.5, f"ERROR\n{e}", ha='center', va='center', fontsize=6)

plt.tight_layout()
out_path = PROJECT / 'ml_dl_models' / 'evaluation' / 'fn_vs_tp_mel_comparison.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved mel comparison to {out_path}")

# =============================================================
# ANALYSIS 5: Per-singer FN concentration
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 5: FN concentration by singer")
print(f"{'='*70}")

fn_singers = Counter(r['singer'] for r in fn_list)
tp_singers = Counter(r['singer'] for r in tp_list)
total_singers = {}
for r in fn_list + tp_list:
    total_singers[r['singer']] = total_singers.get(r['singer'], 0) + 1

for singer in sorted(fn_singers.keys()):
    fn_n = fn_singers[singer]
    tp_n = tp_singers.get(singer, 0)
    total = fn_n + tp_n
    print(f"  {singer}: {fn_n} FN / {tp_n} TP = {100*fn_n/total:.1f}% miss rate")
    # Breakdown by mix_variant within this singer
    fn_v_by_singer = Counter(r['mix_variant'] for r in fn_list if r['singer'] == singer)
    print(f"    FN variants: {dict(fn_v_by_singer)}")

# =============================================================
# ANALYSIS 6: per-song zero-TP analysis
# =============================================================
print(f"\n{'='*70}")
print("ANALYSIS 6: Songs where ALL mix samples are missed (zero TP)")
print(f"{'='*70}")

fn_songs = set(r['song'] for r in fn_list)
tp_songs = set(r['song'] for r in tp_list)
zero_tp_songs = fn_songs - tp_songs

print(f"Songs with FN but ZERO TP: {len(zero_tp_songs)}")
for song in sorted(zero_tp_songs):
    song_fns = [r for r in fn_list if r['song'] == song]
    singer = song_fns[0]['singer']
    variants = Counter(r['mix_variant'] for r in song_fns)
    probs = [r['prob'] for r in song_fns]
    print(f"  {singer}/{song}: {len(song_fns)} FN, variants={dict(variants)}, prob_mean={np.mean(probs):.3f}")

# =============================================================
# FINAL SUMMARY
# =============================================================
print(f"\n{'='*70}")
print("SUMMARY: Is this labeling ambiguity or model defect?")
print(f"{'='*70}")

# Count how many FN are 'head_mix' (mix+falsetto) vs 'clear_mix' (pure mix)
head_mix_fn = sum(1 for r in fn_list if r['mix_variant'] == 'head_mix')
breathy_mix_fn = sum(1 for r in fn_list if r['mix_variant'] == 'breathy_mix')
clear_mix_fn = sum(1 for r in fn_list if r['mix_variant'] == 'clear_mix')

head_mix_tp = sum(1 for r in tp_list if r['mix_variant'] == 'head_mix')
breathy_mix_tp = sum(1 for r in tp_list if r['mix_variant'] == 'breathy_mix')
clear_mix_tp = sum(1 for r in tp_list if r['mix_variant'] == 'clear_mix')

print(f"\nFN breakdown by variant:")
print(f"  head_mix (mix+falsetto): {head_mix_fn}/{head_mix_fn+head_mix_tp} = {100*head_mix_fn/(head_mix_fn+head_mix_tp):.1f}% miss rate")
print(f"  breathy_mix (mix+breathy): {breathy_mix_fn}/{breathy_mix_fn+breathy_mix_tp} = {100*breathy_mix_fn/(breathy_mix_fn+breathy_mix_tp):.1f}% miss rate")
print(f"  clear_mix (pure mix): {clear_mix_fn}/{clear_mix_fn+clear_mix_tp} = {100*clear_mix_fn/(clear_mix_fn+clear_mix_tp):.1f}% miss rate")

# Key question: are FN more likely to be head_mix than TP?
fn_head_pct = 100 * head_mix_fn / len(fn_list) if fn_list else 0
tp_head_pct = 100 * head_mix_tp / len(tp_list) if tp_list else 0
print(f"\n  %head_mix in FN: {fn_head_pct:.1f}% vs %head_mix in TP: {tp_head_pct:.1f}%")

print("\nDone.")
