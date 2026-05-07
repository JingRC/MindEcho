import json
import sys

import debug_mix_rule_offline as d


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('usage: python _tmp_probe_raw_0004.py <wav_path>')
    wav_path = str(sys.argv[1])

    app, module, ui, _ = d.load_runtime(False)
    onepass_payload, worker = d.run_onepass_worker(app, module, ui, wav_path)
    audio, sr = d.decode_audio_for_analysis(module, ui, worker, wav_path)
    ui._onepass_analysis_payload = {
        'segments': list(onepass_payload.get('segments', []) or []),
        'duration': float(onepass_payload.get('duration', 0.0) or 0.0),
    }
    ui._in_onepass_mode = True
    resolved = ui._resolve_technique_analysis_payload()
    frames = list(resolved.get('frames', []) or [])
    visualizer = ui.visualizer
    voice_events = visualizer._build_offline_chest_falsetto_events(frames, audio_samples=audio, sample_rate=sr)
    mix_events = visualizer._build_rule_based_mix_events(frames, voice_events)
    out = []
    for event in voice_events:
        snapshot = dict(getattr(event, 'feature_snapshot', {}) or {})
        out.append(
            {
                'event_type': getattr(event, 'event_type', ''),
                'start_time': round(float(getattr(event, 'start_time', 0.0) or 0.0), 6),
                'end_time': round(float(getattr(event, 'end_time', 0.0) or 0.0), 6),
                'confidence': round(float(getattr(event, 'confidence', 0.0) or 0.0), 6),
                'mean_pitch_hz': round(float(getattr(event, 'mean_pitch_hz', 0.0) or 0.0), 6),
                'voiced_ratio': round(float(getattr(event, 'voiced_ratio', 0.0) or 0.0), 6),
                'chest_prob': round(float(getattr(event, 'chest_prob', 0.0) or 0.0), 6),
                'falsetto_prob': round(float(getattr(event, 'falsetto_prob', 0.0) or 0.0), 6),
                'mix_prob': round(float(getattr(event, 'mix_prob', 0.0) or 0.0), 6),
                'probability_margin': round(float(getattr(event, 'probability_margin', 0.0) or 0.0), 6),
                'snapshot': {
                    'mix_prob': round(float(snapshot.get('mix_prob', 0.0) or 0.0), 6),
                    'mix_threshold': round(float(snapshot.get('mix_threshold', 0.0) or 0.0), 6),
                    'mean_rms': round(float(snapshot.get('mean_rms', 0.0) or 0.0), 6),
                    'stable_ratio': round(float(snapshot.get('stable_ratio', 0.0) or 0.0), 6),
                    'mean_pitch_hz': round(float(snapshot.get('mean_pitch_hz', 0.0) or 0.0), 6),
                    'chest_prob': round(float(snapshot.get('chest_prob', 0.0) or 0.0), 6),
                    'falsetto_prob': round(float(snapshot.get('falsetto_prob', 0.0) or 0.0), 6),
                },
            }
        )

    mix_out = []
    for event in mix_events:
        snapshot = dict(getattr(event, 'feature_snapshot', {}) or {})
        mix_out.append(
            {
                'event_type': getattr(event, 'event_type', ''),
                'start_time': round(float(getattr(event, 'start_time', 0.0) or 0.0), 6),
                'end_time': round(float(getattr(event, 'end_time', 0.0) or 0.0), 6),
                'confidence': round(float(getattr(event, 'confidence', 0.0) or 0.0), 6),
                'mix_support_score': round(float(getattr(event, 'mix_support_score', 0.0) or 0.0), 6),
                'snapshot': {
                    key: snapshot.get(key)
                    for key in [
                        'marginal_head_mix',
                        'released_high_pitch_head_mix',
                        'released_near_threshold_high_pitch_head_mix',
                        'released_ultra_high_pitch_head_mix',
                        'released_low_energy_midhigh_head_mix',
                        'borderline_low_mid_pitch_head_mix',
                        'weak_mix_support_floor',
                        'weak_mix_pitch_floor',
                        'learned_mix_margin',
                        'heuristic_mix_support',
                        'learned_mix_support',
                        'head_bias',
                    ]
                },
            }
        )

    print(json.dumps({'wav_path': wav_path, 'voice_events': out, 'mix_events': mix_out}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
