import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score
from torch.utils.data import DataLoader

import train_mix_binary_squeezenet as trainer


DEFAULT_GROUPS = (
    'Mixed_Voice_Group',
    'Falsetto_Group',
    'Breathy_Group',
    'Control_Group',
)
DEFAULT_BINARY_ROLES = (
    'positive_mix',
    'control_negative',
    'falsetto_group',
    'breathy_group',
)


def load_rows(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def load_artifact_model(artifact_dir: Path, device: torch.device):
    summary_path = artifact_dir / 'training_summary.json'
    checkpoint_path = artifact_dir / 'best_mix_binary_squeezenet.pt'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    backbone_name = str(summary.get('backbone_name', 'squeezenet11') or 'squeezenet11').strip().lower()
    image_size = int(summary.get('image_size', 224) or 224)
    sample_rate = int(summary.get('sample_rate', 22050) or 22050)
    threshold = float(summary.get('best_threshold', 0.45) or 0.45)
    sample_secs = float(summary.get('sample_secs', 2.4) or 2.4)
    n_fft = int(summary.get('n_fft', 1024) or 1024)
    hop_length = int(summary.get('hop_length', 256) or 256)
    n_mels = int(summary.get('n_mels', 128) or 128)
    eval_window_count = max(1, int(summary.get('eval_window_count', 1) or 1))
    eval_window_aggregation = str(summary.get('eval_window_aggregation', 'mean') or 'mean').strip().lower()
    if eval_window_aggregation not in trainer.EVAL_WINDOW_AGGREGATIONS:
        eval_window_aggregation = 'mean'
    eval_window_consistency_penalty = max(0.0, float(summary.get('eval_window_consistency_penalty', 0.0) or 0.0))
    eval_window_support_threshold = min(0.95, max(0.05, float(summary.get('eval_window_support_threshold', 0.40) or 0.40)))
    eval_window_min_support_windows = max(1, int(summary.get('eval_window_min_support_windows', 2) or 2))
    eval_window_high_support_threshold = min(0.99, max(eval_window_support_threshold, float(summary.get('eval_window_high_support_threshold', 0.55) or 0.55)))
    eval_window_min_high_support_windows = max(1, int(summary.get('eval_window_min_high_support_windows', 1) or 1))

    model = trainer.build_model(backbone_name=backbone_name).to(device)
    try:
        checkpoint = torch.load(str(checkpoint_path), map_location=device)
    except TypeError:
        checkpoint = torch.load(str(checkpoint_path), map_location=device, weights_only=False)
    except Exception as exc:
        if 'weights_only' not in str(exc or ''):
            raise
        checkpoint = torch.load(str(checkpoint_path), map_location=device, weights_only=False)
    state_dict = checkpoint.get('model_state_dict', checkpoint) if isinstance(checkpoint, dict) else checkpoint
    model.load_state_dict(state_dict)
    model.eval()
    return (
        model,
        threshold,
        sample_secs,
        n_mels,
        eval_window_count,
        eval_window_aggregation,
        eval_window_consistency_penalty,
        eval_window_support_threshold,
        eval_window_min_support_windows,
        eval_window_high_support_threshold,
        eval_window_min_high_support_windows,
        backbone_name,
        image_size,
        sample_rate,
        n_fft,
        hop_length,
    )


@torch.no_grad()
def score_checkpoint_on_rows(
    artifact_dir: Path,
    rows: Sequence[dict],
    device: torch.device,
    groups: Sequence[str],
    eval_window_count_override: int | None = None,
    eval_window_aggregation_override: str | None = None,
    eval_window_consistency_penalty_override: float | None = None,
    eval_window_support_threshold_override: float | None = None,
    eval_window_min_support_windows_override: int | None = None,
    eval_window_high_support_threshold_override: float | None = None,
    eval_window_min_high_support_windows_override: int | None = None,
) -> Dict[str, object]:
    model, threshold, sample_secs, n_mels, artifact_eval_window_count, artifact_eval_window_aggregation, artifact_eval_window_consistency_penalty, artifact_eval_window_support_threshold, artifact_eval_window_min_support_windows, artifact_eval_window_high_support_threshold, artifact_eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = load_artifact_model(artifact_dir, device)
    eval_window_count = max(1, int(eval_window_count_override or artifact_eval_window_count or 1))
    eval_window_aggregation = str(eval_window_aggregation_override or artifact_eval_window_aggregation or 'mean').strip().lower()
    if eval_window_aggregation not in trainer.EVAL_WINDOW_AGGREGATIONS:
        eval_window_aggregation = 'mean'
    eval_window_consistency_penalty = max(
        0.0,
        float(
            artifact_eval_window_consistency_penalty
            if eval_window_consistency_penalty_override is None
            else eval_window_consistency_penalty_override
        ),
    )
    eval_window_support_threshold = min(
        0.95,
        max(
            0.05,
            float(
                artifact_eval_window_support_threshold
                if eval_window_support_threshold_override is None
                else eval_window_support_threshold_override
            ),
        ),
    )
    eval_window_min_support_windows = max(
        1,
        int(
            artifact_eval_window_min_support_windows
            if eval_window_min_support_windows_override is None
            else eval_window_min_support_windows_override
        ),
    )
    eval_window_high_support_threshold = min(
        0.99,
        max(
            eval_window_support_threshold,
            float(
                artifact_eval_window_high_support_threshold
                if eval_window_high_support_threshold_override is None
                else eval_window_high_support_threshold_override
            ),
        ),
    )
    eval_window_min_high_support_windows = max(
        1,
        int(
            artifact_eval_window_min_high_support_windows
            if eval_window_min_high_support_windows_override is None
            else eval_window_min_high_support_windows_override
        ),
    )
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

    probs: List[float] = []
    labels: List[int] = []
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
        batch_probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
        probs.extend(float(item) for item in batch_probs)
        labels.extend(int(item) for item in batch_labels.numpy().tolist())

    enriched_rows = []
    for row, label, prob in zip(rows, labels, probs):
        item = dict(row)
        item['_label'] = int(label)
        item['_mix_prob'] = float(prob)
        item['_pred'] = int(prob >= threshold)
        enriched_rows.append(item)

    return {
        'threshold': round(threshold, 6),
        'backbone_name': str(artifact_backbone_name),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
        'eval_window_count': int(eval_window_count),
        'eval_window_aggregation': str(eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(eval_window_min_high_support_windows),
        'overall': summarize_rows(enriched_rows),
        'groups': {
            group_name: summarize_rows([row for row in enriched_rows if str(row.get('group_name', '') or '') == group_name])
            for group_name in groups
            if any(str(row.get('group_name', '') or '') == group_name for row in enriched_rows)
        },
        'binary_roles': {
            role_name: summarize_rows([row for row in enriched_rows if str(row.get('binary_role', '') or '') == role_name])
            for role_name in DEFAULT_BINARY_ROLES
            if any(str(row.get('binary_role', '') or '') == role_name for row in enriched_rows)
        },
    }


def summarize_rows(rows: Sequence[dict]) -> Dict[str, object]:
    if not rows:
        return {
            'sample_count': 0,
            'acc': 0.0,
            'balanced_acc': 0.0,
            'mix_f1': 0.0,
            'mix_precision': 0.0,
            'mix_recall': 0.0,
            'predicted_positive_rate': 0.0,
            'avg_mix_prob': 0.0,
        }
    y_true = np.asarray([int(row['_label']) for row in rows], dtype=np.int32)
    y_pred = np.asarray([int(row['_pred']) for row in rows], dtype=np.int32)
    mix_probs = np.asarray([float(row['_mix_prob']) for row in rows], dtype=np.float32)
    return {
        'sample_count': int(len(rows)),
        'acc': round(float(accuracy_score(y_true, y_pred)), 6),
        'balanced_acc': round(float(balanced_accuracy_score(y_true, y_pred)), 6),
        'mix_f1': round(float(f1_score(y_true, y_pred, zero_division=0)), 6),
        'mix_precision': round(float(precision_score(y_true, y_pred, zero_division=0)), 6),
        'mix_recall': round(float(recall_score(y_true, y_pred, zero_division=0)), 6),
        'predicted_positive_rate': round(float(y_pred.mean()) if y_pred.size else 0.0, 6),
        'avg_mix_prob': round(float(mix_probs.mean()) if mix_probs.size else 0.0, 6),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Compare multiple mix-binary checkpoints on the same manifest.')
    parser.add_argument('--manifest', required=True, help='CSV manifest to evaluate on.')
    parser.add_argument('--artifact', action='append', dest='artifacts', required=True, help='Artifact dir containing training_summary.json and best_mix_binary_squeezenet.pt. May be repeated.')
    parser.add_argument('--group', action='append', dest='groups', default=[], help='Optional group names to summarize separately. May be repeated.')
    parser.add_argument('--eval-window-count', type=int, default=0, help='Optional override for eval window count. Defaults to each artifact summary or 1.')
    parser.add_argument('--eval-window-aggregation', choices=['auto', *trainer.EVAL_WINDOW_AGGREGATIONS], default='auto', help='Optional override for eval window aggregation. Defaults to each artifact summary or mean.')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=-1.0, help='Optional override for mean_minus_std penalty. Defaults to each artifact summary or 0.0.')
    parser.add_argument('--eval-window-support-threshold', type=float, default=-1.0, help='Optional override for support_gate weak-support threshold. Defaults to each artifact summary or 0.40.')
    parser.add_argument('--eval-window-min-support-windows', type=int, default=0, help='Optional override for support_gate minimum supported windows. Defaults to each artifact summary or 2.')
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=-1.0, help='Optional override for support_gate_dual high-support threshold. Defaults to each artifact summary or 0.55.')
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=0, help='Optional override for support_gate_dual minimum high-support windows. Defaults to each artifact summary or 1.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    rows = load_rows(manifest_path)
    groups = list(args.groups or []) or list(DEFAULT_GROUPS)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    report = {
        'manifest': str(manifest_path),
        'groups': groups,
        'eval_window_count_override': int(args.eval_window_count or 0),
        'eval_window_aggregation_override': '' if str(args.eval_window_aggregation or 'auto') == 'auto' else str(args.eval_window_aggregation),
        'eval_window_consistency_penalty_override': None if float(args.eval_window_consistency_penalty) < 0.0 else round(float(args.eval_window_consistency_penalty), 6),
        'eval_window_support_threshold_override': None if float(args.eval_window_support_threshold) < 0.0 else round(float(args.eval_window_support_threshold), 6),
        'eval_window_min_support_windows_override': None if int(args.eval_window_min_support_windows or 0) <= 0 else int(args.eval_window_min_support_windows),
        'eval_window_high_support_threshold_override': None if float(args.eval_window_high_support_threshold) < 0.0 else round(float(args.eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows_override': None if int(args.eval_window_min_high_support_windows or 0) <= 0 else int(args.eval_window_min_high_support_windows),
        'artifacts': {},
    }
    for artifact in list(args.artifacts or []):
        artifact_path = Path(artifact)
        report['artifacts'][artifact_path.name] = score_checkpoint_on_rows(
            artifact_path,
            rows,
            device,
            groups,
            eval_window_count_override=int(args.eval_window_count or 0),
            eval_window_aggregation_override=None if str(args.eval_window_aggregation or 'auto') == 'auto' else str(args.eval_window_aggregation),
            eval_window_consistency_penalty_override=None if float(args.eval_window_consistency_penalty) < 0.0 else float(args.eval_window_consistency_penalty),
            eval_window_support_threshold_override=None if float(args.eval_window_support_threshold) < 0.0 else float(args.eval_window_support_threshold),
            eval_window_min_support_windows_override=None if int(args.eval_window_min_support_windows or 0) <= 0 else int(args.eval_window_min_support_windows),
            eval_window_high_support_threshold_override=None if float(args.eval_window_high_support_threshold) < 0.0 else float(args.eval_window_high_support_threshold),
            eval_window_min_high_support_windows_override=None if int(args.eval_window_min_high_support_windows or 0) <= 0 else int(args.eval_window_min_high_support_windows),
        )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(text, encoding='utf-8')
        print(f'json_report={output_path.resolve()}')


if __name__ == '__main__':
    main()