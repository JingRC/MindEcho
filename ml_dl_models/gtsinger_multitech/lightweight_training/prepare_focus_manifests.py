import argparse
import csv
import random
from collections import Counter
from pathlib import Path


TARGET_LABELS = ('mix', 'falsetto', 'breathy')


def read_manifest(path: Path) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'No rows to write for {path}')
    fieldnames = list(rows[0].keys())
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def is_target_positive(row: dict) -> bool:
    return any(int(float(row[name])) for name in TARGET_LABELS)


def row_priority(row: dict) -> tuple[int, int, str, str]:
    label_hits = sum(int(float(row[name])) for name in TARGET_LABELS)
    non_target_hits = sum(int(float(row[name])) for name in ('vibrato', 'glissando', 'pharyngeal'))
    return (
        -label_hits,
        non_target_hits,
        row['group_name'],
        row['item_name'],
    )


def sample_negatives(rows: list[dict], keep_count: int, seed: int) -> list[dict]:
    if keep_count <= 0:
        return []
    if len(rows) <= keep_count:
        return sorted(rows, key=row_priority)
    rnd = random.Random(seed)
    rows = list(rows)
    rnd.shuffle(rows)
    rows.sort(key=row_priority)
    return rows[:keep_count]


def build_focus_split(rows: list[dict], *, keep_control_ratio: float, keep_other_negative_ratio: float, seed: int) -> list[dict]:
    positives = [row for row in rows if is_target_positive(row)]
    control_negatives = [row for row in rows if (not is_target_positive(row)) and row['group_name'] == 'Control_Group']
    other_negatives = [row for row in rows if (not is_target_positive(row)) and row['group_name'] != 'Control_Group']

    keep_control_count = int(round(len(positives) * keep_control_ratio))
    keep_other_negative_count = int(round(len(positives) * keep_other_negative_ratio))

    selected = []
    selected.extend(sorted(positives, key=row_priority))
    selected.extend(sample_negatives(control_negatives, keep_control_count, seed=seed))
    selected.extend(sample_negatives(other_negatives, keep_other_negative_count, seed=seed + 1))
    selected.sort(key=lambda row: (row['group_name'], row['singer'], row['song_name'], row['item_name']))
    return selected


def summarize(rows: list[dict]) -> dict:
    return {
        'items': len(rows),
        'mix': sum(int(float(row['mix'])) for row in rows),
        'falsetto': sum(int(float(row['falsetto'])) for row in rows),
        'breathy': sum(int(float(row['breathy'])) for row in rows),
        'positives_any': sum(1 for row in rows if is_target_positive(row)),
        'groups': Counter(row['group_name'] for row in rows),
    }


def write_summary(path: Path, splits: dict[str, list[dict]], keep_control_ratio: float, keep_other_negative_ratio: float) -> None:
    lines = [
        '# Focused Three-Label Manifest Summary',
        '',
        f'- target_labels: {", ".join(TARGET_LABELS)}',
        f'- keep_control_ratio: {keep_control_ratio}',
        f'- keep_other_negative_ratio: {keep_other_negative_ratio}',
        '',
    ]
    for split_name, rows in splits.items():
        stats = summarize(rows)
        lines.append(f'## {split_name.title()}')
        lines.append('')
        lines.append(f'- items: {stats["items"]}')
        lines.append(f'- positives_any: {stats["positives_any"]}')
        lines.append(f'- mix: {stats["mix"]}')
        lines.append(f'- falsetto: {stats["falsetto"]}')
        lines.append(f'- breathy: {stats["breathy"]}')
        for group_name, count in stats['groups'].most_common():
            lines.append(f'- group_{group_name}: {count}')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare focused manifests for mix/falsetto/breathy training.')
    parser.add_argument('--input-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_core')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_focus_core')
    parser.add_argument('--keep-control-ratio', type=float, default=0.6)
    parser.add_argument('--keep-other-negative-ratio', type=float, default=0.25)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    split_names = ('train', 'validation', 'test')
    split_rows: dict[str, list[dict]] = {}
    for index, split_name in enumerate(split_names):
        rows = read_manifest(input_dir / f'{split_name}_manifest.csv')
        split_rows[split_name] = build_focus_split(
            rows,
            keep_control_ratio=args.keep_control_ratio,
            keep_other_negative_ratio=args.keep_other_negative_ratio,
            seed=args.seed + index * 13,
        )
        write_manifest(output_dir / f'{split_name}_manifest.csv', split_rows[split_name])

    write_summary(
        output_dir / 'manifest_summary.md',
        split_rows,
        keep_control_ratio=args.keep_control_ratio,
        keep_other_negative_ratio=args.keep_other_negative_ratio,
    )
    for split_name in split_names:
        print(split_name, len(split_rows[split_name]))
    print(f'wrote {output_dir}')


if __name__ == '__main__':
    main()