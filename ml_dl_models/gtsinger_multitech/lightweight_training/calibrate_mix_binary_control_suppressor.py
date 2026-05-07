import argparse
import json
from pathlib import Path
from typing import Dict, List, Sequence

import torch

import compare_mix_binary_with_control_suppressor as reranker


DEFAULT_BINARY_ROLES = (
    'positive_mix',
    'control_negative',
    'falsetto_group',
    'breathy_group',
)


def build_threshold_grid(start: float, end: float, step: float) -> List[float]:
    thresholds: List[float] = []
    current = start
    while current <= end + 1e-9:
        thresholds.append(round(current, 6))
        current += step
    return thresholds


def evaluate_threshold(
    rows: Sequence[dict],
    primary_probs: Sequence[float],
    suppressor_probs: Sequence[float],
    *,
    primary_threshold: float,
    suppressor_threshold: float,
) -> Dict[str, object]:
    scored_rows = []
    for row, primary_prob, suppressor_prob in zip(rows, primary_probs, suppressor_probs):
        label = int(float(row.get('mix', 0) or 0))
        primary_pred = int(primary_prob >= primary_threshold)
        combined_pred = int(primary_pred == 1 and suppressor_prob >= suppressor_threshold)
        item = dict(row)
        item['_label'] = label
        item['_pred'] = combined_pred
        item['_mix_prob'] = float(primary_prob)
        scored_rows.append(item)

    overall = reranker.summarize_rows(scored_rows)
    binary_roles = {
        role_name: reranker.summarize_rows([row for row in scored_rows if str(row.get('binary_role', '') or '') == role_name])
        for role_name in DEFAULT_BINARY_ROLES
        if any(str(row.get('binary_role', '') or '') == role_name for row in scored_rows)
    }
    return {
        'suppressor_threshold': round(float(suppressor_threshold), 6),
        'overall': overall,
        'binary_roles': binary_roles,
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
    parser = argparse.ArgumentParser(description='Calibrate a second-stage control suppressor threshold on an in-domain validation manifest.')
    parser.add_argument('--validation-manifest', required=True)
    parser.add_argument('--test-manifest', default='')
    parser.add_argument('--primary-artifact', required=True)
    parser.add_argument('--suppressor-artifact', required=True)
    parser.add_argument('--eval-window-count', type=int, default=0)
    parser.add_argument('--threshold-start', type=float, default=0.30)
    parser.add_argument('--threshold-end', type=float, default=0.80)
    parser.add_argument('--threshold-step', type=float, default=0.025)
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

    primary_only_validation = evaluate_threshold(
        validation_rows,
        validation_primary_probs,
        validation_suppressor_probs,
        primary_threshold=float(primary_info['threshold']),
        suppressor_threshold=0.0,
    )
    primary_only_validation['mode'] = 'primary_only'

    thresholds = build_threshold_grid(args.threshold_start, args.threshold_end, args.threshold_step)
    candidates = [
        evaluate_threshold(
            validation_rows,
            validation_primary_probs,
            validation_suppressor_probs,
            primary_threshold=float(primary_info['threshold']),
            suppressor_threshold=threshold,
        )
        for threshold in thresholds
    ]
    valid_candidates = [item for item in candidates if constraints_ok(item, args)]
    selection_pool = valid_candidates or candidates
    best_validation = pick_best(selection_pool, args.selection_metric)
    top_validation = sorted(
        selection_pool,
        key=lambda item: (
            float(item['overall'].get(args.selection_metric, 0.0) or 0.0),
            float(item['binary_roles'].get('positive_mix', {}).get('predicted_positive_rate', 0.0) or 0.0),
        ),
        reverse=True,
    )[: max(1, int(args.top_k))]

    report: Dict[str, object] = {
        'validation_manifest': args.validation_manifest,
        'test_manifest': args.test_manifest,
        'primary_artifact': reranker.summarize_model_info(primary_info),
        'suppressor_artifact': reranker.summarize_model_info(suppressor_info),
        'selection_metric': args.selection_metric,
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
        report['primary_only_test'] = evaluate_threshold(
            test_rows,
            test_primary_probs,
            test_suppressor_probs,
            primary_threshold=float(primary_info['threshold']),
            suppressor_threshold=0.0,
        )
        report['best_validation_threshold_test'] = evaluate_threshold(
            test_rows,
            test_primary_probs,
            test_suppressor_probs,
            primary_threshold=float(primary_info['threshold']),
            suppressor_threshold=float(best_validation['suppressor_threshold']),
        )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(text, encoding='utf-8')
        print(f'json_report={output_path.resolve()}')


if __name__ == '__main__':
    main()