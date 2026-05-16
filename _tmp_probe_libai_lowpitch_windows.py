import json
from pathlib import Path

import numpy as np

import debug_gui_onepass_practical as practical


ROOT = Path(__file__).resolve().parent
TARGET_WAV = ROOT / 'recordings' / 'VocalConvertOutput' / '人声' / '_lead_backing_stage2' / '单依纯 - 李白 (Live)_人声_lead.wav'
OUTPUT_JSON = ROOT / '_tmp_probe_libai_lowpitch_windows.json'


def _frame_frequency(frame) -> float:
    return float(
        getattr(frame, 'display_frequency_hz', 0.0)
        or getattr(frame, 'detected_frequency_hz', 0.0)
        or 0.0
    )


def _summarize_segment(frames, start_idx: int, end_idx: int) -> dict:
    segment = frames[start_idx:end_idx]
    pitches = np.asarray([_frame_frequency(item) for item in segment], dtype=np.float32)
    confidences = np.asarray([float(getattr(item, 'confidence', 0.0) or 0.0) for item in segment], dtype=np.float32)
    rms_values = np.asarray([float(getattr(item, 'audio_rms', 0.0) or 0.0) for item in segment], dtype=np.float32)
    breath_scores = np.asarray([float(getattr(item, 'breath_score', 0.0) or 0.0) for item in segment], dtype=np.float32)
    breath_hints = np.asarray([1.0 if bool(getattr(item, 'breath_detect_hint', False)) else 0.0 for item in segment], dtype=np.float32)
    positive_pitch = pitches[pitches > 0.0]
    return {
        'start_time': practical.to_jsonable(float(getattr(segment[0], 'timeline_time', 0.0) or 0.0)),
        'end_time': practical.to_jsonable(float(getattr(segment[-1], 'timeline_time', 0.0) or 0.0)),
        'frame_count': len(segment),
        'mean_pitch_hz': practical.to_jsonable(float(np.mean(positive_pitch)) if positive_pitch.size else 0.0),
        'min_pitch_hz': practical.to_jsonable(float(np.min(positive_pitch)) if positive_pitch.size else 0.0),
        'max_pitch_hz': practical.to_jsonable(float(np.max(positive_pitch)) if positive_pitch.size else 0.0),
        'mean_confidence': practical.to_jsonable(float(np.mean(confidences)) if confidences.size else 0.0),
        'stable_ratio': practical.to_jsonable(float(np.mean(confidences >= 0.50)) if confidences.size else 0.0),
        'voiced_ratio': practical.to_jsonable(float(np.mean(confidences >= 0.34)) if confidences.size else 0.0),
        'mean_rms': practical.to_jsonable(float(np.mean(rms_values)) if rms_values.size else 0.0),
        'mean_breath_score': practical.to_jsonable(float(np.mean(breath_scores)) if breath_scores.size else 0.0),
        'breath_hint_ratio': practical.to_jsonable(float(np.mean(breath_hints)) if breath_hints.size else 0.0),
    }


def _collect_lowpitch_frame_segments(frames) -> list:
    segments = []
    start_idx = None
    for idx, frame in enumerate(frames):
        pitch_hz = _frame_frequency(frame)
        conf = float(getattr(frame, 'confidence', 0.0) or 0.0)
        in_band = 220.0 <= pitch_hz <= 420.0 and conf >= 0.28 and not bool(getattr(frame, 'preview_only', False))
        if in_band:
            if start_idx is None:
                start_idx = idx
            continue
        if start_idx is not None:
            if idx - start_idx >= 4:
                segments.append(_summarize_segment(frames, start_idx, idx))
            start_idx = None
    if start_idx is not None and len(frames) - start_idx >= 4:
        segments.append(_summarize_segment(frames, start_idx, len(frames)))
    return segments


def _collect_lowpitch_candidate_windows(viz, frames, audio_samples, sample_rate: int) -> list:
    target_sr = int(getattr(viz, '_CHEST_FALSETTO_TARGET_SR', 16000) or 16000)
    try:
        import gui.integrated_recording_interface as module

        target_sr = int(getattr(module, '_CHEST_FALSETTO_TARGET_SR', target_sr) or target_sr)
        window_s = float(getattr(module, '_CHEST_FALSETTO_WINDOW_S', 0.64) or 0.64)
        hop_s = float(getattr(module, '_CHEST_FALSETTO_HOP_S', 0.16) or 0.16)
    except Exception:
        window_s = 0.64
        hop_s = 0.16

    audio = np.asarray(audio_samples, dtype=np.float32).reshape(-1)
    if int(sample_rate) != target_sr:
        audio = viz._resample_chest_falsetto_audio(audio, int(sample_rate), target_sr)

    valid_frames = [item for item in list(frames or []) if not bool(getattr(item, 'preview_only', False))]
    times = np.asarray([float(getattr(item, 'timeline_time', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    confidences = np.asarray([float(getattr(item, 'confidence', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    has_pitch = np.asarray([bool(getattr(item, 'has_pitch', False)) for item in valid_frames], dtype=bool)
    rms_values = np.asarray([float(getattr(item, 'audio_rms', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    breath_scores = np.asarray([float(getattr(item, 'breath_score', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    breath_hints = np.asarray([1.0 if bool(getattr(item, 'breath_detect_hint', False)) else 0.0 for item in valid_frames], dtype=np.float32)
    pitches = np.asarray([_frame_frequency(item) for item in valid_frames], dtype=np.float32)
    voiced_mask = np.logical_and(has_pitch, confidences >= 0.34)
    stable_mask = np.logical_and(has_pitch, confidences >= 0.50)

    window_samples = max(1, int(round(window_s * target_sr)))
    hop_samples = max(1, int(round(hop_s * target_sr)))
    max_start = max(0, int(audio.size) - window_samples)
    candidate_starts = [0] if max_start <= 0 else list(range(0, max_start + 1, hop_samples))
    if candidate_starts and candidate_starts[-1] != max_start:
        candidate_starts.append(max_start)

    windows = []
    for sample_start in candidate_starts:
        start_time = float(sample_start) / float(target_sr)
        end_time = start_time + window_s
        frame_mask = np.logical_and(times >= start_time, times < end_time)
        frame_count = int(np.count_nonzero(frame_mask))
        if frame_count < 2:
            continue
        voiced_ratio = float(np.mean(voiced_mask[frame_mask])) if frame_count > 0 else 0.0
        stable_ratio = float(np.mean(stable_mask[frame_mask])) if frame_count > 0 else 0.0
        mean_rms = float(np.mean(rms_values[frame_mask])) if frame_count > 0 else 0.0
        mean_breath_score = float(np.mean(breath_scores[frame_mask])) if frame_count > 0 else 0.0
        breath_hint_ratio = float(np.mean(breath_hints[frame_mask])) if frame_count > 0 else 0.0
        if voiced_ratio < 0.17 or stable_ratio < 0.03 or mean_rms < 0.00008:
            continue
        positive_pitch = pitches[frame_mask]
        positive_pitch = positive_pitch[positive_pitch > 0.0]
        mean_pitch_hz = float(np.mean(positive_pitch)) if positive_pitch.size else 0.0
        if not (220.0 <= mean_pitch_hz <= 420.0):
            continue
        windows.append({
            'start_time': practical.to_jsonable(start_time),
            'end_time': practical.to_jsonable(end_time),
            'frame_count': frame_count,
            'mean_pitch_hz': practical.to_jsonable(mean_pitch_hz),
            'voiced_ratio': practical.to_jsonable(voiced_ratio),
            'stable_ratio': practical.to_jsonable(stable_ratio),
            'mean_rms': practical.to_jsonable(mean_rms),
            'mean_breath_score': practical.to_jsonable(mean_breath_score),
            'breath_hint_ratio': practical.to_jsonable(breath_hint_ratio),
        })
    return windows


def _collect_lowpitch_voice_decisions(viz, frames, audio_samples, sample_rate: int) -> dict:
    target_sr = 16000
    try:
        import gui.integrated_recording_interface as module

        target_sr = int(getattr(module, '_CHEST_FALSETTO_TARGET_SR', target_sr) or target_sr)
        window_s = float(getattr(module, '_CHEST_FALSETTO_WINDOW_S', 0.64) or 0.64)
        hop_s = float(getattr(module, '_CHEST_FALSETTO_HOP_S', 0.16) or 0.16)
    except Exception:
        window_s = 0.64
        hop_s = 0.16

    audio = np.asarray(audio_samples, dtype=np.float32).reshape(-1)
    if int(sample_rate) != target_sr:
        audio = viz._resample_chest_falsetto_audio(audio, int(sample_rate), target_sr)

    valid_frames = [item for item in list(frames or []) if not bool(getattr(item, 'preview_only', False))]
    times = np.asarray([float(getattr(item, 'timeline_time', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    confidences = np.asarray([float(getattr(item, 'confidence', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    has_pitch = np.asarray([bool(getattr(item, 'has_pitch', False)) for item in valid_frames], dtype=bool)
    rms_values = np.asarray([float(getattr(item, 'audio_rms', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    zcr_values = np.asarray([float(getattr(item, 'zcr', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    breath_scores = np.asarray([float(getattr(item, 'breath_score', 0.0) or 0.0) for item in valid_frames], dtype=np.float32)
    breath_hints = np.asarray([1.0 if bool(getattr(item, 'breath_detect_hint', False)) else 0.0 for item in valid_frames], dtype=np.float32)
    pitches = np.asarray([_frame_frequency(item) for item in valid_frames], dtype=np.float32)
    voiced_mask = np.logical_and(has_pitch, confidences >= 0.34)
    stable_mask = np.logical_and(has_pitch, confidences >= 0.50)

    window_samples = max(1, int(round(window_s * target_sr)))
    hop_samples = max(1, int(round(hop_s * target_sr)))
    max_start = max(0, int(audio.size) - window_samples)
    candidate_starts = [0] if max_start <= 0 else list(range(0, max_start + 1, hop_samples))
    if candidate_starts and candidate_starts[-1] != max_start:
        candidate_starts.append(max_start)

    candidate_meta = []
    audio_windows = []
    for sample_start in candidate_starts:
        sample_end = min(int(audio.size), int(sample_start + window_samples))
        window = np.asarray(audio[sample_start:sample_end], dtype=np.float32)
        if window.size < window_samples:
            padded = np.zeros(window_samples, dtype=np.float32)
            padded[:window.size] = window
            window = padded
        start_time = float(sample_start) / float(target_sr)
        end_time = start_time + window_s
        frame_mask = np.logical_and(times >= start_time, times < end_time)
        frame_count = int(np.count_nonzero(frame_mask))
        if frame_count < 2:
            continue
        voiced_ratio = float(np.mean(voiced_mask[frame_mask])) if frame_count > 0 else 0.0
        stable_ratio = float(np.mean(stable_mask[frame_mask])) if frame_count > 0 else 0.0
        mean_rms = float(np.mean(rms_values[frame_mask])) if frame_count > 0 else 0.0
        mean_zcr = float(np.mean(zcr_values[frame_mask])) if frame_count > 0 else 0.0
        mean_breath_score = float(np.mean(breath_scores[frame_mask])) if frame_count > 0 else 0.0
        breath_hint_ratio = float(np.mean(breath_hints[frame_mask])) if frame_count > 0 else 0.0
        if voiced_ratio < 0.17 or stable_ratio < 0.03 or mean_rms < 0.00008:
            continue
        positive_pitch = pitches[frame_mask]
        positive_pitch = positive_pitch[positive_pitch > 0.0]
        mean_pitch_hz = float(np.mean(positive_pitch)) if positive_pitch.size else 0.0
        if not (220.0 <= mean_pitch_hz <= 420.0):
            continue
        candidate_meta.append({
            'start_time': start_time,
            'end_time': end_time,
            'frame_count': frame_count,
            'mean_pitch_hz': mean_pitch_hz,
            'voiced_ratio': voiced_ratio,
            'stable_ratio': stable_ratio,
            'mean_rms': mean_rms,
            'mean_zcr': mean_zcr,
            'mean_breath_score': mean_breath_score,
            'breath_hint_ratio': breath_hint_ratio,
        })
        audio_windows.append(window)

    if not audio_windows:
        return {'summary': {'candidate_window_count': 0}, 'windows': []}

    external_results = viz._run_chest_falsetto_external_inference(audio_windows)
    windows = []
    accepted_count = 0
    accepted_relaxed_count = 0
    event_type_counts = {}
    accepted_type_counts = {}
    for idx, meta in enumerate(candidate_meta):
        prob = dict(external_results[idx] or {}) if idx < len(external_results or []) else {}
        model_chest_prob = float(prob.get('chest_prob', 0.0) or 0.0)
        model_falsetto_prob = float(prob.get('falsetto_prob', 0.0) or 0.0)
        adjusted = viz._apply_voice_type_context_priors(
            model_chest_prob,
            model_falsetto_prob,
            mean_pitch_hz=meta['mean_pitch_hz'],
            voiced_ratio=meta['voiced_ratio'],
            stable_ratio=meta['stable_ratio'],
            mean_rms=meta['mean_rms'],
            mean_zcr=meta['mean_zcr'],
            mean_breath_score=meta['mean_breath_score'],
            breath_hint_ratio=meta['breath_hint_ratio'],
        )
        record = dict(meta)
        record.update({
            'model_chest_prob': model_chest_prob,
            'model_falsetto_prob': model_falsetto_prob,
            'event_type': adjusted['event_type'],
            'voice_type': adjusted['voice_type'],
            'chest_prob': float(adjusted['chest_prob'] or 0.0),
            'falsetto_prob': float(adjusted['falsetto_prob'] or 0.0),
            'confidence': float(adjusted['confidence'] or 0.0),
            'probability_margin': float(adjusted['probability_margin'] or 0.0),
            'context_forced_chest': bool(adjusted.get('context_forced_chest', False)),
        })
        accepted = bool(viz._voice_prediction_record_accepted(record, relaxed=False))
        accepted_relaxed = bool(viz._voice_prediction_record_accepted(record, relaxed=True))
        if accepted:
            accepted_count += 1
            accepted_type_counts[record['event_type']] = int(accepted_type_counts.get(record['event_type'], 0)) + 1
        if accepted_relaxed:
            accepted_relaxed_count += 1
        event_type_counts[record['event_type']] = int(event_type_counts.get(record['event_type'], 0)) + 1
        windows.append({key: practical.to_jsonable(value) for key, value in record.items()} | {
            'accepted': accepted,
            'accepted_relaxed': accepted_relaxed,
        })

    windows = sorted(windows, key=lambda item: float(item.get('start_time', 0.0) or 0.0))
    return {
        'summary': {
            'candidate_window_count': len(windows),
            'accepted_count': accepted_count,
            'accepted_relaxed_count': accepted_relaxed_count,
            'event_type_counts': event_type_counts,
            'accepted_type_counts': accepted_type_counts,
        },
        'windows': windows,
    }


def main() -> int:
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
        ui._start_offline_onepass(str(TARGET_WAV))
        practical.wait_qt(app, 50)
        resolved = ui._resolve_technique_analysis_payload()
        if not bool(resolved.get('ok', False)):
            raise RuntimeError(str(resolved.get('reason', '') or 'resolve_failed'))
        frames = list(resolved.get('frames', []) or [])
        audio_samples = resolved.get('audio_samples')
        sample_rate = int(resolved.get('sample_rate', 0) or 0)
        viz = getattr(ui, 'visualizer', None)
        if viz is None:
            raise RuntimeError('visualizer unavailable')

        payload = {
            'wav_path': str(TARGET_WAV),
            'lowpitch_frame_segments': _collect_lowpitch_frame_segments(frames),
            'lowpitch_candidate_windows': _collect_lowpitch_candidate_windows(viz, frames, audio_samples, sample_rate),
            'lowpitch_voice_decisions': _collect_lowpitch_voice_decisions(viz, frames, audio_samples, sample_rate),
        }
        payload['counts'] = {
            'frame_segment_count': len(payload['lowpitch_frame_segments']),
            'candidate_window_count': len(payload['lowpitch_candidate_windows']),
            'decision_window_count': int(((payload.get('lowpitch_voice_decisions', {}) or {}).get('summary', {}) or {}).get('candidate_window_count', 0) or 0),
        }
        OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'output={OUTPUT_JSON}')
        print(f"counts={payload['counts']}")
        return 0
    finally:
        if app is not None and ui is not None:
            practical.close_runtime(app, ui)


if __name__ == '__main__':
    raise SystemExit(main())