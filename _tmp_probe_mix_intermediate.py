import argparse
import copy
import csv
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import debug_mix_rule_offline as dbg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Probe intermediate voice/mix stages for one sample.')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--item-name', required=True)
    parser.add_argument('--output', required=True)
    return parser.parse_args()


def load_row(manifest_path: Path, item_name: str) -> Dict[str, Any]:
    with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if str(row.get('item_name', '') or '').strip() == item_name:
                return dict(row)
    raise KeyError(f'item_name not found: {item_name}')


def resolve_checkpoint(path_text: str) -> Path:
    raw_path = Path(str(path_text or '').strip())
    if not raw_path.exists():
        raise FileNotFoundError(f'artifact path not found: {raw_path}')
    if raw_path.is_dir():
        checkpoint_path = raw_path / 'best_mix_binary_squeezenet.pt'
        if not checkpoint_path.exists():
            raise FileNotFoundError(f'checkpoint not found in artifact directory: {checkpoint_path}')
        return checkpoint_path.resolve()
    return raw_path.resolve()


def reset_mix_runtime_cache(ui: Any) -> None:
    for attr, value in (
        ('_mix_binary_model_bundle', None),
        ('_last_mix_binary_model_error', ''),
        ('_prefer_mix_binary_external_cpu', False),
        ('_external_mix_gpu_retry_blocked', False),
    ):
        try:
            setattr(ui.visualizer, attr, value)
        except Exception:
            pass


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def summarize_event(event: Any) -> Dict[str, Any]:
    payload = dict(getattr(event, 'display_payload', {}) or {})
    snapshot = dict(getattr(event, 'feature_snapshot', {}) or {})
    return {
        'event_type': str(getattr(event, 'event_type', '') or ''),
        'subtype': str(getattr(event, 'subtype', '') or ''),
        'base_voice_type': str(getattr(event, 'base_voice_type', '') or ''),
        'voice_type': str(getattr(event, 'voice_type', '') or ''),
        'start_time': dbg.to_jsonable(safe_float(getattr(event, 'start_time', 0.0))),
        'end_time': dbg.to_jsonable(safe_float(getattr(event, 'end_time', 0.0))),
        'duration': dbg.to_jsonable(max(0.0, safe_float(getattr(event, 'end_time', 0.0)) - safe_float(getattr(event, 'start_time', 0.0)))),
        'confidence': dbg.to_jsonable(safe_float(getattr(event, 'confidence', 0.0))),
        'strength': dbg.to_jsonable(safe_float(getattr(event, 'strength', 0.0))),
        'mean_pitch_hz': dbg.to_jsonable(safe_float(getattr(event, 'mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)))),
        'chest_prob': dbg.to_jsonable(safe_float(getattr(event, 'chest_prob', snapshot.get('chest_prob', 0.0)))),
        'falsetto_prob': dbg.to_jsonable(safe_float(getattr(event, 'falsetto_prob', snapshot.get('falsetto_prob', 0.0)))),
        'mix_prob': dbg.to_jsonable(safe_float(getattr(event, 'mix_prob', payload.get('mix_prob', snapshot.get('mix_prob', 0.0))))),
        'mix_threshold': dbg.to_jsonable(safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)),
        'mix_support': dbg.to_jsonable(safe_float(getattr(event, 'mix_support_score', payload.get('mix_support', snapshot.get('mix_support', 0.0))))),
        'granularity_key': str(payload.get('granularity_key', snapshot.get('granularity_key', '')) or ''),
        'sidecar_segment_label': str(payload.get('sidecar_segment_label', snapshot.get('sidecar_segment_label', '')) or ''),
        'source_layer': str(getattr(event, 'source_layer', '') or ''),
        'feature_snapshot': dbg.to_jsonable(snapshot),
        'display_payload': dbg.to_jsonable(payload),
    }


def summarize_stage(events: List[Any], status: str = 'ok') -> Dict[str, Any]:
    serialized = [summarize_event(event) for event in list(events or [])]
    voice_events = [event for event in serialized if event.get('event_type') in {'chest_voice', 'falsetto'}]
    mix_events = [event for event in serialized if event.get('event_type') in {'strong_mix', 'weak_mix', 'balanced_mix'}]
    best_voice_event = None
    best_voice_mix_prob = -1.0
    for event in voice_events:
        mix_prob = safe_float(event.get('mix_prob', 0.0))
        if best_voice_event is None or mix_prob > best_voice_mix_prob:
            best_voice_event = event
            best_voice_mix_prob = mix_prob
    strongest_mix_event = None
    strongest_mix_support = -1.0
    for event in mix_events:
        mix_support = safe_float(event.get('mix_support', 0.0))
        if strongest_mix_event is None or mix_support > strongest_mix_support:
            strongest_mix_event = event
            strongest_mix_support = mix_support
    return {
        'status': str(status or 'ok'),
        'event_count': len(serialized),
        'voice_event_count': len(voice_events),
        'mix_event_count': len(mix_events),
        'counts': {
            'voice': len(voice_events),
            'mix': len(mix_events),
            'weak_mix': sum(1 for event in mix_events if event.get('event_type') == 'weak_mix'),
            'strong_mix': sum(1 for event in mix_events if event.get('event_type') == 'strong_mix'),
            'balanced_mix': sum(1 for event in mix_events if event.get('event_type') == 'balanced_mix'),
        },
        'best_voice_event': best_voice_event or {},
        'strongest_mix_event': strongest_mix_event or {},
        'events': serialized,
    }


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    checkpoint_path = resolve_checkpoint(args.artifact)
    row = load_row(manifest_path, str(args.item_name or '').strip())

    app = None
    ui = None
    try:
        app, module, ui, _ = dbg.load_runtime(False)
        module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint_path,)
        reset_mix_runtime_cache(ui)

        onepass_payload, worker = dbg.run_onepass_worker(app, module, ui, str(row.get('wav_path', '') or ''))
        audio, sample_rate = dbg.decode_audio_for_analysis(module, ui, worker, str(row.get('wav_path', '') or ''))
        ui._onepass_analysis_payload = {
            'segments': list(onepass_payload.get('segments', []) or []),
            'display_segments': list(onepass_payload.get('segments', []) or []),
            'duration': float(onepass_payload.get('duration', 0.0) or 0.0),
        }
        ui._in_onepass_mode = True
        ui._onepass_playback = SimpleNamespace(
            audio=audio,
            sr=int(sample_rate),
            total_s=float(onepass_payload.get('duration', 0.0) or 0.0),
        )
        resolved = ui._resolve_technique_analysis_payload()
        if not bool(resolved.get('ok', False)):
            raise RuntimeError(f'resolve payload failed: {resolved}')

        viz = ui.visualizer
        frames = list(resolved.get('frames', []) or [])
        resolved_audio = resolved.get('audio_samples')
        resolved_sr = int(resolved.get('sample_rate', sample_rate) or sample_rate)

        output_voice_events = list(viz._build_offline_chest_falsetto_events(frames, audio_samples=resolved_audio, sample_rate=resolved_sr) or [])
        has_mix_source_path = hasattr(viz, '_last_voice_type_mix_source_events')
        mix_source_status = 'available' if has_mix_source_path else 'not_emitted_by_current_runtime'
        mix_source_events = copy.deepcopy(list(getattr(viz, '_last_voice_type_mix_source_events', []) or [])) if has_mix_source_path else []
        if has_mix_source_path:
            raw_mix_events = list(viz._build_rule_based_mix_events(frames, mix_source_events) or [])
            postprocessed_voice_for_mix = list(viz._postprocess_technique_events(copy.deepcopy(mix_source_events)) or [])
            postprocessed_voice_for_mix = [event for event in postprocessed_voice_for_mix if isinstance(event, module.VoiceTypeEvent)]
            merged_mix_events = list(viz._build_rule_based_mix_events(frames, postprocessed_voice_for_mix) or [])
        else:
            raw_mix_events = []
            postprocessed_voice_for_mix = []
            merged_mix_events = []
        output_voice_for_mix = copy.deepcopy(list(output_voice_events or []))
        mix_from_output_voice = list(viz._build_rule_based_mix_events(frames, output_voice_for_mix) or [])
        postprocessed_output_voice_for_mix = list(viz._postprocess_technique_events(copy.deepcopy(output_voice_for_mix)) or [])
        postprocessed_output_voice_for_mix = [event for event in postprocessed_output_voice_for_mix if isinstance(event, module.VoiceTypeEvent)]
        merged_mix_from_output_voice = list(viz._build_rule_based_mix_events(frames, postprocessed_output_voice_for_mix) or [])

        final_summary = viz.analyze_technique_frames(frames, audio_samples=resolved_audio, sample_rate=resolved_sr)
        final_events = list(getattr(viz, '_technique_events', []) or [])

        payload = {
            'item_name': str(row.get('item_name', '') or ''),
            'wav_path': str(row.get('wav_path', '') or ''),
            'checkpoint': str(checkpoint_path),
            'resolved': {
                'analysis_mode': str(resolved.get('analysis_mode', '') or ''),
                'duration': dbg.to_jsonable(safe_float(resolved.get('duration', 0.0))),
                'frame_count': len(frames),
            },
            'mix_source_status': mix_source_status,
            'voice_debug_after_build': dbg.to_jsonable(dict(getattr(viz, '_last_voice_type_debug', {}) or {})),
            'output_voice_events': summarize_stage(output_voice_events),
            'mix_source_events': summarize_stage(mix_source_events, status=mix_source_status),
            'raw_mix_events': summarize_stage(raw_mix_events, status='ok' if has_mix_source_path else 'skipped_no_mix_source'),
            'postprocessed_voice_for_mix': summarize_stage(postprocessed_voice_for_mix, status='ok' if has_mix_source_path else 'skipped_no_mix_source'),
            'merged_mix_events': summarize_stage(merged_mix_events, status='ok' if has_mix_source_path else 'skipped_no_mix_source'),
            'output_voice_for_mix': summarize_stage(output_voice_for_mix),
            'mix_from_output_voice': summarize_stage(mix_from_output_voice),
            'postprocessed_output_voice_for_mix': summarize_stage(postprocessed_output_voice_for_mix),
            'merged_mix_from_output_voice': summarize_stage(merged_mix_from_output_voice),
            'final_summary': dbg.to_jsonable(final_summary),
            'final_events': summarize_stage(final_events),
        }
        Path(args.output).resolve().write_text(json.dumps(dbg.to_jsonable(payload), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'json_report={Path(args.output).resolve()}')
        return 0
    finally:
        if app is not None and ui is not None:
            dbg.close_runtime(app, ui)


if __name__ == '__main__':
    raise SystemExit(main())
