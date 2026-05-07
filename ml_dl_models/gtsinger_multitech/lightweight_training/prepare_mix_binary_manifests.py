import argparse
import csv
import gc
import random
from collections import Counter
from pathlib import Path

import numpy as np


TARGET_LABEL = 'mix'
HARD_NEGATIVE_GROUPS = ('Falsetto_Group', 'Breathy_Group')
OTHER_NEGATIVE_GROUPS = ('Pharyngeal_Group', 'Vibrato_Group', 'Glissando_Group')


def read_manifest(path: Path) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'No rows to write for {path}')
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def is_mix_positive(row: dict) -> bool:
    return int(float(row[TARGET_LABEL])) == 1


def negative_bucket(row: dict) -> str:
    group_name = str(row.get('group_name', '') or '')
    if is_mix_positive(row):
        return 'positive_mix'
    if group_name == 'Control_Group':
        return 'control_negative'
    if group_name in HARD_NEGATIVE_GROUPS:
        return f'{group_name.lower()}'
    return 'other_negative'


def row_priority(row: dict) -> tuple[int, int, int, str, str, str]:
    falsetto = int(float(row.get('falsetto', 0) or 0))
    breathy = int(float(row.get('breathy', 0) or 0))
    vibrato = int(float(row.get('vibrato', 0) or 0))
    glissando = int(float(row.get('glissando', 0) or 0))
    pharyngeal = int(float(row.get('pharyngeal', 0) or 0))
    hard_negative_hits = falsetto + breathy
    other_hits = vibrato + glissando + pharyngeal
    group_name = str(row.get('group_name', '') or '')
    group_rank = {
        'Falsetto_Group': 0,
        'Breathy_Group': 1,
        'Control_Group': 2,
        'Pharyngeal_Group': 3,
        'Vibrato_Group': 4,
        'Glissando_Group': 5,
    }.get(group_name, 9)
    return (
        -hard_negative_hits,
        -other_hits,
        group_rank,
        str(row.get('singer', '') or ''),
        str(row.get('song_name', '') or ''),
        str(row.get('item_name', '') or ''),
    )


def sample_rows(rows: list[dict], keep_count: int, seed: int) -> list[dict]:
    if keep_count <= 0:
        return []
    if len(rows) <= keep_count:
        return sorted(rows, key=row_priority)
    rnd = random.Random(seed)
    pool = list(rows)
    rnd.shuffle(pool)
    pool.sort(key=row_priority)
    return pool[:keep_count]


def normalize_control_stratum_shares(
    easy_share: float,
    mid_share: float,
    hard_share: float,
) -> tuple[float, float, float]:
    shares = [max(0.0, float(easy_share)), max(0.0, float(mid_share)), max(0.0, float(hard_share))]
    total = float(sum(shares))
    if total <= 0.0:
        return 0.2, 0.3, 0.5
    return tuple(float(item / total) for item in shares)


def annotate_control_score_strata(
    rows: list[dict],
    *,
    easy_quantile: float,
    hard_quantile: float,
) -> list[dict]:
    if not rows:
        return []
    scored = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            float(row.get('mined_mix_prob', 0.0) or 0.0),
            *row_priority(row),
        ),
    )
    count = len(scored)
    if count == 1:
        scored[0]['control_stratum'] = 'hard'
        return scored

    easy_q = min(0.49, max(0.05, float(easy_quantile)))
    hard_q = min(0.95, max(easy_q + 0.05, float(hard_quantile)))
    easy_end = max(1, min(count - 1, int(round(count * easy_q))))
    hard_start = max(easy_end + 1, min(count - 1, int(round(count * hard_q))))

    for index, row in enumerate(scored):
        if index < easy_end:
            row['control_stratum'] = 'easy'
        elif index < hard_start:
            row['control_stratum'] = 'mid'
        else:
            row['control_stratum'] = 'hard'
    return scored


def allocate_control_stratum_counts(
    keep_count: int,
    *,
    easy_size: int,
    mid_size: int,
    hard_size: int,
    easy_share: float,
    mid_share: float,
    hard_share: float,
) -> dict[str, int]:
    shares = normalize_control_stratum_shares(easy_share, mid_share, hard_share)
    capacities = {
        'easy': max(0, int(easy_size)),
        'mid': max(0, int(mid_size)),
        'hard': max(0, int(hard_size)),
    }
    desired = {
        'easy': float(keep_count) * shares[0],
        'mid': float(keep_count) * shares[1],
        'hard': float(keep_count) * shares[2],
    }
    counts = {
        name: min(capacities[name], int(np.floor(value)))
        for name, value in desired.items()
    }
    remaining = max(0, int(keep_count) - sum(counts.values()))
    order = sorted(
        desired.keys(),
        key=lambda name: (
            desired[name] - np.floor(desired[name]),
            desired[name],
            capacities[name],
        ),
        reverse=True,
    )
    while remaining > 0:
        progressed = False
        for name in order:
            if counts[name] >= capacities[name]:
                continue
            counts[name] += 1
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break
    return counts


def sample_control_stratified_rows(
    rows: list[dict],
    keep_count: int,
    *,
    seed: int,
    hard_negative_artifact: Path,
    eval_window_count: int,
    eval_window_aggregation: str | None,
    eval_window_consistency_penalty: float | None,
    eval_window_support_threshold: float | None,
    eval_window_min_support_windows: int | None,
    eval_window_high_support_threshold: float | None,
    eval_window_min_high_support_windows: int | None,
    control_easy_share: float,
    control_mid_share: float,
    control_hard_share: float,
    control_easy_quantile: float,
    control_hard_quantile: float,
) -> list[dict]:
    if keep_count <= 0:
        return []
    scored = score_rows_with_artifact(
        rows,
        artifact_dir=hard_negative_artifact,
        eval_window_count=eval_window_count,
        eval_window_aggregation=eval_window_aggregation,
        eval_window_consistency_penalty=eval_window_consistency_penalty,
        eval_window_support_threshold=eval_window_support_threshold,
        eval_window_min_support_windows=eval_window_min_support_windows,
        eval_window_high_support_threshold=eval_window_high_support_threshold,
        eval_window_min_high_support_windows=eval_window_min_high_support_windows,
    )
    annotated = annotate_control_score_strata(
        scored,
        easy_quantile=control_easy_quantile,
        hard_quantile=control_hard_quantile,
    )
    easy_rows = [row for row in annotated if str(row.get('control_stratum', '') or '') == 'easy']
    mid_rows = [row for row in annotated if str(row.get('control_stratum', '') or '') == 'mid']
    hard_rows = [row for row in annotated if str(row.get('control_stratum', '') or '') == 'hard']
    counts = allocate_control_stratum_counts(
        keep_count,
        easy_size=len(easy_rows),
        mid_size=len(mid_rows),
        hard_size=len(hard_rows),
        easy_share=control_easy_share,
        mid_share=control_mid_share,
        hard_share=control_hard_share,
    )
    print(
        f'control_strata_selection easy={counts["easy"]}/{len(easy_rows)} mid={counts["mid"]}/{len(mid_rows)} hard={counts["hard"]}/{len(hard_rows)}',
        flush=True,
    )
    selected: list[dict] = []
    selected.extend(sample_rows(easy_rows, counts['easy'], seed=seed))
    selected.extend(sample_rows(mid_rows, counts['mid'], seed=seed + 1))
    selected.extend(sample_rows(hard_rows, counts['hard'], seed=seed + 2))
    if len(selected) < keep_count:
        selected_keys = {
            (
                str(row.get('singer', '') or ''),
                str(row.get('song_name', '') or ''),
                str(row.get('item_name', '') or ''),
            )
            for row in selected
        }
        remaining_rows = [
            row for row in annotated
            if (
                str(row.get('singer', '') or ''),
                str(row.get('song_name', '') or ''),
                str(row.get('item_name', '') or ''),
            ) not in selected_keys
        ]
        selected.extend(sample_rows(remaining_rows, keep_count - len(selected), seed=seed + 3))
    selected.sort(key=row_priority)
    return selected[:keep_count]


def score_rows_with_artifact(
    rows: list[dict],
    *,
    artifact_dir: Path,
    eval_window_count: int,
    eval_window_aggregation: str | None,
    eval_window_consistency_penalty: float | None,
    eval_window_support_threshold: float | None,
    eval_window_min_support_windows: int | None,
    eval_window_high_support_threshold: float | None,
    eval_window_min_high_support_windows: int | None,
    batch_size: int = 32,
    device_override: str | None = None,
) -> list[dict]:
    import torch
    from torch.utils.data import DataLoader

    import compare_mix_binary_checkpoints as compare
    import train_mix_binary_squeezenet as trainer

    requested_device = str(device_override or 'auto').strip().lower()
    resolved_batch_size = max(1, int(batch_size or 32))

    def choose_device(preference: str) -> torch.device:
        if preference == 'cpu':
            return torch.device('cpu')
        if preference == 'cuda':
            if not torch.cuda.is_available():
                raise RuntimeError('cuda requested but not available')
            return torch.device('cuda')
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def score_once(device: torch.device) -> list[dict]:
        model = None
        dataset = None
        loader = None
        try:
            model, _, sample_secs, n_mels, artifact_eval_window_count, artifact_eval_window_aggregation, artifact_eval_window_consistency_penalty, artifact_eval_window_support_threshold, artifact_eval_window_min_support_windows, artifact_eval_window_high_support_threshold, artifact_eval_window_min_high_support_windows, artifact_backbone_name, artifact_image_size, artifact_sample_rate, artifact_n_fft, artifact_hop_length = compare.load_artifact_model(artifact_dir, device)
            effective_window_count = max(1, int(eval_window_count or artifact_eval_window_count or 1))
            effective_aggregation = str(eval_window_aggregation or artifact_eval_window_aggregation or 'mean').strip().lower()
            if effective_aggregation not in trainer.EVAL_WINDOW_AGGREGATIONS:
                effective_aggregation = 'mean'
            effective_penalty = max(0.0, float(artifact_eval_window_consistency_penalty if eval_window_consistency_penalty is None else eval_window_consistency_penalty))
            effective_support_threshold = min(0.95, max(0.05, float(artifact_eval_window_support_threshold if eval_window_support_threshold is None else eval_window_support_threshold)))
            effective_min_support_windows = max(1, int(artifact_eval_window_min_support_windows if eval_window_min_support_windows is None else eval_window_min_support_windows))
            effective_high_support_threshold = min(0.99, max(effective_support_threshold, float(artifact_eval_window_high_support_threshold if eval_window_high_support_threshold is None else eval_window_high_support_threshold)))
            effective_min_high_support_windows = max(1, int(artifact_eval_window_min_high_support_windows if eval_window_min_high_support_windows is None else eval_window_min_high_support_windows))

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
                eval_anchor_ratios=trainer.build_eval_anchor_ratios(effective_window_count),
            )
            loader = DataLoader(dataset, batch_size=resolved_batch_size, shuffle=False, num_workers=0)

            probs: list[float] = []
            total_batches = len(loader)
            with torch.inference_mode():
                for batch_index, (images, _) in enumerate(loader, start=1):
                    batch_images = images.to(device)
                    logits = trainer.forward_with_window_average(
                        model,
                        batch_images,
                        aggregation=effective_aggregation,
                        consistency_penalty=effective_penalty,
                        support_threshold=effective_support_threshold,
                        min_support_windows=effective_min_support_windows,
                        high_support_threshold=effective_high_support_threshold,
                        min_high_support_windows=effective_min_high_support_windows,
                    )
                    probs.extend(float(item) for item in torch.softmax(logits, dim=1)[:, 1].detach().cpu().numpy().tolist())
                    del batch_images
                    del logits
                    if batch_index == 1 or batch_index == total_batches or batch_index % 10 == 0:
                        print(f'scoring_control_rows_batch={batch_index}/{total_batches} device={device.type}', flush=True)

            enriched: list[dict] = []
            for row, prob in zip(rows, probs):
                item = dict(row)
                item['mined_mix_prob'] = f'{float(prob):.6f}'
                item['mined_device'] = str(device.type)
                enriched.append(item)
            return enriched
        finally:
            loader = None
            dataset = None
            model = None
            gc.collect()
            try:
                if device.type == 'cuda' and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    try:
        initial_device = choose_device(requested_device)
        return score_once(initial_device)
    except (torch.OutOfMemoryError, RuntimeError) as exc:
        message = str(exc or '').lower()
        if requested_device == 'cpu' or 'out of memory' not in message:
            raise
        print(f'score_rows_with_artifact_cuda_oom_fallback artifact={artifact_dir} batch_size={resolved_batch_size}', flush=True)
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        return score_once(torch.device('cpu'))


def sample_control_hardneg_rows(
    rows: list[dict],
    keep_count: int,
    *,
    seed: int,
    control_selection_mode: str,
    hard_negative_artifact: Path | None,
    eval_window_count: int,
    eval_window_aggregation: str | None,
    eval_window_consistency_penalty: float | None,
    eval_window_support_threshold: float | None,
    eval_window_min_support_windows: int | None,
    eval_window_high_support_threshold: float | None,
    eval_window_min_high_support_windows: int | None,
    control_easy_share: float,
    control_mid_share: float,
    control_hard_share: float,
    control_easy_quantile: float,
    control_hard_quantile: float,
) -> list[dict]:
    if control_selection_mode == 'stratified_by_artifact' and hard_negative_artifact is not None:
        return sample_control_stratified_rows(
            rows,
            keep_count,
            seed=seed,
            hard_negative_artifact=hard_negative_artifact,
            eval_window_count=eval_window_count,
            eval_window_aggregation=eval_window_aggregation,
            eval_window_consistency_penalty=eval_window_consistency_penalty,
            eval_window_support_threshold=eval_window_support_threshold,
            eval_window_min_support_windows=eval_window_min_support_windows,
            eval_window_high_support_threshold=eval_window_high_support_threshold,
            eval_window_min_high_support_windows=eval_window_min_high_support_windows,
            control_easy_share=control_easy_share,
            control_mid_share=control_mid_share,
            control_hard_share=control_hard_share,
            control_easy_quantile=control_easy_quantile,
            control_hard_quantile=control_hard_quantile,
        )
    if control_selection_mode != 'hardest_by_artifact' or hard_negative_artifact is None:
        return sample_rows(rows, keep_count, seed=seed)
    scored = score_rows_with_artifact(
        rows,
        artifact_dir=hard_negative_artifact,
        eval_window_count=eval_window_count,
        eval_window_aggregation=eval_window_aggregation,
        eval_window_consistency_penalty=eval_window_consistency_penalty,
        eval_window_support_threshold=eval_window_support_threshold,
        eval_window_min_support_windows=eval_window_min_support_windows,
        eval_window_high_support_threshold=eval_window_high_support_threshold,
        eval_window_min_high_support_windows=eval_window_min_high_support_windows,
    )
    scored.sort(
        key=lambda row: (
            -float(row.get('mined_mix_prob', 0.0) or 0.0),
            *row_priority(row),
        )
    )
    return scored[:keep_count]


def attach_role(rows: list[dict]) -> list[dict]:
    enriched = []
    for row in rows:
        item = dict(row)
        item['binary_role'] = negative_bucket(row)
        enriched.append(item)
    return enriched


def build_mix_binary_split(
    rows: list[dict],
    *,
    keep_control_ratio: float,
    keep_falsetto_ratio: float,
    keep_breathy_ratio: float,
    keep_other_negative_ratio: float,
    seed: int,
    control_selection_mode: str,
    hard_negative_artifact: Path | None,
    eval_window_count: int,
    eval_window_aggregation: str | None,
    eval_window_consistency_penalty: float | None,
    eval_window_support_threshold: float | None,
    eval_window_min_support_windows: int | None,
    eval_window_high_support_threshold: float | None,
    eval_window_min_high_support_windows: int | None,
    control_easy_share: float,
    control_mid_share: float,
    control_hard_share: float,
    control_easy_quantile: float,
    control_hard_quantile: float,
) -> list[dict]:
    positives = [dict(row) for row in rows if is_mix_positive(row)]
    control_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Control_Group']
    falsetto_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Falsetto_Group']
    breathy_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Breathy_Group']
    other_negatives = [
        dict(row)
        for row in rows
        if (not is_mix_positive(row)) and row.get('group_name') in OTHER_NEGATIVE_GROUPS
    ]

    positive_count = len(positives)
    selected = []
    selected.extend(attach_role(sorted(positives, key=row_priority)))
    selected.extend(attach_role(sample_control_hardneg_rows(
        control_negatives,
        int(round(positive_count * keep_control_ratio)),
        seed=seed,
        control_selection_mode=control_selection_mode,
        hard_negative_artifact=hard_negative_artifact,
        eval_window_count=eval_window_count,
        eval_window_aggregation=eval_window_aggregation,
        eval_window_consistency_penalty=eval_window_consistency_penalty,
        eval_window_support_threshold=eval_window_support_threshold,
        eval_window_min_support_windows=eval_window_min_support_windows,
        eval_window_high_support_threshold=eval_window_high_support_threshold,
        eval_window_min_high_support_windows=eval_window_min_high_support_windows,
        control_easy_share=control_easy_share,
        control_mid_share=control_mid_share,
        control_hard_share=control_hard_share,
        control_easy_quantile=control_easy_quantile,
        control_hard_quantile=control_hard_quantile,
    )))
    selected.extend(attach_role(sample_rows(falsetto_negatives, int(round(positive_count * keep_falsetto_ratio)), seed=seed + 1)))
    selected.extend(attach_role(sample_rows(breathy_negatives, int(round(positive_count * keep_breathy_ratio)), seed=seed + 2)))
    selected.extend(attach_role(sample_rows(other_negatives, int(round(positive_count * keep_other_negative_ratio)), seed=seed + 3)))
    for row in selected:
        row.setdefault('mined_mix_prob', '')
        row.setdefault('control_stratum', '')
    selected.sort(key=lambda row: (str(row.get('group_name', '') or ''), str(row.get('singer', '') or ''), str(row.get('song_name', '') or ''), str(row.get('item_name', '') or '')))
    return selected


def summarize(rows: list[dict]) -> dict:
    mined_scores = [float(row.get('mined_mix_prob', 0.0) or 0.0) for row in rows if str(row.get('binary_role', '') or '') == 'control_negative' and str(row.get('mined_mix_prob', '') or '').strip()]
    control_strata = Counter(str(row.get('control_stratum', '') or '') for row in rows if str(row.get('control_stratum', '') or '').strip())
    return {
        'items': len(rows),
        'mix_positive': sum(1 for row in rows if is_mix_positive(row)),
        'mix_negative': sum(1 for row in rows if not is_mix_positive(row)),
        'binary_roles': Counter(str(row.get('binary_role', '') or '') for row in rows),
        'groups': Counter(str(row.get('group_name', '') or '') for row in rows),
        'control_strata': control_strata,
        'mix_variants': Counter(str(row.get('mix_variant', '') or '') for row in rows if is_mix_positive(row)),
        'control_mined_mix_prob_min': float(np.min(mined_scores)) if mined_scores else 0.0,
        'control_mined_mix_prob_mean': float(np.mean(mined_scores)) if mined_scores else 0.0,
        'control_mined_mix_prob_max': float(np.max(mined_scores)) if mined_scores else 0.0,
    }


def write_summary(
    path: Path,
    splits: dict[str, list[dict]],
    *,
    keep_control_ratio: float,
    keep_falsetto_ratio: float,
    keep_breathy_ratio: float,
    keep_other_negative_ratio: float,
    control_selection_mode: str,
    hard_negative_artifact: Path | None,
    control_easy_share: float,
    control_mid_share: float,
    control_hard_share: float,
    control_easy_quantile: float,
    control_hard_quantile: float,
) -> None:
    lines = [
        '# Mix Binary Manifest Summary',
        '',
        '- target_label: mix',
        f'- keep_control_ratio: {keep_control_ratio}',
        f'- keep_falsetto_ratio: {keep_falsetto_ratio}',
        f'- keep_breathy_ratio: {keep_breathy_ratio}',
        f'- keep_other_negative_ratio: {keep_other_negative_ratio}',
        f'- control_selection_mode: {control_selection_mode}',
        f'- hard_negative_artifact: {hard_negative_artifact if hard_negative_artifact is not None else ""}',
        f'- control_easy_share: {control_easy_share}',
        f'- control_mid_share: {control_mid_share}',
        f'- control_hard_share: {control_hard_share}',
        f'- control_easy_quantile: {control_easy_quantile}',
        f'- control_hard_quantile: {control_hard_quantile}',
        '',
        '## Fusion Intent',
        '',
        '- This split trains mix as the primary learned classifier.',
        '- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.',
        '- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.',
        '',
    ]
    for split_name, rows in splits.items():
        stats = summarize(rows)
        positive_rate = (stats['mix_positive'] / stats['items']) if stats['items'] else 0.0
        lines.append(f'## {split_name.title()}')
        lines.append('')
        lines.append(f'- items: {stats["items"]}')
        lines.append(f'- mix_positive: {stats["mix_positive"]}')
        lines.append(f'- mix_negative: {stats["mix_negative"]}')
        lines.append(f'- mix_positive_rate: {positive_rate:.4f}')
        for role_name, count in stats['binary_roles'].most_common():
            lines.append(f'- role_{role_name}: {count}')
        for group_name, count in stats['groups'].most_common():
            lines.append(f'- group_{group_name}: {count}')
        for stratum_name, count in stats['control_strata'].most_common():
            lines.append(f'- control_stratum_{stratum_name}: {count}')
        for variant_name, count in stats['mix_variants'].most_common():
            lines.append(f'- mix_variant_{variant_name}: {count}')
        if float(stats.get('control_mined_mix_prob_mean', 0.0)) > 0.0:
            lines.append(f'- control_mined_mix_prob_min: {float(stats["control_mined_mix_prob_min"]):.6f}')
            lines.append(f'- control_mined_mix_prob_mean: {float(stats["control_mined_mix_prob_mean"]):.6f}')
            lines.append(f'- control_mined_mix_prob_max: {float(stats["control_mined_mix_prob_max"]):.6f}')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare focused manifests for mix binary training.')
    parser.add_argument('--input-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\multitech_core')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core')
    parser.add_argument('--keep-control-ratio', type=float, default=0.55)
    parser.add_argument('--keep-falsetto-ratio', type=float, default=0.55)
    parser.add_argument('--keep-breathy-ratio', type=float, default=0.35)
    parser.add_argument('--keep-other-negative-ratio', type=float, default=0.25)
    parser.add_argument('--control-selection-mode', choices=['priority', 'hardest_by_artifact', 'stratified_by_artifact'], default='priority')
    parser.add_argument('--hard-negative-artifact', default='')
    parser.add_argument('--control-easy-share', type=float, default=0.20)
    parser.add_argument('--control-mid-share', type=float, default=0.30)
    parser.add_argument('--control-hard-share', type=float, default=0.50)
    parser.add_argument('--control-easy-quantile', type=float, default=0.33)
    parser.add_argument('--control-hard-quantile', type=float, default=0.67)
    parser.add_argument('--eval-window-count', type=int, default=0)
    parser.add_argument('--eval-window-aggregation', default='')
    parser.add_argument('--eval-window-consistency-penalty', type=float, default=-1.0)
    parser.add_argument('--eval-window-support-threshold', type=float, default=-1.0)
    parser.add_argument('--eval-window-min-support-windows', type=int, default=0)
    parser.add_argument('--eval-window-high-support-threshold', type=float, default=-1.0)
    parser.add_argument('--eval-window-min-high-support-windows', type=int, default=0)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    hard_negative_artifact = Path(args.hard_negative_artifact) if str(args.hard_negative_artifact or '').strip() else None
    eval_window_aggregation = str(args.eval_window_aggregation or '').strip().lower() or None
    eval_window_consistency_penalty = None if float(args.eval_window_consistency_penalty) < 0.0 else float(args.eval_window_consistency_penalty)
    eval_window_support_threshold = None if float(args.eval_window_support_threshold) < 0.0 else float(args.eval_window_support_threshold)
    eval_window_min_support_windows = None if int(args.eval_window_min_support_windows or 0) <= 0 else int(args.eval_window_min_support_windows)
    eval_window_high_support_threshold = None if float(args.eval_window_high_support_threshold) < 0.0 else float(args.eval_window_high_support_threshold)
    eval_window_min_high_support_windows = None if int(args.eval_window_min_high_support_windows or 0) <= 0 else int(args.eval_window_min_high_support_windows)

    splits: dict[str, list[dict]] = {}
    for index, split_name in enumerate(('train', 'validation', 'test')):
        print(f'building_split={split_name}', flush=True)
        rows = read_manifest(input_dir / f'{split_name}_manifest.csv')
        split_rows = build_mix_binary_split(
            rows,
            keep_control_ratio=args.keep_control_ratio,
            keep_falsetto_ratio=args.keep_falsetto_ratio,
            keep_breathy_ratio=args.keep_breathy_ratio,
            keep_other_negative_ratio=args.keep_other_negative_ratio,
            seed=args.seed + index * 17,
            control_selection_mode=str(args.control_selection_mode),
            hard_negative_artifact=hard_negative_artifact,
            eval_window_count=int(args.eval_window_count or 0),
            eval_window_aggregation=eval_window_aggregation,
            eval_window_consistency_penalty=eval_window_consistency_penalty,
            eval_window_support_threshold=eval_window_support_threshold,
            eval_window_min_support_windows=eval_window_min_support_windows,
            eval_window_high_support_threshold=eval_window_high_support_threshold,
            eval_window_min_high_support_windows=eval_window_min_high_support_windows,
            control_easy_share=float(args.control_easy_share),
            control_mid_share=float(args.control_mid_share),
            control_hard_share=float(args.control_hard_share),
            control_easy_quantile=float(args.control_easy_quantile),
            control_hard_quantile=float(args.control_hard_quantile),
        )
        splits[split_name] = split_rows
        write_manifest(output_dir / f'{split_name}_manifest.csv', split_rows)

    write_summary(
        output_dir / 'manifest_summary.md',
        splits,
        keep_control_ratio=args.keep_control_ratio,
        keep_falsetto_ratio=args.keep_falsetto_ratio,
        keep_breathy_ratio=args.keep_breathy_ratio,
        keep_other_negative_ratio=args.keep_other_negative_ratio,
        control_selection_mode=str(args.control_selection_mode),
        hard_negative_artifact=hard_negative_artifact,
        control_easy_share=float(args.control_easy_share),
        control_mid_share=float(args.control_mid_share),
        control_hard_share=float(args.control_hard_share),
        control_easy_quantile=float(args.control_easy_quantile),
        control_hard_quantile=float(args.control_hard_quantile),
    )

    for split_name, rows in splits.items():
        print(split_name, len(rows))
    print(f'wrote {output_dir}')


if __name__ == '__main__':
    main()