import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'regression_tests' / 'mix_runtime_systematic_cluster_config.json'
DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'
TARGET_GROUPS = ('validation_fn_systematic', 'test_fn_systematic24')
OUTPUT_PATH = ROOT / '_tmp_reject_no_subtype_residuals_current.json'


def run_group(config, group_name):
    group = next(item for item in list(config.get('groups', []) or []) if str(item.get('name', '') or '') == group_name)
    with tempfile.TemporaryDirectory(prefix='mindecho_reject_no_subtype_') as temp_dir:
        output_path = Path(temp_dir) / f'{group_name}.json'
        command = [
            sys.executable,
            str(DIAGNOSE_SCRIPT),
            '--manifest',
            str(ROOT / str(group.get('manifest', '') or '')),
            '--artifact',
            str(ROOT / str(config.get('artifact_dir', '') or '')),
            '--output',
            str(output_path),
        ]
        for item_name in list(group.get('item_names', []) or []):
            command.extend(['--item-name', str(item_name)])
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            check=False,
            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        )
        if completed.returncode != 0:
            raise RuntimeError(f'failed group {group_name}: rc={completed.returncode}')
        return json.loads(output_path.read_text(encoding='utf-8'))


def sample_record(sample):
    diagnosis = dict(sample.get('voice_rule_diagnosis', {}) or {})
    voice_features = dict(diagnosis.get('voice_features', {}) or {})
    supports = dict(diagnosis.get('supports', {}) or {})
    subtype_eval = dict(diagnosis.get('subtype_eval', {}) or {})
    blockers = list(diagnosis.get('blockers', []) or [])
    best_voice_event = dict(sample.get('best_voice_event', {}) or {})
    best_voice_snapshot = dict(best_voice_event.get('feature_snapshot', {}) or {})
    strongest_mix_event = dict(sample.get('strongest_mix_event', {}) or {})
    voice_debug = dict(sample.get('voice_debug', {}) or {})
    start_time = float(best_voice_event.get('start_time', 0.0) or 0.0)
    end_time = float(best_voice_event.get('end_time', 0.0) or 0.0)
    return {
        'item_name': str(sample.get('item_name', '') or ''),
        'song_name': str(sample.get('song_name', '') or ''),
        'outcome': str(sample.get('outcome', '') or ''),
        'miss_reason': str(sample.get('miss_reason', '') or ''),
        'mix_event_count': int(sample.get('mix_event_count', 0) or 0),
        'weak_mix_count': int(sample.get('weak_mix_count', 0) or 0),
        'blockers': blockers,
        'candidate_subtype': str(subtype_eval.get('candidate_subtype', '') or ''),
        'candidate_subtype_conf': float(subtype_eval.get('candidate_subtype_conf', 0.0) or 0.0),
        'best_voice_event_type': str(best_voice_event.get('event_type', '') or ''),
        'best_voice_voice_type': str(best_voice_event.get('voice_type', '') or ''),
        'best_voice_duration': max(0.0, end_time - start_time),
        'best_voice_confidence': float(best_voice_event.get('confidence', 0.0) or 0.0),
        'best_voice_strength': float(best_voice_event.get('strength', 0.0) or 0.0),
        'best_voice_mix_prob': float(best_voice_event.get('mix_prob', 0.0) or 0.0),
        'best_voice_mix_threshold': float(best_voice_event.get('mix_threshold', 0.0) or 0.0),
        'best_voice_probability_margin': float(best_voice_event.get('probability_margin', best_voice_snapshot.get('probability_margin', 0.0)) or 0.0),
        'best_voice_mean_pitch_hz': float(best_voice_event.get('mean_pitch_hz', 0.0) or 0.0),
        'best_voice_chest_prob': float(best_voice_event.get('chest_prob', 0.0) or 0.0),
        'best_voice_falsetto_prob': float(best_voice_event.get('falsetto_prob', 0.0) or 0.0),
        'best_voice_mean_rms': float(best_voice_snapshot.get('mean_rms', 0.0) or 0.0),
        'best_voice_stable_ratio': float(best_voice_snapshot.get('stable_ratio', 0.0) or 0.0),
        'best_voice_voiced_ratio': float(best_voice_snapshot.get('voiced_ratio', 0.0) or 0.0),
        'strongest_mix_event_type': str(strongest_mix_event.get('event_type', '') or ''),
        'strongest_mix_subtype': str(strongest_mix_event.get('subtype', '') or ''),
        'strongest_mix_mix_support': float(strongest_mix_event.get('mix_support_score', 0.0) or 0.0),
        'strongest_mix_mix_prob': float(strongest_mix_event.get('mix_prob', 0.0) or 0.0),
        'strongest_mix_mean_pitch_hz': float(strongest_mix_event.get('mean_pitch_hz', 0.0) or 0.0),
        'voice_debug_reason': str(voice_debug.get('reason', '') or ''),
        'voice_debug_candidate_windows': int(voice_debug.get('candidate_windows', 0) or 0),
        'voice_debug_predicted_windows': int(voice_debug.get('predicted_windows', 0) or 0),
        'voice_debug_accepted_windows': int(voice_debug.get('accepted_windows', 0) or 0),
        'voice_debug_context_adjusted_windows': int(voice_debug.get('context_adjusted_windows', 0) or 0),
        'voice_debug_relaxed_used': bool(voice_debug.get('relaxed_used', False)),
        'voice_debug_backend': str(voice_debug.get('backend', '') or ''),
        'mix_prob': float(voice_features.get('learned_mix_prob', 0.0) or 0.0),
        'mix_threshold': float(voice_features.get('learned_mix_threshold', 0.0) or 0.0),
        'learned_mix_margin': float(voice_features.get('learned_mix_margin', 0.0) or 0.0),
        'probability_margin': float(voice_features.get('probability_margin', 0.0) or 0.0),
        'mix_support': float(supports.get('mix_support', 0.0) or 0.0),
        'heuristic_mix_support': float(supports.get('heuristic_mix_support', 0.0) or 0.0),
        'learned_mix_support': float(supports.get('learned_mix_support', 0.0) or 0.0),
        'weak_mix_support': float(supports.get('weak_mix_support', 0.0) or 0.0),
        'weak_mix_support_floor': float(supports.get('weak_mix_support_floor', 0.0) or 0.0),
        'head_bias': float(supports.get('head_bias', 0.0) or 0.0),
        'chest_bias': float(supports.get('chest_bias', 0.0) or 0.0),
        'pitch_support': float(supports.get('pitch_support', 0.0) or 0.0),
        'stable_support': float(supports.get('stable_support', 0.0) or 0.0),
        'voiced_support': float(supports.get('voiced_support', 0.0) or 0.0),
        'breathiness': float(supports.get('breathiness', 0.0) or 0.0),
        'mean_pitch_hz': float(voice_features.get('mean_pitch_hz', 0.0) or 0.0),
        'chest_prob': float(voice_features.get('chest_prob', 0.0) or 0.0),
        'falsetto_prob': float(voice_features.get('falsetto_prob', 0.0) or 0.0),
        'mean_rms': float(voice_features.get('mean_rms', 0.0) or 0.0),
        'duration': float(voice_features.get('duration', 0.0) or 0.0),
        'stable_ratio': float(voice_features.get('stable_ratio', 0.0) or 0.0),
        'voiced_ratio': float(voice_features.get('voiced_ratio', 0.0) or 0.0),
    }


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    report = {}
    summary = {}
    for group_name in TARGET_GROUPS:
        payload = run_group(config, group_name)
        artifacts = list(payload.get('artifacts', []) or [])
        samples = list(artifacts[0].get('samples', []) or []) if artifacts else []
        residuals = []
        for sample in samples:
            if str(sample.get('outcome', '') or '') == 'hit':
                continue
            record = sample_record(sample)
            if 'reject_no_subtype' not in record['blockers']:
                continue
            residuals.append(record)
        report[group_name] = residuals
        summary[group_name] = {
            'residual_count': len(residuals),
            'mix_event_zero_count': sum(1 for item in residuals if int(item.get('mix_event_count', 0) or 0) == 0),
            'best_voice_type_counts': {
                'falsetto': sum(1 for item in residuals if str(item.get('best_voice_voice_type', '') or '') == 'falsetto'),
                'chest': sum(1 for item in residuals if str(item.get('best_voice_voice_type', '') or '') == 'chest'),
                'other_or_empty': sum(1 for item in residuals if str(item.get('best_voice_voice_type', '') or '') not in {'falsetto', 'chest'}),
            },
        }
    payload = {
        'summary': summary,
        'groups': report,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output_path': str(OUTPUT_PATH), 'summary': summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())