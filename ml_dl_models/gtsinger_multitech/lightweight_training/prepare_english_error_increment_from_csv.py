import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_POSITIVE_SINGERS = ('EN-Alto-2',)
DEFAULT_NEGATIVE_SINGERS = ('EN-Tenor-1',)
DEFAULT_NEGATIVE_ROLES = ('control_negative', 'falsetto_group')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build an exploratory English training increment from exported false-positive and false-negative CSVs.')
    parser.add_argument(
        '--source-manifest',
        default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\english_mix_binary_eval\full_manifest.csv',
        help='Source full English manifest used to recover complete rows by item_name.',
    )
    parser.add_argument(
        '--false-negative-csv',
        default=r'd:\-MindEcho-main\_tmp_english_mix_error_analysis_false_negatives.csv',
        help='False negative CSV exported by analyze_english_mix_errors.py.',
    )
    parser.add_argument(
        '--false-positive-csv',
        default=r'd:\-MindEcho-main\_tmp_english_mix_error_analysis_false_positives.csv',
        help='False positive CSV exported by analyze_english_mix_errors.py.',
    )
    parser.add_argument('--output-dir', required=True, help='Output directory for the exploratory increment manifest and summaries.')
    parser.add_argument('--positive-singer', action='append', dest='positive_singers', default=[])
    parser.add_argument('--negative-singer', action='append', dest='negative_singers', default=[])
    parser.add_argument('--negative-role', action='append', dest='negative_roles', default=[])
    parser.add_argument('--positive-keep-count', type=int, default=96)
    parser.add_argument('--negative-keep-count', type=int, default=96)
    parser.add_argument('--max-per-song', type=int, default=4)
    parser.add_argument('--max-per-singer-song', type=int, default=4)
    parser.add_argument('--min-fn-threshold-gap', type=float, default=0.10)
    parser.add_argument('--min-fp-margin', type=float, default=0.10)
    return parser.parse_args()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in dict(row or {}).items():
        clean_key = str(key or '').lstrip('\ufeff').strip().strip('"').strip()
        normalized[clean_key] = value
    return normalized


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return [normalize_row(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
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


def as_float(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except Exception:
        return 0.0


def select_diverse_rows(
    rows: Iterable[dict[str, Any]],
    keep_count: int,
    *,
    max_per_song: int,
    max_per_singer_song: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    song_counts: Counter[str] = Counter()
    singer_song_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        song_name = str(row.get('song_name', '') or '')
        singer = str(row.get('singer', '') or '')
        singer_song_key = (singer, song_name)
        if song_counts[song_name] >= max_per_song:
            continue
        if singer_song_counts[singer_song_key] >= max_per_singer_song:
            continue
        selected.append(dict(row))
        song_counts[song_name] += 1
        singer_song_counts[singer_song_key] += 1
        if len(selected) >= keep_count:
            break
    return selected


def attach_selection_metadata(rows: list[dict[str, Any]], *, selection_role: str, reference_field: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item['increment_selection_role'] = selection_role
        item['increment_rank'] = str(index)
        item['increment_pool_size'] = str(total)
        item['increment_reference_field'] = reference_field
        item['increment_reference_value'] = str(row.get(reference_field, ''))
        enriched.append(item)
    return enriched


def summarize_rows(rows: list[dict[str, Any]], *, score_field: str) -> dict[str, Any]:
    values = [as_float(row, score_field) for row in rows]
    return {
        'items': len(rows),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
        'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
        score_field + '_min': round(min(values), 6) if values else 0.0,
        score_field + '_mean': round(sum(values) / len(values), 6) if values else 0.0,
        score_field + '_max': round(max(values), 6) if values else 0.0,
    }


def restore_manifest_rows(rows: list[dict[str, Any]], source_by_item_name: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    restored: list[dict[str, Any]] = []
    missing_items: list[str] = []
    seen_item_names: set[str] = set()
    for row in rows:
        item_name = str(row.get('item_name', '') or '')
        if not item_name or item_name in seen_item_names:
            continue
        source_row = source_by_item_name.get(item_name)
        if source_row is None:
            missing_items.append(item_name)
            continue
        merged = dict(source_row)
        for key, value in row.items():
            merged[str(key)] = value
        restored.append(merged)
        seen_item_names.add(item_name)
    return restored, missing_items


def main() -> int:
    args = parse_args()
    source_manifest = Path(args.source_manifest).resolve()
    false_negative_csv = Path(args.false_negative_csv).resolve()
    false_positive_csv = Path(args.false_positive_csv).resolve()
    output_dir = Path(args.output_dir).resolve()
    for path in (source_manifest, false_negative_csv, false_positive_csv):
        if not path.exists():
            raise FileNotFoundError(f'input not found: {path}')

    positive_singers = tuple(args.positive_singers or list(DEFAULT_POSITIVE_SINGERS))
    negative_singers = tuple(args.negative_singers or list(DEFAULT_NEGATIVE_SINGERS))
    negative_roles = tuple(args.negative_roles or list(DEFAULT_NEGATIVE_ROLES))

    source_rows = load_rows(source_manifest)
    source_by_item_name = {str(row.get('item_name', '') or ''): dict(row) for row in source_rows}

    false_negative_rows = load_rows(false_negative_csv)
    false_positive_rows = load_rows(false_positive_csv)

    positive_pool = [
        dict(row)
        for row in false_negative_rows
        if str(row.get('singer', '') or '') in set(positive_singers)
        and str(row.get('binary_role', '') or '') == 'positive_mix'
        and as_float(row, 'threshold_gap') >= float(args.min_fn_threshold_gap)
    ]
    negative_pool = [
        dict(row)
        for row in false_positive_rows
        if str(row.get('singer', '') or '') in set(negative_singers)
        and str(row.get('binary_role', '') or '') in set(negative_roles)
        and as_float(row, 'fp_margin') >= float(args.min_fp_margin)
    ]

    positive_pool.sort(
        key=lambda row: (
            as_float(row, 'mix_prob'),
            -as_float(row, 'threshold_gap'),
            str(row.get('song_name', '') or ''),
            str(row.get('item_name', '') or ''),
        )
    )
    negative_pool.sort(
        key=lambda row: (
            -as_float(row, 'mix_prob'),
            -as_float(row, 'fp_margin'),
            str(row.get('song_name', '') or ''),
            str(row.get('item_name', '') or ''),
        )
    )

    selected_positive_errors = attach_selection_metadata(
        select_diverse_rows(
            positive_pool,
            int(args.positive_keep_count),
            max_per_song=int(args.max_per_song),
            max_per_singer_song=int(args.max_per_singer_song),
        ),
        selection_role='hard_positive',
        reference_field='mix_prob',
    )
    selected_negative_errors = attach_selection_metadata(
        select_diverse_rows(
            negative_pool,
            int(args.negative_keep_count),
            max_per_song=int(args.max_per_song),
            max_per_singer_song=int(args.max_per_singer_song),
        ),
        selection_role='hard_negative',
        reference_field='mix_prob',
    )

    selected_positive_rows, missing_positive_items = restore_manifest_rows(selected_positive_errors, source_by_item_name)
    selected_negative_rows, missing_negative_items = restore_manifest_rows(selected_negative_errors, source_by_item_name)
    increment_rows = selected_positive_rows + selected_negative_rows

    if not increment_rows:
        raise ValueError('No increment rows were selected. Relax the filters or verify the input CSVs.')

    output_dir.mkdir(parents=True, exist_ok=True)
    increment_manifest = output_dir / 'training_increment_manifest.csv'
    summary_path = output_dir / 'plan_summary.json'
    hard_positive_preview = output_dir / 'hard_positive_preview.csv'
    hard_negative_preview = output_dir / 'hard_negative_preview.csv'

    write_rows(increment_manifest, increment_rows)
    write_rows(hard_positive_preview, selected_positive_rows)
    write_rows(hard_negative_preview, selected_negative_rows)

    summary = {
        'plan_name': 'english_error_increment_exploratory_v1',
        'source_manifest': str(source_manifest),
        'false_negative_csv': str(false_negative_csv),
        'false_positive_csv': str(false_positive_csv),
        'output_dir': str(output_dir),
        'focus_config': {
            'positive_singers': list(positive_singers),
            'negative_singers': list(negative_singers),
            'negative_roles': list(negative_roles),
            'positive_keep_count': int(args.positive_keep_count),
            'negative_keep_count': int(args.negative_keep_count),
            'max_per_song': int(args.max_per_song),
            'max_per_singer_song': int(args.max_per_singer_song),
            'min_fn_threshold_gap': float(args.min_fn_threshold_gap),
            'min_fp_margin': float(args.min_fp_margin),
        },
        'rationale': [
            'This increment is exploratory and intentionally targets the dominant English error clusters surfaced by the full-manifest analysis.',
            'EN-Alto-2 false negatives are used as hard positives so the next trainadapt pass explicitly sees the over-conservative miss regime.',
            'EN-Tenor-1 control and falsetto false positives are used as hard negatives so the next trainadapt pass explicitly suppresses the permissive leakage regime.',
            'If these singers are also part of a held-out protocol, using this increment for training invalidates that held-out claim for those same singers.',
        ],
        'counts': {
            'source_rows': len(source_rows),
            'positive_pool_rows': len(positive_pool),
            'negative_pool_rows': len(negative_pool),
            'selected_positive_rows': len(selected_positive_rows),
            'selected_negative_rows': len(selected_negative_rows),
            'increment_rows': len(increment_rows),
            'missing_positive_item_names': len(missing_positive_items),
            'missing_negative_item_names': len(missing_negative_items),
        },
        'missing_item_names': {
            'positive': missing_positive_items,
            'negative': missing_negative_items,
        },
        'summaries': {
            'selected_positives': summarize_rows(selected_positive_rows, score_field='mix_prob'),
            'selected_negatives': summarize_rows(selected_negative_rows, score_field='mix_prob'),
            'increment_rows': {
                'items': len(increment_rows),
                'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in increment_rows)),
                'groups': dict(Counter(str(row.get('group_name', '') or '') for row in increment_rows)),
                'singers': dict(Counter(str(row.get('singer', '') or '') for row in increment_rows)),
            },
        },
        'manifests': {
            'training_increment_manifest': str(increment_manifest),
            'hard_positive_preview': str(hard_positive_preview),
            'hard_negative_preview': str(hard_negative_preview),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())