import argparse
import csv
import json
import os
import random
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


SEED = 42
FOUR_CLASS_LABELS = ('m_chest', 'f_chest', 'm_falsetto', 'f_falsetto')
LABEL_TO_IDX = {label: idx for idx, label in enumerate(FOUR_CLASS_LABELS)}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def parse_label_from_name(name: str) -> int:
    base = os.path.basename(name).lower()
    parts = base.replace('.jpg', '').split('_')
    if len(parts) >= 3:
        gender = parts[1]
        method = parts[2]
    elif len(parts) == 2:
        gender = parts[0]
        method = parts[1]
    else:
        raise ValueError(f'Cannot parse label from filename: {name}')
    four_class = f'{gender}_{method}'
    if four_class in LABEL_TO_IDX:
        return LABEL_TO_IDX[four_class]
    raise ValueError(f'Unrecognized label from filename: {name} (parsed as {four_class})')


def collect_zip_entries(zip_path: Path, dataset_type: str) -> List[Tuple[str, int]]:
    items: List[Tuple[str, int]] = []
    with zipfile.ZipFile(zip_path, 'r') as archive:
        for name in archive.namelist():
            lower = name.lower()
            if not lower.endswith('.jpg'):
                continue
            in_mel_dir = ('/mel/' in lower) or lower.startswith('mel/')
            if dataset_type == 'mel' and not in_mel_dir:
                continue
            if dataset_type == 'eval_triplet' and not in_mel_dir:
                continue
            if dataset_type not in ('mel', 'eval_triplet'):
                raise ValueError(f'Unsupported dataset_type: {dataset_type}')
            if '/chroma/' in lower or '/cqt/' in lower:
                continue
            items.append((name, parse_label_from_name(name)))
    if not items:
        raise RuntimeError(f'No JPG entries found in {zip_path}')
    return items


class ZippedMelDataset(Dataset):
    def __init__(self, zip_path: Path, items: Sequence[Tuple[str, int]], transform=None, dataset_type: str = 'mel'):
        self.zip_path = str(zip_path)
        self.items = list(items)
        self.transform = transform
        self.dataset_type = dataset_type
        self._zip_file = None

    def _archive(self) -> zipfile.ZipFile:
        if self._zip_file is None:
            self._zip_file = zipfile.ZipFile(self.zip_path, 'r')
        return self._zip_file

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        name, label = self.items[index]
        if self.dataset_type == 'mel':
            data = self._archive().read(name)
            image = Image.open(BytesIO(data)).convert('RGB')
        elif self.dataset_type == 'eval_triplet':
            mel_data = self._archive().read(name)
            cqt_name = name.replace('/mel/', '/cqt/')
            chroma_name = name.replace('/mel/', '/chroma/')
            cqt_data = self._archive().read(cqt_name)
            chroma_data = self._archive().read(chroma_name)
            mel_img = Image.open(BytesIO(mel_data)).convert('L')
            cqt_img = Image.open(BytesIO(cqt_data)).convert('L')
            chroma_img = Image.open(BytesIO(chroma_data)).convert('L')
            image = Image.merge('RGB', (mel_img, cqt_img, chroma_img))
        else:
            raise ValueError(f'Unsupported dataset_type: {self.dataset_type}')
        if self.transform is not None:
            image = self.transform(image)
        return image, label

    def __del__(self):
        if self._zip_file is not None:
            try:
                self._zip_file.close()
            except Exception:
                pass


@dataclass
class TrainConfig:
    mel_zip: Path
    output_dir: Path
    dataset_type: str = 'mel'
    augment_profile: str = 'safe'
    batch_size: int = 32
    head_epochs: int = 10
    finetune_epochs: int = 14
    head_lr: float = 1.5e-3
    finetune_lr: float = 3e-4
    weight_decay: float = 1e-4
    image_size: int = 224
    num_workers: int = 0
    seed: int = SEED
    label_smoothing: float = 0.02
    use_class_weights: bool = True


def build_transforms(image_size: int, augment_profile: str = 'safe'):
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    train_ops = [transforms.Resize((image_size, image_size))]
    if augment_profile == 'safe':
        train_ops.extend([
            transforms.RandomApply([transforms.ColorJitter(brightness=0.06, contrast=0.08)], p=0.20),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.45))], p=0.12),
            transforms.RandomAffine(degrees=0, translate=(0.02, 0.02), scale=(0.98, 1.02)),
        ])
    elif augment_profile == 'aggressive':
        train_ops.extend([
            transforms.RandomApply([transforms.ColorJitter(brightness=0.12, contrast=0.12)], p=0.35),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.8))], p=0.20),
            transforms.RandomAffine(degrees=0, translate=(0.03, 0.03), scale=(0.96, 1.04)),
            transforms.RandomHorizontalFlip(p=0.5),
        ])
    else:
        raise ValueError(f'Unsupported augment_profile: {augment_profile}')
    train_ops.extend([
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    if augment_profile == 'aggressive':
        train_ops.append(transforms.RandomErasing(p=0.18, scale=(0.02, 0.08), ratio=(0.5, 1.8), value='random'))
    elif augment_profile == 'safe':
        train_ops.append(transforms.RandomErasing(p=0.06, scale=(0.02, 0.05), ratio=(0.8, 1.25), value='random'))
    train_tf = transforms.Compose(train_ops)
    eval_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    return train_tf, eval_tf


def build_dataloaders(cfg: TrainConfig):
    items = collect_zip_entries(cfg.mel_zip, cfg.dataset_type)
    labels = [label for _, label in items]
    train_items, temp_items = train_test_split(
        items,
        test_size=0.4,
        random_state=cfg.seed,
        stratify=labels,
    )
    temp_labels = [label for _, label in temp_items]
    valid_items, test_items = train_test_split(
        temp_items,
        test_size=0.5,
        random_state=cfg.seed,
        stratify=temp_labels,
    )
    train_tf, eval_tf = build_transforms(cfg.image_size, cfg.augment_profile)
    train_ds = ZippedMelDataset(cfg.mel_zip, train_items, transform=train_tf, dataset_type=cfg.dataset_type)
    valid_ds = ZippedMelDataset(cfg.mel_zip, valid_items, transform=eval_tf, dataset_type=cfg.dataset_type)
    test_ds = ZippedMelDataset(cfg.mel_zip, test_items, transform=eval_tf, dataset_type=cfg.dataset_type)
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers)
    valid_loader = DataLoader(valid_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    test_loader = DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers)
    split_summary = {
        'train': Counter([label for _, label in train_items]),
        'validation': Counter([label for _, label in valid_items]),
        'test': Counter([label for _, label in test_items]),
    }
    print(f"Class distribution: { {k: dict(v) for k, v in split_summary.items()} }")
    # Verify all 4 classes present in each split
    for split_name, counts in split_summary.items():
        if len(counts) < 4:
            print(f"WARNING: {split_name} split has only {len(counts)} classes: {dict(counts)}")
    return train_loader, valid_loader, test_loader, split_summary


def build_model() -> nn.Module:
    try:
        weights = models.SqueezeNet1_1_Weights.DEFAULT
        model = models.squeezenet1_1(weights=weights)
    except Exception:
        model = models.squeezenet1_1(weights=None)
    model.classifier[1] = nn.Conv2d(512, 4, kernel_size=1)
    model.num_classes = 4
    return model


def set_feature_trainable(model: nn.Module, trainable: bool) -> None:
    for param in model.features.parameters():
        param.requires_grad = trainable


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    all_preds: List[int] = []
    all_targets: List[int] = []
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += float(loss.item()) * int(labels.size(0))
        preds = outputs.argmax(dim=1)
        all_preds.extend(preds.detach().cpu().tolist())
        all_targets.extend(labels.detach().cpu().tolist())
    avg_loss = total_loss / max(1, len(loader.dataset))
    acc = accuracy_score(all_targets, all_preds)
    return avg_loss, acc


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    all_preds: List[int] = []
    all_targets: List[int] = []
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        outputs = model(images)
        loss = criterion(outputs, labels)
        total_loss += float(loss.item()) * int(labels.size(0))
        preds = outputs.argmax(dim=1)
        all_preds.extend(preds.detach().cpu().tolist())
        all_targets.extend(labels.detach().cpu().tolist())
    avg_loss = total_loss / max(1, len(loader.dataset))
    acc = accuracy_score(all_targets, all_preds)
    return avg_loss, acc, all_targets, all_preds


def write_history_csv(path: Path, history: List[Dict[str, float]]) -> None:
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)


def main():
    parser = argparse.ArgumentParser(description='Train a 4-class SqueezeNet (m_chest/f_chest/m_falsetto/f_falsetto) classifier.')
    parser.add_argument('--mel-zip', default=r'd:\-MindEcho-main\ml_dl_models\chest_falsetto\dataset\data\mel.zip')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\chest_falsetto\squeezenet_binary\artifacts_mel_safe_v2')
    parser.add_argument('--dataset-type', choices=['mel', 'eval_triplet'], default='mel')
    parser.add_argument('--augment-profile', choices=['safe', 'aggressive'], default='safe')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--head-epochs', type=int, default=10)
    parser.add_argument('--finetune-epochs', type=int, default=14)
    parser.add_argument('--head-lr', type=float, default=1.5e-3)
    parser.add_argument('--finetune-lr', type=float, default=3e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-4)
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--label-smoothing', type=float, default=0.02)
    parser.add_argument('--no-class-weights', action='store_true', help='Disable class weights')
    args = parser.parse_args()

    cfg = TrainConfig(
        mel_zip=Path(args.mel_zip),
        output_dir=Path(args.output_dir),
        dataset_type=args.dataset_type,
        augment_profile=args.augment_profile,
        batch_size=args.batch_size,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        head_lr=args.head_lr,
        finetune_lr=args.finetune_lr,
        weight_decay=args.weight_decay,
        image_size=args.image_size,
        num_workers=args.num_workers,
        label_smoothing=args.label_smoothing,
        use_class_weights=not args.no_class_weights,
    )
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    set_seed(cfg.seed)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")
    print(f"Output dir: {cfg.output_dir}")
    train_loader, valid_loader, test_loader, split_summary = build_dataloaders(cfg)

    model = build_model().to(device)
    # Compute class weights to counteract imbalance
    class_weight = None
    if cfg.use_class_weights:
        train_counts = split_summary['train']
        max_count = max(train_counts.values())
        class_weight = torch.tensor(
            [max_count / max(train_counts.get(i, 1), 1) for i in range(4)],
            dtype=torch.float32, device=device
        )
        print(f"Class weights: {class_weight.cpu().numpy().tolist()}")
    criterion = nn.CrossEntropyLoss(weight=class_weight, label_smoothing=cfg.label_smoothing)
    history: List[Dict[str, float]] = []
    best_state = None
    best_val_acc = -1.0
    best_epoch = -1
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
            train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
            val_loss, val_acc, _, _ = evaluate(model, valid_loader, criterion, device)
            row = {
                'epoch': epoch_cursor,
                'stage': stage_name,
                'train_loss': round(train_loss, 6),
                'train_acc': round(train_acc, 6),
                'val_loss': round(val_loss, 6),
                'val_acc': round(val_acc, 6),
                'lr': round(float(optimizer.param_groups[0]['lr']), 8),
            }
            history.append(row)
            print(json.dumps(row, ensure_ascii=False))
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_epoch = epoch_cursor
                best_state = {
                    'model_state_dict': model.state_dict(),
                    'val_acc': val_acc,
                    'epoch': epoch_cursor,
                    'stage': stage_name,
                    'class_to_idx': LABEL_TO_IDX,
                }
            scheduler.step()

    if best_state is None:
        raise RuntimeError('Training did not produce a valid checkpoint.')

    best_path = cfg.output_dir / 'best_squeezenet_fourclass.pt'
    torch.save(best_state, best_path)
    model.load_state_dict(best_state['model_state_dict'])
    test_loss, test_acc, test_targets, test_preds = evaluate(model, test_loader, criterion, device)
    duration_sec = time.time() - start_time
    report = classification_report(
        test_targets,
        test_preds,
        target_names=list(FOUR_CLASS_LABELS),
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(test_targets, test_preds)
    # Also compute collapsed binary metrics (chest=0,1 vs falsetto=2,3)
    test_targets_binary = [0 if t in (0, 1) else 1 for t in test_targets]
    test_preds_binary = [0 if p in (0, 1) else 1 for p in test_preds]
    binary_acc = accuracy_score(test_targets_binary, test_preds_binary)
    binary_report = classification_report(
        test_targets_binary,
        test_preds_binary,
        target_names=['chest', 'falsetto'],
        output_dict=True,
        zero_division=0,
    )

    summary = {
        'device': str(device),
        'dataset_type': cfg.dataset_type,
        'augment_profile': cfg.augment_profile,
        'best_epoch': best_epoch,
        'best_val_acc': round(float(best_val_acc), 6),
        'test_acc': round(float(test_acc), 6),
        'test_loss': round(float(test_loss), 6),
        'duration_sec': round(float(duration_sec), 3),
        'split_summary': {key: {str(k): int(v) for k, v in value.items()} for key, value in split_summary.items()},
        'confusion_matrix': cm.tolist(),
        'confusion_matrix_labels': list(FOUR_CLASS_LABELS),
        'classification_report': report,
        'collapsed_binary_accuracy': round(float(binary_acc), 6),
        'collapsed_binary_report': binary_report,
        'history': history,
        'checkpoint': str(best_path),
    }
    with (cfg.output_dir / 'training_summary_fourclass.json').open('w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    if history:
        write_history_csv(cfg.output_dir / 'history_fourclass.csv', history)
    print(json.dumps({
        'best_val_acc': summary['best_val_acc'],
        'test_acc': summary['test_acc'],
        'collapsed_binary_acc': summary['collapsed_binary_accuracy'],
        'checkpoint': summary['checkpoint'],
        'duration_sec': summary['duration_sec'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
