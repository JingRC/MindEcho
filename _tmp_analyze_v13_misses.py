import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    report_name = sys.argv[1] if len(sys.argv) > 1 else '_tmp_mix_rule_guarded_alto_below_threshold_runtimeaware_trainadapt_v13.json'
    report_path = root / report_name
    report = json.loads(report_path.read_text(encoding='utf-8'))
    samples = list(report['artifacts'][0]['samples'])
    misses = [
        sample
        for sample in samples
        if sample.get('binary_role') == 'positive_mix' and sample.get('outcome') != 'hit'
    ]

    print(f'miss_count {len(misses)}')
    print('blockers')
    blocker_counts = Counter(
        tuple(sample.get('voice_rule_diagnosis', {}).get('blockers', []) or [])
        for sample in misses
    )
    for blockers, count in blocker_counts.most_common():
        print(f'{count}|{",".join(blockers)}')

    print('candidate_subtypes')
    subtype_counts = Counter(
        str(sample.get('voice_rule_diagnosis', {}).get('subtype_eval', {}).get('candidate_subtype', '') or '')
        for sample in misses
    )
    for subtype, count in subtype_counts.most_common():
        print(f'{count}|{subtype}')

    print('---details---')
    for sample in misses:
        diagnosis = sample.get('voice_rule_diagnosis', {}) or {}
        voice = diagnosis.get('voice_features', {}) or {}
        support = diagnosis.get('supports', {}) or {}
        subtype = diagnosis.get('subtype_eval', {}) or {}
        print('|'.join([
            str(sample.get('item_name', '')),
            ','.join(diagnosis.get('blockers', []) or []),
            str(subtype.get('candidate_subtype', '') or ''),
            f"pitch={float(voice.get('mean_pitch_hz', 0.0)):.3f}",
            f"dur={float(voice.get('duration', 0.0)):.3f}",
            f"rms={float(voice.get('mean_rms', 0.0)):.6f}",
            f"chest={float(voice.get('chest_prob', 0.0)):.6f}",
            f"fal={float(voice.get('falsetto_prob', 0.0)):.6f}",
            f"lmp={float(voice.get('learned_mix_prob', 0.0)):.6f}",
            f"margin={float(voice.get('learned_mix_margin', 0.0)):.6f}",
            f"lms={float(support.get('learned_mix_support', 0.0)):.6f}",
            f"mix={float(support.get('mix_support', 0.0)):.6f}",
            f"heur={float(support.get('heuristic_mix_support', 0.0)):.6f}",
        ]))


if __name__ == '__main__':
    main()