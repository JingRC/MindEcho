import json
import time
from pathlib import Path
from types import MethodType

import debug_gui_onepass_practical as practical


ROOT = Path(__file__).resolve().parent
TARGET_WAV = ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '单依纯 - 李白 (Live)_人声_lead.wav'
OUTPUT_JSON = ROOT / '_tmp_probe_danyichun_libai_lead_sidecar_compare.json'


def collect_counts(sample_result: dict) -> dict:
    return dict(((sample_result.get('analysis', {}) or {}).get('summary', {}) or {}).get('counts', {}) or {})


def collect_voice_debug(sample_result: dict) -> dict:
    voice_debug = dict((sample_result.get('analysis', {}) or {}).get('voice_debug', {}) or {})
    keep_keys = (
        'backend',
        'candidate_windows',
        'predicted_windows',
        'accepted_windows',
        'context_adjusted_windows',
        'sidecar_candidates',
        'sidecar_predicted',
        'sidecar_applied',
        'sidecar_reason',
        'reason',
    )
    return {key: practical.to_jsonable(voice_debug.get(key)) for key in keep_keys if key in voice_debug}


def collect_relevant_events(sample_result: dict) -> list:
    events = list(((sample_result.get('analysis', {}) or {}).get('events', [])) or [])
    relevant = []
    for event in events:
        event_type = str(event.get('event_type', '') or '')
        if event_type not in {'falsetto', 'weak_mix', 'strong_mix', 'balanced_mix'}:
            continue
        feature_snapshot = dict(event.get('feature_snapshot', {}) or {})
        display_payload = dict(event.get('display_payload', {}) or {})
        relevant.append({
            'event_type': event_type,
            'display_label': event.get('display_label'),
            'start_time': practical.to_jsonable(event.get('start_time')),
            'end_time': practical.to_jsonable(event.get('end_time')),
            'confidence': practical.to_jsonable(event.get('confidence')),
            'mean_pitch_hz': practical.to_jsonable(event.get('mean_pitch_hz')),
            'window_count': practical.to_jsonable((event.get('feature_snapshot', {}) or {}).get('window_count')),
            'chest_prob': practical.to_jsonable(event.get('chest_prob')),
            'falsetto_prob': practical.to_jsonable(event.get('falsetto_prob')),
            'mix_prob': practical.to_jsonable(event.get('mix_prob')),
            'raw_chest_prob': practical.to_jsonable(feature_snapshot.get('raw_chest_prob')),
            'raw_falsetto_prob': practical.to_jsonable(feature_snapshot.get('raw_falsetto_prob')),
            'sidecar_window_count': practical.to_jsonable(feature_snapshot.get('sidecar_window_count')),
            'sidecar_candidate_count': practical.to_jsonable(feature_snapshot.get('sidecar_candidate_count')),
            'sidecar_segment_window_count': practical.to_jsonable(feature_snapshot.get('sidecar_segment_window_count')),
            'sidecar_segment_label': practical.to_jsonable(feature_snapshot.get('sidecar_segment_label')),
            'sidecar_falsetto_prob': practical.to_jsonable(feature_snapshot.get('sidecar_falsetto_prob')),
            'sidecar_female_prob': practical.to_jsonable(feature_snapshot.get('sidecar_female_prob')),
            'sidecar_model': practical.to_jsonable(display_payload.get('sidecar_model')),
        })
    return relevant


def run_onepass(*, sidecar_enabled: bool) -> dict:
    app = None
    ui = None
    try:
        app, module, ui, _ = practical.load_runtime(show_init_log=False)
        practical.install_backend_probes(ui)
        practical.configure_backend_preferences(
            ui,
            prefer_mix_cpu=True,
            prefer_voice_cpu=True,
            force_external_mix=True,
            force_external_voice=True,
        )
        viz = getattr(ui, 'visualizer', None)
        if viz is None:
            raise RuntimeError('visualizer unavailable')
        if not sidecar_enabled:
            def _disable_sidecar(self, chest_prob: float, falsetto_prob: float, *, record: dict) -> bool:
                return False
            viz._should_apply_reference_fourclass_sidecar = MethodType(_disable_sidecar, viz)
        return practical.analyze_sample(app, module, ui, str(TARGET_WAV))
    finally:
        if app is not None and ui is not None:
            practical.close_runtime(app, ui)


def compare_counts(before: dict, after: dict) -> dict:
    keys = sorted(set(before.keys()) | set(after.keys()))
    diff = {}
    for key in keys:
        diff[key] = int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0)
    return diff


def main() -> int:
    started_at = time.strftime('%Y-%m-%d %H:%M:%S')
    baseline = run_onepass(sidecar_enabled=False)
    current = run_onepass(sidecar_enabled=True)
    before_counts = collect_counts(baseline)
    after_counts = collect_counts(current)
    report = {
        'generated_at': started_at,
        'wav_path': str(TARGET_WAV),
        'baseline_sidecar_disabled': practical.to_jsonable(baseline),
        'current_sidecar_enabled': practical.to_jsonable(current),
        'comparison': {
            'baseline_counts': before_counts,
            'current_counts': after_counts,
            'count_diff': compare_counts(before_counts, after_counts),
            'baseline_voice_debug': collect_voice_debug(baseline),
            'current_voice_debug': collect_voice_debug(current),
            'baseline_relevant_events': collect_relevant_events(baseline),
            'current_relevant_events': collect_relevant_events(current),
        },
    }
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'baseline_counts={before_counts}')
    print(f'current_counts={after_counts}')
    print(f'baseline_voice_debug={collect_voice_debug(baseline)}')
    print(f'current_voice_debug={collect_voice_debug(current)}')
    print(f'json_report={OUTPUT_JSON}')
    baseline_error = str(baseline.get('error', '') or '')
    current_error = str(current.get('error', '') or '')
    if baseline_error or current_error:
        print(f'baseline_error={baseline_error}')
        print(f'current_error={current_error}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
