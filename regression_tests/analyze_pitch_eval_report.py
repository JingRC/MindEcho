import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

import evaluate_pitch_dataset_metrics as pitch_eval


@dataclass
class VocaditoMetadata:
    track_id: str
    singer_id: str
    average_pitch_midi: Optional[float]
    language: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze a pitch evaluation report with error grouping and local spot-check windows.'
    )
    parser.add_argument('--report', required=True, help='JSON report produced by evaluate_pitch_dataset_metrics.py')
    parser.add_argument('--dataset-root', default='', help='Optional dataset root override for metadata discovery.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    parser.add_argument('--top-n', type=int, default=5, help='How many worst-RPA tracks to spot-check.')
    parser.add_argument('--window-seconds', type=float, default=1.5, help='Window size for local spot checks.')
    parser.add_argument('--window-step-seconds', type=float, default=0.5, help='Step size for local spot checks.')
    parser.add_argument('--min-window-voiced', type=int, default=20, help='Minimum voiced reference frames for a spot-check window.')
    parser.add_argument('--show-init-log', action='store_true', help='Print runtime init logs for the first spot-check track.')
    return parser.parse_args()


def safe_float(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return float(numeric)


def mean_or_none(values: Sequence[Optional[float]]) -> Optional[float]:
    valid = [float(item) for item in values if item is not None and math.isfinite(float(item))]
    if not valid:
        return None
    return float(np.mean(valid))


def quantile_thresholds(values: Sequence[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    valid = np.asarray([float(item) for item in values if item is not None and math.isfinite(float(item))], dtype=np.float64)
    if valid.size < 3:
        return None, None
    lower, upper = np.quantile(valid, [1.0 / 3.0, 2.0 / 3.0])
    return float(lower), float(upper)


def label_tertile(
    value: Optional[float],
    thresholds: Tuple[Optional[float], Optional[float]],
    low_label: str,
    mid_label: str,
    high_label: str,
) -> str:
    lower, upper = thresholds
    if value is None or lower is None or upper is None:
        return 'unknown'
    if value <= lower:
        return low_label
    if value <= upper:
        return mid_label
    return high_label


def normalize_track_token(track_id: Any) -> str:
    text = str(track_id or '').strip()
    if text.lower().startswith('vocadito_'):
        text = text.split('_', 1)[1]
    text = text.lstrip('0')
    return text or '0'


def load_vocadito_metadata(dataset_root: Path) -> Dict[str, VocaditoMetadata]:
    metadata_path = dataset_root / 'vocadito_metadata.csv'
    if not metadata_path.is_file():
        return {}
    records: Dict[str, VocaditoMetadata] = {}
    with metadata_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            track_token = normalize_track_token(row.get('track_id'))
            item = VocaditoMetadata(
                track_id=f'vocadito_{track_token}',
                singer_id=str((row.get('singer_id') or '')).strip(),
                average_pitch_midi=safe_float(row.get('average_pitch')),
                language=str((row.get('language') or 'unknown')).strip() or 'unknown',
            )
            records[track_token] = item
            records[item.track_id] = item
    return records


def hz_to_midi(hz_values: np.ndarray) -> np.ndarray:
    midi = np.zeros_like(hz_values, dtype=np.float64)
    voiced = hz_values > 0.0
    midi[voiced] = 69.0 + (12.0 * np.log2(np.maximum(hz_values[voiced], 1e-12) / 440.0))
    midi[~np.isfinite(midi)] = 0.0
    return midi


def compute_slide_features(times_s: np.ndarray, freqs_hz: np.ndarray) -> Dict[str, Optional[float]]:
    if times_s.size < 2 or freqs_hz.size < 2:
        return {'slide_ratio_80c': None, 'step_cents_p90': None}
    voiced = freqs_hz > 0.0
    if not np.any(voiced):
        return {'slide_ratio_80c': None, 'step_cents_p90': None}
    pair_mask = voiced[:-1] & voiced[1:]
    if not np.any(pair_mask):
        return {'slide_ratio_80c': None, 'step_cents_p90': None}
    if times_s.size >= 2:
        step_candidates = np.diff(times_s)
        finite_steps = step_candidates[np.isfinite(step_candidates) & (step_candidates > 0.0)]
        if finite_steps.size:
            pair_mask = pair_mask & (step_candidates <= (float(np.median(finite_steps)) * 2.5))
    if not np.any(pair_mask):
        return {'slide_ratio_80c': None, 'step_cents_p90': None}
    step_cents = pitch_eval.cents_difference(freqs_hz[:-1][pair_mask], freqs_hz[1:][pair_mask])
    if step_cents.size == 0:
        return {'slide_ratio_80c': None, 'step_cents_p90': None}
    return {
        'slide_ratio_80c': pitch_eval.round_metric(float(np.mean(step_cents >= 80.0))),
        'step_cents_p90': pitch_eval.round_metric(float(np.percentile(step_cents, 90.0))),
    }


def read_audio_mono(audio_path: Path) -> Tuple[np.ndarray, int]:
    samples, sample_rate = sf.read(str(audio_path), always_2d=True)
    if samples.size == 0:
        return np.zeros(0, dtype=np.float64), int(sample_rate)
    mono = np.mean(samples, axis=1, dtype=np.float64)
    return mono.astype(np.float64, copy=False), int(sample_rate)


def rms_dbfs_at_times(audio_path: Path, times_s: np.ndarray, window_s: float = 0.046) -> np.ndarray:
    if times_s.size == 0:
        return np.zeros(0, dtype=np.float64)
    mono, sample_rate = read_audio_mono(audio_path)
    if mono.size == 0 or sample_rate <= 0:
        return np.zeros(times_s.shape[0], dtype=np.float64)
    half_window = max(1, int(round(window_s * sample_rate * 0.5)))
    squared = np.square(mono, dtype=np.float64)
    cumsum = np.concatenate(([0.0], np.cumsum(squared, dtype=np.float64)))
    centers = np.clip(np.rint(times_s * sample_rate).astype(np.int64), 0, mono.size - 1)
    starts = np.clip(centers - half_window, 0, mono.size)
    ends = np.clip(centers + half_window, 0, mono.size)
    counts = np.maximum(ends - starts, 1)
    power = (cumsum[ends] - cumsum[starts]) / counts
    rms = np.sqrt(np.maximum(power, 1e-12))
    return 20.0 * np.log10(np.maximum(rms, 1e-8))


def compute_aligned_metrics(reference_hz: np.ndarray, aligned_estimate_hz: np.ndarray, tolerance_cents: float) -> Dict[str, Any]:
    reference_voiced = reference_hz > 0.0
    estimate_voiced = aligned_estimate_hz > 0.0
    reference_voiced_count = int(np.count_nonzero(reference_voiced))
    reference_unvoiced_count = int(np.count_nonzero(~reference_voiced))
    estimate_voiced_count = int(np.count_nonzero(estimate_voiced))
    voiced_hits = int(np.count_nonzero(reference_voiced & estimate_voiced))
    false_alarms = int(np.count_nonzero((~reference_voiced) & estimate_voiced))

    shared_voiced_mask = reference_voiced & estimate_voiced
    shared_voiced_count = int(np.count_nonzero(shared_voiced_mask))
    if shared_voiced_count > 0:
        ref_voiced_hz = reference_hz[shared_voiced_mask]
        est_voiced_hz = aligned_estimate_hz[shared_voiced_mask]
        pitch_error_cents = pitch_eval.cents_difference(ref_voiced_hz, est_voiced_hz)
        raw_pitch_hits = int(np.count_nonzero(pitch_error_cents <= tolerance_cents))
        raw_chroma_hits = int(np.count_nonzero(pitch_eval.chroma_difference(ref_voiced_hz, est_voiced_hz) <= tolerance_cents))
        gross_pitch_errors = int(np.count_nonzero(pitch_error_cents > tolerance_cents))
        mean_abs_cents_error = float(np.mean(pitch_error_cents))
        median_est_ref_ratio = float(np.median(est_voiced_hz / np.maximum(ref_voiced_hz, 1e-12)))
    else:
        raw_pitch_hits = 0
        raw_chroma_hits = 0
        gross_pitch_errors = 0
        mean_abs_cents_error = None
        median_est_ref_ratio = None

    voicing_recall = pitch_eval.safe_rate(voiced_hits, reference_voiced_count)
    voicing_precision = pitch_eval.safe_rate(voiced_hits, estimate_voiced_count)
    return {
        'counts': {
            'reference_voiced': reference_voiced_count,
            'reference_unvoiced': reference_unvoiced_count,
            'estimate_voiced': estimate_voiced_count,
            'shared_voiced': shared_voiced_count,
            'voiced_hits': voiced_hits,
            'false_alarms': false_alarms,
            'raw_pitch_hits': raw_pitch_hits,
            'raw_chroma_hits': raw_chroma_hits,
            'gross_pitch_errors': gross_pitch_errors,
        },
        'metrics': {
            'raw_pitch_accuracy': pitch_eval.round_metric(pitch_eval.safe_rate(raw_pitch_hits, reference_voiced_count)),
            'raw_chroma_accuracy': pitch_eval.round_metric(pitch_eval.safe_rate(raw_chroma_hits, reference_voiced_count)),
            'gross_pitch_error': pitch_eval.round_metric(pitch_eval.safe_rate(gross_pitch_errors, shared_voiced_count)),
            'voicing_recall': pitch_eval.round_metric(voicing_recall),
            'voicing_precision': pitch_eval.round_metric(voicing_precision),
            'voicing_f1': pitch_eval.round_metric(pitch_eval.safe_f1(voicing_precision, voicing_recall)),
            'voicing_false_alarm': pitch_eval.round_metric(pitch_eval.safe_rate(false_alarms, reference_unvoiced_count)),
            'mean_abs_cents_error': pitch_eval.round_metric(mean_abs_cents_error),
            'median_est_ref_ratio': pitch_eval.round_metric(median_est_ref_ratio),
        },
    }


def summarize_groups(rows: Sequence[Dict[str, Any]], group_key: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(group_key) or 'unknown')
        grouped.setdefault(key, []).append(row)
    summary: List[Dict[str, Any]] = []
    for key, items in grouped.items():
        worst_tracks = sorted(items, key=lambda item: float(item.get('raw_pitch_accuracy') or 1.0))[:3]
        summary.append(
            {
                'group': key,
                'track_count': len(items),
                'mean_raw_pitch_accuracy': pitch_eval.round_metric(mean_or_none([item.get('raw_pitch_accuracy') for item in items])),
                'mean_raw_chroma_accuracy': pitch_eval.round_metric(mean_or_none([item.get('raw_chroma_accuracy') for item in items])),
                'mean_gross_pitch_error': pitch_eval.round_metric(mean_or_none([item.get('gross_pitch_error') for item in items])),
                'mean_voicing_f1': pitch_eval.round_metric(mean_or_none([item.get('voicing_f1') for item in items])),
                'mean_voicing_false_alarm': pitch_eval.round_metric(mean_or_none([item.get('voicing_false_alarm') for item in items])),
                'mean_average_pitch_midi': pitch_eval.round_metric(mean_or_none([item.get('average_pitch_midi') for item in items])),
                'mean_slide_ratio_80c': pitch_eval.round_metric(mean_or_none([item.get('slide_ratio_80c') for item in items])),
                'mean_voiced_rms_dbfs': pitch_eval.round_metric(mean_or_none([item.get('voiced_rms_dbfs') for item in items])),
                'worst_tracks': [
                    {
                        'track_id': item.get('track_id'),
                        'raw_pitch_accuracy': item.get('raw_pitch_accuracy'),
                        'language': item.get('language'),
                    }
                    for item in worst_tracks
                ],
            }
        )
    summary.sort(key=lambda item: (float(item.get('mean_raw_pitch_accuracy') or 1.0), -int(item.get('track_count') or 0), item.get('group', '')))
    return summary


def count_values(rows: Sequence[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or 'unknown')
        counts[label] = counts.get(label, 0) + 1
    items = [{'group': label, 'track_count': count} for label, count in counts.items()]
    items.sort(key=lambda item: (-int(item['track_count']), item['group']))
    return items


def build_track_rows(report: Dict[str, Any], metadata_by_track: Dict[str, VocaditoMetadata]) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[float, float]], Dict[str, Any]]:
    track_rows: List[Dict[str, Any]] = []
    track_items = list(report.get('tracks', []) or [])
    for item in track_items:
        track_id = str(item.get('track_id') or '').strip()
        if not track_id:
            continue
        reference = pitch_eval.TrackSpec(
            track_id=track_id,
            audio_path=str(item.get('audio_path') or ''),
            annotation_path=str(item.get('annotation_path') or ''),
            annotation_format=str(item.get('annotation_format') or 'time-hz'),
            dataset_name=str(item.get('dataset_name') or report.get('dataset') or ''),
            audio_mode=str(item.get('audio_mode') or 'auto'),
        )
        reference_series = pitch_eval.load_reference_series(reference)
        voiced_mask = reference_series.freqs_hz > 0.0
        voiced_hz = reference_series.freqs_hz[voiced_mask]
        reference_midi = hz_to_midi(voiced_hz) if voiced_hz.size else np.zeros(0, dtype=np.float64)
        token = normalize_track_token(track_id)
        metadata = metadata_by_track.get(track_id) or metadata_by_track.get(token)
        voiced_rms = rms_dbfs_at_times(Path(reference.audio_path), reference_series.times_s)
        voiced_rms_dbfs = None
        if voiced_rms.size and np.any(voiced_mask):
            voiced_rms_dbfs = float(np.mean(voiced_rms[voiced_mask]))
        slide_features = compute_slide_features(reference_series.times_s, reference_series.freqs_hz)
        track_rows.append(
            {
                'track_id': track_id,
                'audio_path': reference.audio_path,
                'annotation_path': reference.annotation_path,
                'annotation_format': reference.annotation_format,
                'audio_mode': reference.audio_mode,
                'dataset_name': reference.dataset_name,
                'language': metadata.language if metadata else 'unknown',
                'singer_id': metadata.singer_id if metadata else '',
                'average_pitch_midi': metadata.average_pitch_midi if metadata and metadata.average_pitch_midi is not None else pitch_eval.round_metric(float(np.mean(reference_midi))) if reference_midi.size else None,
                'median_reference_midi': pitch_eval.round_metric(float(np.median(reference_midi))) if reference_midi.size else None,
                'slide_ratio_80c': slide_features.get('slide_ratio_80c'),
                'step_cents_p90': slide_features.get('step_cents_p90'),
                'voiced_rms_dbfs': pitch_eval.round_metric(voiced_rms_dbfs),
                'raw_pitch_accuracy': safe_float((item.get('metrics', {}) or {}).get('raw_pitch_accuracy')),
                'raw_chroma_accuracy': safe_float((item.get('metrics', {}) or {}).get('raw_chroma_accuracy')),
                'gross_pitch_error': safe_float((item.get('metrics', {}) or {}).get('gross_pitch_error')),
                'voicing_recall': safe_float((item.get('metrics', {}) or {}).get('voicing_recall')),
                'voicing_precision': safe_float((item.get('metrics', {}) or {}).get('voicing_precision')),
                'voicing_f1': safe_float((item.get('metrics', {}) or {}).get('voicing_f1')),
                'voicing_false_alarm': safe_float((item.get('metrics', {}) or {}).get('voicing_false_alarm')),
            }
        )

    pitch_thresholds = quantile_thresholds([item.get('average_pitch_midi') for item in track_rows])
    slide_thresholds = quantile_thresholds([item.get('slide_ratio_80c') for item in track_rows])
    energy_thresholds = quantile_thresholds([item.get('voiced_rms_dbfs') for item in track_rows])
    for item in track_rows:
        item['pitch_band'] = label_tertile(item.get('average_pitch_midi'), pitch_thresholds, 'low-pitch', 'mid-pitch', 'high-pitch')
        item['slide_band'] = label_tertile(item.get('slide_ratio_80c'), slide_thresholds, 'stable', 'moderate-slide', 'slide-heavy')
        item['energy_band'] = label_tertile(item.get('voiced_rms_dbfs'), energy_thresholds, 'weak-energy', 'mid-energy', 'strong-energy')

    rpa_values = [item.get('raw_pitch_accuracy') for item in track_rows]
    rpa_valid = [float(item) for item in rpa_values if item is not None and math.isfinite(float(item))]
    low_score_threshold = float(np.quantile(np.asarray(rpa_valid, dtype=np.float64), 0.25)) if rpa_valid else None

    thresholds = {
        'average_pitch_midi_tertiles': pitch_thresholds,
        'slide_ratio_80c_tertiles': slide_thresholds,
        'voiced_rms_dbfs_tertiles': energy_thresholds,
        'low_score_rpa_cutoff': low_score_threshold,
    }
    extras = {
        'track_count': len(track_rows),
        'low_score_track_count': int(np.count_nonzero([(item.get('raw_pitch_accuracy') is not None and low_score_threshold is not None and float(item.get('raw_pitch_accuracy')) <= low_score_threshold) for item in track_rows])) if low_score_threshold is not None else 0,
    }
    return track_rows, thresholds, extras


def classify_window_issue(
    metrics: Dict[str, Any],
    slide_ratio_80c: Optional[float],
    voiced_rms_dbfs: Optional[float],
    slide_thresholds: Tuple[Optional[float], Optional[float]],
    energy_thresholds: Tuple[Optional[float], Optional[float]],
) -> str:
    median_ratio = safe_float((metrics.get('metrics', {}) or {}).get('median_est_ref_ratio'))
    voicing_false_alarm = safe_float((metrics.get('metrics', {}) or {}).get('voicing_false_alarm'))
    voicing_recall = safe_float((metrics.get('metrics', {}) or {}).get('voicing_recall'))
    if median_ratio is not None and median_ratio >= 1.8:
        return 'high-harmonic-lock'
    if median_ratio is not None and median_ratio <= 0.55:
        return 'octave-low'
    if voicing_false_alarm is not None and voicing_false_alarm >= 0.5:
        return 'over-voicing'
    if voicing_recall is not None and voicing_recall <= 0.6:
        return 'voicing-drop'
    slide_heavy_threshold = slide_thresholds[1]
    if slide_ratio_80c is not None and slide_heavy_threshold is not None and slide_ratio_80c >= slide_heavy_threshold:
        return 'slide-heavy'
    weak_energy_threshold = energy_thresholds[0]
    if voiced_rms_dbfs is not None and weak_energy_threshold is not None and voiced_rms_dbfs <= weak_energy_threshold:
        return 'weak-energy'
    return 'large-pitch-offset'


def collect_spotcheck_windows(
    track_row: Dict[str, Any],
    tolerance_cents: float,
    max_align_gap: float,
    window_seconds: float,
    window_step_seconds: float,
    min_window_voiced: int,
    slide_thresholds: Tuple[Optional[float], Optional[float]],
    energy_thresholds: Tuple[Optional[float], Optional[float]],
    show_init_log: bool,
) -> Dict[str, Any]:
    reference = pitch_eval.TrackSpec(
        track_id=str(track_row.get('track_id') or ''),
        audio_path=str(track_row.get('audio_path') or ''),
        annotation_path=str(track_row.get('annotation_path') or ''),
        annotation_format=str(track_row.get('annotation_format') or 'time-hz'),
        dataset_name=str(track_row.get('dataset_name') or ''),
        audio_mode=str(track_row.get('audio_mode') or 'auto'),
    )
    reference_series = pitch_eval.load_reference_series(reference)
    temp_audio_path: Optional[str] = None
    app = None
    ui = None
    runtime_summary: Dict[str, Any] = {}
    try:
        analysis_audio_path, temp_audio_path = pitch_eval.prepare_analysis_audio(reference)
        app, module, ui, init_log = pitch_eval.onepass.load_runtime(show_init_log=show_init_log)
        if show_init_log and init_log:
            print(init_log)
        estimate_series, runtime_summary = pitch_eval.extract_estimated_series(app, ui, analysis_audio_path)
        aligned_estimate = pitch_eval.align_estimates_to_reference(reference_series, estimate_series, max_align_gap)
    finally:
        if app is not None and ui is not None:
            try:
                pitch_eval.onepass.close_runtime(app, ui)
            except Exception:
                pass
        if temp_audio_path:
            try:
                Path(temp_audio_path).unlink(missing_ok=True)
            except Exception:
                pass

    audio_rms_dbfs = rms_dbfs_at_times(Path(reference.audio_path), reference_series.times_s)
    window_summaries: List[Dict[str, Any]] = []
    if reference_series.times_s.size:
        start_time = float(reference_series.times_s[0])
        end_limit = float(reference_series.times_s[-1])
        current = start_time
        while current <= end_limit:
            window_end = current + window_seconds
            mask = (reference_series.times_s >= current) & (reference_series.times_s < window_end)
            if np.count_nonzero(mask) == 0:
                current += window_step_seconds
                continue
            ref_window = reference_series.freqs_hz[mask]
            est_window = aligned_estimate[mask]
            voiced_count = int(np.count_nonzero(ref_window > 0.0))
            if voiced_count < int(min_window_voiced):
                current += window_step_seconds
                continue
            metric_block = compute_aligned_metrics(ref_window, est_window, tolerance_cents)
            slide_features = compute_slide_features(reference_series.times_s[mask], ref_window)
            voiced_mask = ref_window > 0.0
            voiced_rms_dbfs = None
            if audio_rms_dbfs.size and np.any(voiced_mask):
                voiced_rms_dbfs = float(np.mean(audio_rms_dbfs[mask][voiced_mask]))
            issue = classify_window_issue(
                metric_block,
                slide_features.get('slide_ratio_80c'),
                voiced_rms_dbfs,
                slide_thresholds,
                energy_thresholds,
            )
            window_summaries.append(
                {
                    'start_s': pitch_eval.round_metric(current),
                    'end_s': pitch_eval.round_metric(window_end),
                    'reference_voiced_frames': voiced_count,
                    'slide_ratio_80c': slide_features.get('slide_ratio_80c'),
                    'step_cents_p90': slide_features.get('step_cents_p90'),
                    'voiced_rms_dbfs': pitch_eval.round_metric(voiced_rms_dbfs),
                    'dominant_issue': issue,
                    'counts': metric_block.get('counts', {}),
                    'metrics': metric_block.get('metrics', {}),
                }
            )
            current += window_step_seconds

    ranked_windows = sorted(
        window_summaries,
        key=lambda item: (
            float((item.get('metrics', {}) or {}).get('raw_pitch_accuracy') or 1.0),
            -int(item.get('reference_voiced_frames') or 0),
            -float((item.get('metrics', {}) or {}).get('gross_pitch_error') or 0.0),
            -float((item.get('metrics', {}) or {}).get('mean_abs_cents_error') or 0.0),
        ),
    )
    selected: List[Dict[str, Any]] = []
    for item in ranked_windows:
        overlaps = False
        for chosen in selected:
            if not (float(item['end_s']) <= float(chosen['start_s']) or float(item['start_s']) >= float(chosen['end_s'])):
                overlaps = True
                break
        if overlaps:
            continue
        selected.append(item)
        if len(selected) >= 3:
            break

    return {
        'track_id': track_row.get('track_id'),
        'language': track_row.get('language'),
        'pitch_band': track_row.get('pitch_band'),
        'slide_band': track_row.get('slide_band'),
        'energy_band': track_row.get('energy_band'),
        'raw_pitch_accuracy': track_row.get('raw_pitch_accuracy'),
        'gross_pitch_error': track_row.get('gross_pitch_error'),
        'voicing_f1': track_row.get('voicing_f1'),
        'voicing_false_alarm': track_row.get('voicing_false_alarm'),
        'runtime': runtime_summary,
        'windows': selected,
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report).resolve()
    report = json.loads(report_path.read_text(encoding='utf-8'))

    dataset_root_text = str(args.dataset_root or report.get('dataset_root') or '').strip()
    dataset_root = Path(dataset_root_text).resolve() if dataset_root_text else None
    metadata_by_track = load_vocadito_metadata(dataset_root) if dataset_root is not None else {}

    track_rows, thresholds, extras = build_track_rows(report, metadata_by_track)
    track_rows_sorted = sorted(track_rows, key=lambda item: float(item.get('raw_pitch_accuracy') or 1.0))
    low_score_threshold = thresholds.get('low_score_rpa_cutoff')
    low_score_rows = [
        item
        for item in track_rows_sorted
        if low_score_threshold is not None and item.get('raw_pitch_accuracy') is not None and float(item['raw_pitch_accuracy']) <= float(low_score_threshold)
    ]

    settings = dict(report.get('settings', {}) or {})
    tolerance_cents = safe_float(settings.get('tolerance_cents')) or pitch_eval.DEFAULT_TOLERANCE_CENTS
    max_align_gap = safe_float(settings.get('max_align_gap')) or 0.05

    worst_rows = track_rows_sorted[: max(int(args.top_n), 0)]
    spotchecks: List[Dict[str, Any]] = []
    for index, row in enumerate(worst_rows, start=1):
        print(f"[pitch-analysis] {index}/{len(worst_rows)} {row.get('track_id')}")
        spotchecks.append(
            collect_spotcheck_windows(
                row,
                tolerance_cents,
                max_align_gap,
                float(args.window_seconds),
                float(args.window_step_seconds),
                int(args.min_window_voiced),
                tuple(thresholds.get('slide_ratio_80c_tertiles') or (None, None)),
                tuple(thresholds.get('voiced_rms_dbfs_tertiles') or (None, None)),
                bool(args.show_init_log and index == 1),
            )
        )

    issue_counts: Dict[str, int] = {}
    for item in spotchecks:
        windows = list(item.get('windows', []) or [])
        if not windows:
            continue
        issue = str((windows[0] or {}).get('dominant_issue') or 'unknown')
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    analysis = {
        'report_path': str(report_path),
        'dataset': report.get('dataset'),
        'dataset_root': str(dataset_root) if dataset_root is not None else '',
        'thresholds': pitch_eval.to_jsonable(thresholds),
        'summary': {
            'track_count': extras.get('track_count'),
            'low_score_track_count': extras.get('low_score_track_count'),
            'micro': (report.get('aggregate', {}) or {}).get('micro', {}),
            'macro': (report.get('aggregate', {}) or {}).get('macro', {}),
        },
        'group_summaries': {
            'language': summarize_groups(track_rows, 'language'),
            'pitch_band': summarize_groups(track_rows, 'pitch_band'),
            'slide_band': summarize_groups(track_rows, 'slide_band'),
            'energy_band': summarize_groups(track_rows, 'energy_band'),
        },
        'low_score_profile': {
            'rpa_cutoff': pitch_eval.round_metric(low_score_threshold),
            'language': count_values(low_score_rows, 'language'),
            'pitch_band': count_values(low_score_rows, 'pitch_band'),
            'slide_band': count_values(low_score_rows, 'slide_band'),
            'energy_band': count_values(low_score_rows, 'energy_band'),
        },
        'worst_tracks': [
            {
                'track_id': item.get('track_id'),
                'language': item.get('language'),
                'average_pitch_midi': item.get('average_pitch_midi'),
                'pitch_band': item.get('pitch_band'),
                'slide_band': item.get('slide_band'),
                'energy_band': item.get('energy_band'),
                'raw_pitch_accuracy': item.get('raw_pitch_accuracy'),
                'gross_pitch_error': item.get('gross_pitch_error'),
                'voicing_f1': item.get('voicing_f1'),
                'voicing_false_alarm': item.get('voicing_false_alarm'),
            }
            for item in worst_rows
        ],
        'spotchecks': spotchecks,
        'spotcheck_issue_summary': [
            {'issue': issue, 'track_count': count}
            for issue, count in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }

    low_pitch_group = summarize_groups(track_rows, 'pitch_band')
    language_group = summarize_groups(track_rows, 'language')
    slide_group = summarize_groups(track_rows, 'slide_band')
    energy_group = summarize_groups(track_rows, 'energy_band')
    print(
        f"[pitch-analysis] tracks={extras.get('track_count')} low-score={extras.get('low_score_track_count')} "
        f"cutoff={pitch_eval.format_metric(low_score_threshold)}"
    )
    if low_pitch_group:
        worst_pitch = low_pitch_group[0]
        print(
            f"  worst pitch-band {worst_pitch.get('group')} RPA={pitch_eval.format_metric(worst_pitch.get('mean_raw_pitch_accuracy'))} "
            f"tracks={worst_pitch.get('track_count')}"
        )
    if language_group:
        worst_language = language_group[0]
        print(
            f"  worst language {worst_language.get('group')} RPA={pitch_eval.format_metric(worst_language.get('mean_raw_pitch_accuracy'))} "
            f"tracks={worst_language.get('track_count')}"
        )
    if slide_group:
        worst_slide = slide_group[0]
        print(
            f"  worst slide-band {worst_slide.get('group')} RPA={pitch_eval.format_metric(worst_slide.get('mean_raw_pitch_accuracy'))} "
            f"tracks={worst_slide.get('track_count')}"
        )
    if energy_group:
        worst_energy = energy_group[0]
        print(
            f"  worst energy-band {worst_energy.get('group')} RPA={pitch_eval.format_metric(worst_energy.get('mean_raw_pitch_accuracy'))} "
            f"tracks={worst_energy.get('track_count')}"
        )
    for item in spotchecks:
        windows = list(item.get('windows', []) or [])
        head = windows[0] if windows else {}
        print(
            f"  spotcheck {item.get('track_id')} RPA={pitch_eval.format_metric(item.get('raw_pitch_accuracy'))} "
            f"issue={(head or {}).get('dominant_issue', 'n/a')} "
            f"window={pitch_eval.round_metric((head or {}).get('start_s'))}-{pitch_eval.round_metric((head or {}).get('end_s'))}"
        )

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(pitch_eval.to_jsonable(analysis), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[pitch-analysis] wrote {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())