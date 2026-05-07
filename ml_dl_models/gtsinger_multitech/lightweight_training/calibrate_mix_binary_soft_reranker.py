import argparse
import json
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch

import compare_mix_binary_with_control_suppressor as reranker


DEFAULT_BINARY_ROLES = (
    'positive_mix',
    'control_negative',
    'falsetto_group',
    'breathy_group',
)


def build_float_grid(start: float, end: float, step: float) -> List[float]:
    values: List[float] = []
    current = float(start)
    upper = float(end)
    delta = max(1e-9, float(step))
    while current <= upper + 1e-9:
        values.append(round(current, 6))
        current += delta
    return values


def safe_logit(value: np.ndarray | float, eps: float = 1e-6) -> np.ndarray:
    clipped = np.clip(np.asarray(value, dtype=np.float64), eps, 1.0 - eps)
    return np.log(clipped / (1.0 - clipped))


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


def build_scored_rows(
    rows: Sequence[dict],
    probs: Sequence[float],
    preds: Sequence[int],
) -> List[dict]:
    scored_rows: List[dict] = []
    for row, prob, pred in zip(rows, probs, preds):
        item = dict(row)
        item['_label'] = int(float(row.get('mix', 0) or 0))
        item['_pred'] = int(pred)
        item['_mix_prob'] = float(prob)
        scored_rows.append(item)
    return scored_rows


def summarize_scored_rows(rows: Sequence[dict]) -> Dict[str, object]:
    overall = reranker.summarize_rows(rows)
    binary_roles = {
        role_name: reranker.summarize_rows([row for row in rows if str(row.get('binary_role', '') or '') == role_name])
        for role_name in DEFAULT_BINARY_ROLES
        if any(str(row.get('binary_role', '') or '') == role_name for row in rows)
    }
    return {
        'overall': overall,
        'binary_roles': binary_roles,
    }


def evaluate_primary_only(
    rows: Sequence[dict],
    primary_probs: Sequence[float],
    *,
    primary_threshold: float,
) -> Dict[str, object]:
    preds = [int(float(prob) >= float(primary_threshold)) for prob in primary_probs]
    scored_rows = build_scored_rows(rows, primary_probs, preds)
    summary = summarize_scored_rows(scored_rows)
    return {
        'mode': 'primary_only',
        'primary_threshold': round(float(primary_threshold), 6),
        **summary,
    }


def evaluate_fusion(
    rows: Sequence[dict],
    primary_probs: Sequence[float],
    suppressor_probs: Sequence[float],
    *,
    primary_threshold: float,
    suppressor_anchor: float,
    suppressor_weight: float,
    bias: float,
) -> Dict[str, object]:
    primary_array = np.asarray(primary_probs, dtype=np.float64)
    suppressor_array = np.asarray(suppressor_probs, dtype=np.float64)
    primary_margin = safe_logit(primary_array) - float(safe_logit(float(primary_threshold)))
    suppressor_margin = safe_logit(suppressor_array) - float(safe_logit(float(suppressor_anchor)))
    fused_margin = primary_margin + float(suppressor_weight) * suppressor_margin + float(bias)
    fused_probs = sigmoid(fused_margin)
    fused_preds = (fused_margin >= 0.0).astype(np.int32)
    scored_rows = build_scored_rows(rows, fused_probs.tolist(), fused_preds.tolist())
    summary = summarize_scored_rows(scored_rows)
    return {
        'mode': 'soft_reranker',
        'primary_threshold': round(float(primary_threshold), 6),
        'suppressor_anchor': round(float(suppressor_anchor), 6),
        'suppressor_weight': round(float(suppressor_weight), 6),
        'bias': round(float(bias), 6),
        **summary,
    }


def constraints_ok(candidate: Dict[str, object], args: argparse.Namespace) -> bool:
    binary_roles = candidate.get('binary_roles', {})
    positive_mix = float(binary_roles.get('positive_mix', {}).get('predicted_positive_rate', 0.0) or 0.0)
    control_negative = float(binary_roles.get('control_negative', {}).get('predicted_positive_rate', 0.0) or 0.0)
    falsetto_group = float(binary_roles.get('falsetto_group', {}).get('predicted_positive_rate', 0.0) or 0.0)
    breathy_group = float(binary_roles.get('breathy_group', {}).get('predicted_positive_rate', 0.0) or 0.0)
    return (
        positive_mix >= float(args.min_positive_mix_rate)
        and control_negative <= float(args.max_control_negative_rate)
        and falsetto_group <= float(args.max_falsetto_negative_rate)
        and breathy_group <= float(args.max_breathy_negative_rate)
    )


def pick_best(candidates: Sequence[Dict[str, object]], selection_metric: str) -> Dict[str, object]:
    return max(
        candidates,
        key=lambda item: (
            float(item['overall'].get(selection_metric, 0.0) or 0.0),
            float(item['binary_roles'].get('positive_mix', {}).get('predicted_positive_rate', 0.0) or 0.0),
            -float(item['binary_roles'].get('control_negative', {}).get('predicted_positive_rate', 1.0) or 1.0),
        ),
    )


def score_manifest(
    rows: Sequence[dict],
    primary_info: Dict[str, object],
    suppressor_info: Dict[str, object],
    device: torch.device,
) -> tuple[List[float], List[float]]:
    if reranker.models_share_preprocessing(primary_info, suppressor_info):
        print('shared_preprocessing=true', flush=True)
        return reranker.score_rows_shared(primary_info, suppressor_info, rows, device)

    print('shared_preprocessing=false', flush=True)
    primary_probs, _, _ = reranker.score_rows(
        Path(str(primary_info['path'])),
        rows,
        device,
        eval_window_count_override=int(primary_info['eval_window_count']),
    )
    suppressor_probs, _, _ = reranker.score_rows(
        Path(str(suppressor_info['path'])),
        rows,
        device,
        eval_window_count_override=int(suppressor_info['eval_window_count']),
    )
    return primary_probs, suppressor_probs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Calibrate a soft reranker that fuses a primary mix model with a control-only model.')
    parser.add_argument('--validation-manifest', required=True)
    parser.add_argument('--test-manifest', default='')
    parser.add_argument('--primary-artifact', required=True)
    parser.add_argument('--suppressor-artifact', required=True)
    parser.add_argument('--eval-window-count', type=int, default=0)
    parser.add_argument('--weight-start', type=float, default=0.0)
    parser.add_argument('--weight-end', type=float, default=2.0)
    parser.add_argument('--weight-step', type=float, default=0.125)
    parser.add_argument('--bias-start', type=float, default=-1.0)
    parser.add_argument('--bias-end', type=float, default=1.0)
    parser.add_argument('--bias-step', type=float, default=0.1)
    parser.add_argument('--selection-metric', default='balanced_acc')
    parser.add_argument('--min-positive-mix-rate', type=float, default=0.0)
    parser.add_argument('--max-control-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-falsetto-negative-rate', type=float, default=1.0)
    parser.add_argument('--max-breathy-negative-rate', type=float, default=1.0)
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--output', default='')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    validation_rows = reranker.load_rows(Path(args.validation_manifest))
    primary_info = reranker.load_artifact(
        Path(args.primary_artifact),
        device,
        eval_window_count_override=int(args.eval_window_count or 0),
    )
    suppressor_info = reranker.load_artifact(
        Path(args.suppressor_artifact),
        device,
        eval_window_count_override=int(args.eval_window_count or 0),
    )

    validation_primary_probs, validation_suppressor_probs = score_manifest(
        validation_rows,
        primary_info,
        suppressor_info,
        device,
    )

    primary_only_validation = evaluate_primary_only(
        validation_rows,
        validation_primary_probs,
        primary_threshold=float(primary_info['threshold']),
    )

    weight_grid = build_float_grid(args.weight_start, args.weight_end, args.weight_step)
    bias_grid = build_float_grid(args.bias_start, args.bias_end, args.bias_step)
    candidates = [
        evaluate_fusion(
            validation_rows,
            validation_primary_probs,
            validation_suppressor_probs,
            primary_threshold=float(primary_info['threshold']),
            suppressor_anchor=float(suppressor_info['threshold']),
            suppressor_weight=weight,
            bias=bias,
        )
        for weight in weight_grid
        for bias in bias_grid
    ]
    valid_candidates = [item for item in candidates if constraints_ok(item, args)]
    selection_pool = valid_candidates or candidates
    best_validation = pick_best(selection_pool, args.selection_metric)
    top_validation = sorted(
        selection_pool,
        key=lambda item: (
            float(item['overall'].get(args.selection_metric, 0.0) or 0.0),
            float(item['binary_roles'].get('positive_mix', {}).get('predicted_positive_rate', 0.0) or 0.0),
            -float(item['binary_roles'].get('control_negative', {}).get('predicted_positive_rate', 1.0) or 1.0),
        ),
        reverse=True,
    )[: max(1, int(args.top_k))]

    report: Dict[str, object] = {
        'validation_manifest': args.validation_manifest,
        'test_manifest': args.test_manifest,
        'primary_artifact': reranker.summarize_model_info(primary_info),
        'suppressor_artifact': reranker.summarize_model_info(suppressor_info),
        'selection_metric': args.selection_metric,
        'search_space': {
            'weight_start': float(args.weight_start),
            'weight_end': float(args.weight_end),
            'weight_step': float(args.weight_step),
            'bias_start': float(args.bias_start),
            'bias_end': float(args.bias_end),
            'bias_step': float(args.bias_step),
        },
        'constraints': {
            'min_positive_mix_rate': float(args.min_positive_mix_rate),
            'max_control_negative_rate': float(args.max_control_negative_rate),
            'max_falsetto_negative_rate': float(args.max_falsetto_negative_rate),
            'max_breathy_negative_rate': float(args.max_breathy_negative_rate),
        },
        'primary_only_validation': primary_only_validation,
        'best_validation': best_validation,
        'top_validation': top_validation,
        'constraint_satisfied_candidate_count': len(valid_candidates),
        'candidate_count': len(candidates),
    }

    if args.test_manifest:
        test_rows = reranker.load_rows(Path(args.test_manifest))
        test_primary_probs, test_suppressor_probs = score_manifest(
            test_rows,
            primary_info,
            suppressor_info,
            device,
        )
        report['primary_only_test'] = evaluate_primary_only(
            test_rows,
            test_primary_probs,
            primary_threshold=float(primary_info['threshold']),
        )
        report['best_validation_test'] = evaluate_fusion(
            test_rows,
            test_primary_probs,
            test_suppressor_probs,
            primary_threshold=float(primary_info['threshold']),
            suppressor_anchor=float(suppressor_info['threshold']),
            suppressor_weight=float(best_validation['suppressor_weight']),
            bias=float(best_validation['bias']),
        )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(text, encoding='utf-8')
        print(f'json_report={output_path.resolve()}')


if __name__ == '__main__':
    main()