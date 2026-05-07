import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'regression_tests' / 'mix_runtime_systematic_cluster_config.json'
DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Replay current FN systematic groups and summarize remaining misses.')
    parser.add_argument(
        '--group',
        action='append',
        default=[],
        help='Optional config group names. Defaults to validation_fn_systematic and test_fn_systematic24.',
    )
    return parser.parse_args()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))


def run_group(config: dict, group_name: str) -> tuple[Path, list[dict]]:
    artifact_path = ROOT / str(config.get('artifact_dir', '') or '')
    group = next(item for item in list(config.get('groups', []) or []) if str(item.get('name', '') or '') == group_name)
    output_path = ROOT / f'_tmp_{group_name}_probe_current.json'
    command = [
        sys.executable,
        str(DIAGNOSE_SCRIPT),
        '--manifest',
        str(ROOT / str(group.get('manifest', '') or '')),
        '--artifact',
        str(artifact_path),
        '--output',
        str(output_path),
    ]
    for item_name in list(group.get('item_names', []) or []):
        command.extend(['--item-name', str(item_name)])

    env = dict(os.environ)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    completed = subprocess.run(command, cwd=str(ROOT), env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(f'{group_name}: replay failed with rc={completed.returncode}')

    payload = json.loads(output_path.read_text(encoding='utf-8'))
    artifacts = list(payload.get('artifacts', []) or [])
    if len(artifacts) != 1:
        raise SystemExit(f'{group_name}: expected exactly one artifact, got {len(artifacts)}')
    samples = list(artifacts[0].get('samples', []) or [])
    misses = [sample for sample in samples if str(sample.get('outcome', '') or '') != 'hit']
    return output_path, misses


def summarize_blockers(misses: list[dict]) -> list[tuple[str, int]]:
    counter = Counter(
        ','.join(list(sample.get('voice_rule_diagnosis', {}).get('blockers', []) or []))
        for sample in misses
    )
    return list(counter.most_common())


def is_zero_support_highpitch(sample: dict) -> bool:
    diagnosis = sample.get('voice_rule_diagnosis', {}) or {}
    voice = diagnosis.get('voice_features', {}) or {}
    support = diagnosis.get('supports', {}) or {}
    return (
        float(voice.get('mean_pitch_hz', 0.0) or 0.0) >= 430.0
        and float(support.get('head_bias', 0.0) or 0.0) >= 0.97
        and float(support.get('learned_mix_support', 0.0) or 0.0) <= 0.005
        and float(support.get('mix_support', 0.0) or 0.0) <= 0.005
        and float(support.get('heuristic_mix_support', 0.0) or 0.0) <= 0.020
    )


def print_sample(prefix: str, sample: dict) -> None:
    diagnosis = sample.get('voice_rule_diagnosis', {}) or {}
    voice = diagnosis.get('voice_features', {}) or {}
    support = diagnosis.get('supports', {}) or {}
    subtype = diagnosis.get('subtype_eval', {}) or {}
    print('|'.join([
        prefix,
        str(sample.get('item_name', '') or ''),
        str(sample.get('outcome', '') or ''),
        ','.join(list(diagnosis.get('blockers', []) or [])),
        str(subtype.get('candidate_subtype', '') or ''),
        f"pitch={float(voice.get('mean_pitch_hz', 0.0) or 0.0):.3f}",
        f"dur={float(voice.get('duration', 0.0) or 0.0):.3f}",
        f"head={float(support.get('head_bias', 0.0) or 0.0):.6f}",
        f"chestbias={float(support.get('chest_bias', 0.0) or 0.0):.6f}",
        f"chest={float(voice.get('chest_prob', 0.0) or 0.0):.6f}",
        f"fal={float(voice.get('falsetto_prob', 0.0) or 0.0):.6f}",
        f"lmp={float(voice.get('learned_mix_prob', 0.0) or 0.0):.6f}",
        f"thr={float(voice.get('learned_mix_threshold', 0.0) or 0.0):.6f}",
        f"margin={float(voice.get('learned_mix_margin', 0.0) or 0.0):.6f}",
        f"rms={float(voice.get('mean_rms', 0.0) or 0.0):.6f}",
        f"lms={float(support.get('learned_mix_support', 0.0) or 0.0):.6f}",
        f"mix={float(support.get('mix_support', 0.0) or 0.0):.6f}",
        f"heur={float(support.get('heuristic_mix_support', 0.0) or 0.0):.6f}",
        f"weak={float(support.get('weak_mix_support', 0.0) or 0.0):.6f}",
        f"floor={float(support.get('weak_mix_support_floor', 0.0) or 0.0):.6f}",
    ]))


def main() -> None:
    args = parse_args()
    config = load_config()
    groups = list(args.group or []) or ['validation_fn_systematic', 'test_fn_systematic24']

    for group_name in groups:
        output_path, misses = run_group(config, group_name)
        print(f'group {group_name}')
        print(f'output {output_path.name}')
        print(f'miss_count {len(misses)}')
        print('blockers')
        for blocker_text, count in summarize_blockers(misses):
            print(f'{count}|{blocker_text}')

        zero_support_highpitch = [sample for sample in misses if is_zero_support_highpitch(sample)]
        print(f'zero_support_highpitch_miss_count {len(zero_support_highpitch)}')
        for sample in sorted(
            zero_support_highpitch,
            key=lambda item: (
                float((item.get('voice_rule_diagnosis', {}) or {}).get('voice_features', {}).get('mean_pitch_hz', 0.0) or 0.0),
                -float((item.get('voice_rule_diagnosis', {}) or {}).get('voice_features', {}).get('learned_mix_prob', 0.0) or 0.0),
            ),
            reverse=True,
        ):
            print_sample('zero_support_highpitch', sample)

        print('all_misses')
        for sample in sorted(
            misses,
            key=lambda item: (
                float((item.get('voice_rule_diagnosis', {}) or {}).get('supports', {}).get('learned_mix_support', 0.0) or 0.0),
                float((item.get('voice_rule_diagnosis', {}) or {}).get('voice_features', {}).get('mean_pitch_hz', 0.0) or 0.0),
            ),
        ):
            print_sample('miss', sample)


if __name__ == '__main__':
    main()