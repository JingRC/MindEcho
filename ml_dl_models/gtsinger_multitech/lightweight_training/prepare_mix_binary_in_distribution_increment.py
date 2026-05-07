import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from prepare_mix_binary_manifests import negative_bucket, read_manifest, row_priority, score_rows_with_artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Mine in-distribution hard positives and hard negatives from a train manifest using an existing mix artifact.')
    parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\train_manifest.csv')
    parser.add_argument('--artifact-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--positive-keep-count', type=int, default=16)
    parser.add_argument('--negative-keep-count', type=int, default=32)
    parser.add_argument('--negative-role', action='append', dest='negative_roles', default=[])
    parser.add_argument('--max-per-singer', type=int, default=6)
    parser.add_argument('--max-per-song', type=int, default=4)
    parser.add_argument('--max-per-singer-song', type=int, default=2)
    parser.add_argument('--eval-window-count', type=int, default=3)
    parser.add_argument('--eval-window-aggregation', default='mean')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=0.0)
    parser.add_argument('--eval-window-support-threshold', type=float, default=0.40)
    parser.add_argument('--eval-window-min-support-windows', type=int, default=2)
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=0.55)
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=1)
    parser.add_argument('--score-batch-size', type=int, default=32)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    return parser.parse_args()


def write_rows(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f'No rows to write: {path}')
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


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    mix_probs = [float(row.get('mined_mix_prob', 0.0) or 0.0) for row in rows]
    return {
        'items': int(len(rows)),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
        'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
        'mix_prob_min': round(min(mix_probs), 6) if mix_probs else 0.0,
        'mix_prob_mean': round(sum(mix_probs) / len(mix_probs), 6) if mix_probs else 0.0,
        'mix_prob_max': round(max(mix_probs), 6) if mix_probs else 0.0,
    }


def as_float(row: Dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except Exception:
        return 0.0


def positive_sort_key(row: Dict[str, Any]) -> tuple:
    return (
        as_float(row, 'mined_mix_prob'),
        -int(float(row.get('pharyngeal', 0) or 0)),
        -int(float(row.get('falsetto', 0) or 0)),
        str(row.get('singer', '') or ''),
        str(row.get('song_name', '') or ''),
        str(row.get('item_name', '') or ''),
    )


def negative_sort_key(row: Dict[str, Any]) -> tuple:
    return (
        -as_float(row, 'mined_mix_prob'),
        *row_priority(row),
    )


def select_diverse_rows(
    rows: Iterable[Dict[str, Any]],
    keep_count: int,
    *,
    max_per_singer: int,
    max_per_song: int,
    max_per_singer_song: int,
) -> List[Dict[str, Any]]:
    if int(keep_count) <= 0:
        return []
    selected: List[Dict[str, Any]] = []
    singer_counts: Counter[str] = Counter()
    song_counts: Counter[str] = Counter()
    singer_song_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        singer = str(row.get('singer', '') or '')
        song_name = str(row.get('song_name', '') or '')
        singer_key = singer
        song_key = song_name
        singer_song_key = (singer, song_name)
        if singer_counts[singer_key] >= max_per_singer:
            continue
        if song_counts[song_key] >= max_per_song:
            continue
        if singer_song_counts[singer_song_key] >= max_per_singer_song:
            continue
        selected.append(dict(row))
        singer_counts[singer_key] += 1
        song_counts[song_key] += 1
        singer_song_counts[singer_song_key] += 1
        if len(selected) >= keep_count:
            break
    return selected


def attach_selection_metadata(rows: Sequence[Dict[str, Any]], selection_role: str) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item['mined_selection_role'] = selection_role
        item['mined_rank'] = str(index)
        item['mined_pool_size'] = str(total)
        enriched.append(item)
    return enriched


def main() -> int:
    args = parse_args()
    train_manifest = Path(args.train_manifest).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not train_manifest.exists():
        raise FileNotFoundError(f'train manifest not found: {train_manifest}')
    if not artifact_dir.exists():
        raise FileNotFoundError(f'artifact dir not found: {artifact_dir}')

    negative_roles = tuple(args.negative_roles or ['control_negative'])
    train_rows = read_manifest(train_manifest)
    scored_rows = score_rows_with_artifact(
        train_rows,
        artifact_dir=artifact_dir,
        eval_window_count=int(args.eval_window_count),
        eval_window_aggregation=str(args.eval_window_aggregation),
        eval_window_consistency_penalty=float(args.eval_window_consistency_penalty),
        eval_window_support_threshold=float(args.eval_window_support_threshold),
        eval_window_min_support_windows=int(args.eval_window_min_support_windows),
        eval_window_high_support_threshold=float(args.eval_window_high_support_threshold),
        eval_window_min_high_support_windows=int(args.eval_window_min_high_support_windows),
        batch_size=int(args.score_batch_size),
        device_override=str(args.device),
    )

    positives = [dict(row) for row in scored_rows if int(float(row.get('mix', 0) or 0)) == 1]
    negatives = [
        dict(row)
        for row in scored_rows
        if int(float(row.get('mix', 0) or 0)) == 0 and negative_bucket(row) in negative_roles
    ]

    positives.sort(key=positive_sort_key)
    negatives.sort(key=negative_sort_key)

    selected_positives = attach_selection_metadata(
        select_diverse_rows(
            positives,
            int(args.positive_keep_count),
            max_per_singer=int(args.max_per_singer),
            max_per_song=int(args.max_per_song),
            max_per_singer_song=int(args.max_per_singer_song),
        ),
        'hard_positive',
    )
    selected_negatives = attach_selection_metadata(
        select_diverse_rows(
            negatives,
            int(args.negative_keep_count),
            max_per_singer=int(args.max_per_singer),
            max_per_song=int(args.max_per_song),
            max_per_singer_song=int(args.max_per_singer_song),
        ),
        'hard_negative',
    )
    increment_rows = selected_positives + selected_negatives

    output_dir.mkdir(parents=True, exist_ok=True)
    increment_manifest = output_dir / 'training_increment_manifest.csv'
    summary_path = output_dir / 'plan_summary.json'
    positives_preview_path = output_dir / 'hard_positive_preview.csv'
    negatives_preview_path = output_dir / 'hard_negative_preview.csv'

    write_rows(increment_manifest, increment_rows)
    write_rows(positives_preview_path, selected_positives if selected_positives else [{'message': 'no_rows'}])
    write_rows(negatives_preview_path, selected_negatives if selected_negatives else [{'message': 'no_rows'}])

    summary = {
        'train_manifest': str(train_manifest),
        'artifact_dir': str(artifact_dir),
        'output_dir': str(output_dir),
        'negative_roles': list(negative_roles),
        'selection_config': {
            'positive_keep_count': int(args.positive_keep_count),
            'negative_keep_count': int(args.negative_keep_count),
            'max_per_singer': int(args.max_per_singer),
            'max_per_song': int(args.max_per_song),
            'max_per_singer_song': int(args.max_per_singer_song),
            'eval_window_count': int(args.eval_window_count),
            'eval_window_aggregation': str(args.eval_window_aggregation),
            'eval_window_consistency_penalty': float(args.eval_window_consistency_penalty),
            'eval_window_support_threshold': float(args.eval_window_support_threshold),
            'eval_window_min_support_windows': int(args.eval_window_min_support_windows),
            'eval_window_high_support_threshold': float(args.eval_window_high_support_threshold),
            'eval_window_min_high_support_windows': int(args.eval_window_min_high_support_windows),
            'score_batch_size': int(args.score_batch_size),
            'device': str(args.device),
        },
        'counts': {
            'train_rows': len(train_rows),
            'scored_positive_pool': len(positives),
            'scored_negative_pool': len(negatives),
            'selected_positive_rows': len(selected_positives),
            'selected_negative_rows': len(selected_negatives),
            'increment_rows': len(increment_rows),
        },
        'rationale': [
            'Mine hard positives from the original train split by selecting low-score positive_mix rows under the current stable artifact.',
            'Mine hard negatives from the original train split by selecting high-score in-distribution negative rows, instead of injecting guarded test-side samples into training.',
            'Apply simple singer and song caps so the increment is not dominated by a single local pocket of the train distribution.',
        ],
        'summaries': {
            'selected_positives': summarize_rows(selected_positives),
            'selected_negatives': summarize_rows(selected_negatives),
            'increment_rows': summarize_rows(increment_rows),
        },
        'manifests': {
            'training_increment_manifest': str(increment_manifest),
            'hard_positive_preview': str(positives_preview_path),
            'hard_negative_preview': str(negatives_preview_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())