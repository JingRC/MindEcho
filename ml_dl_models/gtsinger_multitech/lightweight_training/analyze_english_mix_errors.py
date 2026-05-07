import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import torch
from torch.utils.data import DataLoader

import compare_mix_binary_checkpoints as compare
import train_mix_binary_squeezenet as trainer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Analyze false positives and false negatives on the English mix evaluation manifest.')
    parser.add_argument('--manifest', required=True, help='English evaluation manifest CSV path.')
    parser.add_argument('--artifact-dir', required=True, help='Artifact directory containing training_summary.json and best_mix_binary_squeezenet.pt.')
    parser.add_argument('--output-prefix', default='', help='Output prefix for the JSON/CSV reports. Defaults next to the manifest.')
    parser.add_argument('--top-k', type=int, default=50, help='Top sample count to keep for the near-threshold and dangerous error lists.')
    parser.add_argument('--batch-size', type=int, default=32, help='Evaluation batch size.')
    return parser.parse_args()


@torch.no_grad()
def score_rows(rows: Sequence[dict], artifact_dir: Path, *, batch_size: int) -> tuple[float, list[dict], dict]:
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    (
        model,
        threshold,
        sample_secs,
        n_mels,
        artifact_eval_window_count,
        artifact_eval_window_aggregation,
        artifact_eval_window_consistency_penalty,
        artifact_eval_window_support_threshold,
        artifact_eval_window_min_support_windows,
        artifact_eval_window_high_support_threshold,
        artifact_eval_window_min_high_support_windows,
        artifact_backbone_name,
        artifact_image_size,
        artifact_sample_rate,
        artifact_n_fft,
        artifact_hop_length,
    ) = compare.load_artifact_model(artifact_dir, device)

    eval_anchor_ratios = trainer.build_eval_anchor_ratios(artifact_eval_window_count)
    _, eval_transform = trainer.build_transforms(image_size=artifact_image_size, augment_profile='safe')
    dataset = trainer.MixBinaryAudioDataset(
        rows,
        sample_rate=artifact_sample_rate,
        sample_secs=sample_secs,
        image_size=artifact_image_size,
        n_fft=artifact_n_fft,
        hop_length=artifact_hop_length,
        n_mels=n_mels,
        transform=eval_transform,
        train=False,
        eval_anchor_ratios=eval_anchor_ratios,
    )
    loader = DataLoader(dataset, batch_size=max(1, int(batch_size)), shuffle=False, num_workers=0)

    probs: list[float] = []
    labels: list[int] = []
    for images, batch_labels in loader:
        logits = trainer.forward_with_window_average(
            model,
            images.to(device),
            aggregation=artifact_eval_window_aggregation,
            consistency_penalty=artifact_eval_window_consistency_penalty,
            support_threshold=artifact_eval_window_support_threshold,
            min_support_windows=artifact_eval_window_min_support_windows,
            high_support_threshold=artifact_eval_window_high_support_threshold,
            min_high_support_windows=artifact_eval_window_min_high_support_windows,
        )
        batch_probs = torch.softmax(logits, dim=1)[:, 1].detach().cpu().numpy().tolist()
        probs.extend(float(item) for item in batch_probs)
        labels.extend(int(item) for item in batch_labels.detach().cpu().numpy().tolist())

    scored_rows: list[dict] = []
    for row, label, prob in zip(rows, labels, probs):
        pred = int(float(prob) >= float(threshold))
        item = dict(row)
        item['_label'] = int(label)
        item['_mix_prob'] = round(float(prob), 6)
        item['_pred'] = pred
        item['_threshold'] = round(float(threshold), 6)
        item['_margin_vs_threshold'] = round(float(prob) - float(threshold), 6)
        if int(label) == 1 and pred == 0:
            item['_error_type'] = 'false_negative'
            item['_error_gap'] = round(float(threshold) - float(prob), 6)
        elif int(label) == 0 and pred == 1:
            item['_error_type'] = 'false_positive'
            item['_error_gap'] = round(float(prob) - float(threshold), 6)
        else:
            item['_error_type'] = ''
            item['_error_gap'] = 0.0
        scored_rows.append(item)

    artifact_info = {
        'threshold': round(float(threshold), 6),
        'backbone_name': str(artifact_backbone_name),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
        'eval_window_count': int(artifact_eval_window_count),
        'eval_window_aggregation': str(artifact_eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(artifact_eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(artifact_eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(artifact_eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(artifact_eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(artifact_eval_window_min_high_support_windows),
    }
    return float(threshold), scored_rows, artifact_info


def group_positive_miss_stats(rows: Sequence[dict], key_fields: Sequence[str]) -> list[dict]:
    buckets: dict[tuple[str, ...], dict] = {}
    for row in rows:
        if int(row.get('_label', 0)) != 1:
            continue
        key = tuple(str(row.get(field, '') or '') for field in key_fields)
        bucket = buckets.setdefault(
            key,
            {
                'key': key,
                'sample_count': 0,
                'miss_count': 0,
                'avg_mix_prob_sum': 0.0,
                'avg_miss_prob_sum': 0.0,
            },
        )
        bucket['sample_count'] += 1
        bucket['avg_mix_prob_sum'] += float(row.get('_mix_prob', 0.0) or 0.0)
        if str(row.get('_error_type', '') or '') == 'false_negative':
            bucket['miss_count'] += 1
            bucket['avg_miss_prob_sum'] += float(row.get('_mix_prob', 0.0) or 0.0)

    results: list[dict] = []
    for bucket in buckets.values():
        sample_count = int(bucket['sample_count'])
        miss_count = int(bucket['miss_count'])
        item = {
            key_fields[index]: bucket['key'][index]
            for index in range(len(key_fields))
        }
        item['sample_count'] = sample_count
        item['miss_count'] = miss_count
        item['miss_rate'] = round(float(miss_count) / float(sample_count), 6) if sample_count else 0.0
        item['avg_mix_prob'] = round(float(bucket['avg_mix_prob_sum']) / float(sample_count), 6) if sample_count else 0.0
        item['avg_fn_mix_prob'] = round(float(bucket['avg_miss_prob_sum']) / float(miss_count), 6) if miss_count else 0.0
        results.append(item)
    results.sort(key=lambda item: (-int(item['miss_count']), -float(item['miss_rate']), str(item)))
    return results


def group_negative_fp_stats(rows: Sequence[dict], key_fields: Sequence[str]) -> list[dict]:
    buckets: dict[tuple[str, ...], dict] = {}
    for row in rows:
        if int(row.get('_label', 0)) != 0:
            continue
        key = tuple(str(row.get(field, '') or '') for field in key_fields)
        bucket = buckets.setdefault(
            key,
            {
                'key': key,
                'sample_count': 0,
                'fp_count': 0,
                'avg_mix_prob_sum': 0.0,
                'avg_fp_prob_sum': 0.0,
            },
        )
        bucket['sample_count'] += 1
        bucket['avg_mix_prob_sum'] += float(row.get('_mix_prob', 0.0) or 0.0)
        if str(row.get('_error_type', '') or '') == 'false_positive':
            bucket['fp_count'] += 1
            bucket['avg_fp_prob_sum'] += float(row.get('_mix_prob', 0.0) or 0.0)

    results: list[dict] = []
    for bucket in buckets.values():
        sample_count = int(bucket['sample_count'])
        fp_count = int(bucket['fp_count'])
        item = {
            key_fields[index]: bucket['key'][index]
            for index in range(len(key_fields))
        }
        item['sample_count'] = sample_count
        item['fp_count'] = fp_count
        item['fp_rate'] = round(float(fp_count) / float(sample_count), 6) if sample_count else 0.0
        item['avg_mix_prob'] = round(float(bucket['avg_mix_prob_sum']) / float(sample_count), 6) if sample_count else 0.0
        item['avg_fp_mix_prob'] = round(float(bucket['avg_fp_prob_sum']) / float(fp_count), 6) if fp_count else 0.0
        results.append(item)
    results.sort(key=lambda item: (-int(item['fp_count']), -float(item['fp_rate']), str(item)))
    return results


def probability_band_summary(rows: Sequence[dict], *, threshold: float) -> dict:
    false_negatives = [row for row in rows if str(row.get('_error_type', '') or '') == 'false_negative']
    false_positives = [row for row in rows if str(row.get('_error_type', '') or '') == 'false_positive']

    def summarize_gaps(items: Sequence[dict]) -> dict:
        counts = {
            'le_0p02': 0,
            '0p02_to_0p05': 0,
            '0p05_to_0p10': 0,
            'gt_0p10': 0,
        }
        for row in items:
            gap = float(row.get('_error_gap', 0.0) or 0.0)
            if gap <= 0.02:
                counts['le_0p02'] += 1
            elif gap <= 0.05:
                counts['0p02_to_0p05'] += 1
            elif gap <= 0.10:
                counts['0p05_to_0p10'] += 1
            else:
                counts['gt_0p10'] += 1
        counts['sample_count'] = len(items)
        counts['threshold'] = round(float(threshold), 6)
        return counts

    return {
        'false_negative_gap_bands': summarize_gaps(false_negatives),
        'false_positive_gap_bands': summarize_gaps(false_positives),
    }


def select_top_error_samples(rows: Sequence[dict], *, error_type: str, top_k: int, reverse_prob: bool) -> list[dict]:
    filtered = [row for row in rows if str(row.get('_error_type', '') or '') == error_type]
    filtered.sort(
        key=lambda row: (
            -float(row.get('_mix_prob', 0.0) or 0.0) if reverse_prob else float(row.get('_mix_prob', 0.0) or 0.0),
            str(row.get('singer', '') or ''),
            str(row.get('song_name', '') or ''),
            str(row.get('item_name', '') or ''),
        )
    )
    selected: list[dict] = []
    for row in filtered[: max(1, int(top_k))]:
        selected.append({
            'item_name': str(row.get('item_name', '') or ''),
            'singer': str(row.get('singer', '') or ''),
            'song_name': str(row.get('song_name', '') or ''),
            'group_name': str(row.get('group_name', '') or ''),
            'binary_role': str(row.get('binary_role', '') or ''),
            'mix_variant': str(row.get('mix_variant', '') or ''),
            'mix': int(float(row.get('mix', 0) or 0)),
            'mix_prob': round(float(row.get('_mix_prob', 0.0) or 0.0), 6),
            'threshold_gap': round(float(row.get('_error_gap', 0.0) or 0.0), 6),
        })
    return selected


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    output_prefix = Path(args.output_prefix).resolve() if args.output_prefix else manifest_path.with_name('english_mix_error_analysis')

    rows = compare.load_rows(manifest_path)
    threshold, scored_rows, artifact_info = score_rows(rows, artifact_dir, batch_size=int(args.batch_size))

    false_negatives = [row for row in scored_rows if str(row.get('_error_type', '') or '') == 'false_negative']
    false_positives = [row for row in scored_rows if str(row.get('_error_type', '') or '') == 'false_positive']

    summary = {
        'manifest': str(manifest_path),
        'artifact_dir': str(artifact_dir),
        'artifact_info': artifact_info,
        'sample_count': len(scored_rows),
        'positive_count': sum(1 for row in scored_rows if int(row.get('_label', 0)) == 1),
        'negative_count': sum(1 for row in scored_rows if int(row.get('_label', 0)) == 0),
        'false_negative_count': len(false_negatives),
        'false_positive_count': len(false_positives),
        'false_negative_gap_summary': probability_band_summary(scored_rows, threshold=threshold)['false_negative_gap_bands'],
        'false_positive_gap_summary': probability_band_summary(scored_rows, threshold=threshold)['false_positive_gap_bands'],
        'positive_mix_by_singer': group_positive_miss_stats(scored_rows, ['singer']),
        'positive_mix_by_song': group_positive_miss_stats(scored_rows, ['singer', 'song_name', 'group_name']),
        'negative_fp_by_singer_role': group_negative_fp_stats(scored_rows, ['singer', 'binary_role']),
        'negative_fp_by_song_role': group_negative_fp_stats(scored_rows, ['singer', 'song_name', 'group_name', 'binary_role']),
        'top_false_negatives_near_threshold': select_top_error_samples(scored_rows, error_type='false_negative', top_k=int(args.top_k), reverse_prob=True),
        'top_false_negatives_far_below_threshold': select_top_error_samples(scored_rows, error_type='false_negative', top_k=int(args.top_k), reverse_prob=False),
        'top_false_positives_high_confidence': select_top_error_samples(scored_rows, error_type='false_positive', top_k=int(args.top_k), reverse_prob=True),
    }

    summary_path = output_prefix.with_suffix('.json')
    false_negative_csv = output_prefix.with_name(output_prefix.name + '_false_negatives.csv')
    false_positive_csv = output_prefix.with_name(output_prefix.name + '_false_positives.csv')

    summary_text = json.dumps(summary, ensure_ascii=False, indent=2)
    summary_path.write_text(summary_text, encoding='utf-8')

    fn_rows = [
        {
            'item_name': str(row.get('item_name', '') or ''),
            'singer': str(row.get('singer', '') or ''),
            'song_name': str(row.get('song_name', '') or ''),
            'group_name': str(row.get('group_name', '') or ''),
            'binary_role': str(row.get('binary_role', '') or ''),
            'mix_variant': str(row.get('mix_variant', '') or ''),
            'mix_prob': round(float(row.get('_mix_prob', 0.0) or 0.0), 6),
            'threshold_gap': round(float(row.get('_error_gap', 0.0) or 0.0), 6),
        }
        for row in sorted(false_negatives, key=lambda item: (-float(item.get('_mix_prob', 0.0) or 0.0), str(item.get('item_name', '') or '')))
    ]
    fp_rows = [
        {
            'item_name': str(row.get('item_name', '') or ''),
            'singer': str(row.get('singer', '') or ''),
            'song_name': str(row.get('song_name', '') or ''),
            'group_name': str(row.get('group_name', '') or ''),
            'binary_role': str(row.get('binary_role', '') or ''),
            'mix_variant': str(row.get('mix_variant', '') or ''),
            'mix_prob': round(float(row.get('_mix_prob', 0.0) or 0.0), 6),
            'fp_margin': round(float(row.get('_error_gap', 0.0) or 0.0), 6),
        }
        for row in sorted(false_positives, key=lambda item: (-float(item.get('_mix_prob', 0.0) or 0.0), str(item.get('item_name', '') or '')))
    ]
    write_csv(false_negative_csv, fn_rows)
    write_csv(false_positive_csv, fp_rows)

    print(summary_text)
    print(f'summary_json={summary_path}')
    print(f'false_negative_csv={false_negative_csv}')
    print(f'false_positive_csv={false_positive_csv}')


if __name__ == '__main__':
    main()