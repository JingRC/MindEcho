import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a mix-binary augmented dataset by appending an increment train manifest onto a base train manifest.')
    parser.add_argument('--base-train-manifest', required=True, help='Base train manifest, usually the stable core train split.')
    parser.add_argument('--increment-train-manifest', required=True, help='Increment train manifest to append onto the base train split.')
    parser.add_argument('--validation-manifest', required=True, help='Validation manifest to copy unchanged into the output dataset.')
    parser.add_argument('--test-manifest', required=True, help='Test manifest to copy or filter into the output dataset.')
    parser.add_argument('--positive-repeat', type=int, default=1, help='Repeat count for increment rows with binary_role=positive_mix.')
    parser.add_argument('--control-negative-repeat', type=int, default=1, help='Repeat count for increment rows with binary_role=control_negative.')
    parser.add_argument('--other-role-repeat', type=int, default=1, help='Repeat count for increment rows with any other or missing binary_role.')
    parser.add_argument('--exclude-increment-items-from-test', action='store_true', help='Remove increment item_name rows from the copied test split to avoid train-test leakage in trainadapt experiments.')
    parser.add_argument('--output-dir', required=True, help='Output dataset directory containing train/validation/test manifests and summary JSON.')
    return parser.parse_args()


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in dict(row or {}).items():
        clean_key = str(key or '').lstrip('\ufeff').strip().strip('"').strip()
        normalized[clean_key] = value
    return normalized


def load_manifest(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return [normalize_row(row) for row in csv.DictReader(handle)]


def write_manifest(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            name = str(key)
            if name not in seen:
                seen.add(name)
                fieldnames.append(name)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def copy_manifest(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def repeat_count_for_row(row: Dict[str, Any], args: argparse.Namespace) -> int:
    role = str(row.get('binary_role', '') or '').strip()
    if role == 'positive_mix':
        return max(0, int(args.positive_repeat))
    if role == 'control_negative':
        return max(0, int(args.control_negative_repeat))
    return max(0, int(args.other_role_repeat))


def expand_increment_rows(rows: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    expanded: List[Dict[str, Any]] = []
    for row in rows:
        repeat_count = repeat_count_for_row(row, args)
        for repeat_index in range(repeat_count):
            item = dict(row)
            item['increment_repeat_index'] = str(repeat_index + 1)
            item['increment_repeat_count'] = str(repeat_count)
            expanded.append(item)
    return expanded


def filter_test_rows(rows: List[Dict[str, Any]], excluded_item_names: set[str]) -> List[Dict[str, Any]]:
    if not excluded_item_names:
        return [dict(row) for row in rows]
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        item_name = str(row.get('item_name', '') or '')
        if item_name in excluded_item_names:
            continue
        filtered.append(dict(row))
    return filtered


def summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int] | int]:
    return {
        'items': len(rows),
        'labels': dict(Counter(str(int(float(row.get('mix', 0) or 0))) for row in rows)),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
    }


def main() -> int:
    args = parse_args()
    base_train_manifest = Path(args.base_train_manifest).resolve()
    increment_train_manifest = Path(args.increment_train_manifest).resolve()
    validation_manifest = Path(args.validation_manifest).resolve()
    test_manifest = Path(args.test_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()

    for path in (base_train_manifest, increment_train_manifest, validation_manifest, test_manifest):
        if not path.exists():
            raise FileNotFoundError(f'manifest not found: {path}')

    base_rows = load_manifest(base_train_manifest)
    increment_rows = load_manifest(increment_train_manifest)
    weighted_increment_rows = expand_increment_rows(increment_rows, args)
    train_rows = [dict(row) for row in base_rows] + [dict(row) for row in weighted_increment_rows]
    validation_rows = load_manifest(validation_manifest)
    test_rows = load_manifest(test_manifest)
    excluded_item_names = {
        str(row.get('item_name', '') or '').strip()
        for row in increment_rows
        if str(row.get('item_name', '') or '').strip()
    }
    output_test_rows = filter_test_rows(test_rows, excluded_item_names) if args.exclude_increment_items_from_test else [dict(row) for row in test_rows]

    output_dir.mkdir(parents=True, exist_ok=True)
    train_output = output_dir / 'train_manifest.csv'
    validation_output = output_dir / 'validation_manifest.csv'
    test_output = output_dir / 'test_manifest.csv'
    summary_output = output_dir / 'plan_summary.json'

    write_manifest(train_output, train_rows)
    write_manifest(validation_output, validation_rows)
    write_manifest(test_output, output_test_rows)

    summary = {
        'base_train_manifest': str(base_train_manifest),
        'increment_train_manifest': str(increment_train_manifest),
        'validation_manifest': str(validation_manifest),
        'test_manifest': str(test_manifest),
        'output_dir': str(output_dir),
        'repeat_config': {
            'positive_repeat': int(args.positive_repeat),
            'control_negative_repeat': int(args.control_negative_repeat),
            'other_role_repeat': int(args.other_role_repeat),
        },
        'test_filter': {
            'exclude_increment_items_from_test': bool(args.exclude_increment_items_from_test),
            'excluded_item_name_count': len(excluded_item_names) if args.exclude_increment_items_from_test else 0,
        },
        'rationale': [
            'Append the provided increment manifest onto the stable base core train manifest instead of training on the increment-only slice.',
            'Keep validation unchanged so global model selection remains comparable while frozen GUI runtime remains the real acceptance gate.',
            'Preserve increment row multiplicity as-is so any upstream weighting choice remains explicit in the selected increment manifest itself.',
            'When requested, filter increment item_names from the copied test split to avoid direct train-test leakage in trainadapt experiments.',
        ],
        'counts': {
            'base_train_rows': len(base_rows),
            'increment_unique_rows': len(increment_rows),
            'increment_weighted_rows': len(weighted_increment_rows),
            'augmented_train_rows': len(train_rows),
            'validation_rows': len(validation_rows),
            'base_test_rows': len(test_rows),
            'output_test_rows': len(output_test_rows),
        },
        'split_summary': {
            'base_train': summarize_rows(base_rows),
            'increment_train': summarize_rows(increment_rows),
            'weighted_increment_train': summarize_rows(weighted_increment_rows),
            'augmented_train': summarize_rows(train_rows),
            'validation': summarize_rows(validation_rows),
            'test': summarize_rows(output_test_rows),
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