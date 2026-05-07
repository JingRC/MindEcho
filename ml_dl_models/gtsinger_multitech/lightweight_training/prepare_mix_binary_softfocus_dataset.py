import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Annotate a base mix-binary train manifest with per-row soft-focus weights instead of hard repeats.')
    parser.add_argument('--base-train-manifest', required=True, help='Base train manifest to annotate in place for soft-focus training.')
    parser.add_argument('--focus-manifest', required=True, help='Manifest of selected focus rows, typically mined in-distribution hard cases from the same train split.')
    parser.add_argument('--validation-manifest', required=True, help='Validation manifest copied unchanged into the output dataset.')
    parser.add_argument('--test-manifest', required=True, help='Test manifest copied unchanged into the output dataset.')
    parser.add_argument('--output-dir', required=True, help='Output directory containing annotated train/validation/test manifests and summary JSON.')
    parser.add_argument('--hard-positive-sample-multiplier', type=float, default=1.35)
    parser.add_argument('--hard-positive-loss-multiplier', type=float, default=1.15)
    parser.add_argument('--control-negative-sample-multiplier', type=float, default=1.35)
    parser.add_argument('--control-negative-loss-multiplier', type=float, default=1.2)
    parser.add_argument('--falsetto-negative-sample-multiplier', type=float, default=1.7)
    parser.add_argument('--falsetto-negative-loss-multiplier', type=float, default=1.35)
    parser.add_argument('--breathy-negative-sample-multiplier', type=float, default=1.15)
    parser.add_argument('--breathy-negative-loss-multiplier', type=float, default=1.1)
    parser.add_argument('--other-negative-sample-multiplier', type=float, default=1.15)
    parser.add_argument('--other-negative-loss-multiplier', type=float, default=1.1)
    parser.add_argument('--difficulty-scaling-mode', choices=['none', 'within_focus_role'], default='none')
    parser.add_argument('--difficulty-floor', type=float, default=0.35, help='Minimum relative strength when score-scaled multipliers are enabled.')
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
    sample_weight_values = [float(row.get('sample_weight_multiplier', 1.0) or 1.0) for row in rows]
    loss_weight_values = [float(row.get('loss_weight_multiplier', 1.0) or 1.0) for row in rows]
    focused_rows = [row for row in rows if float(row.get('sample_weight_multiplier', 1.0) or 1.0) != 1.0 or float(row.get('loss_weight_multiplier', 1.0) or 1.0) != 1.0]
    return {
        'items': len(rows),
        'focused_rows': len(focused_rows),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
        'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
        'focus_roles': dict(Counter(str(row.get('soft_focus_role', '') or '') for row in focused_rows)),
        'sample_weight_min': round(min(sample_weight_values), 6) if sample_weight_values else 0.0,
        'sample_weight_max': round(max(sample_weight_values), 6) if sample_weight_values else 0.0,
        'loss_weight_min': round(min(loss_weight_values), 6) if loss_weight_values else 0.0,
        'loss_weight_max': round(max(loss_weight_values), 6) if loss_weight_values else 0.0,
    }


def as_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return float(default)


def resolve_focus_weights(row: dict[str, Any], args: argparse.Namespace) -> tuple[float, float, str]:
    selection_role = str(row.get('mined_selection_role', '') or '')
    binary_role = str(row.get('binary_role', '') or '')
    if selection_role == 'hard_positive' or binary_role == 'positive_mix':
        return float(args.hard_positive_sample_multiplier), float(args.hard_positive_loss_multiplier), 'hard_positive'
    if binary_role == 'control_negative':
        return float(args.control_negative_sample_multiplier), float(args.control_negative_loss_multiplier), 'control_negative'
    if binary_role == 'falsetto_group':
        return float(args.falsetto_negative_sample_multiplier), float(args.falsetto_negative_loss_multiplier), 'falsetto_negative'
    if binary_role == 'breathy_group':
        return float(args.breathy_negative_sample_multiplier), float(args.breathy_negative_loss_multiplier), 'breathy_negative'
    return float(args.other_negative_sample_multiplier), float(args.other_negative_loss_multiplier), 'other_negative'


def build_focus_score_stats(focus_rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, dict[str, float]]:
    if str(args.difficulty_scaling_mode or 'none') == 'none':
        return {}
    values_by_role: dict[str, list[float]] = {}
    for row in focus_rows:
        _, _, focus_role = resolve_focus_weights(row, args)
        values_by_role.setdefault(focus_role, []).append(as_float(row, 'mined_mix_prob', 0.0))
    stats: dict[str, dict[str, float]] = {}
    for focus_role, values in values_by_role.items():
        if not values:
            continue
        stats[focus_role] = {
            'min': float(min(values)),
            'max': float(max(values)),
        }
    return stats


def scale_multiplier(base_multiplier: float, *, focus_role: str, focus_row: dict[str, Any], score_stats: dict[str, dict[str, float]], args: argparse.Namespace) -> float:
    if str(args.difficulty_scaling_mode or 'none') == 'none':
        return float(base_multiplier)
    if base_multiplier <= 1.0:
        return float(base_multiplier)
    stats = score_stats.get(focus_role)
    if not stats:
        return float(base_multiplier)
    score_value = as_float(focus_row, 'mined_mix_prob', 0.0)
    score_min = float(stats.get('min', score_value))
    score_max = float(stats.get('max', score_value))
    if score_max <= score_min + 1e-12:
        difficulty_ratio = 1.0
    else:
        normalized = (score_value - score_min) / max(1e-12, score_max - score_min)
        if focus_role == 'hard_positive':
            normalized = 1.0 - normalized
        difficulty_ratio = max(0.0, min(1.0, normalized))
    floor = max(0.0, min(1.0, float(args.difficulty_floor)))
    scaled_ratio = floor + (1.0 - floor) * difficulty_ratio
    return 1.0 + (float(base_multiplier) - 1.0) * scaled_ratio


def main() -> int:
    args = parse_args()
    base_train_manifest = Path(args.base_train_manifest).resolve()
    focus_manifest = Path(args.focus_manifest).resolve()
    validation_manifest = Path(args.validation_manifest).resolve()
    test_manifest = Path(args.test_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    for path in (base_train_manifest, focus_manifest, validation_manifest, test_manifest):
        if not path.exists():
            raise FileNotFoundError(f'manifest not found: {path}')

    base_rows = load_manifest(base_train_manifest)
    focus_rows = load_manifest(focus_manifest)
    focus_score_stats = build_focus_score_stats(focus_rows, args)
    focus_by_item_name: dict[str, dict[str, Any]] = {}
    for row in focus_rows:
        item_name = str(row.get('item_name', '') or '').strip()
        if item_name:
            focus_by_item_name[item_name] = dict(row)

    annotated_train_rows: list[dict[str, Any]] = []
    focused_item_count = 0
    for row in base_rows:
        item = dict(row)
        item['sample_weight_multiplier'] = '1.0'
        item['loss_weight_multiplier'] = '1.0'
        item['soft_focus_role'] = ''
        item['soft_focus_selected'] = '0'
        item['soft_focus_source'] = ''
        item_name = str(item.get('item_name', '') or '').strip()
        focus_row = focus_by_item_name.get(item_name)
        if focus_row is not None:
            sample_multiplier, loss_multiplier, focus_role = resolve_focus_weights(focus_row, args)
            sample_multiplier = scale_multiplier(sample_multiplier, focus_role=focus_role, focus_row=focus_row, score_stats=focus_score_stats, args=args)
            loss_multiplier = scale_multiplier(loss_multiplier, focus_role=focus_role, focus_row=focus_row, score_stats=focus_score_stats, args=args)
            item['sample_weight_multiplier'] = str(round(float(sample_multiplier), 6))
            item['loss_weight_multiplier'] = str(round(float(loss_multiplier), 6))
            item['soft_focus_role'] = focus_role
            item['soft_focus_selected'] = '1'
            item['soft_focus_source'] = str(focus_row.get('mined_selection_role', '') or '')
            focused_item_count += 1
        annotated_train_rows.append(item)

    validation_rows = load_manifest(validation_manifest)
    test_rows = load_manifest(test_manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    train_output = output_dir / 'train_manifest.csv'
    validation_output = output_dir / 'validation_manifest.csv'
    test_output = output_dir / 'test_manifest.csv'
    summary_output = output_dir / 'plan_summary.json'

    write_manifest(train_output, annotated_train_rows)
    write_manifest(validation_output, validation_rows)
    write_manifest(test_output, test_rows)

    missing_focus_item_names = sorted(set(focus_by_item_name.keys()) - {str(row.get('item_name', '') or '').strip() for row in base_rows})
    summary = {
        'base_train_manifest': str(base_train_manifest),
        'focus_manifest': str(focus_manifest),
        'validation_manifest': str(validation_manifest),
        'test_manifest': str(test_manifest),
        'output_dir': str(output_dir),
        'focus_weight_config': {
            'hard_positive_sample_multiplier': float(args.hard_positive_sample_multiplier),
            'hard_positive_loss_multiplier': float(args.hard_positive_loss_multiplier),
            'control_negative_sample_multiplier': float(args.control_negative_sample_multiplier),
            'control_negative_loss_multiplier': float(args.control_negative_loss_multiplier),
            'falsetto_negative_sample_multiplier': float(args.falsetto_negative_sample_multiplier),
            'falsetto_negative_loss_multiplier': float(args.falsetto_negative_loss_multiplier),
            'breathy_negative_sample_multiplier': float(args.breathy_negative_sample_multiplier),
            'breathy_negative_loss_multiplier': float(args.breathy_negative_loss_multiplier),
            'other_negative_sample_multiplier': float(args.other_negative_sample_multiplier),
            'other_negative_loss_multiplier': float(args.other_negative_loss_multiplier),
            'difficulty_scaling_mode': str(args.difficulty_scaling_mode),
            'difficulty_floor': float(args.difficulty_floor),
        },
        'rationale': [
            'Soft-focus weighting keeps every train row unique and annotates only selected in-distribution hard cases with higher sampler and loss multipliers.',
            'The focus rows must come from the same official train split, so no held-out singer samples are leaked into training.',
            'This is intentionally a softer alternative to hard repeats for exploratory trainadapt work.',
        ],
        'counts': {
            'base_train_rows': len(base_rows),
            'focus_rows': len(focus_rows),
            'focused_item_count': focused_item_count,
            'missing_focus_item_names': len(missing_focus_item_names),
            'validation_rows': len(validation_rows),
            'test_rows': len(test_rows),
        },
        'missing_focus_item_names': missing_focus_item_names,
        'split_summary': {
            'train': summarize_rows(annotated_train_rows),
            'validation': summarize_rows(validation_rows),
            'test': summarize_rows(test_rows),
        },
        'manifests': {
            'train_manifest': str(train_output),
            'validation_manifest': str(validation_output),
            'test_manifest': str(test_output),
        },
    }
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())