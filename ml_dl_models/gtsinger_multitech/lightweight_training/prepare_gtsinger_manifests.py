import csv
import json
import random
from collections import Counter
from pathlib import Path

from sklearn.model_selection import train_test_split


LABEL_NAMES = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']


def parse_item_name(item_name: str) -> dict:
    language, singer, technique, song_name, group_name, clip_id = item_name.split('#', 5)
    return {
        'language': language,
        'singer': singer,
        'technique': technique,
        'song_name': song_name,
        'group_name': group_name,
        'clip_id': clip_id,
    }


def get_flag(meta: dict, name: str) -> int:
    return int(any(meta.get(f'{name}_tech', [])))


def build_rows(metadata: list[dict], raw_root: Path) -> list[dict]:
    rows = []
    for meta in metadata:
        wav_path = raw_root / meta['wav_fn']
        if not wav_path.exists():
            continue
        parsed = parse_item_name(meta['item_name'])
        row = {
            'item_name': meta['item_name'],
            'wav_path': str(wav_path),
            'wav_fn': meta['wav_fn'],
            'language': parsed['language'],
            'singer': parsed['singer'],
            'song_name': parsed['song_name'],
            'group_name': parsed['group_name'],
        }
        for label_name in LABEL_NAMES:
            row[label_name] = get_flag(meta, label_name)
        row['any_tech'] = int(any(row[label_name] for label_name in LABEL_NAMES))
        if row['mix'] and row['breathy']:
            row['mix_variant'] = 'breathy_mix'
        elif row['mix'] and row['falsetto']:
            row['mix_variant'] = 'head_mix'
        elif row['mix']:
            row['mix_variant'] = 'clear_mix'
        else:
            row['mix_variant'] = 'non_mix'
        signature = ''.join(str(row[label_name]) for label_name in LABEL_NAMES)
        row['label_signature'] = signature
        rows.append(row)
    return rows


def build_stratify_keys(rows: list[dict]) -> list[str]:
    counter = Counter(row['label_signature'] for row in rows)
    keys = []
    for row in rows:
        sig = row['label_signature']
        if counter[sig] >= 3:
            keys.append(sig)
        else:
            keys.append('fallback_' + row['group_name'])
    return keys


def choose_stratify_labels(rows: list[dict]) -> list[str] | None:
    keys = build_stratify_keys(rows)
    counter = Counter(keys)
    if not counter:
        return None
    if min(counter.values()) < 2:
        return None
    return keys


def split_rows(rows: list[dict], seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    stratify_keys = choose_stratify_labels(rows)
    train_rows, temp_rows = train_test_split(
        rows,
        test_size=0.2,
        random_state=seed,
        stratify=stratify_keys,
    )
    temp_keys = choose_stratify_labels(temp_rows)
    valid_rows, test_rows = train_test_split(
        temp_rows,
        test_size=0.5,
        random_state=seed,
        stratify=temp_keys,
    )
    return train_rows, valid_rows, test_rows


def write_manifest(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        'item_name',
        'wav_path',
        'wav_fn',
        'language',
        'singer',
        'song_name',
        'group_name',
        'mix',
        'falsetto',
        'breathy',
        'vibrato',
        'glissando',
        'pharyngeal',
        'any_tech',
        'mix_variant',
        'label_signature',
    ]
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, train_rows: list[dict], valid_rows: list[dict], test_rows: list[dict]) -> None:
    split_map = {
        'train': train_rows,
        'validation': valid_rows,
        'test': test_rows,
    }
    lines = [
        '# Chinese Multi-Tech Manifest Summary',
        '',
    ]
    for split_name, rows in split_map.items():
        lines.append(f'## {split_name.title()}')
        lines.append('')
        lines.append(f'- items: {len(rows)}')
        group_counter = Counter(row['group_name'] for row in rows)
        for label_name in LABEL_NAMES:
            count = sum(row[label_name] for row in rows)
            lines.append(f'- {label_name}: {count}')
        for group_name, count in group_counter.most_common():
            lines.append(f'- group_{group_name}: {count}')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    random.seed(42)
    base_dir = Path(__file__).resolve().parents[1]
    raw_root = base_dir / 'dataset' / 'raw'
    metadata_path = base_dir / 'dataset' / 'processed' / 'Chinese' / 'metadata.json'
    output_dir = base_dir / 'dataset' / 'curated' / 'multitech_core'
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    rows = build_rows(metadata, raw_root)
    train_rows, valid_rows, test_rows = split_rows(rows, seed=42)

    write_manifest(output_dir / 'train_manifest.csv', train_rows)
    write_manifest(output_dir / 'validation_manifest.csv', valid_rows)
    write_manifest(output_dir / 'test_manifest.csv', test_rows)
    write_summary(output_dir / 'manifest_summary.md', train_rows, valid_rows, test_rows)

    print(f'train={len(train_rows)} validation={len(valid_rows)} test={len(test_rows)}')
    print(f'wrote {output_dir}')


if __name__ == '__main__':
    main()