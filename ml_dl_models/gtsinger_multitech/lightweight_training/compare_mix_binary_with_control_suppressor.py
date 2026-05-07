import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Sequence

import torch
from torch.utils.data import DataLoader

import compare_mix_binary_checkpoints as compare
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


def load_artifact(
    artifact_dir: Path,
    device: torch.device,
    *,
    eval_window_count_override: int | None = None,
) -> Dict[str, object]:
    model, threshold, sample_secs, n_mels, artifact_eval_window_count, artifact_eval_window_aggregation, artifact_eval_window_consistency_penalty, artifact_eval_window_support_threshold, artifact_eval_window_min_support_windows, artifact_eval_window_high_support_threshold, artifact_eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = compare.load_artifact_model(artifact_dir, device)
    eval_window_count = max(1, int(eval_window_count_override or artifact_eval_window_count or 1))
    return {
        'path': str(artifact_dir),
        'model': model,
        'backbone_name': str(artifact_backbone_name),
        'threshold': float(threshold),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'sample_secs': float(sample_secs),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
        'n_mels': int(n_mels),
        'eval_window_count': int(eval_window_count),
        'eval_window_aggregation': str(artifact_eval_window_aggregation),
        'eval_window_consistency_penalty': float(artifact_eval_window_consistency_penalty),
        'eval_window_support_threshold': float(artifact_eval_window_support_threshold),
        'eval_window_min_support_windows': int(artifact_eval_window_min_support_windows),
        'eval_window_high_support_threshold': float(artifact_eval_window_high_support_threshold),
        'eval_window_min_high_support_windows': int(artifact_eval_window_min_high_support_windows),
    }


def build_loader(
    rows: Sequence[dict],
    *,
    image_size: int,
    sample_rate: int,
    sample_secs: float,
    n_fft: int,
    hop_length: int,
    n_mels: int,
    eval_window_count: int,
) -> DataLoader:
    _, eval_transform = trainer.build_transforms(image_size=image_size, augment_profile='safe')
    dataset = trainer.MixBinaryAudioDataset(
        rows,
        sample_rate=sample_rate,
        sample_secs=sample_secs,
        image_size=image_size,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        transform=eval_transform,
        train=False,
        eval_anchor_ratios=trainer.build_eval_anchor_ratios(eval_window_count),
    )
    return DataLoader(dataset, batch_size=32, shuffle=False, num_workers=0)


def run_model_batch(model_info: Dict[str, object], images: torch.Tensor, device: torch.device) -> torch.Tensor:
    logits = trainer.forward_with_window_average(
        model_info['model'],
        images.to(device),
        aggregation=str(model_info['eval_window_aggregation']),
        consistency_penalty=float(model_info['eval_window_consistency_penalty']),
        support_threshold=float(model_info['eval_window_support_threshold']),
        min_support_windows=int(model_info['eval_window_min_support_windows']),
        high_support_threshold=float(model_info['eval_window_high_support_threshold']),
        min_high_support_windows=int(model_info['eval_window_min_high_support_windows']),
    )
    return torch.softmax(logits, dim=1)[:, 1].detach().cpu()


def summarize_model_info(model_info: Dict[str, object]) -> Dict[str, object]:
    return {
        'path': str(model_info['path']),
        'backbone_name': str(model_info['backbone_name']),
        'threshold': round(float(model_info['threshold']), 6),
        'image_size': int(model_info['image_size']),
        'sample_rate': int(model_info['sample_rate']),
        'sample_secs': round(float(model_info['sample_secs']), 6),
        'n_fft': int(model_info['n_fft']),
        'hop_length': int(model_info['hop_length']),
        'n_mels': int(model_info['n_mels']),
        'eval_window_count': int(model_info['eval_window_count']),
        'eval_window_aggregation': str(model_info['eval_window_aggregation']),
        'eval_window_consistency_penalty': round(float(model_info['eval_window_consistency_penalty']), 6),
        'eval_window_support_threshold': round(float(model_info['eval_window_support_threshold']), 6),
        'eval_window_min_support_windows': int(model_info['eval_window_min_support_windows']),
        'eval_window_high_support_threshold': round(float(model_info['eval_window_high_support_threshold']), 6),
        'eval_window_min_high_support_windows': int(model_info['eval_window_min_high_support_windows']),
    }


def models_share_preprocessing(*model_infos: Dict[str, object]) -> bool:
    if not model_infos:
        return False
    first = model_infos[0]
    return all(
        int(item['image_size']) == int(first['image_size'])
        and int(item['sample_rate']) == int(first['sample_rate'])
        float(item['sample_secs']) == float(first['sample_secs'])
        and int(item['n_fft']) == int(first['n_fft'])
        and int(item['hop_length']) == int(first['hop_length'])
        and int(item['n_mels']) == int(first['n_mels'])
        and int(item['eval_window_count']) == int(first['eval_window_count'])
        for item in model_infos[1:]
    )


@torch.no_grad()
def score_rows(
    artifact_dir: Path,
    rows: Sequence[dict],
    device: torch.device,
    *,
    eval_window_count_override: int | None = None,
) -> tuple[List[float], float, Dict[str, object]]:
    model_info = load_artifact(
        artifact_dir,
        device,
        eval_window_count_override=eval_window_count_override,
    )
    loader = build_loader(
        rows,
        image_size=int(model_info['image_size']),
        sample_rate=int(model_info['sample_rate']),
        sample_secs=float(model_info['sample_secs']),
        n_fft=int(model_info['n_fft']),
        hop_length=int(model_info['hop_length']),
        n_mels=int(model_info['n_mels']),
        eval_window_count=int(model_info['eval_window_count']),
    )
    probs: List[float] = []
    for images, _ in loader:
        probs.extend(float(item) for item in run_model_batch(model_info, images, device).numpy().tolist())
    return probs, float(model_info['threshold']), summarize_model_info(model_info)


@torch.no_grad()
def score_rows_shared(
    primary_info: Dict[str, object],
    suppressor_info: Dict[str, object],
    rows: Sequence[dict],
    device: torch.device,
) -> tuple[List[float], List[float]]:
    loader = build_loader(
        rows,
        image_size=int(primary_info['image_size']),
        sample_rate=int(primary_info['sample_rate']),
        sample_secs=float(primary_info['sample_secs']),
        n_fft=int(primary_info['n_fft']),
        hop_length=int(primary_info['hop_length']),
        n_mels=int(primary_info['n_mels']),
        eval_window_count=int(primary_info['eval_window_count']),
    )
    primary_probs: List[float] = []
    suppressor_probs: List[float] = []
    total_batches = len(loader)
    for batch_index, (images, _) in enumerate(loader, start=1):
        primary_probs.extend(float(item) for item in run_model_batch(primary_info, images, device).numpy().tolist())
        suppressor_probs.extend(float(item) for item in run_model_batch(suppressor_info, images, device).numpy().tolist())
        if batch_index == 1 or batch_index == total_batches or batch_index % 10 == 0:
            print(f'scoring_batch={batch_index}/{total_batches}', flush=True)
    return primary_probs, suppressor_probs


def summarize_rows(rows: Sequence[dict]) -> Dict[str, object]:
    return compare.summarize_rows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Evaluate a primary mix model plus a control suppressor model on the same manifest.')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--primary-artifact', required=True)
    parser.add_argument('--suppressor-artifact', required=True)
    parser.add_argument('--eval-window-count', type=int, default=0)
    parser.add_argument('--output', default='')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    rows = load_rows(manifest_path)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    primary_info = load_artifact(
        Path(args.primary_artifact),
        device,
        eval_window_count_override=int(args.eval_window_count or 0),
    )
    suppressor_info = load_artifact(
        Path(args.suppressor_artifact),
        device,
        eval_window_count_override=int(args.eval_window_count or 0),
    )
    if models_share_preprocessing(primary_info, suppressor_info):
        print('shared_preprocessing=true', flush=True)
        primary_probs, suppressor_probs = score_rows_shared(primary_info, suppressor_info, rows, device)
    else:
        print('shared_preprocessing=false', flush=True)
        primary_probs, primary_threshold, primary_meta = score_rows(
            Path(args.primary_artifact),
            rows,
            device,
            eval_window_count_override=int(args.eval_window_count or 0),
        )
        suppressor_probs, suppressor_threshold, suppressor_meta = score_rows(
            Path(args.suppressor_artifact),
            rows,
            device,
            eval_window_count_override=int(args.eval_window_count or 0),
        )
        primary_info['threshold'] = primary_threshold
        suppressor_info['threshold'] = suppressor_threshold
        primary_info.update(primary_meta)
        suppressor_info.update(suppressor_meta)

    primary_threshold = float(primary_info['threshold'])
    suppressor_threshold = float(suppressor_info['threshold'])

    primary_rows = []
    combined_rows = []
    for row, primary_prob, suppressor_prob in zip(rows, primary_probs, suppressor_probs):
        label = int(float(row.get('mix', 0) or 0))
        primary_pred = int(primary_prob >= primary_threshold)
        suppressor_pass = int(suppressor_prob >= suppressor_threshold)
        combined_pred = int(primary_pred == 1 and suppressor_pass == 1)

        primary_item = dict(row)
        primary_item['_label'] = label
        primary_item['_mix_prob'] = float(primary_prob)
        primary_item['_pred'] = primary_pred
        primary_rows.append(primary_item)

        combined_item = dict(row)
        combined_item['_label'] = label
        combined_item['_mix_prob'] = float(primary_prob)
        combined_item['_pred'] = combined_pred
        combined_item['_primary_mix_prob'] = float(primary_prob)
        combined_item['_suppressor_mix_prob'] = float(suppressor_prob)
        combined_rows.append(combined_item)

    report = {
        'manifest': str(manifest_path),
        'eval_window_count_override': int(args.eval_window_count or 0),
        'primary_artifact': summarize_model_info(primary_info),
        'suppressor_artifact': summarize_model_info(suppressor_info),
        'primary_only': {
            'overall': summarize_rows(primary_rows),
            'groups': {
                group_name: summarize_rows([row for row in primary_rows if str(row.get('group_name', '') or '') == group_name])
                for group_name in DEFAULT_GROUPS
                if any(str(row.get('group_name', '') or '') == group_name for row in primary_rows)
            },
            'binary_roles': {
                role_name: summarize_rows([row for row in primary_rows if str(row.get('binary_role', '') or '') == role_name])
                for role_name in DEFAULT_BINARY_ROLES
                if any(str(row.get('binary_role', '') or '') == role_name for row in primary_rows)
            },
        },
        'primary_plus_suppressor': {
            'overall': summarize_rows(combined_rows),
            'groups': {
                group_name: summarize_rows([row for row in combined_rows if str(row.get('group_name', '') or '') == group_name])
                for group_name in DEFAULT_GROUPS
                if any(str(row.get('group_name', '') or '') == group_name for row in combined_rows)
            },
            'binary_roles': {
                role_name: summarize_rows([row for row in combined_rows if str(row.get('binary_role', '') or '') == role_name])
                for role_name in DEFAULT_BINARY_ROLES
                if any(str(row.get('binary_role', '') or '') == role_name for row in combined_rows)
            },
        },
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(text, encoding='utf-8')
        print(f'json_report={output_path.resolve()}')


if __name__ == '__main__':
    main()