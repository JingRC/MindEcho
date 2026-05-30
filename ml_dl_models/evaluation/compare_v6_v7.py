"""Head-to-head comparison: V6 vs V7 on all test sets with threshold sweeps."""
import csv, time, sys, json
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix
import torch

PROJECT = Path(r'd:\-MindEcho-main')
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training'))
sys.path.insert(0, str(PROJECT / 'ml_dl_models' / 'evaluation'))
from train_mix_binary_squeezenet_latefusion import (read_audio, mel_tensor_from_audio,
    compute_spectral_features, build_transforms, SqueezeNetLateFusion)
from evaluate_mix_voice import resolve_device

DEVICE = resolve_device()
TARGET_SR = 22050
TARGET_LEN = int(round(TARGET_SR * 2.4))
_, eval_tf = build_transforms(image_size=224, augment_profile='safe')

CURATED = PROJECT / 'ml_dl_models/gtsinger_multitech/dataset/curated'

CHECKPOINTS = {
    'V6': PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt',
    'V7': PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v7_multilang/best_mix_binary_latefusion.pt',
}

# Test sets: all available
TEST_SETS = {}
for name, path in [
    ('core_CN', CURATED / 'mix_binary_core' / 'test_manifest.csv'),
    ('eng_holdout', CURATED / 'mix_binary_english_singer_holdout_v1' / 'test_manifest.csv'),
    ('song_level_v1', CURATED / 'mix_binary_song_level_v1' / 'test_manifest.csv'),
    ('song_level_v2', CURATED / 'mix_binary_song_level_v2' / 'test_manifest.csv'),
]:
    if path.exists():
        TEST_SETS[name] = path

print(f"Device: {DEVICE}")
print(f"Test sets: {list(TEST_SETS.keys())}")


def load_model(ckpt_path):
    ckpt = torch.load(str(ckpt_path), map_location=DEVICE, weights_only=False)
    sd = ckpt.get('model_state_dict', ckpt)
    sd2 = ckpt.get('spectral_dim', 16) or 16
    do = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
    best_thr = float(ckpt.get('best_threshold', 0.4))
    model = SqueezeNetLateFusion(spectral_dim=int(sd2), dropout=do).to(DEVICE)
    model.load_state_dict(sd)
    model.eval()
    return model, int(sd2), do, best_thr


@torch.no_grad()
def predict_one(model, row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(DEVICE)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(DEVICE)
    logits = model(mel, sp)
    return float(torch.softmax(logits, dim=1)[0, 1].cpu())


def load_manifest(path):
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def run_inference(model, manifest):
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


# ============================================================
# Load models and manifests
# ============================================================
print("\n=== Loading models ===")
models = {}
for name, ckpt_path in CHECKPOINTS.items():
    model, sd2, do, best_thr = load_model(ckpt_path)
    models[name] = {'model': model, 'spectral_dim': sd2, 'dropout': do, 'training_best_thr': best_thr}
    print(f"  {name}: spectral_dim={sd2}, dropout={do:.2f}, training_best_threshold={best_thr}")

print("\n=== Loading manifests ===")
manifests = {}
for name, path in TEST_SETS.items():
    manifests[name] = load_manifest(path)
    n_pos = sum(1 for r in manifests[name] if int(float(r.get('mix', 0) or 0)) == 1)
    print(f"  {name}: {len(manifests[name])} samples (pos={n_pos}, neg={len(manifests[name]) - n_pos})")

# ============================================================
# Run inference
# ============================================================
print("\n=== Running inference ===")
all_preds = {}  # all_preds[model_name][test_name] = (y_true, y_prob)
for model_name, md in models.items():
    print(f"\n{model_name}:")
    all_preds[model_name] = {}
    for test_name, manifest in manifests.items():
        t0 = time.time()
        y_true, y_prob = run_inference(md['model'], manifest)
        all_preds[model_name][test_name] = (y_true, y_prob)
        pos = sum(y_true)
        print(f"  {test_name}: {len(y_true)} samples in {time.time()-t0:.1f}s (pos={pos})")

# ============================================================
# Threshold sweep
# ============================================================
thresholds = np.arange(0.10, 0.90, 0.025)
print(f"\n{'='*140}")
print(f"THRESHOLD SWEEP: {len(thresholds)} steps ({thresholds[0]:.3f}..{thresholds[-1]:.3f})")
print(f"{'='*140}")

# Collect all rows
sweep_rows = []
for thr in thresholds:
    for model_name in all_preds:
        for test_name in all_preds[model_name]:
            y_true, y_prob = all_preds[model_name][test_name]
            y_pred = [1 if p > thr else 0 for p in y_prob]
            acc = accuracy_score(y_true, y_pred)
            f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
            prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
            rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
            sweep_rows.append({
                'threshold': thr,
                'model': model_name,
                'test_set': test_name,
                'acc': acc, 'f1': f1, 'precision': prec, 'recall': rec,
            })

# ============================================================
# Report: Best threshold per model per test set
# ============================================================
print(f"\n{'='*80}")
print("BEST THRESHOLD BY TEST SET")
print(f"{'='*80}")

best_per_model_test = {}
for model_name in all_preds:
    best_per_model_test[model_name] = {}
    print(f"\n{model_name}:")
    print(f"  {'Test Set':<20} {'TrainBestThr':>10} {'OptThr':>8} {'Acc':>8} {'F1':>8} {'Prec':>8} {'Rec':>8}")
    print(f"  {'-'*70}")
    for test_name in all_preds[model_name]:
        test_rows = [r for r in sweep_rows if r['model'] == model_name and r['test_set'] == test_name]
        best_row = max(test_rows, key=lambda r: r['f1'])
        best_per_model_test[model_name][test_name] = best_row
        train_thr = models[model_name]['training_best_thr']
        print(f"  {test_name:<20} {train_thr:>10.3f} {best_row['threshold']:>8.3f} {best_row['acc']:>8.4f} {best_row['f1']:>8.4f} {best_row['precision']:>8.4f} {best_row['recall']:>8.4f}")

# ============================================================
# Head-to-head: detail at each model's best training threshold
# ============================================================
print(f"\n{'='*120}")
print("HEAD-TO-HEAD AT TRAINING BEST THRESHOLD")
print(f"{'='*120}")

for model_name in all_preds:
    train_thr = models[model_name]['training_best_thr']
    print(f"\n{model_name} @ training threshold {train_thr:.3f}:")
    print(f"  {'Test Set':<20} {'N':>6} {'Pos':>6} {'Acc':>8} {'F1':>8} {'Prec':>8} {'Rec':>8} {'CM'}")
    print(f"  {'-'*100}")
    for test_name in all_preds[model_name]:
        y_true, y_prob = all_preds[model_name][test_name]
        y_pred = [1 if p > train_thr else 0 for p in y_prob]
        acc = accuracy_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
        prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
        rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
        cm = confusion_matrix(y_true, y_pred)
        n_pos = sum(y_true)
        print(f"  {test_name:<20} {len(y_true):>6} {n_pos:>6} {acc:>8.4f} {f1:>8.4f} {prec:>8.4f} {rec:>8.4f} {cm.tolist()}")

# ============================================================
# Global optimum: maximize core CN F1, show other sets
# ============================================================
print(f"\n{'='*120}")
print("GLOBAL OPTIMUM: Maximize core_CN F1")
print(f"{'='*120}")

for model_name in all_preds:
    core_rows = [r for r in sweep_rows if r['model'] == model_name and r['test_set'] == 'core_CN']
    best_core = max(core_rows, key=lambda r: r['f1'])
    best_thr = best_core['threshold']
    print(f"\n{model_name} @ threshold {best_thr:.3f} (max core_CN F1):")
    print(f"  {'Test Set':<20} {'Acc':>8} {'F1':>8} {'Prec':>8} {'Rec':>8}")
    print(f"  {'-'*55}")
    for test_name in all_preds[model_name]:
        y_true, y_prob = all_preds[model_name][test_name]
        y_pred = [1 if p > best_thr else 0 for p in y_prob]
        acc = accuracy_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
        prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
        rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
        print(f"  {test_name:<20} {acc:>8.4f} {f1:>8.4f} {prec:>8.4f} {rec:>8.4f}")

# ============================================================
# Breakdown by language in song_level_v2
# ============================================================
if 'song_level_v2' in manifests:
    print(f"\n{'='*120}")
    print("LANGUAGE BREAKDOWN: song_level_v2")
    print(f"{'='*120}")

    for model_name in all_preds:
        y_true, y_prob = all_preds[model_name]['song_level_v2']
        manifest = manifests['song_level_v2']

        # Group by language
        lang_data = {}
        for i, row in enumerate(manifest):
            lang = row.get('language', 'Unknown')
            if lang not in lang_data:
                lang_data[lang] = {'y_true': [], 'y_prob': [], 'count': 0, 'pos': 0}
            lang_data[lang]['y_true'].append(y_true[i])
            lang_data[lang]['y_prob'].append(y_prob[i])
            lang_data[lang]['count'] += 1
            if y_true[i] == 1:
                lang_data[lang]['pos'] += 1

        train_thr = models[model_name]['training_best_thr']
        print(f"\n{model_name} @ training threshold {train_thr:.3f}:")
        print(f"  {'Lang':<12} {'N':>6} {'Pos':>6} {'Acc':>8} {'F1':>8} {'Prec':>8} {'Rec':>8}")
        print(f"  {'-'*65}")
        for lang in sorted(lang_data.keys()):
            d = lang_data[lang]
            y_pred = [1 if p > train_thr else 0 for p in d['y_prob']]
            acc = accuracy_score(d['y_true'], y_pred)
            f1 = f1_score(d['y_true'], y_pred, pos_label=1, zero_division=0)
            prec = precision_score(d['y_true'], y_pred, pos_label=1, zero_division=0)
            rec = recall_score(d['y_true'], y_pred, pos_label=1, zero_division=0)
            print(f"  {lang:<12} {d['count']:>6} {d['pos']:>6} {acc:>8.4f} {f1:>8.4f} {prec:>8.4f} {rec:>8.4f}")

print(f"\n{'='*120}")
print("DONE")
