import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_TRAIN_SINGERS = ('EN-Alto-1',)
DEFAULT_VALIDATION_SINGERS = ('EN-Tenor-1',)
DEFAULT_TEST_SINGERS = ('EN-Alto-2',)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Freeze a singer-held-out English mix-binary protocol from the full English manifest.')
    parser.add_argument(
        '--source-manifest',
        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\english_mix_binary_eval\full_manifest.csv',
        help='Full English evaluation manifest to split by singer.',
    )
    parser.add_argument('--output-dir', required=True, help='Output directory for the held-out protocol manifests.')
    parser.add_argument('--train-singer', action='append', dest='train_singers', default=[])
    parser.add_argument('--validation-singer', action='append', dest='validation_singers', default=[])
    parser.add_argument('--test-singer', action='append', dest='test_singers', default=[])
    return parser.parse_args()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in dict(row or {}).items():
        clean_key = str(key or '').lstrip('\ufeff').strip().strip('"').strip()
        normalized[clean_key] = value
    return normalized


def load_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return [normalize_row(row) for row in csv.DictReader(handle)]


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f'No rows to write: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            key_name = str(key)
            if key_name not in seen:
                seen.add(key_name)
                fieldnames.append(key_name)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'items': len(rows),
        'labels': dict(Counter(str(int(float(row.get('mix', 0) or 0))) for row in rows)),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
        'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
        'mix_variants': dict(Counter(str(row.get('mix_variant', '') or '') for row in rows)),
    }


def resolve_assignments(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[str], list[str], list[str], list[str], bool]:
    available_singers = sorted({str(row.get('singer', '') or '') for row in rows if str(row.get('singer', '') or '')})
    train_singers = [str(item) for item in (args.train_singers or list(DEFAULT_TRAIN_SINGERS))]
    validation_singers = [str(item) for item in (args.validation_singers or list(DEFAULT_VALIDATION_SINGERS))]
    test_singers = [str(item) for item in (args.test_singers or list(DEFAULT_TEST_SINGERS))]
    used_default_protocol = not bool(args.train_singers or args.validation_singers or args.test_singers)

    overlap = (set(train_singers) & set(validation_singers)) | (set(train_singers) & set(test_singers)) | (set(validation_singers) & set(test_singers))
    if overlap:
        raise ValueError(f'Singer assignments must be disjoint, overlap={sorted(overlap)}')

    unknown = (set(train_singers) | set(validation_singers) | set(test_singers)) - set(available_singers)
    if unknown:
        raise ValueError(f'Unknown singers in assignment: {sorted(unknown)}')

    unassigned = sorted(set(available_singers) - set(train_singers) - set(validation_singers) - set(test_singers))
    if unassigned:
        raise ValueError(f'All singers must be assigned. Unassigned singers: {unassigned}')

    return train_singers, validation_singers, test_singers, available_singers, used_default_protocol


def write_protocol_summary(path: Path, summary: dict[str, Any]) -> None:
    split_map = summary['split_summary']
    lines = [
        '# English Singer Held-Out Protocol',
        '',
        f"- protocol_name: {summary['protocol_name']}",
        f"- source_manifest: {summary['source_manifest']}",
        f"- train_singers: {', '.join(summary['split_assignment']['train'])}",
        f"- validation_singers: {', '.join(summary['split_assignment']['validation'])}",
        f"- test_singers: {', '.join(summary['split_assignment']['test'])}",
        '',
        '## Notes',
        '',
    ]
    for note in summary['rationale']:
        lines.append(f'- {note}')
    lines.extend([
        '',
        '## Split Counts',
        '',
    ])
    for split_name in ('train', 'validation', 'test'):
        split_summary = split_map[split_name]
        lines.append(f'### {split_name.title()}')
        lines.append('')
        lines.append(f"- items: {split_summary['items']}")
        for bucket_name in ('labels', 'binary_roles', 'groups', 'mix_variants', 'singers'):
            for key, value in split_summary[bucket_name].items():
                lines.append(f'- {bucket_name}_{key}: {value}')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    args = parse_args()
    source_manifest = Path(args.source_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not source_manifest.exists():
        raise FileNotFoundError(f'source manifest not found: {source_manifest}')

    rows = load_manifest(source_manifest)
    train_singers, validation_singers, test_singers, available_singers, used_default_protocol = resolve_assignments(rows, args)

    train_rows = [dict(row) for row in rows if str(row.get('singer', '') or '') in set(train_singers)]
    validation_rows = [dict(row) for row in rows if str(row.get('singer', '') or '') in set(validation_singers)]
    test_rows = [dict(row) for row in rows if str(row.get('singer', '') or '') in set(test_singers)]

    if not train_rows or not validation_rows or not test_rows:
        raise ValueError('Each split must contain at least one row.')

    output_dir.mkdir(parents=True, exist_ok=True)
    train_manifest = output_dir / 'train_manifest.csv'
    validation_manifest = output_dir / 'validation_manifest.csv'
    test_manifest = output_dir / 'test_manifest.csv'
    summary_path = output_dir / 'protocol_summary.json'
    summary_markdown = output_dir / 'protocol_summary.md'

    write_manifest(train_manifest, train_rows)
    write_manifest(validation_manifest, validation_rows)
    write_manifest(test_manifest, test_rows)

    rationale = [
        'This protocol is frozen by singer identity. Using validation or test singers in training invalidates the held-out claim.',
        'The default assignment keeps EN-Alto-1 as the adaptation singer, EN-Tenor-1 as validation, and EN-Alto-2 as the final test singer.',
        'That default maps the more permissive high-false-positive regime to validation and the more over-conservative high-false-negative regime to the final test.',
    ]
    if not used_default_protocol:
        rationale = [
            'This protocol uses a custom singer assignment supplied on the command line.',
            'Using validation or test singers in training invalidates the held-out claim.',
        ]

    summary = {
        'protocol_name': 'english_singer_holdout_v1',
        'source_manifest': str(source_manifest),
        'output_dir': str(output_dir),
        'available_singers': available_singers,
        'used_default_protocol': bool(used_default_protocol),
        'split_assignment': {
            'train': train_singers,
            'validation': validation_singers,
            'test': test_singers,
        },
        'rationale': rationale,
        'split_summary': {
            'train': summarize_rows(train_rows),
            'validation': summarize_rows(validation_rows),
            'test': summarize_rows(test_rows),
        },
        'manifests': {
            'train_manifest': str(train_manifest),
            'validation_manifest': str(validation_manifest),
            'test_manifest': str(test_manifest),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    write_protocol_summary(summary_markdown, summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())