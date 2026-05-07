import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_PATHS = {
    'validation_fn': ROOT / '_tmp_validation_fn_systematic_probe_current.json',
    'test_fn': ROOT / '_tmp_test_fn_systematic24_probe_current.json',
    'validation_fp': ROOT / '_tmp_validation_fp_systematic_probe_current.json',
    'test_fp': ROOT / '_tmp_test_fp_systematic_probe_current.json',
}


def load_samples(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    return list((payload.get('artifacts') or [{}])[0].get('samples') or [])


def matches(sample: dict, spec: dict) -> bool:
    diagnosis = sample.get('voice_rule_diagnosis', {}) or {}
    voice = diagnosis.get('voice_features', {}) or {}
    support = diagnosis.get('supports', {}) or {}

    head_bias = float(support.get('head_bias', 0.0) or 0.0)
    learned_mix_prob = float(voice.get('learned_mix_prob', 0.0) or 0.0)
    learned_mix_margin = float(voice.get('learned_mix_margin', 0.0) or 0.0)
    mean_pitch_hz = float(voice.get('mean_pitch_hz', 0.0) or 0.0)
    chest_prob = float(voice.get('chest_prob', 0.0) or 0.0)
    falsetto_prob = float(voice.get('falsetto_prob', 0.0) or 0.0)
    duration = float(voice.get('duration', 0.0) or 0.0)
    mean_rms = float(voice.get('mean_rms', 0.0) or 0.0)
    heuristic_mix_support = float(support.get('heuristic_mix_support', 0.0) or 0.0)
    learned_mix_support = float(support.get('learned_mix_support', 0.0) or 0.0)
    mix_support = float(support.get('mix_support', 0.0) or 0.0)

    return (
        head_bias >= spec['head_bias_min']
        and learned_mix_prob >= spec['learned_mix_prob_min']
        and learned_mix_prob <= spec['learned_mix_prob_max']
        and learned_mix_margin >= spec['learned_mix_margin_min']
        and learned_mix_margin <= spec['learned_mix_margin_max']
        and mean_pitch_hz >= spec['mean_pitch_hz_min']
        and mean_pitch_hz <= spec['mean_pitch_hz_max']
        and chest_prob >= spec['chest_prob_min']
        and chest_prob <= spec['chest_prob_max']
        and falsetto_prob >= spec['falsetto_prob_min']
        and falsetto_prob <= spec['falsetto_prob_max']
        and duration >= spec['duration_min']
        and duration <= spec['duration_max']
        and mean_rms >= spec['mean_rms_min']
        and mean_rms <= spec['mean_rms_max']
        and heuristic_mix_support <= spec['heuristic_mix_support_max']
        and learned_mix_support <= spec['learned_mix_support_max']
        and mix_support <= spec['mix_support_max']
    )


def main() -> None:
    specs = {
        'short_ultrahigh_zero_support': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.360,
            'learned_mix_prob_max': 0.430,
            'learned_mix_margin_min': -0.280,
            'learned_mix_margin_max': -0.200,
            'mean_pitch_hz_min': 540.0,
            'mean_pitch_hz_max': 575.0,
            'chest_prob_min': 0.020,
            'chest_prob_max': 0.050,
            'falsetto_prob_min': 0.950,
            'falsetto_prob_max': 0.980,
            'duration_min': 1.5,
            'duration_max': 3.2,
            'mean_rms_min': 0.080,
            'mean_rms_max': 0.120,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
        'ultrahigh_chestier_zero_support': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.350,
            'learned_mix_prob_max': 0.430,
            'learned_mix_margin_min': -0.300,
            'learned_mix_margin_max': -0.200,
            'mean_pitch_hz_min': 640.0,
            'mean_pitch_hz_max': 730.0,
            'chest_prob_min': 0.045,
            'chest_prob_max': 0.070,
            'falsetto_prob_min': 0.930,
            'falsetto_prob_max': 0.955,
            'duration_min': 12.0,
            'duration_max': 18.0,
            'mean_rms_min': 0.080,
            'mean_rms_max': 0.120,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
        'extreme_lowprob_zero_support': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.150,
            'learned_mix_prob_max': 0.220,
            'learned_mix_margin_min': -0.500,
            'learned_mix_margin_max': -0.400,
            'mean_pitch_hz_min': 520.0,
            'mean_pitch_hz_max': 550.0,
            'chest_prob_min': 0.020,
            'chest_prob_max': 0.035,
            'falsetto_prob_min': 0.970,
            'falsetto_prob_max': 0.985,
            'duration_min': 12.0,
            'duration_max': 18.0,
            'mean_rms_min': 0.050,
            'mean_rms_max': 0.080,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
        'headbiased_lowprob_zero_support_long_combo': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.390,
            'learned_mix_prob_max': 0.430,
            'learned_mix_margin_min': -0.280,
            'learned_mix_margin_max': -0.200,
            'mean_pitch_hz_min': 380.0,
            'mean_pitch_hz_max': 730.0,
            'chest_prob_min': 0.020,
            'chest_prob_max': 0.130,
            'falsetto_prob_min': 0.870,
            'falsetto_prob_max': 0.980,
            'duration_min': 5.0,
            'duration_max': 18.0,
            'mean_rms_min': 0.060,
            'mean_rms_max': 0.120,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
        'headbiased_lowprob_zero_support_combo_including_short': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.390,
            'learned_mix_prob_max': 0.430,
            'learned_mix_margin_min': -0.280,
            'learned_mix_margin_max': -0.200,
            'mean_pitch_hz_min': 380.0,
            'mean_pitch_hz_max': 730.0,
            'chest_prob_min': 0.020,
            'chest_prob_max': 0.130,
            'falsetto_prob_min': 0.870,
            'falsetto_prob_max': 0.980,
            'duration_min': 1.5,
            'duration_max': 18.0,
            'mean_rms_min': 0.060,
            'mean_rms_max': 0.120,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
        'midhigh_headbiased_zero_support_combo': {
            'head_bias_min': 0.99,
            'learned_mix_prob_min': 0.410,
            'learned_mix_prob_max': 0.430,
            'learned_mix_margin_min': -0.235,
            'learned_mix_margin_max': -0.205,
            'mean_pitch_hz_min': 385.0,
            'mean_pitch_hz_max': 420.0,
            'chest_prob_min': 0.075,
            'chest_prob_max': 0.125,
            'falsetto_prob_min': 0.870,
            'falsetto_prob_max': 0.930,
            'duration_min': 5.0,
            'duration_max': 9.0,
            'mean_rms_min': 0.079,
            'mean_rms_max': 0.115,
            'heuristic_mix_support_max': 0.020,
            'learned_mix_support_max': 0.002,
            'mix_support_max': 0.002,
        },
    }

    reports = {name: load_samples(path) for name, path in REPORT_PATHS.items()}
    for spec_name, spec in specs.items():
        print(spec_name)
        for report_name, samples in reports.items():
            matched = [sample for sample in samples if matches(sample, spec)]
            print(f'{report_name}|count={len(matched)}')
            for sample in matched:
                diagnosis = sample.get('voice_rule_diagnosis', {}) or {}
                voice = diagnosis.get('voice_features', {}) or {}
                print('|'.join([
                    report_name,
                    str(sample.get('item_name', '') or ''),
                    str(sample.get('outcome', '') or ''),
                    f"pitch={float(voice.get('mean_pitch_hz', 0.0) or 0.0):.3f}",
                    f"dur={float(voice.get('duration', 0.0) or 0.0):.3f}",
                    f"lmp={float(voice.get('learned_mix_prob', 0.0) or 0.0):.6f}",
                    f"margin={float(voice.get('learned_mix_margin', 0.0) or 0.0):.6f}",
                ]))


if __name__ == '__main__':
    main()