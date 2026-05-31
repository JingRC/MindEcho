"""Prepare breath binary classification manifest from mix_binary_core.

Positive: Breathy_Group samples (breathy==1 or group_name=='Breathy_Group')
Negative: Falsetto_Group + Control_Group (teach model to distinguish breath from falsetto)

Keeps the same train/val/test split as mix_binary_core.
Output: breath_binary_core/{train,validation,test}_manifest.csv
"""

import csv
from pathlib import Path

PROJECT = Path(r'd:\-MindEcho-main')
CURATED = PROJECT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated'

SOURCE_MANIFESTS = {
    'train': CURATED / 'mix_binary_core' / 'train_manifest.csv',
    'validation': CURATED / 'mix_binary_core' / 'validation_manifest.csv',
    'test': CURATED / 'mix_binary_core' / 'test_manifest.csv',
}

OUTPUT_DIR = CURATED / 'breath_binary_core'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    total_pos = 0
    total_neg = 0

    for split, path in SOURCE_MANIFESTS.items():
        if not path.exists():
            print(f"  SKIP {split}: {path} not found")
            continue

        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))

        out_rows = []
        pos_count = 0
        neg_count = 0
        skipped = 0

        for row in rows:
            group = str(row.get('group_name', '') or '')
            breathy_flag = int(float(row.get('breathy', 0) or 0))

            is_breath_positive = (breathy_flag == 1) or (group == 'Breathy_Group')
            is_falsetto = (group == 'Falsetto_Group')
            is_control = (group == 'Control_Group')

            if is_breath_positive:
                row['breath'] = '1'
                pos_count += 1
            elif is_falsetto or is_control:
                row['breath'] = '0'
                neg_count += 1
            else:
                # Skip Mixed_Voice_Group, Pharyngeal_Group, Vibrato_Group, Glissando_Group
                # These have ambiguous breath characteristics
                skipped += 1
                continue

            out_rows.append(row)

        # Write output manifest (keep all original columns + breath label)
        fieldnames = list(rows[0].keys())
        out_path = OUTPUT_DIR / f'{split}_manifest.csv'
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(out_rows)

        print(f"[{split}] {len(out_rows)} rows (pos={pos_count}, neg={neg_count}, skipped={skipped}) → {out_path}")
        total_pos += pos_count
        total_neg += neg_count

    print(f"\nTotal: {total_pos} positive (breath), {total_neg} negative (falsetto+control)")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
