import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build a stratified English runtime replay batch from offline errors and summarize runtime outcomes by song/group/role.'
    )
    parser.add_argument('--manifest', required=True, help='Full source manifest CSV used to recover complete rows by item_name.')
    parser.add_argument('--error-csv', required=True, help='Offline false-negative or false-positive CSV exported by analyze_english_mix_errors.py.')
    parser.add_argument('--artifact', required=True, help='Artifact directory or checkpoint to replay through the frozen runtime.')
    parser.add_argument('--output-prefix', required=True, help='Output prefix for the selected manifest, diagnosis JSON, and cluster summary JSON.')
    parser.add_argument('--mode', choices=('fn', 'fp'), required=True, help='Whether the error CSV contains false negatives or false positives.')
    parser.add_argument('--target-count', type=int, default=48, help='Target item count for the stratified replay batch.')
    parser.add_argument('--max-per-song', type=int, default=2, help='Maximum selected rows per song.')
    parser.add_argument('--bucket-field', default='', help='Primary stratification bucket. Defaults to group_name for fn and binary_role for fp.')
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
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            key_name = str(key)
            if key_name not in seen:
                seen.add(key_name)
                fieldnames.append(key_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_float(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except Exception:
        return 0.0


def resolve_checkpoint(path_text: str) -> Path:
    raw_path = Path(str(path_text or '').strip())
    if not raw_path.exists():
        raise FileNotFoundError(f'artifact path not found: {raw_path}')
    if raw_path.is_dir():
        checkpoint_path = raw_path / 'best_mix_binary_squeezenet.pt'
        if not checkpoint_path.exists():
            raise FileNotFoundError(f'checkpoint not found in artifact directory: {checkpoint_path}')
        return checkpoint_path.resolve()
    return raw_path.resolve()


def sort_error_rows(rows: Iterable[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    row_list = [dict(row) for row in rows]
    if mode == 'fn':
        row_list.sort(
            key=lambda row: (
                -as_float(row, 'mix_prob'),
                as_float(row, 'threshold_gap'),
                str(row.get('song_name', '') or ''),
                str(row.get('item_name', '') or ''),
            )
        )
        return row_list
    row_list.sort(
        key=lambda row: (
            -as_float(row, 'mix_prob'),
            -as_float(row, 'fp_margin'),
            str(row.get('song_name', '') or ''),
            str(row.get('item_name', '') or ''),
        )
    )
    return row_list


def select_stratified_rows(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    bucket_field: str,
    target_count: int,
    max_per_song: int,
) -> list[dict[str, Any]]:
    if target_count <= 0:
        raise ValueError('target_count must be positive')
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sort_error_rows(rows, mode):
        bucket_key = str(row.get(bucket_field, '') or '') or 'unknown'
        buckets[bucket_key].append(dict(row))

    bucket_names = sorted(buckets.keys(), key=lambda key: (len(buckets[key]), key))
    bucket_indices: dict[str, int] = {key: 0 for key in bucket_names}
    song_counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    seen_items: set[str] = set()

    while len(selected) < target_count:
        made_progress = False
        for bucket_name in bucket_names:
            bucket_rows = buckets[bucket_name]
            next_index = int(bucket_indices[bucket_name])
            while next_index < len(bucket_rows):
                candidate = dict(bucket_rows[next_index])
                next_index += 1
                item_name = str(candidate.get('item_name', '') or '')
                song_name = str(candidate.get('song_name', '') or '')
                if not item_name or item_name in seen_items:
                    continue
                if song_counts[song_name] >= max_per_song:
                    continue
                candidate['selection_bucket_field'] = bucket_field
                candidate['selection_bucket_value'] = bucket_name
                selected.append(candidate)
                seen_items.add(item_name)
                song_counts[song_name] += 1
                made_progress = True
                break
            bucket_indices[bucket_name] = next_index
            if len(selected) >= target_count:
                break
        if not made_progress:
            break
    return selected


def restore_manifest_rows(rows: list[dict[str, Any]], source_by_item_name: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    restored: list[dict[str, Any]] = []
    missing_items: list[str] = []
    for rank, row in enumerate(rows, start=1):
        item_name = str(row.get('item_name', '') or '')
        source_row = source_by_item_name.get(item_name)
        if source_row is None:
            missing_items.append(item_name)
            continue
        merged = dict(source_row)
        merged['runtime_batch_rank'] = str(rank)
        merged['runtime_batch_bucket_field'] = str(row.get('selection_bucket_field', '') or '')
        merged['runtime_batch_bucket_value'] = str(row.get('selection_bucket_value', '') or '')
        merged['runtime_batch_offline_mix_prob'] = str(row.get('mix_prob', '') or '')
        merged['runtime_batch_offline_gap'] = str(row.get('threshold_gap', row.get('fp_margin', '')) or '')
        restored.append(merged)
    return restored, missing_items


def run_diagnose(manifest_path: Path, item_names: list[str], artifact_path: Path, output_path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(DIAGNOSE_SCRIPT),
        '--manifest',
        str(manifest_path),
        '--artifact',
        str(artifact_path),
        '--output',
        str(output_path),
    ]
    for item_name in item_names:
        command.extend(['--item-name', item_name])
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f'diagnose runtime batch failed: exit={completed.returncode}')
    return json.loads(output_path.read_text(encoding='utf-8'))


def success_outcomes(mode: str) -> set[str]:
    if mode == 'fn':
        return {'hit'}
    return {'clean', 'no_mix'}


def summarize_samples(samples: list[dict[str, Any]], *, mode: str, field: str) -> list[dict[str, Any]]:
    success_values = success_outcomes(mode)
    buckets: dict[str, dict[str, Any]] = {}
    for sample in samples:
        bucket_key = str(sample.get(field, '') or '') or 'unknown'
        bucket = buckets.setdefault(
            bucket_key,
            {
                field: bucket_key,
                'sample_count': 0,
                'success_count': 0,
                'song_names': set(),
                'outcome_counts': Counter(),
                'failure_blockers': Counter(),
            },
        )
        outcome = str(sample.get('outcome', '') or '')
        bucket['sample_count'] += 1
        bucket['song_names'].add(str(sample.get('song_name', '') or ''))
        bucket['outcome_counts'].update([outcome])
        if outcome in success_values:
            bucket['success_count'] += 1
        else:
            diagnosis = dict(sample.get('voice_rule_diagnosis', {}) or {})
            bucket['failure_blockers'].update(list(diagnosis.get('blockers', []) or []))

    summary_rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        sample_count = int(bucket['sample_count'])
        success_count = int(bucket['success_count'])
        summary_rows.append(
            {
                field: bucket[field],
                'sample_count': sample_count,
                'success_count': success_count,
                'success_rate': round(float(success_count) / float(sample_count), 6) if sample_count else 0.0,
                'song_count': len(bucket['song_names']),
                'outcome_counts': dict(bucket['outcome_counts']),
                'top_failure_blockers': bucket['failure_blockers'].most_common(6),
            }
        )
    summary_rows.sort(
        key=lambda row: (
            -int(row['success_count']),
            -float(row['success_rate']),
            -int(row['sample_count']),
            str(row.get(field, '') or ''),
        )
    )
    return summary_rows


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    error_csv_path = Path(args.error_csv).resolve()
    artifact_path = resolve_checkpoint(args.artifact)
    output_prefix = Path(args.output_prefix).resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    if not manifest_path.exists():
        raise FileNotFoundError(f'manifest not found: {manifest_path}')
    if not error_csv_path.exists():
        raise FileNotFoundError(f'error CSV not found: {error_csv_path}')
    if not DIAGNOSE_SCRIPT.exists():
        raise FileNotFoundError(f'diagnose script not found: {DIAGNOSE_SCRIPT}')

    bucket_field = str(args.bucket_field or '').strip() or ('group_name' if args.mode == 'fn' else 'binary_role')
    source_rows = load_rows(manifest_path)
    source_by_item_name = {str(row.get('item_name', '') or ''): dict(row) for row in source_rows}
    error_rows = load_rows(error_csv_path)

    selected_error_rows = select_stratified_rows(
        error_rows,
        mode=str(args.mode),
        bucket_field=bucket_field,
        target_count=int(args.target_count),
        max_per_song=int(args.max_per_song),
    )
    selected_manifest_rows, missing_items = restore_manifest_rows(selected_error_rows, source_by_item_name)
    if not selected_manifest_rows:
        raise ValueError('No runtime batch rows were selected. Relax the filters or verify the inputs.')

    selected_manifest_path = output_prefix.with_name(output_prefix.name + '_selected_manifest.csv')
    selected_preview_path = output_prefix.with_name(output_prefix.name + '_selected_preview.csv')
    diagnosis_path = output_prefix.with_suffix('.json')
    summary_path = output_prefix.with_name(output_prefix.name + '_summary.json')

    write_rows(selected_manifest_path, selected_manifest_rows)
    write_rows(selected_preview_path, selected_error_rows)

    diagnosis_payload = run_diagnose(
        selected_manifest_path,
        [str(row.get('item_name', '') or '') for row in selected_manifest_rows],
        artifact_path,
        diagnosis_path,
    )

    artifacts = list(diagnosis_payload.get('artifacts', []) or [])
    if len(artifacts) != 1:
        raise RuntimeError(f'Expected exactly one artifact in diagnosis output, got {len(artifacts)}')
    samples = list(artifacts[0].get('samples', []) or [])

    success_values = success_outcomes(str(args.mode))
    overall_outcomes = Counter(str(sample.get('outcome', '') or '') for sample in samples)
    success_count = sum(1 for sample in samples if str(sample.get('outcome', '') or '') in success_values)
    summary = {
        'manifest': str(manifest_path),
        'error_csv': str(error_csv_path),
        'artifact': str(artifact_path),
        'mode': str(args.mode),
        'bucket_field': bucket_field,
        'requested_target_count': int(args.target_count),
        'selected_count': len(selected_manifest_rows),
        'missing_manifest_items': missing_items,
        'overall': {
            'sample_count': len(samples),
            'success_count': success_count,
            'success_rate': round(float(success_count) / float(len(samples)), 6) if samples else 0.0,
            'outcome_counts': dict(overall_outcomes),
            'song_count': len({str(sample.get('song_name', '') or '') for sample in samples}),
            'group_count': len({str(sample.get('group_name', '') or '') for sample in samples}),
            'role_count': len({str(sample.get('binary_role', '') or '') for sample in samples}),
        },
        'by_song': summarize_samples(samples, mode=str(args.mode), field='song_name'),
        'by_group': summarize_samples(samples, mode=str(args.mode), field='group_name'),
        'by_role': summarize_samples(samples, mode=str(args.mode), field='binary_role'),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({'selected_count': len(selected_manifest_rows), 'overall': summary['overall']}, ensure_ascii=False))
    print(f'selected_manifest={selected_manifest_path}')
    print(f'selected_preview={selected_preview_path}')
    print(f'diagnosis_json={diagnosis_path}')
    print(f'summary_json={summary_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())