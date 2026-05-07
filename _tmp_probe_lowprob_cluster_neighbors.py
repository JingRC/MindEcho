import json
import math
import sys
from pathlib import Path


TARGET_ITEMS = {
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#红玫瑰#Mixed_Voice_Group#0008',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#爱情转移#Mixed_Voice_Group#0009',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#我的歌声里#Mixed_Voice_Group#0008',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#给电影人的情书#Mixed_Voice_Group#0002',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#演员#Mixed_Voice_Group#0003',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#演员#Mixed_Voice_Group#0022',
}

FEATURE_SCALES = {
    'mean_pitch_hz': 120.0,
    'duration': 4.0,
    'mean_rms': 0.04,
    'chest_prob': 0.10,
    'falsetto_prob': 0.10,
    'learned_mix_prob': 0.10,
}


def feature_vector(sample: dict) -> dict:
    voice = sample.get('voice_rule_diagnosis', {}).get('voice_features', {})
    return {
        'mean_pitch_hz': float(voice.get('mean_pitch_hz', 0.0) or 0.0),
        'duration': float(voice.get('duration', 0.0) or 0.0),
        'mean_rms': float(voice.get('mean_rms', 0.0) or 0.0),
        'chest_prob': float(voice.get('chest_prob', 0.0) or 0.0),
        'falsetto_prob': float(voice.get('falsetto_prob', 0.0) or 0.0),
        'learned_mix_prob': float(voice.get('learned_mix_prob', 0.0) or 0.0),
    }


def distance(left: dict, right: dict) -> float:
    total = 0.0
    for key, scale in FEATURE_SCALES.items():
        total += ((left[key] - right[key]) / scale) ** 2
    return math.sqrt(total)


def main() -> None:
    root = Path(__file__).resolve().parent
    report_path = root / '_tmp_mix_rule_guarded_alto_below_threshold_runtimeaware_trainadapt_v13.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    samples = list(report['artifacts'][0]['samples'])

    requested_items = {item for item in sys.argv[1:] if item}
    target_items = requested_items or TARGET_ITEMS
    targets = [sample for sample in samples if sample.get('item_name') in target_items]
    controls = [sample for sample in samples if sample.get('binary_role') == 'control_negative']

    print('targets')
    for sample in targets:
        voice = sample.get('voice_rule_diagnosis', {}).get('voice_features', {})
        support = sample.get('voice_rule_diagnosis', {}).get('supports', {})
        print('|'.join([
            sample['item_name'],
            f"pitch={float(voice.get('mean_pitch_hz', 0.0)):.3f}",
            f"dur={float(voice.get('duration', 0.0)):.3f}",
            f"rms={float(voice.get('mean_rms', 0.0)):.6f}",
            f"chest={float(voice.get('chest_prob', 0.0)):.6f}",
            f"fal={float(voice.get('falsetto_prob', 0.0)):.6f}",
            f"lmp={float(voice.get('learned_mix_prob', 0.0)):.6f}",
            f"lms={float(support.get('learned_mix_support', 0.0)):.6f}",
            f"mix={float(support.get('mix_support', 0.0)):.6f}",
        ]))

    print('nearest_controls')
    control_vectors = [(sample, feature_vector(sample)) for sample in controls]
    for sample in targets:
        target_vector = feature_vector(sample)
        nearest = sorted(
            (
                distance(target_vector, control_vector),
                control_sample,
            )
            for control_sample, control_vector in control_vectors
        )[:5]
        print(sample['item_name'])
        for score, control_sample in nearest:
            voice = control_sample.get('voice_rule_diagnosis', {}).get('voice_features', {})
            support = control_sample.get('voice_rule_diagnosis', {}).get('supports', {})
            print('  ' + '|'.join([
                f'd={score:.3f}',
                control_sample['item_name'],
                f"pitch={float(voice.get('mean_pitch_hz', 0.0)):.3f}",
                f"dur={float(voice.get('duration', 0.0)):.3f}",
                f"rms={float(voice.get('mean_rms', 0.0)):.6f}",
                f"chest={float(voice.get('chest_prob', 0.0)):.6f}",
                f"fal={float(voice.get('falsetto_prob', 0.0)):.6f}",
                f"lmp={float(voice.get('learned_mix_prob', 0.0)):.6f}",
                f"lms={float(support.get('learned_mix_support', 0.0)):.6f}",
                f"mix={float(support.get('mix_support', 0.0)):.6f}",
            ]))


if __name__ == '__main__':
    main()