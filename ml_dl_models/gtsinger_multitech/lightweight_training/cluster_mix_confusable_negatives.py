import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader

import compare_mix_binary_checkpoints as compare
import train_mix_binary_squeezenet as trainer


DEFAULT_FOCUS_ROLES = (
    'control_negative',
    'breathy_group',
    'falsetto_group',
)
DEFAULT_OUTPUT_DATASET = r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_confusable_cluster_v1'
DEFAULT_ARTIFACT = r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_hardneg_v2_3win_guarded_gpu'
CLUSTER_IGNORE_VALUE = -100


def load_rows(path: Path) -> List[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: Sequence[dict]) -> None:
    if not rows:
        raise ValueError(f'No rows to write for {path}')
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def is_focus_row(row: dict, focus_roles: Sequence[str]) -> bool:
    mix_label = int(float(row.get('mix', 0) or 0))
    if mix_label == 1:
        return False
    return str(row.get('binary_role', '') or '') in set(focus_roles)


def build_row_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get('singer', '') or ''),
        str(row.get('song_name', '') or ''),
        str(row.get('item_name', '') or ''),
    )


def build_metadata_vector(row: dict, known_groups: Sequence[str], known_languages: Sequence[str]) -> np.ndarray:
    group_name = str(row.get('group_name', '') or '')
    language = str(row.get('language', '') or '')
    group_one_hot = [1.0 if group_name == item else 0.0 for item in known_groups]
    language_one_hot = [1.0 if language == item else 0.0 for item in known_languages]
    technique_flags = [
        float(row.get('falsetto', 0) or 0),
        float(row.get('breathy', 0) or 0),
        float(row.get('vibrato', 0) or 0),
        float(row.get('glissando', 0) or 0),
        float(row.get('pharyngeal', 0) or 0),
        float(row.get('any_tech', 0) or 0),
    ]
    return np.asarray(group_one_hot + language_one_hot + technique_flags, dtype=np.float32)


@torch.no_grad()
def collect_focus_features(
    rows: Sequence[dict],
    *,
    artifact_dir: Path,
    focus_roles: Sequence[str],
) -> tuple[list[dict], np.ndarray, np.ndarray, np.ndarray, dict]:
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model, _, sample_secs, n_mels, eval_window_count, eval_window_aggregation, eval_window_consistency_penalty, eval_window_support_threshold, eval_window_min_support_windows, eval_window_high_support_threshold, eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = compare.load_artifact_model(artifact_dir, device)
    focus_rows = [dict(row) for row in rows if is_focus_row(row, focus_roles)]
    if not focus_rows:
        return [], np.zeros((0, 0), dtype=np.float32), np.zeros((0, 0), dtype=np.float32), np.zeros((0,), dtype=np.float32), {
            'backbone_name': str(artifact_backbone_name),
            'image_size': int(artifact_image_size),
            'sample_rate': int(artifact_sample_rate),
            'sample_secs': float(sample_secs),
            'n_fft': int(artifact_n_fft),
            'hop_length': int(artifact_hop_length),
            'n_mels': int(n_mels),
            'eval_window_count': int(eval_window_count),
            'eval_window_aggregation': str(eval_window_aggregation),
        }

    known_groups = sorted({str(row.get('group_name', '') or '') for row in focus_rows})
    known_languages = sorted({str(row.get('language', '') or '') for row in focus_rows})
    _, eval_transform = trainer.build_transforms(image_size=artifact_image_size, augment_profile='safe')
    dataset = trainer.MixBinaryAudioDataset(
        focus_rows,
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
    loader = DataLoader(dataset, batch_size=24, shuffle=False, num_workers=0)

    embedding_batches: list[np.ndarray] = []
    mix_prob_batches: list[np.ndarray] = []
    total_batches = len(loader)
    for batch_index, (images, _) in enumerate(loader, start=1):
        images = images.to(device)
        mix_logits = trainer.forward_with_window_average(
            model,
            images,
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        if images.ndim == 5:
            batch_size, window_count, channels, height, width = images.shape
            flat_images = images.reshape(batch_size * window_count, channels, height, width)
            flat_embeddings = trainer.extract_model_embeddings(model, flat_images)
            embeddings = flat_embeddings.reshape(batch_size, window_count, -1).mean(dim=1)
        else:
            embeddings = trainer.extract_model_embeddings(model, images)
        embedding_batches.append(embeddings.detach().cpu().numpy().astype(np.float32))
        mix_prob_batches.append(torch.softmax(mix_logits, dim=1)[:, trainer.MIX_LABEL].detach().cpu().numpy().astype(np.float32))
        if batch_index == 1 or batch_index == total_batches or batch_index % 10 == 0:
            print(f'collect_focus_features batch={batch_index}/{total_batches}', flush=True)

    metadata = np.stack([build_metadata_vector(row, known_groups, known_languages) for row in focus_rows], axis=0)
    embeddings = np.concatenate(embedding_batches, axis=0) if embedding_batches else np.zeros((0, trainer.get_model_embedding_dim(model)), dtype=np.float32)
    mix_probs = np.concatenate(mix_prob_batches, axis=0) if mix_prob_batches else np.zeros((0,), dtype=np.float32)
    info = {
        'backbone_name': str(artifact_backbone_name),
        'image_size': int(artifact_image_size),
        'sample_rate': int(artifact_sample_rate),
        'sample_secs': float(sample_secs),
        'n_fft': int(artifact_n_fft),
        'hop_length': int(artifact_hop_length),
        'n_mels': int(n_mels),
        'eval_window_count': int(eval_window_count),
        'eval_window_aggregation': str(eval_window_aggregation),
        'known_groups': known_groups,
        'known_languages': known_languages,
    }
    return focus_rows, embeddings, metadata, mix_probs, info


def build_cluster_inputs(
    embeddings: np.ndarray,
    metadata: np.ndarray,
    mix_probs: np.ndarray,
    *,
    embedding_weight: float,
    metadata_weight: float,
    mix_prob_weight: float,
) -> np.ndarray:
    parts = []
    if embeddings.size:
        parts.append(np.asarray(embeddings, dtype=np.float32) * float(embedding_weight))
    if metadata.size:
        parts.append(np.asarray(metadata, dtype=np.float32) * float(metadata_weight))
    if mix_probs.size:
        parts.append(np.asarray(mix_probs, dtype=np.float32).reshape(-1, 1) * float(mix_prob_weight))
    if not parts:
        return np.zeros((0, 0), dtype=np.float32)
    return np.concatenate(parts, axis=1).astype(np.float32)


def summarize_cluster_rows(rows: Sequence[dict], cluster_count: int) -> dict[str, object]:
    summary: dict[str, object] = {}
    for cluster_index in range(cluster_count):
        cluster_rows = [row for row in rows if int(row.get('confusable_cluster_id', CLUSTER_IGNORE_VALUE) or CLUSTER_IGNORE_VALUE) == cluster_index]
        role_counts = Counter(str(row.get('binary_role', '') or '') for row in cluster_rows)
        group_counts = Counter(str(row.get('group_name', '') or '') for row in cluster_rows)
        mix_probs = [float(row.get('confusable_cluster_mix_prob', 0.0) or 0.0) for row in cluster_rows]
        summary[f'cluster_{cluster_index:02d}'] = {
            'sample_count': int(len(cluster_rows)),
            'binary_roles': {str(key): int(value) for key, value in role_counts.items()},
            'groups': {str(key): int(value) for key, value in group_counts.items()},
            'mix_prob_mean': round(float(np.mean(mix_probs)) if mix_probs else 0.0, 6),
            'mix_prob_min': round(float(np.min(mix_probs)) if mix_probs else 0.0, 6),
            'mix_prob_max': round(float(np.max(mix_probs)) if mix_probs else 0.0, 6),
        }
    return summary


def apply_cluster_annotations(
    rows: Sequence[dict],
    focus_rows: Sequence[dict],
    cluster_ids: np.ndarray,
    distances: np.ndarray,
    mix_probs: np.ndarray,
) -> list[dict]:
    focus_map = {
        build_row_key(row): {
            'cluster_id': int(cluster_id),
            'cluster_label': f'confusable_cluster_{int(cluster_id):02d}',
            'distance': float(distance),
            'mix_prob': float(mix_prob),
        }
        for row, cluster_id, distance, mix_prob in zip(focus_rows, cluster_ids.tolist(), distances.tolist(), mix_probs.tolist())
    }
    annotated: list[dict] = []
    for row in rows:
        item = dict(row)
        payload = focus_map.get(build_row_key(row))
        if payload is None:
            item['confusable_cluster_focus'] = '0'
            item['confusable_cluster_id'] = str(CLUSTER_IGNORE_VALUE)
            item['confusable_cluster_label'] = 'ignore'
            item['confusable_cluster_distance'] = ''
            item['confusable_cluster_mix_prob'] = ''
        else:
            item['confusable_cluster_focus'] = '1'
            item['confusable_cluster_id'] = str(int(payload['cluster_id']))
            item['confusable_cluster_label'] = str(payload['cluster_label'])
            item['confusable_cluster_distance'] = f'{float(payload["distance"]):.6f}'
            item['confusable_cluster_mix_prob'] = f'{float(payload["mix_prob"]):.6f}'
        annotated.append(item)
    return annotated


def write_summary_markdown(path: Path, summary: dict[str, object]) -> None:
    lines: list[str] = []
    lines.append('# Mix Binary Confusable Cluster Summary')
    lines.append('')
    lines.append('## Config')
    lines.append('')
    lines.append(f'- artifact: `{summary["artifact_dir"]}`')
    lines.append(f'- focus_roles: `{", ".join(summary["focus_roles"])} `')
    lines.append(f'- cluster_count: `{summary["cluster_count"]}`')
    lines.append(f'- backbone_name: `{summary["artifact_info"]["backbone_name"]}`')
    lines.append(f'- image_size: `{summary["artifact_info"]["image_size"]}`')
    lines.append(f'- sample_rate: `{summary["artifact_info"]["sample_rate"]}`')
    lines.append(f'- sample_secs: `{summary["artifact_info"]["sample_secs"]}`')
    lines.append(f'- n_fft / hop_length / n_mels: `{summary["artifact_info"]["n_fft"]} / {summary["artifact_info"]["hop_length"]} / {summary["artifact_info"]["n_mels"]}`')
    lines.append('')
    for split_name in ('train', 'validation', 'test'):
        split_summary = summary['splits'][split_name]
        lines.append(f'## {split_name.title()}')
        lines.append('')
        lines.append(f'- focus_sample_count: `{split_summary["focus_sample_count"]}`')
        lines.append(f'- focus_binary_roles: `{json.dumps(split_summary["focus_binary_roles"], ensure_ascii=False)}`')
        lines.append('')
        lines.append('| cluster | count | roles | groups | mix_prob_mean |')
        lines.append('| --- | ---: | --- | --- | ---: |')
        for cluster_name, cluster_info in split_summary['clusters'].items():
            lines.append(
                f'| {cluster_name} | {cluster_info["sample_count"]} | {json.dumps(cluster_info["binary_roles"], ensure_ascii=False)} | {json.dumps(cluster_info["groups"], ensure_ascii=False)} | {cluster_info["mix_prob_mean"]:.6f} |'
            )
        lines.append('')
    path.write_text('\n'.join(lines), encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Cluster semantically confusable non-mix rows and write cluster ids back into manifests.')
    parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\train_manifest.csv')
    parser.add_argument('--validation-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\validation_manifest.csv')
    parser.add_argument('--test-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\test_manifest.csv')
    parser.add_argument('--artifact-dir', default=DEFAULT_ARTIFACT)
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DATASET)
    parser.add_argument('--focus-role', action='append', dest='focus_roles', default=[])
    parser.add_argument('--cluster-count', type=int, default=6)
    parser.add_argument('--pca-dim', type=int, default=32)
    parser.add_argument('--embedding-weight', type=float, default=1.0)
    parser.add_argument('--metadata-weight', type=float, default=0.5)
    parser.add_argument('--mix-prob-weight', type=float, default=0.35)
    parser.add_argument('--seed', type=int, default=trainer.SEED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    focus_roles = tuple(args.focus_roles or DEFAULT_FOCUS_ROLES)
    artifact_dir = Path(args.artifact_dir)
    output_dir = Path(args.output_dir)
    split_paths = {
        'train': Path(args.train_manifest),
        'validation': Path(args.validation_manifest),
        'test': Path(args.test_manifest),
    }
    split_rows = {name: load_rows(path) for name, path in split_paths.items()}

    train_focus_rows, train_embeddings, train_metadata, train_mix_probs, artifact_info = collect_focus_features(
        split_rows['train'],
        artifact_dir=artifact_dir,
        focus_roles=focus_roles,
    )
    if len(train_focus_rows) < 2:
        raise RuntimeError('Not enough focus rows to cluster.')

    train_inputs = build_cluster_inputs(
        train_embeddings,
        train_metadata,
        train_mix_probs,
        embedding_weight=float(args.embedding_weight),
        metadata_weight=float(args.metadata_weight),
        mix_prob_weight=float(args.mix_prob_weight),
    )
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_inputs).astype(np.float32)
    effective_pca_dim = max(0, min(int(args.pca_dim), int(train_scaled.shape[1]), max(0, int(train_scaled.shape[0]) - 1)))
    if effective_pca_dim >= 2 and effective_pca_dim < int(train_scaled.shape[1]):
        pca = PCA(n_components=effective_pca_dim, random_state=int(args.seed))
        train_cluster_inputs = pca.fit_transform(train_scaled).astype(np.float32)
    else:
        pca = None
        train_cluster_inputs = train_scaled
    cluster_count = max(2, min(int(args.cluster_count), int(train_cluster_inputs.shape[0])))
    kmeans = KMeans(n_clusters=cluster_count, n_init=10, random_state=int(args.seed))
    train_cluster_ids = kmeans.fit_predict(train_cluster_inputs)
    train_distances = np.linalg.norm(train_cluster_inputs - kmeans.cluster_centers_[train_cluster_ids], axis=1)

    summary = {
        'artifact_dir': str(artifact_dir),
        'focus_roles': list(focus_roles),
        'cluster_count': int(cluster_count),
        'artifact_info': artifact_info,
        'pca_dim': int(effective_pca_dim),
        'embedding_weight': round(float(args.embedding_weight), 6),
        'metadata_weight': round(float(args.metadata_weight), 6),
        'mix_prob_weight': round(float(args.mix_prob_weight), 6),
        'splits': {},
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    split_cluster_rows: dict[str, list[dict]] = {}
    for split_name in ('train', 'validation', 'test'):
        focus_rows, embeddings, metadata, mix_probs, _ = collect_focus_features(
            split_rows[split_name],
            artifact_dir=artifact_dir,
            focus_roles=focus_roles,
        )
        if split_name == 'train':
            cluster_ids = train_cluster_ids
            distances = train_distances
        elif focus_rows:
            split_inputs = build_cluster_inputs(
                embeddings,
                metadata,
                mix_probs,
                embedding_weight=float(args.embedding_weight),
                metadata_weight=float(args.metadata_weight),
                mix_prob_weight=float(args.mix_prob_weight),
            )
            split_scaled = scaler.transform(split_inputs).astype(np.float32)
            split_cluster_inputs = pca.transform(split_scaled).astype(np.float32) if pca is not None else split_scaled
            cluster_ids = kmeans.predict(split_cluster_inputs)
            distances = np.linalg.norm(split_cluster_inputs - kmeans.cluster_centers_[cluster_ids], axis=1)
        else:
            cluster_ids = np.zeros((0,), dtype=np.int32)
            distances = np.zeros((0,), dtype=np.float32)
        annotated_rows = apply_cluster_annotations(split_rows[split_name], focus_rows, cluster_ids.astype(np.int32), distances.astype(np.float32), mix_probs.astype(np.float32))
        split_cluster_rows[split_name] = annotated_rows
        write_rows(output_dir / f'{split_name}_manifest.csv', annotated_rows)
        focus_role_counts = Counter(str(row.get('binary_role', '') or '') for row in focus_rows)
        summary['splits'][split_name] = {
            'focus_sample_count': int(len(focus_rows)),
            'focus_binary_roles': {str(key): int(value) for key, value in focus_role_counts.items()},
            'clusters': summarize_cluster_rows(annotated_rows, cluster_count),
        }

    (output_dir / 'cluster_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    write_summary_markdown(output_dir / 'cluster_summary.md', summary)
    print(json.dumps({
        'output_dir': str(output_dir),
        'cluster_count': int(cluster_count),
        'focus_roles': list(focus_roles),
        'train_focus_sample_count': int(len(train_focus_rows)),
        'artifact_backbone_name': str(artifact_info['backbone_name']),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()