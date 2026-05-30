"""Fair V1 vs V6 comparison on same test sets with correct window inference."""
import csv, time, sys
from pathlib import Path
import numpy as np
import torch
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

CHECKPOINTS = {
    'V1': PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v1/best_mix_binary_latefusion.pt',
    'V6': PROJECT / 'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt',
}

CURATED = PROJECT / 'ml_dl_models/gtsinger_multitech/dataset/curated'
TEST_SETS = {
    'core': CURATED / 'mix_binary_core' / 'test_manifest.csv',
    'english_holdout': CURATED / 'mix_binary_english_singer_holdout_v1' / 'test_manifest.csv',
    'song_level': CURATED / 'mix_binary_song_level_v1' / 'test_manifest.csv',
}


def load_model(ckpt_path):
    ckpt = torch.load(str(ckpt_path), map_location=DEVICE, weights_only=False)
    sd = ckpt.get('model_state_dict', ckpt)
    sd2 = ckpt.get('spectral_dim', 16) or 16
    do = float(ckpt.get('fusion_dropout', 0.3) or 0.3)
    model = SqueezeNetLateFusion(spectral_dim=int(sd2), dropout=do).to(DEVICE)
    model.load_state_dict(sd)
    model.eval()
    return model


@torch.no_grad()
def predict_one(model, row):
    audio = read_audio(Path(row['wav_path']), TARGET_SR, target_length=TARGET_LEN, train=False)
    mel = mel_tensor_from_audio(audio, TARGET_SR, image_size=224, n_fft=1024, hop_length=256, n_mels=128)
    spectral = compute_spectral_features(audio, TARGET_SR)
    mel = eval_tf(mel).unsqueeze(0).to(DEVICE)
    sp = torch.from_numpy(spectral).unsqueeze(0).to(DEVICE)
    logits = model(mel, sp)
    return float(torch.softmax(logits, dim=1)[0, 1].cpu())


def evaluate_model(model, test_path):
    with open(test_path, 'r', encoding='utf-8-sig', newline='') as f:
        manifest = list(csv.DictReader(f))
    y_true, y_pred, y_prob = [], [], []
    for row in manifest:
        try:
            prob = predict_one(model, row)
            label = int(float(row.get('mix', 0) or 0))
            y_true.append(label)
            y_pred.append(1 if prob > 0.5 else 0)
            y_prob.append(prob)
        except Exception:
            pass

    pos_mask = [t == 1 for t in y_true]
    neg_mask = [t == 0 for t in y_true]
    return {
        'n': len(y_true),
        'n_pos': sum(pos_mask),
        'n_neg': sum(neg_mask),
        'acc': accuracy_score(y_true, y_pred),
        'f1': f1_score(y_true, y_pred, pos_label=1, zero_division=0),
        'precision': precision_score(y_true, y_pred, pos_label=1, zero_division=0),
        'recall': recall_score(y_true, y_pred, pos_label=1, zero_division=0),
        'cm': confusion_matrix(y_true, y_pred).tolist(),
        'avg_prob_pos': float(np.mean([p for p, m in zip(y_prob, pos_mask) if m])),
        'avg_prob_neg': float(np.mean([p for p, m in zip(y_prob, neg_mask) if m])),
    }


print(f"Device: {DEVICE}")
results = {}
for model_name, ckpt in CHECKPOINTS.items():
    if not ckpt.exists():
        print(f"Skip {model_name}: not found")
        continue
    print(f"\n{'='*60}\nLoading {model_name}: {ckpt.name}")
    t0 = time.time()
    model = load_model(ckpt)
    print(f"  Loaded in {time.time()-t0:.1f}s")

    model_results = {}
    for test_name, test_path in TEST_SETS.items():
        if not test_path.exists():
            print(f"  Skip {test_name}: not found")
            continue
        t1 = time.time()
        r = evaluate_model(model, test_path)
        r['time_s'] = time.time() - t1
        model_results[test_name] = r
        print(f"  {test_name}: n={r['n']} acc={r['acc']:.4f} f1={r['f1']:.4f} "
              f"P={r['precision']:.4f} R={r['recall']:.4f} "
              f"pos_prob={r['avg_prob_pos']:.3f} neg_prob={r['avg_prob_neg']:.3f} "
              f"({r['time_s']:.1f}s)")
    results[model_name] = model_results
    del model
    torch.cuda.empty_cache()

# Comparison
print(f"\n{'='*80}")
print("HEAD-TO-HEAD COMPARISON (same test sets, same inference pipeline)")
print(f"{'='*80}")
for test_name in TEST_SETS:
    if test_name not in results.get('V1', {}) or test_name not in results.get('V6', {}):
        continue
    print(f"\n--- {test_name} ---")
    v1 = results['V1'][test_name]
    v6 = results['V6'][test_name]
    print(f"{'Metric':<20} {'V1 (clip-split)':<15} {'V6 (song-split)':<15} {'Delta':<10}")
    print('-' * 60)
    for m in ['acc', 'f1', 'precision', 'recall']:
        d = v6[m] - v1[m]
        s = '+' if d > 0 else ''
        print(f"{m:<20} {v1[m]:<15.4f} {v6[m]:<15.4f} {s}{d:<9.4f}")
