import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from torch.utils.data import DataLoader

import compare_mix_binary_checkpoints as compare
import train_mix_binary_squeezenet as trainer


def load_rows(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


@torch.no_grad()
def collect_labels_and_probs(
    artifact_dir: Path,
    rows: Sequence[dict],
    device: torch.device,
    eval_window_count_override: int | None = None,
) -> tuple[List[int], List[float], float, int, int, str, float, float, int, float, int, str, int, int, int, int]:
    model, _, sample_secs, n_mels, artifact_eval_window_count, artifact_eval_window_aggregation, artifact_eval_window_consistency_penalty, artifact_eval_window_support_threshold, artifact_eval_window_min_support_windows, artifact_eval_window_high_support_threshold, artifact_eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = compare.load_artifact_model(artifact_dir, device)
    eval_window_count = max(1, int(eval_window_count_override or artifact_eval_window_count or 1))
    eval_window_aggregation = str(artifact_eval_window_aggregation or 'mean').strip().lower()
    if eval_window_aggregation not in trainer.EVAL_WINDOW_AGGREGATIONS:
        eval_window_aggregation = 'mean'
    eval_window_consistency_penalty = max(0.0, float(artifact_eval_window_consistency_penalty or 0.0))
    eval_window_support_threshold = min(0.95, max(0.05, float(artifact_eval_window_support_threshold or 0.40)))
    eval_window_min_support_windows = max(1, int(artifact_eval_window_min_support_windows or 2))
    eval_window_high_support_threshold = min(0.99, max(eval_window_support_threshold, float(artifact_eval_window_high_support_threshold or 0.55)))
    eval_window_min_high_support_windows = max(1, int(artifact_eval_window_min_high_support_windows or 1))
    eval_anchor_ratios = trainer.build_eval_anchor_ratios(eval_window_count)
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
    loader = DataLoader(dataset, batch_size=32, shuffle=False, num_workers=0)

    labels: List[int] = []
    probs: List[float] = []
    for images, batch_labels in loader:
        logits = trainer.forward_with_window_average(
            model,
            images.to(device),
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        batch_probs = torch.softmax(logits, dim=1)[:, 1].detach().cpu().numpy()
        labels.extend(int(item) for item in batch_labels.detach().cpu().numpy().tolist())
        probs.extend(float(item) for item in batch_probs.tolist())
    return (
        labels,
        probs,
        float(sample_secs),
        int(n_mels),
        int(eval_window_count),
        str(eval_window_aggregation),
        float(eval_window_consistency_penalty),
        float(eval_window_support_threshold),
        int(eval_window_min_support_windows),
        float(eval_window_high_support_threshold),
        int(eval_window_min_high_support_windows),
        str(artifact_backbone_name),
        int(artifact_image_size),
        int(artifact_sample_rate),
        int(artifact_n_fft),
        int(artifact_hop_length),
    )


def find_best_threshold(
    labels: Sequence[int],
    probs: Sequence[float],
    rows: Sequence[dict],
    *,
    metric: str,
    threshold_min: float,
    threshold_max: float,
    threshold_step: float,
    min_constraints: Dict[str, float],
    min_role_constraints: Dict[str, float],
    max_role_constraints: Dict[str, float],
) -> tuple[float, Dict[str, float], Dict[str, float]]:
    labels_np = np.asarray(list(labels), dtype=np.int32)
    probs_np = np.asarray(list(probs), dtype=np.float32)
    candidates = np.arange(threshold_min, threshold_max + 1e-9, threshold_step, dtype=np.float32)
    best_threshold = float(threshold_min)
    best_preds = (probs_np >= best_threshold).astype(np.int32)
    best_metrics = trainer.compute_binary_metrics(labels_np, best_preds)
    best_role_rates = trainer.summarize_binary_role_positive_rates(rows, best_preds)
    best_score = float(best_metrics.get(metric, best_metrics['mix_f1']))
    matched_any_constraint = False
    constrained_threshold = None
    constrained_metrics = None
    constrained_role_rates = None
    constrained_score = None
    for candidate in candidates:
        preds = (probs_np >= float(candidate)).astype(np.int32)
        metrics = trainer.compute_binary_metrics(labels_np, preds)
        role_rates = trainer.summarize_binary_role_positive_rates(rows, preds)
        if any(float(metrics.get(key, 0.0)) + 1e-12 < float(value) for key, value in min_constraints.items()):
            continue
        if any(float(role_rates.get(key, 0.0)) + 1e-12 < float(value) for key, value in min_role_constraints.items()):
            continue
        if any(float(role_rates.get(key, 0.0)) - 1e-12 > float(value) for key, value in max_role_constraints.items()):
            continue
        matched_any_constraint = True
        score = float(metrics.get(metric, metrics['mix_f1']))
        if constrained_score is None or score > float(constrained_score) + 1e-12:
            constrained_threshold = float(candidate)
            constrained_metrics = metrics
            constrained_role_rates = role_rates
            constrained_score = score
        if score > best_score + 1e-12:
            best_threshold = float(candidate)
            best_metrics = metrics
            best_role_rates = role_rates
            best_score = score
    if (min_constraints or min_role_constraints or max_role_constraints) and not matched_any_constraint:
        parts = []
        parts.extend(f'{key}>={value}' for key, value in sorted(min_constraints.items()))
        parts.extend(f'{key}>={value}' for key, value in sorted(min_role_constraints.items()))
        parts.extend(f'{key}<={value}' for key, value in sorted(max_role_constraints.items()))
        constraint_text = ', '.join(parts)
        raise RuntimeError(f'No threshold satisfied constraints: {constraint_text}')
    if matched_any_constraint and (min_constraints or min_role_constraints or max_role_constraints):
        return float(constrained_threshold), constrained_metrics or best_metrics, constrained_role_rates or best_role_rates
    return best_threshold, best_metrics, best_role_rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Create a calibrated copy of a mix-binary artifact with a new threshold.')
    parser.add_argument('--source-artifact', required=True, help='Existing artifact dir containing checkpoint and training_summary.json.')
    parser.add_argument('--manifest', required=True, help='Manifest used for threshold calibration, typically validation_manifest.csv.')
    parser.add_argument('--output-artifact', required=True, help='Destination artifact dir for the calibrated copy.')
    parser.add_argument('--metric', choices=['acc', 'balanced_acc', 'macro_f1', 'mix_f1', 'mix_precision', 'mix_recall'], default='mix_recall')
    parser.add_argument('--threshold-min', type=float, default=0.15)
    parser.add_argument('--threshold-max', type=float, default=0.55)
    parser.add_argument('--threshold-step', type=float, default=0.025)
    parser.add_argument('--eval-window-count', type=int, default=0, help='Optional override for eval window count. Defaults to artifact summary or 1.')
    parser.add_argument('--eval-window-aggregation', choices=['auto', *trainer.EVAL_WINDOW_AGGREGATIONS], default='auto', help='Optional override for eval window aggregation. Defaults to artifact summary or mean.')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=-1.0, help='Optional override for mean_minus_std penalty. Defaults to artifact summary or 0.0.')
    parser.add_argument('--eval-window-support-threshold', type=float, default=-1.0, help='Optional override for support_gate weak-support threshold. Defaults to artifact summary or 0.40.')
    parser.add_argument('--eval-window-min-support-windows', type=int, default=0, help='Optional override for support_gate minimum supported windows. Defaults to artifact summary or 2.')
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=-1.0, help='Optional override for support_gate_dual high-support threshold. Defaults to artifact summary or 0.55.')
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=0, help='Optional override for support_gate_dual minimum high-support windows. Defaults to artifact summary or 1.')
    parser.add_argument('--min-acc', type=float, default=-1.0)
    parser.add_argument('--min-balanced-acc', type=float, default=-1.0)
    parser.add_argument('--min-macro-f1', type=float, default=-1.0)
    parser.add_argument('--min-mix-f1', type=float, default=-1.0)
    parser.add_argument('--min-mix-precision', type=float, default=-1.0)
    parser.add_argument('--min-mix-recall', type=float, default=-1.0)
    parser.add_argument('--min-positive-mix-rate', type=float, default=-1.0)
    parser.add_argument('--max-control-negative-rate', type=float, default=-1.0)
    parser.add_argument('--max-breathy-negative-rate', type=float, default=-1.0)
    parser.add_argument('--max-falsetto-negative-rate', type=float, default=-1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_artifact = Path(args.source_artifact)
    output_artifact = Path(args.output_artifact)
    manifest_path = Path(args.manifest)
    summary_path = source_artifact / 'training_summary.json'
    checkpoint_path = source_artifact / 'best_mix_binary_squeezenet.pt'
    label_map_path = source_artifact / 'label_map.json'

    if not summary_path.exists():
        raise FileNotFoundError(f'Missing training summary: {summary_path}')
    if not checkpoint_path.exists():
        raise FileNotFoundError(f'Missing checkpoint: {checkpoint_path}')

    rows = load_rows(manifest_path)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    override_aggregation = None if str(args.eval_window_aggregation or 'auto') == 'auto' else str(args.eval_window_aggregation)
    override_penalty = None if float(args.eval_window_consistency_penalty) < 0.0 else float(args.eval_window_consistency_penalty)
    override_support_threshold = None if float(args.eval_window_support_threshold) < 0.0 else float(args.eval_window_support_threshold)
    override_min_support_windows = None if int(args.eval_window_min_support_windows or 0) <= 0 else int(args.eval_window_min_support_windows)
    override_high_support_threshold = None if float(args.eval_window_high_support_threshold) < 0.0 else float(args.eval_window_high_support_threshold)
    override_min_high_support_windows = None if int(args.eval_window_min_high_support_windows or 0) <= 0 else int(args.eval_window_min_high_support_windows)
    if override_aggregation is not None or override_penalty is not None or override_support_threshold is not None or override_min_support_windows is not None or override_high_support_threshold is not None or override_min_high_support_windows is not None:
        model, _, sample_secs, n_mels, artifact_eval_window_count, artifact_eval_window_aggregation, artifact_eval_window_consistency_penalty, artifact_eval_window_support_threshold, artifact_eval_window_min_support_windows, artifact_eval_window_high_support_threshold, artifact_eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = compare.load_artifact_model(source_artifact, device)
        eval_window_count = max(1, int(args.eval_window_count or artifact_eval_window_count or 1))
        eval_window_aggregation = str(override_aggregation or artifact_eval_window_aggregation or 'mean').strip().lower()
        if eval_window_aggregation not in trainer.EVAL_WINDOW_AGGREGATIONS:
            eval_window_aggregation = 'mean'
        eval_window_consistency_penalty = max(0.0, float(artifact_eval_window_consistency_penalty if override_penalty is None else override_penalty))
        eval_window_support_threshold = min(0.95, max(0.05, float(artifact_eval_window_support_threshold if override_support_threshold is None else override_support_threshold)))
        eval_window_min_support_windows = max(1, int(artifact_eval_window_min_support_windows if override_min_support_windows is None else override_min_support_windows))
        eval_window_high_support_threshold = min(0.99, max(eval_window_support_threshold, float(artifact_eval_window_high_support_threshold if override_high_support_threshold is None else override_high_support_threshold)))
        eval_window_min_high_support_windows = max(1, int(artifact_eval_window_min_high_support_windows if override_min_high_support_windows is None else override_min_high_support_windows))
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
            eval_anchor_ratios=trainer.build_eval_anchor_ratios(eval_window_count),
        )
        loader = DataLoader(dataset, batch_size=32, shuffle=False, num_workers=0)
        labels = []
        probs = []
        for images, batch_labels in loader:
            logits = trainer.forward_with_window_average(
                model,
                images.to(device),
                aggregation=eval_window_aggregation,
                consistency_penalty=eval_window_consistency_penalty,
                support_threshold=eval_window_support_threshold,
                min_support_windows=eval_window_min_support_windows,
                high_support_threshold=eval_window_high_support_threshold,
                min_high_support_windows=eval_window_min_high_support_windows,
            )
            batch_probs = torch.softmax(logits, dim=1)[:, 1].detach().cpu().numpy()
            labels.extend(int(item) for item in batch_labels.detach().cpu().numpy().tolist())
            probs.extend(float(item) for item in batch_probs.tolist())
    else:
        labels, probs, sample_secs, n_mels, eval_window_count, eval_window_aggregation, eval_window_consistency_penalty, eval_window_support_threshold, eval_window_min_support_windows, eval_window_high_support_threshold, eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = collect_labels_and_probs(
            source_artifact,
            rows,
            device,
            eval_window_count_override=int(args.eval_window_count or 0),
        )
    original_summary = json.loads(summary_path.read_text(encoding='utf-8'))
    original_threshold = float(original_summary.get('best_threshold', 0.45) or 0.45)
    min_constraints = {
        key: float(value)
        for key, value in {
            'acc': args.min_acc,
            'balanced_acc': args.min_balanced_acc,
            'macro_f1': args.min_macro_f1,
            'mix_f1': args.min_mix_f1,
            'mix_precision': args.min_mix_precision,
            'mix_recall': args.min_mix_recall,
        }.items()
        if float(value) >= 0.0
    }
    min_role_constraints = {
        key: float(value)
        for key, value in {
            'positive_mix': args.min_positive_mix_rate,
        }.items()
        if float(value) >= 0.0
    }
    max_role_constraints = {
        key: float(value)
        for key, value in {
            'control_negative': args.max_control_negative_rate,
            'breathy_group': args.max_breathy_negative_rate,
            'falsetto_group': args.max_falsetto_negative_rate,
        }.items()
        if float(value) >= 0.0
    }
    best_threshold, best_metrics, best_role_rates = find_best_threshold(
        labels,
        probs,
        rows,
        metric=args.metric,
        threshold_min=float(args.threshold_min),
        threshold_max=float(args.threshold_max),
        threshold_step=float(args.threshold_step),
        min_constraints=min_constraints,
        min_role_constraints=min_role_constraints,
        max_role_constraints=max_role_constraints,
    )

    output_artifact.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint_path, output_artifact / checkpoint_path.name)
    if label_map_path.exists():
        shutil.copy2(label_map_path, output_artifact / label_map_path.name)
    history_path = source_artifact / 'history.csv'
    if history_path.exists():
        shutil.copy2(history_path, output_artifact / history_path.name)

    calibrated_summary = dict(original_summary)
    calibrated_summary['checkpoint'] = str((output_artifact / checkpoint_path.name).resolve())
    calibrated_summary['best_threshold'] = round(float(best_threshold), 6)
    calibrated_summary['backbone_name'] = str(calibrated_summary.get('backbone_name', artifact_backbone_name))
    calibrated_summary['image_size'] = int(calibrated_summary.get('image_size', artifact_image_size))
    calibrated_summary['sample_rate'] = int(calibrated_summary.get('sample_rate', artifact_sample_rate))
    calibrated_summary['n_fft'] = int(calibrated_summary.get('n_fft', artifact_n_fft))
    calibrated_summary['hop_length'] = int(calibrated_summary.get('hop_length', artifact_hop_length))
    calibrated_summary['eval_window_count'] = int(eval_window_count)
    calibrated_summary['eval_window_aggregation'] = str(eval_window_aggregation)
    calibrated_summary['eval_window_consistency_penalty'] = round(float(eval_window_consistency_penalty), 6)
    calibrated_summary['eval_window_support_threshold'] = round(float(eval_window_support_threshold), 6)
    calibrated_summary['eval_window_min_support_windows'] = int(eval_window_min_support_windows)
    calibrated_summary['eval_window_high_support_threshold'] = round(float(eval_window_high_support_threshold), 6)
    calibrated_summary['eval_window_min_high_support_windows'] = int(eval_window_min_high_support_windows)
    calibrated_summary['posthoc_threshold_calibration'] = {
        'source_artifact': str(source_artifact.resolve()),
        'manifest': str(manifest_path.resolve()),
        'metric': str(args.metric),
        'eval_window_count': int(eval_window_count),
        'eval_window_aggregation': str(eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(eval_window_min_high_support_windows),
        'threshold_min': round(float(args.threshold_min), 6),
        'threshold_max': round(float(args.threshold_max), 6),
        'threshold_step': round(float(args.threshold_step), 6),
        'min_constraints': {key: round(float(value), 6) for key, value in min_constraints.items()},
        'min_role_constraints': {key: round(float(value), 6) for key, value in min_role_constraints.items()},
        'max_role_constraints': {key: round(float(value), 6) for key, value in max_role_constraints.items()},
        'original_threshold': round(float(original_threshold), 6),
        'calibrated_threshold': round(float(best_threshold), 6),
        'manifest_metrics': {key: round(float(value), 6) for key, value in best_metrics.items()},
        'manifest_binary_role_rates': {key: round(float(value), 6) for key, value in best_role_rates.items()},
        'sample_count': int(len(rows)),
        'backbone_name': str(artifact_backbone_name),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'sample_secs': round(float(sample_secs), 6),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
        'n_mels': int(n_mels),
    }
    (output_artifact / 'training_summary.json').write_text(
        json.dumps(calibrated_summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    print(json.dumps({
        'source_artifact': str(source_artifact.resolve()),
        'output_artifact': str(output_artifact.resolve()),
        'metric': args.metric,
        'eval_window_count': int(eval_window_count),
        'eval_window_aggregation': str(eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(eval_window_min_high_support_windows),
        'min_constraints': {key: round(float(value), 6) for key, value in min_constraints.items()},
        'min_role_constraints': {key: round(float(value), 6) for key, value in min_role_constraints.items()},
        'max_role_constraints': {key: round(float(value), 6) for key, value in max_role_constraints.items()},
        'original_threshold': round(float(original_threshold), 6),
        'calibrated_threshold': round(float(best_threshold), 6),
        'manifest_metrics': {key: round(float(value), 6) for key, value in best_metrics.items()},
        'manifest_binary_role_rates': {key: round(float(value), 6) for key, value in best_role_rates.items()},
        'backbone_name': str(artifact_backbone_name),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()