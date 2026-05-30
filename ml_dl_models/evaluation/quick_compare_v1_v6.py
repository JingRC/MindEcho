"""Quick evaluation: V6 vs V1 comparison on key test sets."""
import sys, json, csv, time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import models, transforms
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix, classification_report

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ml_dl_models' / 'evaluation'))
from evaluate_mix_voice import (build_cf_model, build_mix_model, build_cf_transform,
                                 build_mix_transform, build_mix_mel_tensor,
                                 compute_spectral_features, TARGET_SR,
                                 MEAN, STD, SqueezeNetLateFusion)
from evaluate_mix_voice import resolve_device as resolve_dev

GTSINGER_CURATED = Path(r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated')
CF_CKPT = Path(r'd:\-MindEcho-main\ml_dl_models\chest_falsetto\squeezenet_binary\artifacts_mel_safe_v2\best_squeezenet_fourclass.pt')

MIX_CKPTS = {
    'V1': Path(r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_latefusion_v1\best_mix_binary_latefusion.pt'),
    'V6': Path(r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_latefusion_v6_song_level\best_mix_binary_latefusion.pt'),
}

MANIFESTS = {
    'core': GTSINGER_CURATED / 'mix_binary_core' / 'test_manifest.csv',
    'english_holdout': GTSINGER_CURATED / 'mix_binary_english_singer_holdout_v1' / 'test_manifest.csv',
    'song_level': GTSINGER_CURATED / 'mix_binary_song_level_v1' / 'test_manifest.csv',
}


def load_manifest(path: Path) -> list[dict]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


@torch.no_grad()
def evaluate(mix_model, cf_model, manifest, device, mix_transform, cf_transform):
    is_latefusion = bool(getattr(mix_model, '_is_latefusion', False))
    cf_num_classes = int(getattr(cf_model, 'num_classes', 2) or 2)

    y_true_mix, y_pred_mix, mix_probs = [], [], []
    y_true_cf, y_pred_cf = [], []

    for row in manifest:
        wav_path = Path(row['wav_path'])
        if not wav_path.exists():
            continue

        # Read audio
        import soundfile as sf
        audio, sr = sf.read(str(wav_path))
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        audio = np.asarray(audio, dtype=np.float32)

        # Mix inference
        mix_tensor = build_mix_mel_tensor(audio, int(sr)).unsqueeze(0).to(device)
        mix_tensor = mix_transform(mix_tensor)
        if is_latefusion:
            spectral = compute_spectral_features(audio, int(sr))
            spectral_tensor = torch.from_numpy(spectral).unsqueeze(0).to(device)
            mix_logits = mix_model(mix_tensor, spectral_tensor)
        else:
            mix_logits = mix_model(mix_tensor)
        mix_prob = float(torch.softmax(mix_logits, dim=1)[0, 1].cpu())

        mix_true = int(float(row.get('mix', 0) or 0))
        y_true_mix.append(mix_true)
        y_pred_mix.append(1 if mix_prob > 0.5 else 0)
        mix_probs.append(mix_prob)

        # CF inference
        cf_img = transforms.Resize((224, 224))(transforms.ToPILImage()(mix_tensor[0].cpu()))
        cf_tensor = cf_transform(cf_img).unsqueeze(0).to(device)
        cf_logits = cf_model(cf_tensor)
        cf_probs = torch.softmax(cf_logits, dim=1)[0].cpu().numpy()
        if cf_num_classes >= 4:
            fal_prob = float(cf_probs[2] + cf_probs[3])
        else:
            fal_prob = float(cf_probs[1])
        y_true_cf.append(int(float(row.get('falsetto', 0) or 0)))
        y_pred_cf.append(1 if fal_prob > 0.5 else 0)

    return {
        'mix_acc': accuracy_score(y_true_mix, y_pred_mix),
        'mix_f1': f1_score(y_true_mix, y_pred_mix, pos_label=1, zero_division=0),
        'mix_precision': precision_score(y_true_mix, y_pred_mix, pos_label=1, zero_division=0),
        'mix_recall': recall_score(y_true_mix, y_pred_mix, pos_label=1, zero_division=0),
        'mix_cm': confusion_matrix(y_true_mix, y_pred_mix).tolist(),
        'mix_prob_mean_pos': float(np.mean([p for p, t in zip(mix_probs, y_true_mix) if t == 1])),
        'mix_prob_mean_neg': float(np.mean([p for p, t in zip(mix_probs, y_true_mix) if t == 0])),
        'n': len(y_true_mix),
        'n_pos': sum(y_true_mix),
        'n_neg': sum(y_true_mix) - sum(y_true_mix),  # total - pos
    }


def main():
    device = resolve_dev()
    print(f"Device: {device}")
    cf_model = build_cf_model(CF_CKPT, device)
    cf_transform = build_cf_transform()

    results = {}
    for model_name, ckpt_path in MIX_CKPTS.items():
        if not ckpt_path.exists():
            print(f"Skip {model_name}: {ckpt_path} not found")
            continue
        print(f"\n{'='*60}")
        print(f"Loading {model_name}: {ckpt_path}")
        mix_model = build_mix_model(ckpt_path, device)
        mix_transform = build_mix_transform()

        model_results = {}
        for manifest_name, manifest_path in MANIFESTS.items():
            if not manifest_path.exists():
                print(f"  Skip {manifest_name}: not found")
                continue
            manifest = load_manifest(manifest_path)
            print(f"  {manifest_name}: {len(manifest)} entries...")
            t0 = time.time()
            r = evaluate(mix_model, cf_model, manifest, device, mix_transform, cf_transform)
            r['time_s'] = time.time() - t0
            model_results[manifest_name] = r
            print(f"    acc={r['mix_acc']:.4f}  mix_f1={r['mix_f1']:.4f}  "
                  f"P={r['mix_precision']:.4f}  R={r['mix_recall']:.4f}  "
                  f"prob_pos={r['mix_prob_mean_pos']:.3f}  prob_neg={r['mix_prob_mean_neg']:.3f}")

        results[model_name] = model_results

    # Comparison table
    print(f"\n{'='*80}")
    print("COMPARISON: V1 (clip-split, CN-only) vs V6 (song-split, CN+EN)")
    print(f"{'='*80}")
    for manifest_name in MANIFESTS:
        if manifest_name not in next(iter(results.values())):
            continue
        print(f"\n--- {manifest_name} ---")
        print(f"{'Metric':<20} {'V1':<12} {'V6':<12} {'Delta':<12}")
        print('-' * 56)
        v1 = results.get('V1', {}).get(manifest_name, {})
        v6 = results.get('V6', {}).get(manifest_name, {})
        if not v1 or not v6:
            continue
        for metric in ['mix_acc', 'mix_f1', 'mix_precision', 'mix_recall']:
            v1v = v1.get(metric, 0)
            v6v = v6.get(metric, 0)
            delta = v6v - v1v
            sign = '+' if delta > 0 else ''
            print(f"{metric:<20} {v1v:<12.4f} {v6v:<12.4f} {sign}{delta:<11.4f}")

    # Save
    out = {}
    for model_name, model_results in results.items():
        out[model_name] = {k: {kk: vv for kk, vv in v.items() if kk != 'mix_cm'} for k, v in model_results.items()}
    print(f"\n\nFull results:\n{json.dumps(out, indent=2, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
