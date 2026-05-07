import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESIDUAL_REPORT = ROOT / '_tmp_reject_no_subtype_residuals_current.json'
FP_REPORTS = {
    'validation_fp': ROOT / '_tmp_validation_fp_systematic_probe_current.json',
    'test_fp': ROOT / '_tmp_test_fp_systematic_probe_current.json',
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def residual_samples(group_name: str) -> list[dict]:
    payload = load_json(RESIDUAL_REPORT)
    return list((payload.get('groups') or {}).get(group_name) or [])


def fp_samples(report_name: str) -> list[dict]:
    payload = load_json(FP_REPORTS[report_name])
    artifacts = list(payload.get('artifacts') or [])
    return list((artifacts[0] if artifacts else {}).get('samples') or [])


def extract_features(sample: dict, source: str) -> dict:
    if source == 'residual':
        chest_prob = float(sample.get('best_voice_chest_prob', 0.0) or 0.0)
        falsetto_prob = float(sample.get('best_voice_falsetto_prob', 0.0) or 0.0)
        mix_prob = float(sample.get('best_voice_mix_prob', 0.0) or 0.0)
        mix_threshold = float(sample.get('best_voice_mix_threshold', 0.64) or 0.64)
        mean_pitch_hz = float(sample.get('best_voice_mean_pitch_hz', 0.0) or 0.0)
        duration = float(sample.get('best_voice_duration', 0.0) or 0.0)
        mean_rms = float(sample.get('best_voice_mean_rms', 0.0) or 0.0)
        learned_mix_support = float(sample.get('learned_mix_support', 0.0) or 0.0)
        mix_support = float(sample.get('mix_support', 0.0) or 0.0)
        weak_mix_support = float(sample.get('weak_mix_support', 0.0) or 0.0)
        item_name = str(sample.get('item_name', '') or '')
        outcome = str(sample.get('outcome', '') or '')
    else:
        diagnosis = dict(sample.get('voice_rule_diagnosis', {}) or {})
        voice = dict(diagnosis.get('voice_features', {}) or {})
        supports = dict(diagnosis.get('supports', {}) or {})
        chest_prob = float(voice.get('chest_prob', 0.0) or 0.0)
        falsetto_prob = float(voice.get('falsetto_prob', 0.0) or 0.0)
        mix_prob = float(voice.get('learned_mix_prob', 0.0) or 0.0)
        mix_threshold = float(voice.get('learned_mix_threshold', 0.64) or 0.64)
        mean_pitch_hz = float(voice.get('mean_pitch_hz', 0.0) or 0.0)
        duration = float(voice.get('duration', 0.0) or 0.0)
        mean_rms = float(voice.get('mean_rms', 0.0) or 0.0)
        learned_mix_support = float(supports.get('learned_mix_support', 0.0) or 0.0)
        mix_support = float(supports.get('mix_support', 0.0) or 0.0)
        weak_mix_support = float(supports.get('weak_mix_support', 0.0) or 0.0)
        item_name = str(sample.get('item_name', '') or '')
        outcome = str(sample.get('outcome', '') or '')
    head_bias = max(0.0, min(1.0, (falsetto_prob - chest_prob + 0.18) / 0.50))
    return {
        'item_name': item_name,
        'outcome': outcome,
        'mix_prob': mix_prob,
        'mix_threshold': mix_threshold,
        'mix_margin': mix_prob - mix_threshold if mix_prob > 0.0 else 0.0,
        'mean_pitch_hz': mean_pitch_hz,
        'duration': duration,
        'mean_rms': mean_rms,
        'learned_mix_support': learned_mix_support,
        'mix_support': mix_support,
        'weak_mix_support': weak_mix_support,
        'chest_prob': chest_prob,
        'falsetto_prob': falsetto_prob,
        'head_bias': head_bias,
    }


def matches(features: dict, spec: dict) -> bool:
    return (
        features['head_bias'] >= spec['head_bias_min']
        and features['mix_prob'] >= spec['mix_prob_min']
        and features['mix_prob'] <= spec['mix_prob_max']
        and features['mix_margin'] >= spec['mix_margin_min']
        and features['mix_margin'] <= spec['mix_margin_max']
        and features['mean_pitch_hz'] >= spec['mean_pitch_hz_min']
        and features['mean_pitch_hz'] <= spec['mean_pitch_hz_max']
        and features['duration'] >= spec.get('duration_min', 0.0)
        and features['duration'] <= spec.get('duration_max', 999.0)
        and features['mean_rms'] >= spec.get('mean_rms_min', 0.0)
        and features['mean_rms'] <= spec.get('mean_rms_max', 999.0)
        and features['learned_mix_support'] >= spec.get('learned_mix_support_min', 0.0)
        and features['learned_mix_support'] <= spec.get('learned_mix_support_max', 999.0)
        and features['mix_support'] >= spec.get('mix_support_min', 0.0)
        and features['mix_support'] <= spec.get('mix_support_max', 999.0)
        and features['weak_mix_support'] >= spec.get('weak_mix_support_min', 0.0)
        and features['weak_mix_support'] <= spec.get('weak_mix_support_max', 999.0)
        and features['chest_prob'] >= spec['chest_prob_min']
        and features['chest_prob'] <= spec['chest_prob_max']
        and features['falsetto_prob'] >= spec['falsetto_prob_min']
        and features['falsetto_prob'] <= spec['falsetto_prob_max']
    )


def main() -> None:
    specs = {
        'crosssplit_midhigh_falsetto_lowprob_loose': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.20,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.44,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 320.0,
            'mean_pitch_hz_max': 400.0,
            'chest_prob_min': 0.12,
            'chest_prob_max': 0.23,
            'falsetto_prob_min': 0.78,
            'falsetto_prob_max': 0.88,
        },
        'crosssplit_midhigh_falsetto_lowprob_longform': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.20,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.44,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 320.0,
            'mean_pitch_hz_max': 400.0,
            'duration_min': 5.0,
            'duration_max': 15.5,
            'mean_rms_min': 0.030,
            'mean_rms_max': 0.090,
            'chest_prob_min': 0.12,
            'chest_prob_max': 0.23,
            'falsetto_prob_min': 0.78,
            'falsetto_prob_max': 0.88,
        },
        'crosssplit_midhigh_falsetto_lowprob_longform_hotter': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.20,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.44,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 320.0,
            'mean_pitch_hz_max': 400.0,
            'duration_min': 5.0,
            'duration_max': 15.5,
            'mean_rms_min': 0.045,
            'mean_rms_max': 0.090,
            'chest_prob_min': 0.12,
            'chest_prob_max': 0.23,
            'falsetto_prob_min': 0.78,
            'falsetto_prob_max': 0.88,
        },
        'supportful_midhigh_nearthreshold_midband': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.52,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.13,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 315.0,
            'mean_pitch_hz_max': 370.0,
            'duration_min': 5.0,
            'duration_max': 8.5,
            'mean_rms_min': 0.045,
            'mean_rms_max': 0.065,
            'learned_mix_support_min': 0.01,
            'learned_mix_support_max': 0.08,
            'mix_support_min': 0.01,
            'mix_support_max': 0.05,
            'weak_mix_support_min': 0.01,
            'weak_mix_support_max': 0.05,
            'chest_prob_min': 0.19,
            'chest_prob_max': 0.22,
            'falsetto_prob_min': 0.78,
            'falsetto_prob_max': 0.81,
        },
        'supportful_midhigh_nearthreshold_stay_relaxed': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.52,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.13,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 305.0,
            'mean_pitch_hz_max': 370.0,
            'duration_min': 5.0,
            'duration_max': 8.5,
            'mean_rms_min': 0.045,
            'mean_rms_max': 0.065,
            'learned_mix_support_min': 0.01,
            'learned_mix_support_max': 0.08,
            'mix_support_min': 0.01,
            'mix_support_max': 0.05,
            'weak_mix_support_min': 0.01,
            'weak_mix_support_max': 0.05,
            'chest_prob_min': 0.19,
            'chest_prob_max': 0.226,
            'falsetto_prob_min': 0.774,
            'falsetto_prob_max': 0.81,
        },
        'supportful_highpitch_nearthreshold_airy': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.53,
            'mix_prob_max': 0.55,
            'mix_margin_min': -0.12,
            'mix_margin_max': -0.09,
            'mean_pitch_hz_min': 540.0,
            'mean_pitch_hz_max': 590.0,
            'duration_min': 0.6,
            'duration_max': 1.2,
            'mean_rms_min': 0.0005,
            'mean_rms_max': 0.0030,
            'learned_mix_support_min': 0.03,
            'learned_mix_support_max': 0.06,
            'mix_support_min': 0.02,
            'mix_support_max': 0.04,
            'weak_mix_support_min': 0.02,
            'weak_mix_support_max': 0.04,
            'chest_prob_min': 0.16,
            'chest_prob_max': 0.19,
            'falsetto_prob_min': 0.81,
            'falsetto_prob_max': 0.83,
        },
        'crosssplit_midhigh_falsetto_lowprob_midband': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.20,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.44,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 300.0,
            'mean_pitch_hz_max': 405.0,
            'chest_prob_min': 0.12,
            'chest_prob_max': 0.24,
            'falsetto_prob_min': 0.76,
            'falsetto_prob_max': 0.88,
        },
        'testheavy_ultrahigh_falsetto_lowprob': {
            'head_bias_min': 0.99,
            'mix_prob_min': 0.17,
            'mix_prob_max': 0.56,
            'mix_margin_min': -0.47,
            'mix_margin_max': -0.08,
            'mean_pitch_hz_min': 520.0,
            'mean_pitch_hz_max': 710.0,
            'chest_prob_min': 0.02,
            'chest_prob_max': 0.19,
            'falsetto_prob_min': 0.82,
            'falsetto_prob_max': 0.98,
        },
    }

    groups = {
        'validation_fn_residual': [extract_features(item, 'residual') for item in residual_samples('validation_fn_systematic')],
        'test_fn_residual': [extract_features(item, 'residual') for item in residual_samples('test_fn_systematic24')],
        'validation_fp': [extract_features(item, 'fp') for item in fp_samples('validation_fp')],
        'test_fp': [extract_features(item, 'fp') for item in fp_samples('test_fp')],
    }

    for spec_name, spec in specs.items():
        print(spec_name)
        for group_name, samples in groups.items():
            matched = [item for item in samples if matches(item, spec)]
            print(f'{group_name}|count={len(matched)}')
            for item in matched:
                print('|'.join([
                    group_name,
                    item['item_name'],
                    item['outcome'],
                    f"pitch={item['mean_pitch_hz']:.3f}",
                    f"dur={item['duration']:.3f}",
                    f"rms={item['mean_rms']:.6f}",
                    f"mix_prob={item['mix_prob']:.6f}",
                    f"margin={item['mix_margin']:.6f}",
                    f"lms={item['learned_mix_support']:.6f}",
                    f"ms={item['mix_support']:.6f}",
                    f"chest={item['chest_prob']:.6f}",
                    f"fal={item['falsetto_prob']:.6f}",
                ]))


if __name__ == '__main__':
    main()