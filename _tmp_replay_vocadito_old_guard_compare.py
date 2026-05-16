import json
import statistics
import sys
import types
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regression_tests.evaluate_pitch_dataset_metrics import (  # noqa: E402
    PitchSeries,
    TrackSpec,
    align_estimates_to_reference,
    canonicalize_series,
    cents_difference,
    compute_track_metrics,
    extract_estimated_series,
    load_reference_series,
    onepass,
    safe_float,
)
from _tmp_probe_vocadito_21_compare_windows import _inspect_refine_branch  # noqa: E402


DATASET_ROOT = Path(r"D:\Data\vocadito_public_20260512\extracted")
OUTPUT_PATH = ROOT / "_tmp_vocadito_public_eval_20260512" / "replay_vocadito_old_guard_compare.json"
TOLERANCE_CENTS = 50.0
MAX_ALIGN_GAP_S = 0.050
TARGETS = [
    {
        "track_id": "vocadito_21",
        "windows": [
            {"label": "w0_0_1_5", "start_s": 0.0, "end_s": 1.5},
            {"label": "w6_0_7_5", "start_s": 6.0, "end_s": 7.5},
            {"label": "w9_0_10_5", "start_s": 9.0, "end_s": 10.5},
            {"label": "w20_5_22_0", "start_s": 20.5, "end_s": 22.0},
        ],
    },
    {
        "track_id": "vocadito_25",
        "windows": [
            {"label": "w7_0_8_5", "start_s": 7.0, "end_s": 8.5},
            {"label": "w8_5_10_0", "start_s": 8.5, "end_s": 10.0},
            {"label": "w14_0_15_5", "start_s": 14.0, "end_s": 15.5},
        ],
    },
    {
        "track_id": "vocadito_22",
        "windows": [
            {"label": "w5_5_7_0", "start_s": 5.5, "end_s": 7.0},
            {"label": "w9_0_10_5", "start_s": 9.0, "end_s": 10.5},
            {"label": "w33_5_35_0", "start_s": 33.5, "end_s": 35.0},
        ],
    },
    {
        "track_id": "vocadito_9",
        "windows": [
            {"label": "w4_5_6_0", "start_s": 4.5, "end_s": 6.0},
            {"label": "w12_0_13_5", "start_s": 12.0, "end_s": 13.5},
            {"label": "w14_5_16_0", "start_s": 14.5, "end_s": 16.0},
        ],
    },
]


def build_track(track_id: str) -> TrackSpec:
    wav_path = DATASET_ROOT / "Audio" / f"{track_id}.wav"
    annotation_path = DATASET_ROOT / "Annotations" / "F0" / f"{track_id}_f0.csv"
    return TrackSpec(
        track_id=track_id,
        audio_path=str(wav_path),
        annotation_path=str(annotation_path),
        annotation_format="time-hz",
        dataset_name="vocadito",
        audio_mode="auto",
    )


def slice_series(series: PitchSeries, start_s: float, end_s: float) -> PitchSeries:
    mask = (series.times_s >= float(start_s)) & (series.times_s < float(end_s))
    return canonicalize_series(series.times_s[mask], series.freqs_hz[mask])


def summarize_window(reference: PitchSeries, estimate: PitchSeries) -> Dict[str, Any]:
    aligned_estimate_hz = align_estimates_to_reference(reference, estimate, MAX_ALIGN_GAP_S)
    shared_mask = (reference.freqs_hz > 0.0) & (aligned_estimate_hz > 0.0)
    if not shared_mask.any():
        return {
            "shared_voiced": 0,
            "mean_abs_cents_error": None,
            "median_abs_cents_error": None,
            "median_est_ref_ratio": None,
        }
    ref_voiced_hz = reference.freqs_hz[shared_mask]
    est_voiced_hz = aligned_estimate_hz[shared_mask]
    cents_error = cents_difference(ref_voiced_hz, est_voiced_hz)
    ratios = est_voiced_hz / ref_voiced_hz
    return {
        "shared_voiced": int(shared_mask.sum()),
        "mean_abs_cents_error": round(float(cents_error.mean()), 6),
        "median_abs_cents_error": round(float(statistics.median(cents_error.tolist())), 6),
        "median_est_ref_ratio": round(float(statistics.median(ratios.tolist())), 6),
    }


def install_old_guard_replay(ui: Any) -> None:
    original_refine = ui._refine_onepass_payload_display_frequency

    def patched_refine(self: Any, pitch_data: Dict[str, Any], frequency: float, *, last_display: float = 0.0) -> float:
        current_frequency = safe_float(frequency, 0.0)
        actual_frequency = safe_float(
            original_refine(pitch_data, frequency, last_display=float(last_display or 0.0)),
            current_frequency,
        )
        branch_info = _inspect_refine_branch(self, pitch_data, current_frequency, float(last_display or 0.0))
        if str(branch_info.get("stage", "") or "") != "pull_applied":
            return float(actual_frequency)
        if abs(actual_frequency - current_frequency) > 1e-6:
            return float(actual_frequency)
        if not bool(branch_info.get("residual_octave_low_pull", False) or branch_info.get("history_anchored_low_pull", False)):
            return float(actual_frequency)
        corrected_frequency = safe_float(branch_info.get("corrected_frequency", 0.0), 0.0)
        if corrected_frequency > 0.0:
            return float(corrected_frequency)
        return float(actual_frequency)

    ui._refine_onepass_payload_display_frequency = types.MethodType(patched_refine, ui)


def run_track(track_spec: TrackSpec, windows: List[Dict[str, Any]], *, replay_old_guard: bool) -> Dict[str, Any]:
    app = None
    ui = None
    try:
        app, _module, ui, _ = onepass.load_runtime(show_init_log=False)
        onepass.install_backend_probes(ui)
        onepass.configure_backend_preferences(
            ui,
            prefer_mix_cpu=True,
            prefer_voice_cpu=True,
            force_external_mix=True,
            force_external_voice=True,
        )
        if replay_old_guard:
            install_old_guard_replay(ui)

        reference = load_reference_series(track_spec)
        estimate, runtime_summary = extract_estimated_series(app, ui, track_spec.audio_path)
        track_metrics = compute_track_metrics(track_spec, reference, estimate, TOLERANCE_CENTS, MAX_ALIGN_GAP_S)

        window_summaries: List[Dict[str, Any]] = []
        for window in windows:
            reference_window = slice_series(reference, float(window["start_s"]), float(window["end_s"]))
            estimate_window = slice_series(estimate, float(window["start_s"]), float(window["end_s"]))
            window_metrics = compute_track_metrics(track_spec, reference_window, estimate_window, TOLERANCE_CENTS, MAX_ALIGN_GAP_S)
            window_summaries.append(
                {
                    "label": str(window["label"]),
                    "start_s": float(window["start_s"]),
                    "end_s": float(window["end_s"]),
                    "counts": dict(window_metrics.get("counts", {}) or {}),
                    "metrics": dict(window_metrics.get("metrics", {}) or {}),
                    "error_summary": summarize_window(reference_window, estimate_window),
                }
            )

        return {
            "track_id": track_spec.track_id,
            "mode": "old_guard_replay" if replay_old_guard else "current",
            "runtime": runtime_summary,
            "counts": dict(track_metrics.get("counts", {}) or {}),
            "metrics": dict(track_metrics.get("metrics", {}) or {}),
            "windows": window_summaries,
        }
    finally:
        if app is not None and ui is not None:
            onepass.close_runtime(app, ui)


def compare_runs(current_run: Dict[str, Any], replay_run: Dict[str, Any]) -> Dict[str, Any]:
    current_metrics = dict(current_run.get("metrics", {}) or {})
    replay_metrics = dict(replay_run.get("metrics", {}) or {})
    window_deltas: List[Dict[str, Any]] = []
    replay_by_label = {str(item.get("label", "") or ""): item for item in list(replay_run.get("windows", []) or [])}
    for current_window in list(current_run.get("windows", []) or []):
        label = str(current_window.get("label", "") or "")
        replay_window = replay_by_label.get(label, {})
        current_error = dict(current_window.get("error_summary", {}) or {})
        replay_error = dict(replay_window.get("error_summary", {}) or {})
        current_window_metrics = dict(current_window.get("metrics", {}) or {})
        replay_window_metrics = dict(replay_window.get("metrics", {}) or {})
        window_deltas.append(
            {
                "label": label,
                "current_rpa": current_window_metrics.get("raw_pitch_accuracy"),
                "replay_rpa": replay_window_metrics.get("raw_pitch_accuracy"),
                "delta_rpa": round(float((replay_window_metrics.get("raw_pitch_accuracy") or 0.0) - (current_window_metrics.get("raw_pitch_accuracy") or 0.0)), 6),
                "current_mean_abs_cents_error": current_error.get("mean_abs_cents_error"),
                "replay_mean_abs_cents_error": replay_error.get("mean_abs_cents_error"),
                "delta_mean_abs_cents_error": None
                if current_error.get("mean_abs_cents_error") is None or replay_error.get("mean_abs_cents_error") is None
                else round(float(replay_error.get("mean_abs_cents_error") - current_error.get("mean_abs_cents_error")), 6),
                "current_median_est_ref_ratio": current_error.get("median_est_ref_ratio"),
                "replay_median_est_ref_ratio": replay_error.get("median_est_ref_ratio"),
            }
        )
    return {
        "track_id": str(current_run.get("track_id", "") or ""),
        "current_rpa": current_metrics.get("raw_pitch_accuracy"),
        "replay_rpa": replay_metrics.get("raw_pitch_accuracy"),
        "delta_rpa": round(float((replay_metrics.get("raw_pitch_accuracy") or 0.0) - (current_metrics.get("raw_pitch_accuracy") or 0.0)), 6),
        "current_gpe": current_metrics.get("gross_pitch_error"),
        "replay_gpe": replay_metrics.get("gross_pitch_error"),
        "current_vfa": current_metrics.get("voicing_false_alarm"),
        "replay_vfa": replay_metrics.get("voicing_false_alarm"),
        "window_deltas": window_deltas,
    }


def main() -> int:
    payload: Dict[str, Any] = {"tracks": [], "comparisons": []}
    for target in TARGETS:
        track_spec = build_track(str(target["track_id"]))
        windows = list(target["windows"])
        current_run = run_track(track_spec, windows, replay_old_guard=False)
        replay_run = run_track(track_spec, windows, replay_old_guard=True)
        payload["tracks"].append(current_run)
        payload["tracks"].append(replay_run)
        comparison = compare_runs(current_run, replay_run)
        payload["comparisons"].append(comparison)

        print(
            f"[track] {track_spec.track_id} current_rpa={comparison['current_rpa']} replay_rpa={comparison['replay_rpa']} delta={comparison['delta_rpa']}",
            flush=True,
        )
        for item in comparison["window_deltas"]:
            print(
                "  "
                + f"{item['label']} rpa={item['current_rpa']}->{item['replay_rpa']} "
                + f"mean_abs_cents={item['current_mean_abs_cents_error']}->{item['replay_mean_abs_cents_error']} "
                + f"median_ratio={item['current_median_est_ref_ratio']}->{item['replay_median_est_ref_ratio']}",
                flush=True,
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={OUTPUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())