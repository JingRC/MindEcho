"""Generate female-weighted training manifest for gender-aware fine-tuning.

Female mix samples get 2.5x loss weight, female control-group non-mix get 1.3x.
This addresses the gender acoustic generalization gap (female mix 3.7x harder
to detect than male mix).

Usage:
    python prepare_female_weighted_manifest.py
    # Then run:
    python train_mix_binary_squeezenet_latefusion.py \
        --init-checkpoint <V6_CKPT> \
        --train-manifest <output_train_manifest> \
        --validation-manifest <same as before> \
        --test-manifest <same as before> \
        --output-dir <new_artifacts_dir> \
        --freeze-backbone --head-epochs 0 --finetune-epochs 8
"""
import csv
from pathlib import Path

PROJECT = Path(r'd:\-MindEcho-main')
CURATED = PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated'

# Input manifests (V6 training data)
INPUT_MANIFESTS = {
    'train': CURATED / 'mix_binary_core' / 'train_manifest.csv',
    'validation': CURATED / 'mix_binary_core' / 'validation_manifest.csv',
    'test': CURATED / 'mix_binary_core' / 'test_manifest.csv',
}

# Output directory
OUTPUT_DIR = CURATED / 'mix_binary_core_female_weighted'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FEMALE_KEYWORDS = ['Alto', 'Soprano', 'Mezzo']
FEMALE_MIX_WEIGHT = 2.5
FEMALE_CONTROL_NEGATIVE_WEIGHT = 1.3


def is_female(singer: str) -> bool:
    return any(kw in str(singer) for kw in FEMALE_KEYWORDS)


def compute_weight(row, is_female_singer: bool) -> float:
    """Compute loss_weight_multiplier for a training row."""
    if not is_female_singer:
        return 1.0
    label = int(float(row.get('mix', 0) or 0))
    group = str(row.get('group_name', '') or '')
    if label == 1:
        return FEMALE_MIX_WEIGHT
    if group == 'Control_Group':
        return FEMALE_CONTROL_NEGATIVE_WEIGHT
    return 1.0


def main():
    for split, path in INPUT_MANIFESTS.items():
        if not path.exists():
            print(f"  SKIP {split}: {path} not found")
            continue

        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))

        fieldnames = list(rows[0].keys())
        if 'loss_weight_multiplier' not in fieldnames:
            fieldnames.append('loss_weight_multiplier')

        female_count = 0
        mix_female_count = 0
        for row in rows:
            singer = str(row.get('singer', '') or '')
            if not singer:
                # Fallback: parse from item_name
                parts = str(row.get('item_name', '') or '').split('#')
                singer = parts[1] if len(parts) > 1 else ''
            female = is_female(singer)
            if female:
                female_count += 1
                if int(float(row.get('mix', 0) or 0)) == 1:
                    mix_female_count += 1
            weight = compute_weight(row, female)
            row['loss_weight_multiplier'] = str(weight)

        out_path = OUTPUT_DIR / f'{split}_manifest.csv'
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        weight_dist = {}
        for row in rows:
            w = row['loss_weight_multiplier']
            weight_dist[w] = weight_dist.get(w, 0) + 1

        print(f"[{split}] {len(rows)} rows → {out_path}")
        print(f"  Female rows: {female_count} (mix={mix_female_count})")
        print(f"  Weight distribution: {weight_dist}")

    print(f"\nDone. Manifests written to {OUTPUT_DIR}")
    print(f"\nTo train:")
    print(f"  python train_mix_binary_squeezenet_latefusion.py \\")
    print(f"    --init-checkpoint <V6_CKPT> \\")
    print(f"    --train-manifest {OUTPUT_DIR / 'train_manifest.csv'} \\")
    print(f"    --validation-manifest {OUTPUT_DIR / 'validation_manifest.csv'} \\")
    print(f"    --test-manifest {OUTPUT_DIR / 'test_manifest.csv'} \\")
    print(f"    --output-dir <NEW_ARTIFACTS_DIR> \\")
    print(f"    --freeze-backbone --head-epochs 0 --finetune-epochs 8")


if __name__ == '__main__':
    main()
