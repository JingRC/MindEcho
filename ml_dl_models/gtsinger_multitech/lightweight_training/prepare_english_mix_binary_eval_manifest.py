import argparse
import csv
import json
from collections import Counter
from pathlib import Path


LABEL_NAMES = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build an English mix-binary evaluation manifest from processed metadata and downloaded raw wav files.')
    parser.add_argument(
        '--metadata',
        default='',
        help='Optional English metadata.json path. Defaults to dataset/processed/English/metadata.json.',
    )
    parser.add_argument(
        '--raw-root',
        default='',
        help='Optional raw root path. Defaults to dataset/raw.',
    )
    parser.add_argument(
        '--output-dir',
        default='',
        help='Optional output directory. Defaults to dataset/curated/english_mix_binary_eval.',
    )
    return parser.parse_args()


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


def infer_mix_variant(row: dict) -> str:
    if int(row['mix']) and int(row['breathy']):
        return 'breathy_mix'
    if int(row['mix']) and int(row['falsetto']):
        return 'head_mix'
    if int(row['mix']):
        return 'clear_mix'
    return 'non_mix'


def infer_binary_role(row: dict) -> str:
    if int(row['mix']) == 1:
        return 'positive_mix'
    group_name = str(row.get('group_name', '') or '')
    if group_name == 'Control_Group':
        return 'control_negative'
    if group_name == 'Breathy_Group':
        return 'breathy_group'
    if group_name == 'Falsetto_Group':
        return 'falsetto_group'
    return 'other_negative'


def build_rows(metadata: list[dict], raw_root: Path) -> list[dict]:
    rows: list[dict] = []
    for meta in metadata:
        wav_fn = str(meta.get('wav_fn', '') or '').replace('\\', '/')
        if not wav_fn.startswith('English/'):
            continue
        wav_path = raw_root / wav_fn
        if not wav_path.exists():
            continue
        parsed = parse_item_name(str(meta['item_name']))
        row = {
            'item_name': meta['item_name'],
            'wav_path': str(wav_path),
            'wav_fn': wav_fn,
            'language': parsed['language'],
            'singer': parsed['singer'],
            'song_name': parsed['song_name'],
            'group_name': parsed['group_name'],
        }
        for label_name in LABEL_NAMES:
            row[label_name] = get_flag(meta, label_name)
        row['any_tech'] = int(any(int(row[label_name]) for label_name in LABEL_NAMES))
        row['mix_variant'] = infer_mix_variant(row)
        row['label_signature'] = ''.join(str(int(row[label_name])) for label_name in LABEL_NAMES)
        row['binary_role'] = infer_binary_role(row)
        rows.append(row)
    return rows


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
        'binary_role',
    ]
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict], missing_count: int) -> None:
    role_counter = Counter(str(row.get('binary_role', '') or '') for row in rows)
    group_counter = Counter(str(row.get('group_name', '') or '') for row in rows)
    singer_counter = Counter(str(row.get('singer', '') or '') for row in rows)
    lines = [
        '# English Mix Binary Eval Manifest Summary',
        '',
        f'- rows_written: {len(rows)}',
        f'- missing_wavs_skipped: {missing_count}',
        '',
        '## Binary Roles',
        '',
    ]
    for key, value in role_counter.most_common():
        lines.append(f'- {key}: {value}')
    lines.extend([
        '',
        '## Groups',
        '',
    ])
    for key, value in group_counter.most_common():
        lines.append(f'- {key}: {value}')
    lines.extend([
        '',
        '## Singers',
        '',
    ])
    for key, value in singer_counter.most_common():
        lines.append(f'- {key}: {value}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    metadata_path = Path(args.metadata).resolve() if args.metadata else (base_dir / 'dataset' / 'processed' / 'English' / 'metadata.json')
    raw_root = Path(args.raw_root).resolve() if args.raw_root else (base_dir / 'dataset' / 'raw')
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (base_dir / 'dataset' / 'curated' / 'english_mix_binary_eval')
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    total_english = sum(1 for item in metadata if str(item.get('wav_fn', '') or '').replace('\\', '/').startswith('English/'))
    rows = build_rows(metadata, raw_root)
    missing_count = total_english - len(rows)

    manifest_path = output_dir / 'full_manifest.csv'
    summary_path = output_dir / 'manifest_summary.md'
    write_manifest(manifest_path, rows)
    write_summary(summary_path, rows, missing_count=missing_count)

    print(f'english_items={total_english}')
    print(f'rows_written={len(rows)}')
    print(f'missing_wavs_skipped={missing_count}')
    print(f'manifest={manifest_path}')
    print(f'summary={summary_path}')


if __name__ == '__main__':
    main()