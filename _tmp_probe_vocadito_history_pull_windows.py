import json
from collections import Counter
from pathlib import Path

import debug_gui_onepass_practical as practical


ROOT = Path(__file__).resolve().parent
DATASET_ROOT = Path(r"D:\Data\vocadito_public_20260512\extracted")
OUTPUT_JSON = ROOT / "_tmp_vocadito_public_eval_20260512" / "probe_vocadito_25_4_history_pull_windows.json"
TARGETS = [
    {
        "track_id": "vocadito_25",
        "wav_path": DATASET_ROOT / "Audio" / "vocadito_25.wav",
        "windows": [
            {"label": "w7_0_8_5", "start_s": 7.0, "end_s": 8.5},
            {"label": "w8_5_10_0", "start_s": 8.5, "end_s": 10.0},
            {"label": "w14_0_15_5", "start_s": 14.0, "end_s": 15.5},
        ],
    },
    {
        "track_id": "vocadito_4",
        "wav_path": DATASET_ROOT / "Audio" / "vocadito_4.wav",
        "windows": [
            {"label": "w1_5_3_0", "start_s": 1.5, "end_s": 3.0},
        ],
    },
]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _payload_time(payload):
    return _safe_float(payload.get("global_time", payload.get("timestamp", 0.0)), 0.0)


def _summarize_candidates(harmonic_candidates):
    summary = []
    for cand in list(harmonic_candidates or []):
        try:
            summary.append(
                {
                    "frequency": round(_safe_float(cand.get("frequency", 0.0), 0.0), 6),
                    "confidence": round(_safe_float(cand.get("confidence", 0.55), 0.55), 6),
                }
            )
        except Exception:
            continue
    summary.sort(key=lambda item: item["frequency"])
    return summary


def _inspect_refine_branch(ui, pitch_data, current_frequency, last_display):
    helper = getattr(ui, "audio_processor", None)
    if helper is None:
        return {"stage": "no_audio_processor"}
    pick_display_fundamental_candidate = getattr(helper, "_pick_display_fundamental_candidate", None)
    pitch_semitone_distance = getattr(helper, "_pitch_semitone_distance", None)
    is_likely_upper_harmonic_ratio = getattr(helper, "_is_likely_upper_harmonic_ratio", None)
    if not callable(pick_display_fundamental_candidate):
        return {"stage": "no_pick_display_fundamental_candidate"}
    if not callable(pitch_semitone_distance):
        return {"stage": "no_pitch_semitone_distance"}
    if not callable(is_likely_upper_harmonic_ratio):
        return {"stage": "no_is_likely_upper_harmonic_ratio"}

    current_frequency = _safe_float(current_frequency, 0.0)
    if current_frequency <= 0.0:
        return {"stage": "non_positive_current"}

    raw_frequency = _safe_float(pitch_data.get("raw_frequency", 0.0), 0.0)
    detected_frequency = _safe_float(
        pitch_data.get("detected_frequency", pitch_data.get("frequency", 0.0)),
        0.0,
    )
    confidence = _safe_float(pitch_data.get("confidence", 0.0), 0.0)
    audio_rms = _safe_float(pitch_data.get("audio_rms", 0.0), 0.0)
    breath_hint = bool(pitch_data.get("breath_detect_hint", False))
    harmonic_candidates = list(pitch_data.get("harmonic_candidates", []) or [])

    details = {
        "current_frequency": round(current_frequency, 6),
        "last_display": round(_safe_float(last_display, 0.0), 6),
        "raw_frequency": round(raw_frequency, 6),
        "detected_frequency": round(detected_frequency, 6),
        "confidence": round(confidence, 6),
        "audio_rms": round(audio_rms, 9),
        "breath_hint": breath_hint,
        "harmonic_candidates": _summarize_candidates(harmonic_candidates),
    }

    if not harmonic_candidates:
        details["stage"] = "no_harmonic_candidates"
        return details

    reference_frequency = max(raw_frequency, detected_frequency, current_frequency)
    details["reference_frequency"] = round(reference_frequency, 6)
    if reference_frequency <= 0.0:
        details["stage"] = "non_positive_reference"
        return details

    try:
        detected_gap = pitch_semitone_distance(float(current_frequency), float(detected_frequency)) if detected_frequency > 0.0 else 999.0
    except Exception:
        detected_gap = 999.0
    details["detected_gap"] = round(_safe_float(detected_gap, 999.0), 6)

    try:
        raw_detected_gap = pitch_semitone_distance(float(raw_frequency), float(detected_frequency)) if raw_frequency > 0.0 and detected_frequency > 0.0 else 999.0
    except Exception:
        raw_detected_gap = 999.0
    raw_detected_locked = bool(raw_frequency > 0.0 and detected_frequency > 0.0 and raw_detected_gap <= 0.85)
    suspicious_low_display = bool(
        (not breath_hint)
        and confidence >= 0.88
        and audio_rms >= 0.0012
        and 170.0 <= float(detected_frequency) <= 320.0
        and 4.8 <= float(detected_gap) <= 15.5
        and float(current_frequency) <= float(detected_frequency) * 0.76
        and raw_detected_locked
    )
    details["raw_detected_gap"] = round(_safe_float(raw_detected_gap, 999.0), 6)
    details["raw_detected_locked"] = raw_detected_locked
    details["suspicious_low_display"] = suspicious_low_display
    if suspicious_low_display:
        details["stage"] = "suspicious_low_display"
        return details

    lower_candidate = _safe_float(
        pick_display_fundamental_candidate(
            float(reference_frequency),
            harmonic_candidates,
            float(last_display or 0.0),
        ),
        0.0,
    )
    details["lower_candidate"] = round(lower_candidate, 6)
    if lower_candidate <= 0.0 or lower_candidate >= float(current_frequency) * 0.995:
        details["stage"] = "no_lower_candidate_pull"
        return details

    lower_gap = _safe_float(pitch_semitone_distance(float(current_frequency), float(lower_candidate)), 999.0)
    harmonic_ratio = float(reference_frequency) / max(float(lower_candidate), 1e-9)
    harmonic_like = bool(is_likely_upper_harmonic_ratio(harmonic_ratio))
    details["lower_gap"] = round(lower_gap, 6)
    details["harmonic_ratio"] = round(harmonic_ratio, 6)
    details["harmonic_like"] = harmonic_like
    details["reference_current_ratio"] = round(float(reference_frequency) / max(float(current_frequency), 1e-9), 6)
    details["current_lower_ratio"] = round(float(current_frequency) / max(float(lower_candidate), 1e-9), 6)
    if (not harmonic_like) and lower_gap < 6.0:
        details["stage"] = "non_harmonic_small_gap"
        return details

    corroborated_subharmonic = False
    corroboration_kind = ""
    for cand in harmonic_candidates:
        cand_freq = _safe_float(cand.get("frequency", 0.0), 0.0)
        if cand_freq <= 0.0 or abs(cand_freq - float(lower_candidate)) <= max(8.0, float(lower_candidate) * 0.08):
            continue
        ladder_ratio = cand_freq / max(float(lower_candidate), 1e-9)
        if 1.62 <= ladder_ratio <= 2.28:
            corroborated_subharmonic = True
            corroboration_kind = "2x_ladder"
            break
        if (
            float(reference_frequency) >= 420.0
            and float(lower_candidate) <= 220.0
            and float(reference_frequency) / max(float(lower_candidate), 1e-9) >= 4.4
            and 2.72 <= ladder_ratio <= 3.34
        ):
            corroborated_subharmonic = True
            corroboration_kind = "3x_ladder"
            break
        if (
            float(reference_frequency) >= 420.0
            and float(lower_candidate) <= 220.0
            and float(reference_frequency) / max(float(lower_candidate), 1e-9) >= 4.4
            and 4.6 <= ladder_ratio <= 8.4
        ):
            corroborated_subharmonic = True
            corroboration_kind = "5to8x_ladder"
            break
    details["corroborated_subharmonic"] = corroborated_subharmonic
    details["corroboration_kind"] = corroboration_kind

    try:
        current_history_gap = pitch_semitone_distance(float(current_frequency), float(last_display)) if float(last_display) > 0.0 else 999.0
    except Exception:
        current_history_gap = 999.0
    try:
        lower_history_gap = pitch_semitone_distance(float(lower_candidate), float(last_display)) if float(last_display) > 0.0 else 999.0
    except Exception:
        lower_history_gap = 999.0
    details["current_history_gap"] = round(_safe_float(current_history_gap, 999.0), 6)
    details["lower_history_gap"] = round(_safe_float(lower_history_gap, 999.0), 6)

    pull_weight = 0.0
    pull_branch = "none"
    if corroborated_subharmonic and lower_gap >= 7.0:
        pull_weight = 0.94 if harmonic_ratio >= 2.72 else 0.90
        pull_branch = "corroborated_subharmonic"
    elif harmonic_like and lower_gap >= 8.4:
        pull_weight = 0.92 if harmonic_ratio >= 2.72 else 0.86
        pull_branch = "harmonic_high_gap"
    elif harmonic_like and lower_gap >= 5.4 and (lower_history_gap + 0.40 < current_history_gap):
        pull_weight = 0.86 if harmonic_ratio >= 2.72 else 0.80
        pull_branch = "harmonic_history_pull"
    elif harmonic_like and lower_gap >= 6.6 and float(last_display or 0.0) <= 0.0:
        pull_weight = 0.82
        pull_branch = "harmonic_no_history"

    details["pull_branch"] = pull_branch
    details["pull_weight"] = round(_safe_float(pull_weight, 0.0), 6)
    if pull_weight <= 0.0:
        details["stage"] = "no_pull_weight"
        return details

    strong_current_candidate = False
    for cand in harmonic_candidates:
        cand_freq = _safe_float(cand.get("frequency", 0.0), 0.0)
        cand_conf = _safe_float(cand.get("confidence", 0.55), 0.55)
        if cand_freq <= 0.0 or abs(cand_freq - float(lower_candidate)) <= max(8.0, float(lower_candidate) * 0.08):
            continue
        try:
            near_current = pitch_semitone_distance(float(cand_freq), float(current_frequency)) <= 1.25
        except Exception:
            near_current = False
        if near_current and cand_conf >= 0.95:
            strong_current_candidate = True
            break
    details["strong_current_candidate"] = strong_current_candidate
    if (
        strong_current_candidate
        and float(current_frequency) <= 360.0
        and lower_gap >= 6.8
        and float(lower_candidate) <= float(current_frequency) * 0.72
    ):
        details["stage"] = "blocked_by_strong_current_candidate"
        return details

    corrected = float(pull_weight) * float(lower_candidate) + (1.0 - float(pull_weight)) * min(
        float(current_frequency),
        float(lower_candidate) * 1.08,
    )
    details["stage"] = "pull_applied"
    details["corrected_frequency"] = round(corrected, 6)
    return details


def _simulate_track(ui, app, track_id, wav_path, windows):
    ui._start_offline_onepass(str(wav_path))
    practical.wait_qt(app, 50)

    collect_payloads = getattr(ui, "_collect_onepass_full_pitch_payloads", None)
    if callable(collect_payloads):
        payloads = list(collect_payloads() or [])
    else:
        onepass_payload = dict(getattr(ui, "_onepass_analysis_payload", {}) or {})
        payloads = list(onepass_payload.get("pitch_payloads", []) or [])
        payloads = [dict(item or {}) for item in payloads if bool(dict(item or {}).get("has_pitch", False))]
        payloads.sort(key=_payload_time)

    results = []
    window_counters = {item["label"]: Counter() for item in windows}
    prev_display = 0.0
    prev_detected = 0.0
    prev_voiced_rms = 0.0

    for index, pitch_data in enumerate(payloads):
        timeline_time = _payload_time(pitch_data)
        detected_frequency = _safe_float(pitch_data.get("detected_frequency", pitch_data.get("frequency", 0.0)), 0.0)
        display_frequency = _safe_float(pitch_data.get("display_frequency", detected_frequency), detected_frequency)
        raw_frequency = _safe_float(pitch_data.get("raw_frequency", 0.0), 0.0)
        confidence = max(0.0, _safe_float(pitch_data.get("confidence", 0.0), 0.0))
        audio_rms = _safe_float(pitch_data.get("audio_rms", 0.0), 0.0)
        breath_hint = bool(pitch_data.get("breath_detect_hint", False))
        has_pitch = bool(pitch_data.get("has_pitch", False)) and max(display_frequency, detected_frequency) > 0.0
        if not has_pitch:
            continue

        current_frequency = float(display_frequency if display_frequency > 0.0 else detected_frequency)
        try:
            current_frequency = ui._normal_mode_ui_correct_octave_overshoot(
                pitch_data,
                current_frequency,
                last_plot_freq=float(prev_display or 0.0),
            )
            current_frequency = ui._normal_mode_ui_align_to_fundamental_support(
                pitch_data,
                current_frequency,
                last_plot_freq=float(prev_display or 0.0),
            )
        except Exception:
            current_frequency = float(display_frequency if display_frequency > 0.0 else detected_frequency)
        if current_frequency <= 0.0:
            current_frequency = float(display_frequency if display_frequency > 0.0 else detected_frequency)

        branch_info = _inspect_refine_branch(ui, pitch_data, current_frequency, prev_display)
        actual_refined = _safe_float(
            ui._refine_onepass_payload_display_frequency(
                pitch_data,
                current_frequency,
                last_display=float(prev_display or 0.0),
            ),
            current_frequency,
        )

        released_to_unvoiced = False
        try:
            stable_track = bool(
                prev_detected > 0.0
                and detected_frequency > 0.0
                and ui._normal_mode_ui_semitone_distance(float(prev_detected), float(detected_frequency)) <= 2.6
            )
            mid_register_track = bool(170.0 <= max(float(detected_frequency), float(actual_refined)) <= 320.0)
            low_relative_energy = bool(
                prev_voiced_rms > 0.0
                and audio_rms > 0.0
                and audio_rms <= max(0.0045, float(prev_voiced_rms) * 0.42)
            )
            if has_pitch and (not breath_hint) and stable_track and mid_register_track and low_relative_energy:
                has_pitch = False
                actual_refined = 0.0
                released_to_unvoiced = True
        except Exception:
            released_to_unvoiced = False

        matched_window = None
        for window in windows:
            start_s = _safe_float(window["start_s"], 0.0)
            end_s = _safe_float(window["end_s"], 0.0)
            if start_s <= timeline_time < end_s:
                matched_window = window
                break
        if matched_window is not None:
            pull_branch = str(branch_info.get("pull_branch", "none") or "none")
            stage = str(branch_info.get("stage", "") or "")
            bucket = pull_branch if stage == "pull_applied" else stage
            window_counters[matched_window["label"]][bucket] += 1
            results.append(
                {
                    "track_id": track_id,
                    "window_label": matched_window["label"],
                    "timeline_time": round(timeline_time, 6),
                    "payload_index": index,
                    "pre_refine_display": round(current_frequency, 6),
                    "post_refine_display": round(actual_refined, 6),
                    "released_to_unvoiced": released_to_unvoiced,
                    "payload_display_frequency": round(display_frequency, 6),
                    "payload_detected_frequency": round(detected_frequency, 6),
                    "payload_raw_frequency": round(raw_frequency, 6),
                    "branch_info": branch_info,
                }
            )

        if detected_frequency > 0.0:
            prev_detected = detected_frequency
        if actual_refined > 0.0:
            prev_display = actual_refined
        if has_pitch and audio_rms > 0.0:
            if prev_voiced_rms > 0.0:
                prev_voiced_rms = (0.84 * float(prev_voiced_rms)) + (0.16 * float(audio_rms))
            else:
                prev_voiced_rms = float(audio_rms)

    summary_windows = []
    for window in windows:
        counts = dict(window_counters[window["label"]])
        summary_windows.append(
            {
                "label": window["label"],
                "start_s": window["start_s"],
                "end_s": window["end_s"],
                "frame_count": sum(counts.values()),
                "branch_counts": counts,
            }
        )
    return {
        "track_id": track_id,
        "wav_path": str(wav_path),
        "window_summaries": summary_windows,
        "frames": results,
    }


def _run_target(target):
    app = None
    ui = None
    try:
        app, _module, ui, _ = practical.load_runtime(show_init_log=False)
        practical.install_backend_probes(ui)
        practical.configure_backend_preferences(
            ui,
            prefer_mix_cpu=True,
            prefer_voice_cpu=True,
            force_external_mix=True,
            force_external_voice=True,
        )
        return _simulate_track(
            ui,
            app,
            str(target["track_id"]),
            Path(target["wav_path"]),
            list(target["windows"]),
        )
    finally:
        if app is not None and ui is not None:
            try:
                practical.exit_onepass_mode(ui)
                practical.wait_qt(app, 20)
            except Exception:
                pass
            practical.close_runtime(app, ui)


def main():
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {"targets": []}
    for target in TARGETS:
        result = _run_target(target)
        payload["targets"].append(result)
        summary_text = ", ".join(
            f"{window['label']}={window['branch_counts']}"
            for window in result.get("window_summaries", [])
        )
        print(f"[probe] {result['track_id']} {summary_text}", flush=True)

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={OUTPUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())