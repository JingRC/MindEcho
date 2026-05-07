import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix, f1_score
from torch import nn
from torch.utils.data import DataLoader

import train_mix_binary_squeezenet as base


AUX_IGNORE_INDEX = -100


def parse_aux_target(raw_value: object, ignore_index: int) -> int:
    text = str(raw_value or '').strip()
    if not text:
        return int(ignore_index)
    try:
        return int(float(text))
    except Exception:
        return int(ignore_index)


def build_aux_mapping(rows: Sequence[dict], aux_target_column: str, ignore_index: int) -> dict[int, int]:
    values = sorted({
        parse_aux_target(row.get(aux_target_column, ignore_index), ignore_index)
        for row in rows
        if parse_aux_target(row.get(aux_target_column, ignore_index), ignore_index) != int(ignore_index)
    })
    return {value: index for index, value in enumerate(values)}


def build_aux_label_lookup(rows: Sequence[dict], aux_target_column: str, aux_label_column: str, ignore_index: int, mapping: dict[int, int]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for row in rows:
        raw_value = parse_aux_target(row.get(aux_target_column, ignore_index), ignore_index)
        if raw_value == int(ignore_index) or raw_value not in mapping:
            continue
        mapped_value = int(mapping[raw_value])
        label = str(row.get(aux_label_column, '') or f'aux_class_{mapped_value:02d}')
        labels.setdefault(mapped_value, label)
    return labels


def attach_aux_targets(rows: Sequence[dict], aux_target_column: str, ignore_index: int, mapping: dict[int, int]) -> list[dict]:
    prepared: list[dict] = []
    for row in rows:
        item = dict(row)
        raw_value = parse_aux_target(row.get(aux_target_column, ignore_index), ignore_index)
        item['_aux_target'] = int(mapping.get(raw_value, int(ignore_index))) if raw_value != int(ignore_index) else int(ignore_index)
        prepared.append(item)
    return prepared


def summarize_aux_targets(rows: Sequence[dict]) -> Dict[str, int]:
    counts = Counter(int(row.get('_aux_target', AUX_IGNORE_INDEX)) for row in rows)
    return {str(key): int(value) for key, value in sorted(counts.items(), key=lambda item: int(item[0]))}


class ClusterAwareMixBinaryAudioDataset(base.MixBinaryAudioDataset):
    def __getitem__(self, index: int):
        row = self.rows[index]
        if (not self.train) and len(self.eval_anchor_ratios) > 1:
            image = torch.stack([self._load_image(row, anchor_ratio=item) for item in self.eval_anchor_ratios], dim=0)
        else:
            anchor_ratio = None if self.train else self.eval_anchor_ratios[0]
            image = self._load_image(row, anchor_ratio=anchor_ratio)
        label = base.MIX_LABEL if int(float(row.get('mix', 0) or 0)) == 1 else base.NON_MIX_LABEL
        aux_target = int(row.get('_aux_target', AUX_IGNORE_INDEX))
        if self.train and self.loss_weight_mode != 'none':
            if self.loss_weight_mode == 'technique_focus':
                loss_weight = base.compute_row_focus_multiplier(row, **self.loss_weight_config)
            else:
                raise ValueError(f'Unsupported loss_weight_mode: {self.loss_weight_mode}')
            return image, label, aux_target, float(loss_weight)
        return image, label, aux_target


@dataclass
class TrainConfig(base.TrainConfig):
    aux_target_column: str = 'confusable_cluster_id'
    aux_label_column: str = 'confusable_cluster_label'
    aux_ignore_index: int = AUX_IGNORE_INDEX
    aux_loss_weight: float = 0.35
    aux_class_weight_mode: str = 'inverse_freq'
    aux_hidden_dim: int = 256


class ClusterAwareMixModel(nn.Module):
    def __init__(self, *, backbone_name: str, aux_num_classes: int, aux_hidden_dim: int) -> None:
        super().__init__()
        self.backbone = base.build_model(backbone_name=backbone_name)
        embedding_dim = int(base.get_model_embedding_dim(self.backbone))
        hidden_dim = max(32, min(int(aux_hidden_dim), embedding_dim)) if int(aux_hidden_dim) > 0 else min(embedding_dim, 256)
        self.aux_head = nn.Sequential(
            nn.Dropout(p=0.35),
            nn.Linear(embedding_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.20),
            nn.Linear(hidden_dim, int(aux_num_classes)),
        )

    def forward(self, images: torch.Tensor, *, return_aux: bool = False):
        mix_logits = self.backbone(images)
        if not return_aux:
            return mix_logits
        embeddings = base.extract_model_embeddings(self.backbone, images)
        aux_logits = self.aux_head(embeddings)
        return mix_logits, aux_logits

    def export_mix_state_dict(self) -> Dict[str, torch.Tensor]:
        return self.backbone.state_dict()


def clone_state_dict(state_dict: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    return {key: value.detach().cpu().clone() for key, value in state_dict.items()}


def build_aux_class_weights(rows: Sequence[dict], mode: str, ignore_index: int) -> torch.Tensor | None:
    if mode == 'none':
        return None
    counts = Counter(int(row.get('_aux_target', ignore_index)) for row in rows if int(row.get('_aux_target', ignore_index)) != int(ignore_index))
    if not counts:
        return None
    total = max(1, sum(counts.values()))
    class_count = max(counts.keys()) + 1
    weights = np.ones((class_count,), dtype=np.float32)
    if mode == 'inverse_freq':
        for class_index in range(class_count):
            count = max(1, int(counts.get(class_index, 0)))
            weights[class_index] = float(total) / float(class_count * count)
    elif mode == 'inverse_sqrt':
        for class_index in range(class_count):
            count = max(1, int(counts.get(class_index, 0)))
            weights[class_index] = float(np.sqrt(float(total) / float(class_count * count)))
    else:
        raise ValueError(f'Unsupported aux_class_weight_mode: {mode}')
    return torch.tensor(weights, dtype=torch.float32)


def summarize_aux_metrics(targets: Sequence[int], preds: Sequence[int]) -> Dict[str, float]:
    if not targets:
        return {
            'acc': 0.0,
            'balanced_acc': 0.0,
            'macro_f1': 0.0,
            'sample_count': 0.0,
        }
    targets_np = np.asarray(list(targets), dtype=np.int32)
    preds_np = np.asarray(list(preds), dtype=np.int32)
    return {
        'acc': float(accuracy_score(targets_np, preds_np)),
        'balanced_acc': float(balanced_accuracy_score(targets_np, preds_np)),
        'macro_f1': float(f1_score(targets_np, preds_np, average='macro', zero_division=0)),
        'sample_count': float(targets_np.size),
    }


def forward_clusteraware_with_window_average(
    model: ClusterAwareMixModel,
    images: torch.Tensor,
    *,
    aggregation: str = 'mean',
    consistency_penalty: float = 0.0,
    support_threshold: float = 0.40,
    min_support_windows: int = 2,
    high_support_threshold: float = 0.55,
    min_high_support_windows: int = 1,
) -> tuple[torch.Tensor, torch.Tensor]:
    if images.ndim == 4:
        return model(images, return_aux=True)
    if images.ndim != 5:
        raise ValueError(f'Expected image batch rank 4 or 5, got shape={tuple(images.shape)}')
    batch_size, window_count, channels, height, width = images.shape
    flat_images = images.reshape(batch_size * window_count, channels, height, width)
    mix_logits, aux_logits = model(flat_images, return_aux=True)
    mix_aggregated = base.aggregate_window_logits(
        mix_logits.reshape(batch_size, window_count, -1),
        aggregation=aggregation,
        consistency_penalty=consistency_penalty,
        support_threshold=support_threshold,
        min_support_windows=min_support_windows,
        high_support_threshold=high_support_threshold,
        min_high_support_windows=min_high_support_windows,
    )
    aux_aggregated = aux_logits.reshape(batch_size, window_count, -1).mean(dim=1)
    return mix_aggregated, aux_aggregated


def set_feature_trainable(model: ClusterAwareMixModel, trainable: bool) -> None:
    for param in model.backbone.features.parameters():
        param.requires_grad = trainable


def build_dataloaders(cfg: TrainConfig):
    raw_train_rows = base.load_manifest(cfg.train_manifest)
    raw_valid_rows = base.load_manifest(cfg.validation_manifest)
    raw_test_rows = base.load_manifest(cfg.test_manifest)
    aux_mapping = build_aux_mapping(raw_train_rows, cfg.aux_target_column, cfg.aux_ignore_index)
    if not aux_mapping:
        raise RuntimeError(f'No valid auxiliary targets found in column: {cfg.aux_target_column}')
    aux_label_lookup = build_aux_label_lookup(raw_train_rows + raw_valid_rows + raw_test_rows, cfg.aux_target_column, cfg.aux_label_column, cfg.aux_ignore_index, aux_mapping)
    train_rows = attach_aux_targets(raw_train_rows, cfg.aux_target_column, cfg.aux_ignore_index, aux_mapping)
    valid_rows = attach_aux_targets(raw_valid_rows, cfg.aux_target_column, cfg.aux_ignore_index, aux_mapping)
    test_rows = attach_aux_targets(raw_test_rows, cfg.aux_target_column, cfg.aux_ignore_index, aux_mapping)
    eval_anchor_ratios = base.build_eval_anchor_ratios(cfg.eval_window_count)
    train_tf, eval_tf = base.build_transforms(cfg.image_size, cfg.augment_profile)
    train_ds = ClusterAwareMixBinaryAudioDataset(
        train_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=train_tf,
        train=True,
        loss_weight_mode=cfg.loss_weight_mode,
        loss_weight_config={
            'head_mix_boost': cfg.head_mix_loss_boost,
            'breathy_mix_boost': cfg.breathy_mix_loss_boost,
            'control_negative_boost': cfg.control_negative_loss_boost,
            'falsetto_negative_boost': cfg.falsetto_negative_loss_boost,
            'breathy_negative_boost': cfg.breathy_negative_loss_boost,
            'other_negative_boost': cfg.other_negative_loss_boost,
        },
    )
    valid_ds = ClusterAwareMixBinaryAudioDataset(
        valid_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=eval_tf,
        train=False,
        eval_anchor_ratios=eval_anchor_ratios,
    )
    test_ds = ClusterAwareMixBinaryAudioDataset(
        test_rows,
        sample_rate=cfg.sample_rate,
        sample_secs=cfg.sample_secs,
        image_size=cfg.image_size,
        n_fft=cfg.n_fft,
        hop_length=cfg.hop_length,
        n_mels=cfg.n_mels,
        transform=eval_tf,
        train=False,
        eval_anchor_ratios=eval_anchor_ratios,
    )
    sampler = base.build_weighted_sampler(train_rows, cfg) if cfg.weighted_sampler else None
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=sampler is None, sampler=sampler, num_workers=cfg.num_workers)
    valid_loader = DataLoader(valid_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    test_loader = DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    split_summary = {
        'train': base.summarize_rows(train_rows),
        'validation': base.summarize_rows(valid_rows),
        'test': base.summarize_rows(test_rows),
    }
    aux_target_summary = {
        'train': summarize_aux_targets(train_rows),
        'validation': summarize_aux_targets(valid_rows),
        'test': summarize_aux_targets(test_rows),
    }
    return train_loader, valid_loader, test_loader, split_summary, aux_target_summary, aux_mapping, aux_label_lookup, train_rows, valid_rows, test_rows


def train_one_epoch(
    model: ClusterAwareMixModel,
    loader,
    optimizer,
    mix_criterion,
    aux_criterion,
    device,
    *,
    aux_loss_weight: float,
    aux_ignore_index: int,
    eval_window_aggregation: str = 'mean',
    eval_window_consistency_penalty: float = 0.0,
    eval_window_support_threshold: float = 0.40,
    eval_window_min_support_windows: int = 2,
    eval_window_high_support_threshold: float = 0.55,
    eval_window_min_high_support_windows: int = 1,
) -> Dict[str, float]:
    model.train()
    total_loss = 0.0
    total_mix_loss = 0.0
    total_aux_loss = 0.0
    total_aux_items = 0
    mix_preds: List[int] = []
    mix_targets: List[int] = []
    aux_preds: List[int] = []
    aux_targets: List[int] = []
    for batch in loader:
        if len(batch) == 4:
            images, labels, batch_aux_targets, loss_weights = batch
            loss_weights = loss_weights.to(device=device, dtype=torch.float32)
        else:
            images, labels, batch_aux_targets = batch
            loss_weights = None
        images = images.to(device)
        labels = labels.to(device)
        batch_aux_targets = batch_aux_targets.to(device=device, dtype=torch.int64)
        optimizer.zero_grad(set_to_none=True)
        mix_logits, aux_logits = forward_clusteraware_with_window_average(
            model,
            images,
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        mix_loss_values = mix_criterion(mix_logits, labels)
        if getattr(mix_loss_values, 'ndim', 0) == 0:
            mix_loss = mix_loss_values
        else:
            if loss_weights is not None:
                mix_loss_values = mix_loss_values * loss_weights
            mix_loss = mix_loss_values.mean()
        aux_mask = batch_aux_targets != int(aux_ignore_index)
        if bool(aux_mask.any().item()):
            aux_loss_values = aux_criterion(aux_logits[aux_mask], batch_aux_targets[aux_mask])
            aux_loss = aux_loss_values if getattr(aux_loss_values, 'ndim', 0) == 0 else aux_loss_values.mean()
            aux_batch_preds = aux_logits[aux_mask].argmax(dim=1)
            aux_preds.extend(aux_batch_preds.detach().cpu().tolist())
            aux_targets.extend(batch_aux_targets[aux_mask].detach().cpu().tolist())
            observed_count = int(aux_mask.sum().item())
            total_aux_loss += float(aux_loss.item()) * observed_count
            total_aux_items += observed_count
            loss = mix_loss + float(aux_loss_weight) * aux_loss
        else:
            loss = mix_loss
        loss.backward()
        optimizer.step()
        batch_size = int(labels.size(0))
        total_loss += float(loss.item()) * batch_size
        total_mix_loss += float(mix_loss.item()) * batch_size
        mix_batch_preds = mix_logits.argmax(dim=1)
        mix_preds.extend(mix_batch_preds.detach().cpu().tolist())
        mix_targets.extend(labels.detach().cpu().tolist())
    aux_metrics = summarize_aux_metrics(aux_targets, aux_preds)
    return {
        'loss': total_loss / max(1, len(loader.dataset)),
        'mix_loss': total_mix_loss / max(1, len(loader.dataset)),
        'aux_loss': total_aux_loss / max(1, total_aux_items),
        'mix_acc': float(accuracy_score(mix_targets, mix_preds)) if mix_targets else 0.0,
        'aux_acc': float(aux_metrics['acc']),
        'aux_balanced_acc': float(aux_metrics['balanced_acc']),
        'aux_macro_f1': float(aux_metrics['macro_f1']),
    }


@torch.no_grad()
def evaluate(
    model: ClusterAwareMixModel,
    loader,
    mix_criterion,
    aux_criterion,
    device,
    threshold: float = 0.5,
    *,
    aux_loss_weight: float,
    aux_ignore_index: int,
    eval_window_aggregation: str = 'mean',
    eval_window_consistency_penalty: float = 0.0,
    eval_window_support_threshold: float = 0.40,
    eval_window_min_support_windows: int = 2,
    eval_window_high_support_threshold: float = 0.55,
    eval_window_min_high_support_windows: int = 1,
):
    model.eval()
    total_loss = 0.0
    total_mix_loss = 0.0
    total_aux_loss = 0.0
    total_aux_items = 0
    mix_targets: List[int] = []
    mix_preds: List[int] = []
    all_probs: List[List[float]] = []
    aux_targets: List[int] = []
    aux_preds: List[int] = []
    for images, labels, batch_aux_targets in loader:
        images = images.to(device)
        labels = labels.to(device)
        batch_aux_targets = batch_aux_targets.to(device=device, dtype=torch.int64)
        mix_logits, aux_logits = forward_clusteraware_with_window_average(
            model,
            images,
            aggregation=eval_window_aggregation,
            consistency_penalty=eval_window_consistency_penalty,
            support_threshold=eval_window_support_threshold,
            min_support_windows=eval_window_min_support_windows,
            high_support_threshold=eval_window_high_support_threshold,
            min_high_support_windows=eval_window_min_high_support_windows,
        )
        mix_loss = mix_criterion(mix_logits, labels)
        aux_mask = batch_aux_targets != int(aux_ignore_index)
        if bool(aux_mask.any().item()):
            aux_loss = aux_criterion(aux_logits[aux_mask], batch_aux_targets[aux_mask])
            aux_batch_preds = aux_logits[aux_mask].argmax(dim=1)
            aux_preds.extend(aux_batch_preds.detach().cpu().tolist())
            aux_targets.extend(batch_aux_targets[aux_mask].detach().cpu().tolist())
            observed_count = int(aux_mask.sum().item())
            total_aux_loss += float(aux_loss.item()) * observed_count
            total_aux_items += observed_count
            combined_loss = mix_loss + float(aux_loss_weight) * aux_loss
        else:
            combined_loss = mix_loss
        probs = torch.softmax(mix_logits, dim=1)
        total_loss += float(combined_loss.item()) * int(labels.size(0))
        total_mix_loss += float(mix_loss.item()) * int(labels.size(0))
        preds = (probs[:, base.MIX_LABEL] >= float(threshold)).to(dtype=torch.int64)
        mix_targets.extend(labels.detach().cpu().tolist())
        mix_preds.extend(preds.detach().cpu().tolist())
        all_probs.extend(probs.detach().cpu().tolist())
    aux_metrics = summarize_aux_metrics(aux_targets, aux_preds)
    return (
        total_loss / max(1, len(loader.dataset)),
        total_mix_loss / max(1, len(loader.dataset)),
        total_aux_loss / max(1, total_aux_items),
        float(accuracy_score(mix_targets, mix_preds)) if mix_targets else 0.0,
        mix_targets,
        mix_preds,
        all_probs,
        aux_metrics,
    )


def run_training(cfg: TrainConfig) -> Path:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    base.set_seed(cfg.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    train_loader, valid_loader, test_loader, split_summary, aux_target_summary, aux_mapping, aux_label_lookup, train_rows, valid_rows, test_rows = build_dataloaders(cfg)
    aux_num_classes = max(1, len(aux_mapping))
    model = ClusterAwareMixModel(backbone_name=cfg.backbone_name, aux_num_classes=aux_num_classes, aux_hidden_dim=cfg.aux_hidden_dim).to(device)
    mix_class_weights = base.build_class_weights(train_rows, cfg.class_weight_mode)
    aux_class_weights = build_aux_class_weights(train_rows, cfg.aux_class_weight_mode, cfg.aux_ignore_index)
    train_mix_criterion = nn.CrossEntropyLoss(weight=mix_class_weights.to(device) if mix_class_weights is not None else None, label_smoothing=cfg.label_smoothing, reduction='none')
    eval_mix_criterion = nn.CrossEntropyLoss(weight=mix_class_weights.to(device) if mix_class_weights is not None else None, label_smoothing=cfg.label_smoothing)
    train_aux_criterion = nn.CrossEntropyLoss(weight=aux_class_weights.to(device) if aux_class_weights is not None else None, reduction='none')
    eval_aux_criterion = nn.CrossEntropyLoss(weight=aux_class_weights.to(device) if aux_class_weights is not None else None)

    history: List[Dict[str, float]] = []
    best_state = None
    best_val_score = -1.0
    best_epoch = -1
    best_threshold = 0.5
    best_path = cfg.output_dir / 'best_mix_binary_squeezenet.pt'
    stage_schedule = [
        ('head', cfg.head_epochs, cfg.head_lr, False),
        ('finetune', cfg.finetune_epochs, cfg.finetune_lr, True),
    ]
    start_time = time.time()
    epoch_cursor = 0
    for stage_name, epochs, lr, feature_trainable in stage_schedule:
        if epochs <= 0:
            continue
        set_feature_trainable(model, feature_trainable)
        params = [param for param in model.parameters() if param.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=cfg.weight_decay)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
        for _ in range(epochs):
            epoch_cursor += 1
            train_stats = train_one_epoch(
                model,
                train_loader,
                optimizer,
                train_mix_criterion,
                train_aux_criterion,
                device,
                aux_loss_weight=cfg.aux_loss_weight,
                aux_ignore_index=cfg.aux_ignore_index,
                eval_window_aggregation=cfg.eval_window_aggregation,
                eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
                eval_window_support_threshold=cfg.eval_window_support_threshold,
                eval_window_min_support_windows=cfg.eval_window_min_support_windows,
                eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
                eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
            )
            val_loss_raw, val_mix_loss, val_aux_loss, _, val_targets, _, val_probs, val_aux_metrics = evaluate(
                model,
                valid_loader,
                eval_mix_criterion,
                eval_aux_criterion,
                device,
                threshold=0.5,
                aux_loss_weight=cfg.aux_loss_weight,
                aux_ignore_index=cfg.aux_ignore_index,
                eval_window_aggregation=cfg.eval_window_aggregation,
                eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
                eval_window_support_threshold=cfg.eval_window_support_threshold,
                eval_window_min_support_windows=cfg.eval_window_min_support_windows,
                eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
                eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
            )
            val_mix_probs = [float(item[base.MIX_LABEL]) for item in val_probs]
            val_threshold, val_metrics, val_group_rates, val_role_rates, val_constraints_ok = base.find_best_threshold(val_targets, val_mix_probs, cfg, rows=valid_rows)
            val_selection_score = base.compute_selection_score(val_metrics, val_role_rates, cfg)
            row = {
                'epoch': epoch_cursor,
                'stage': stage_name,
                'train_loss': round(float(train_stats['loss']), 6),
                'train_mix_loss': round(float(train_stats['mix_loss']), 6),
                'train_aux_loss': round(float(train_stats['aux_loss']), 6),
                'train_acc': round(float(train_stats['mix_acc']), 6),
                'train_aux_acc': round(float(train_stats['aux_acc']), 6),
                'train_aux_balanced_acc': round(float(train_stats['aux_balanced_acc']), 6),
                'train_aux_macro_f1': round(float(train_stats['aux_macro_f1']), 6),
                'val_loss': round(float(val_loss_raw), 6),
                'val_mix_loss': round(float(val_mix_loss), 6),
                'val_aux_loss': round(float(val_aux_loss), 6),
                'val_acc': round(float(val_metrics['acc']), 6),
                'val_balanced_acc': round(float(val_metrics['balanced_acc']), 6),
                'val_macro_f1': round(float(val_metrics['macro_f1']), 6),
                'val_mix_f1': round(float(val_metrics['mix_f1']), 6),
                'val_mix_precision': round(float(val_metrics['mix_precision']), 6),
                'val_mix_recall': round(float(val_metrics['mix_recall']), 6),
                'val_mixed_group_positive_rate': round(float(val_group_rates.get('Mixed_Voice_Group', 0.0)), 6),
                'val_control_group_positive_rate': round(float(val_group_rates.get('Control_Group', 0.0)), 6),
                'val_breathy_group_positive_rate': round(float(val_group_rates.get('Breathy_Group', 0.0)), 6),
                'val_falsetto_group_positive_rate': round(float(val_group_rates.get('Falsetto_Group', 0.0)), 6),
                'val_positive_mix_rate': round(float(val_role_rates.get('positive_mix', 0.0)), 6),
                'val_control_negative_rate': round(float(val_role_rates.get('control_negative', 0.0)), 6),
                'val_breathy_negative_rate': round(float(val_role_rates.get('breathy_group', 0.0)), 6),
                'val_falsetto_negative_rate': round(float(val_role_rates.get('falsetto_group', 0.0)), 6),
                'val_aux_acc': round(float(val_aux_metrics['acc']), 6),
                'val_aux_balanced_acc': round(float(val_aux_metrics['balanced_acc']), 6),
                'val_aux_macro_f1': round(float(val_aux_metrics['macro_f1']), 6),
                'val_selection_score': round(float(val_selection_score), 6),
                'val_threshold_constraints_ok': bool(val_constraints_ok),
                'val_threshold': round(float(val_threshold), 4),
                'lr': round(float(optimizer.param_groups[0]['lr']), 8),
            }
            history.append(row)
            base.write_history_csv(cfg.output_dir / 'history.csv', history)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            current_score = float(val_selection_score)
            if current_score > best_val_score:
                best_val_score = current_score
                best_epoch = epoch_cursor
                best_threshold = float(val_threshold)
                best_state = {
                    'model_state_dict': clone_state_dict(model.export_mix_state_dict()),
                    'clusteraware_model_state_dict': clone_state_dict(model.state_dict()),
                    'val_score': current_score,
                    'val_metrics': val_metrics,
                    'val_group_rates': val_group_rates,
                    'val_role_rates': val_role_rates,
                    'val_aux_metrics': val_aux_metrics,
                    'val_selection_score': val_selection_score,
                    'val_threshold_constraints_ok': bool(val_constraints_ok),
                    'threshold': best_threshold,
                    'epoch': epoch_cursor,
                    'stage': stage_name,
                    'class_to_idx': {'non_mix': base.NON_MIX_LABEL, 'mix': base.MIX_LABEL},
                    'aux_class_to_idx': {str(key): int(value) for key, value in aux_mapping.items()},
                    'config': cfg.__dict__,
                }
                torch.save(best_state, best_path)
            scheduler.step()

    if best_state is None:
        raise RuntimeError('Training did not produce a valid checkpoint.')

    model.load_state_dict(best_state['clusteraware_model_state_dict'])
    test_loss, test_mix_loss, test_aux_loss, test_acc, test_targets, test_preds, test_probs, test_aux_metrics = evaluate(
        model,
        test_loader,
        eval_mix_criterion,
        eval_aux_criterion,
        device,
        threshold=best_threshold,
        aux_loss_weight=cfg.aux_loss_weight,
        aux_ignore_index=cfg.aux_ignore_index,
        eval_window_aggregation=cfg.eval_window_aggregation,
        eval_window_consistency_penalty=cfg.eval_window_consistency_penalty,
        eval_window_support_threshold=cfg.eval_window_support_threshold,
        eval_window_min_support_windows=cfg.eval_window_min_support_windows,
        eval_window_high_support_threshold=cfg.eval_window_high_support_threshold,
        eval_window_min_high_support_windows=cfg.eval_window_min_high_support_windows,
    )
    duration_sec = time.time() - start_time
    test_metrics = base.compute_binary_metrics(test_targets, test_preds)
    test_group_rates = base.summarize_group_positive_rates(test_rows, test_preds)
    test_role_rates = base.summarize_binary_role_positive_rates(test_rows, test_preds)
    report = classification_report(test_targets, test_preds, target_names=['non_mix', 'mix'], output_dict=True, zero_division=0)
    mix_probs = [float(item[base.MIX_LABEL]) for item in test_probs]
    summary = {
        'device': str(device),
        'task': 'mix_binary_clusteraware_multitask',
        'backbone_name': str(cfg.backbone_name),
        'augment_profile': cfg.augment_profile,
        'image_size': int(cfg.image_size),
        'sample_rate': int(cfg.sample_rate),
        'sample_secs': cfg.sample_secs,
        'eval_window_count': int(cfg.eval_window_count),
        'eval_window_aggregation': str(cfg.eval_window_aggregation),
        'eval_window_consistency_penalty': round(float(cfg.eval_window_consistency_penalty), 6),
        'eval_window_support_threshold': round(float(cfg.eval_window_support_threshold), 6),
        'eval_window_min_support_windows': int(cfg.eval_window_min_support_windows),
        'eval_window_high_support_threshold': round(float(cfg.eval_window_high_support_threshold), 6),
        'eval_window_min_high_support_windows': int(cfg.eval_window_min_high_support_windows),
        'n_fft': int(cfg.n_fft),
        'hop_length': int(cfg.hop_length),
        'n_mels': cfg.n_mels,
        'best_epoch': best_epoch,
        'class_weight_mode': cfg.class_weight_mode,
        'aux_class_weight_mode': cfg.aux_class_weight_mode,
        'aux_loss_weight': round(float(cfg.aux_loss_weight), 6),
        'aux_target_column': str(cfg.aux_target_column),
        'aux_label_column': str(cfg.aux_label_column),
        'aux_ignore_index': int(cfg.aux_ignore_index),
        'aux_hidden_dim': int(cfg.aux_hidden_dim),
        'aux_mapping': {str(key): int(value) for key, value in aux_mapping.items()},
        'aux_label_lookup': {str(key): str(value) for key, value in aux_label_lookup.items()},
        'weighted_sampler': bool(cfg.weighted_sampler),
        'sample_weight_mode': cfg.sample_weight_mode,
        'loss_weight_mode': cfg.loss_weight_mode,
        'selection_metric': cfg.selection_metric,
        'best_threshold': round(float(best_threshold), 6),
        'best_val_score': round(float(best_val_score), 6),
        'best_val_selection_score': round(float(best_state.get('val_selection_score', best_val_score)), 6),
        'best_val_metrics': {key: round(float(value), 6) for key, value in best_state.get('val_metrics', {}).items()},
        'best_val_group_rates': {key: round(float(value), 6) for key, value in best_state.get('val_group_rates', {}).items()},
        'best_val_binary_role_rates': {key: round(float(value), 6) for key, value in best_state.get('val_role_rates', {}).items()},
        'best_val_aux_metrics': {key: round(float(value), 6) for key, value in best_state.get('val_aux_metrics', {}).items()},
        'best_val_threshold_constraints_ok': bool(best_state.get('val_threshold_constraints_ok', True)),
        'validation_threshold_constraints': {
            'min_positive_mix_rate': round(float(cfg.min_positive_mix_rate), 6),
            'max_control_negative_rate': round(float(cfg.max_control_negative_rate), 6),
            'max_breathy_negative_rate': round(float(cfg.max_breathy_negative_rate), 6),
            'max_falsetto_negative_rate': round(float(cfg.max_falsetto_negative_rate), 6),
        },
        'best_val_acc': round(float(best_state.get('val_metrics', {}).get('acc', 0.0)), 6),
        'test_acc': round(float(test_acc), 6),
        'test_loss': round(float(test_loss), 6),
        'test_mix_loss': round(float(test_mix_loss), 6),
        'test_aux_loss': round(float(test_aux_loss), 6),
        'test_metrics': {key: round(float(value), 6) for key, value in test_metrics.items()},
        'test_group_rates': {key: round(float(value), 6) for key, value in test_group_rates.items()},
        'test_binary_role_rates': {key: round(float(value), 6) for key, value in test_role_rates.items()},
        'test_aux_metrics': {key: round(float(value), 6) for key, value in test_aux_metrics.items()},
        'duration_sec': round(float(duration_sec), 3),
        'split_summary': split_summary,
        'aux_target_summary': aux_target_summary,
        'confusion_matrix': confusion_matrix(test_targets, test_preds).tolist(),
        'classification_report': report,
        'test_mix_probability': {
            'mean': round(float(np.mean(mix_probs)) if mix_probs else 0.0, 6),
            'min': round(float(np.min(mix_probs)) if mix_probs else 0.0, 6),
            'max': round(float(np.max(mix_probs)) if mix_probs else 0.0, 6),
        },
        'history': history,
        'checkpoint': str(best_path),
    }
    (cfg.output_dir / 'training_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (cfg.output_dir / 'label_map.json').write_text(json.dumps({'labels': ['non_mix', 'mix']}, ensure_ascii=False, indent=2), encoding='utf-8')
    if history:
        base.write_history_csv(cfg.output_dir / 'history.csv', history)
    print(json.dumps({
        'best_val_score': summary['best_val_score'],
        'best_threshold': summary['best_threshold'],
        'test_acc': summary['test_acc'],
        'test_metrics': summary['test_metrics'],
        'test_binary_role_rates': summary['test_binary_role_rates'],
        'test_aux_metrics': summary['test_aux_metrics'],
        'checkpoint': summary['checkpoint'],
        'duration_sec': summary['duration_sec'],
    }, ensure_ascii=False, indent=2), flush=True)
    return best_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Train a cluster-aware multi-head mix model using manifest-provided auxiliary cluster ids.')
    parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\train_manifest.csv')
    parser.add_argument('--validation-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\validation_manifest.csv')
    parser.add_argument('--test-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\test_manifest.csv')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_clusteraware_v1_gpu')
    parser.add_argument('--backbone-name', choices=list(base.SUPPORTED_BACKBONES), default='squeezenet11')
    parser.add_argument('--augment-profile', choices=['safe', 'aggressive'], default='safe')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--head-epochs', type=int, default=6)
    parser.add_argument('--finetune-epochs', type=int, default=8)
    parser.add_argument('--head-lr', type=float, default=1e-3)
    parser.add_argument('--finetune-lr', type=float, default=2e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-4)
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--sample-rate', type=int, default=22050)
    parser.add_argument('--sample-secs', type=float, default=2.4)
    parser.add_argument('--eval-window-count', type=int, default=1)
    parser.add_argument('--eval-window-aggregation', choices=list(base.EVAL_WINDOW_AGGREGATIONS), default='mean')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=0.0)
    parser.add_argument('--eval-window-support-threshold', type=float, default=0.40)
    parser.add_argument('--eval-window-min-support-windows', type=int, default=2)
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=0.55)
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=1)
    parser.add_argument('--n-fft', type=int, default=1024)
    parser.add_argument('--hop-length', type=int, default=256)
    parser.add_argument('--n-mels', type=int, default=128)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--seed', type=int, default=base.SEED)
    parser.add_argument('--label-smoothing', type=float, default=0.03)
    parser.add_argument('--class-weight-mode', choices=['none', 'inverse_freq', 'inverse_sqrt'], default='none')
    parser.add_argument('--aux-class-weight-mode', choices=['none', 'inverse_freq', 'inverse_sqrt'], default='inverse_freq')
    parser.add_argument('--aux-loss-weight', type=float, default=0.35)
    parser.add_argument('--aux-hidden-dim', type=int, default=256)
    parser.add_argument('--aux-target-column', default='confusable_cluster_id')
    parser.add_argument('--aux-label-column', default='confusable_cluster_label')
    parser.add_argument('--aux-ignore-index', type=int, default=AUX_IGNORE_INDEX)
    parser.add_argument('--weighted-sampler', action='store_true', default=False)
    parser.add_argument('--no-weighted-sampler', dest='weighted_sampler', action='store_false')
    parser.add_argument('--sample-weight-mode', choices=['class_balanced', 'technique_focus'], default='class_balanced')
    parser.add_argument('--head-mix-boost', type=float, default=1.0)
    parser.add_argument('--breathy-mix-boost', type=float, default=1.0)
    parser.add_argument('--control-negative-boost', type=float, default=1.0)
    parser.add_argument('--falsetto-negative-boost', type=float, default=1.0)
    parser.add_argument('--breathy-negative-boost', type=float, default=1.0)
    parser.add_argument('--other-negative-boost', type=float, default=1.0)
    parser.add_argument('--loss-weight-mode', choices=['none', 'technique_focus'], default='none')
    parser.add_argument('--head-mix-loss-boost', type=float, default=1.0)
    parser.add_argument('--breathy-mix-loss-boost', type=float, default=1.0)
    parser.add_argument('--control-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--falsetto-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--breathy-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--other-negative-loss-boost', type=float, default=1.0)
    parser.add_argument('--selection-metric', choices=['acc', 'balanced_acc', 'macro_f1', 'mix_f1', 'mix_precision', 'mix_recall', 'product_proxy'], default='balanced_acc')
    parser.add_argument('--threshold-min', type=float, default=0.25)
    parser.add_argument('--threshold-max', type=float, default=0.70)
    parser.add_argument('--threshold-step', type=float, default=0.025)
    parser.add_argument('--min-positive-mix-rate', type=float, default=0.0)
    parser.add_argument('--max-control-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-breathy-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-falsetto-negative-rate', type=float, default=1.0)
    parser.add_argument('--product-proxy-positive-weight', type=float, default=0.35)
    parser.add_argument('--product-proxy-control-penalty', type=float, default=0.30)
    parser.add_argument('--product-proxy-breathy-penalty', type=float, default=0.20)
    parser.add_argument('--product-proxy-falsetto-penalty', type=float, default=0.15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = TrainConfig(
        train_manifest=Path(args.train_manifest),
        validation_manifest=Path(args.validation_manifest),
        test_manifest=Path(args.test_manifest),
        output_dir=Path(args.output_dir),
        backbone_name=args.backbone_name,
        augment_profile=args.augment_profile,
        batch_size=args.batch_size,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        head_lr=args.head_lr,
        finetune_lr=args.finetune_lr,
        weight_decay=args.weight_decay,
        image_size=args.image_size,
        sample_rate=args.sample_rate,
        sample_secs=args.sample_secs,
        eval_window_count=args.eval_window_count,
        eval_window_aggregation=args.eval_window_aggregation,
        eval_window_consistency_penalty=args.eval_window_consistency_penalty,
        eval_window_support_threshold=args.eval_window_support_threshold,
        eval_window_min_support_windows=args.eval_window_min_support_windows,
        eval_window_high_support_threshold=args.eval_window_high_support_threshold,
        eval_window_min_high_support_windows=args.eval_window_min_high_support_windows,
        n_fft=args.n_fft,
        hop_length=args.hop_length,
        n_mels=args.n_mels,
        num_workers=args.num_workers,
        seed=args.seed,
        label_smoothing=args.label_smoothing,
        class_weight_mode=args.class_weight_mode,
        weighted_sampler=bool(args.weighted_sampler),
        sample_weight_mode=args.sample_weight_mode,
        head_mix_boost=args.head_mix_boost,
        breathy_mix_boost=args.breathy_mix_boost,
        control_negative_boost=args.control_negative_boost,
        falsetto_negative_boost=args.falsetto_negative_boost,
        breathy_negative_boost=args.breathy_negative_boost,
        other_negative_boost=args.other_negative_boost,
        loss_weight_mode=args.loss_weight_mode,
        head_mix_loss_boost=args.head_mix_loss_boost,
        breathy_mix_loss_boost=args.breathy_mix_loss_boost,
        control_negative_loss_boost=args.control_negative_loss_boost,
        falsetto_negative_loss_boost=args.falsetto_negative_loss_boost,
        breathy_negative_loss_boost=args.breathy_negative_loss_boost,
        other_negative_loss_boost=args.other_negative_loss_boost,
        selection_metric=args.selection_metric,
        threshold_min=args.threshold_min,
        threshold_max=args.threshold_max,
        threshold_step=args.threshold_step,
        min_positive_mix_rate=args.min_positive_mix_rate,
        max_control_negative_rate=args.max_control_negative_rate,
        max_breathy_negative_rate=args.max_breathy_negative_rate,
        max_falsetto_negative_rate=args.max_falsetto_negative_rate,
        product_proxy_positive_weight=args.product_proxy_positive_weight,
        product_proxy_control_penalty=args.product_proxy_control_penalty,
        product_proxy_breathy_penalty=args.product_proxy_breathy_penalty,
        product_proxy_falsetto_penalty=args.product_proxy_falsetto_penalty,
        aux_target_column=args.aux_target_column,
        aux_label_column=args.aux_label_column,
        aux_ignore_index=args.aux_ignore_index,
        aux_loss_weight=args.aux_loss_weight,
        aux_class_weight_mode=args.aux_class_weight_mode,
        aux_hidden_dim=args.aux_hidden_dim,
    )
    best_path = run_training(cfg)
    print(f'best_checkpoint={best_path}')


if __name__ == '__main__':
    main()