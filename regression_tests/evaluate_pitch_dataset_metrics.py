import argparse
import csv
import json
import math
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    import matplotlib

    matplotlib.use('Agg')
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import debug_gui_onepass_practical as onepass  # noqa: E402


AUDIO_SUFFIXES = {'.wav', '.flac', '.mp3', '.ogg', '.m4a', '.aac', '.aiff', '.aif'}
IKALA_TIME_STEP_SECONDS = 0.032
DEFAULT_TOLERANCE_CENTS = 50.0
FLOAT_RE = re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')


@dataclass
class TrackSpec:
    track_id: str
    audio_path: str
    annotation_path: str
    annotation_format: str
    dataset_name: str
    audio_mode: str = 'auto'


@dataclass
class PitchSeries:
    times_s: np.ndarray
    freqs_hz: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Evaluate the project pitch tracker against annotated singing datasets via the real GUI one-pass runtime.'
    )
    parser.add_argument(
        '--dataset',
        choices=('medleydb-pitch', 'ikala', 'vocadito', 'manifest'),
        required=True,
        help='Dataset flavor. manifest means explicit track pairs from a CSV file.',
    )
    parser.add_argument('--dataset-root', default='', help='Dataset root for medleydb-pitch or ikala auto-discovery.')
    parser.add_argument(
        '--manifest',
        default='',
        help='Optional CSV manifest. Required for dataset=manifest. Columns: track_id,audio_path,annotation_path[,annotation_format][,audio_mode].',
    )
    parser.add_argument(
        '--annotation-format',
        choices=('medleydb-pitch', 'ikala-midi-lines', 'time-hz'),
        default='',
        help='Default annotation format for manifest rows when the column is omitted.',
    )
    parser.add_argument(
        '--audio-mode',
        choices=('auto', 'vocal', 'mix', 'instrumental'),
        default='auto',
        help='Audio interpretation. For iKala, auto resolves to vocal. Manifest rows may override this.',
    )
    parser.add_argument('--track-id', action='append', default=[], help='Restrict evaluation to one or more track ids.')
    parser.add_argument('--limit', type=int, default=0, help='Optional maximum number of tracks to evaluate.')
    parser.add_argument('--tolerance-cents', type=float, default=DEFAULT_TOLERANCE_CENTS, help='Pitch tolerance for RPA/RCA.')
    parser.add_argument(
        '--max-align-gap',
        type=float,
        default=0.050,
        help='Maximum nearest-neighbor alignment gap in seconds when mapping estimates to reference frames.',
    )
    parser.add_argument('--show-init-log', action='store_true', help='Print captured runtime initialization logs.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    parser.add_argument(
        '--fail-on-track-error',
        action='store_true',
        help='Return a non-zero exit code if any selected track fails to evaluate.',
    )
    return parser.parse_args()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(numeric):
        return float(default)
    return numeric


def safe_rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def safe_f1(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
    if precision is None or recall is None:
        return None
    if precision <= 0.0 and recall <= 0.0:
        return 0.0
    denom = float(precision) + float(recall)
    if denom <= 0.0:
        return None
    return (2.0 * float(precision) * float(recall)) / denom


def round_metric(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 6)


def rel_or_abs(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def parse_float_tokens(text: str) -> List[float]:
    return [float(match.group(0)) for match in FLOAT_RE.finditer(str(text or ''))]


def midi_to_hz(midi_values: np.ndarray) -> np.ndarray:
    hz = 440.0 * np.power(2.0, (midi_values - 69.0) / 12.0)
    hz = np.where(midi_values > 0.0, hz, 0.0)
    hz = np.where(np.isfinite(hz), hz, 0.0)
    return hz.astype(np.float64, copy=False)


def canonicalize_series(times_s: Sequence[float], freqs_hz: Sequence[float]) -> PitchSeries:
    if len(times_s) == 0 or len(freqs_hz) == 0:
        return PitchSeries(np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))
    times = np.asarray(times_s, dtype=np.float64)
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    finite_mask = np.isfinite(times) & np.isfinite(freqs)
    times = times[finite_mask]
    freqs = freqs[finite_mask]
    freqs = np.where(freqs > 0.0, freqs, 0.0)
    if times.size == 0:
        return PitchSeries(np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))
    order = np.argsort(times, kind='mergesort')
    times = times[order]
    freqs = freqs[order]
    unique_times: List[float] = []
    unique_freqs: List[float] = []
    for time_value, freq_value in zip(times, freqs):
        time_scalar = float(time_value)
        freq_scalar = float(freq_value)
        if unique_times and math.isclose(unique_times[-1], time_scalar, rel_tol=0.0, abs_tol=1e-9):
            unique_freqs[-1] = freq_scalar
        else:
            unique_times.append(time_scalar)
            unique_freqs.append(freq_scalar)
    return PitchSeries(np.asarray(unique_times, dtype=np.float64), np.asarray(unique_freqs, dtype=np.float64))


def load_manifest_tracks(manifest_path: Path, default_annotation_format: str, default_audio_mode: str) -> List[TrackSpec]:
    rows: List[TrackSpec] = []
    with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        required = {'track_id', 'audio_path', 'annotation_path'}
        missing = required.difference(set(reader.fieldnames or []))
        if missing:
            raise ValueError(f'manifest missing required columns: {sorted(missing)}')
        for row_index, row in enumerate(reader, start=2):
            track_id = str((row.get('track_id') or '')).strip()
            audio_path = str((row.get('audio_path') or '')).strip()
            annotation_path = str((row.get('annotation_path') or '')).strip()
            annotation_format = str((row.get('annotation_format') or default_annotation_format or '')).strip()
            audio_mode = str((row.get('audio_mode') or default_audio_mode or 'auto')).strip() or 'auto'
            if not track_id or not audio_path or not annotation_path:
                raise ValueError(f'manifest row {row_index} has empty required values')
            if not annotation_format:
                raise ValueError(f'manifest row {row_index} needs annotation_format or --annotation-format')
            rows.append(
                TrackSpec(
                    track_id=track_id,
                    audio_path=str(rel_or_abs(audio_path, manifest_path.parent)),
                    annotation_path=str(rel_or_abs(annotation_path, manifest_path.parent)),
                    annotation_format=annotation_format,
                    dataset_name='manifest',
                    audio_mode=audio_mode,
                )
            )
    return rows


def find_named_dir(root: Path, target_names: Iterable[str]) -> Optional[Path]:
    normalized = {name.lower() for name in target_names}
    for candidate in [root] + [path for path in root.rglob('*') if path.is_dir()]:
        if candidate.name.lower() in normalized:
            return candidate
    return None


def build_ikala_tracks(root: Path, default_audio_mode: str) -> List[TrackSpec]:
    pitch_dir = find_named_dir(root, ('PitchLabel',))
    audio_dir = find_named_dir(root, ('Wavfile', 'WavFile'))
    if pitch_dir is None or audio_dir is None:
        raise FileNotFoundError('ikala auto-discovery needs PitchLabel and Wavfile directories under --dataset-root')

    audio_by_stem: Dict[str, Path] = {}
    for audio_path in audio_dir.rglob('*'):
        if audio_path.is_file() and audio_path.suffix.lower() in AUDIO_SUFFIXES:
            audio_by_stem[audio_path.stem.lower()] = audio_path

    tracks: List[TrackSpec] = []
    resolved_audio_mode = default_audio_mode if default_audio_mode != 'auto' else 'vocal'
    for annotation_path in sorted(path for path in pitch_dir.rglob('*') if path.is_file()):
        key = annotation_path.stem.lower()
        audio_path = audio_by_stem.get(key)
        if audio_path is None:
            continue
        tracks.append(
            TrackSpec(
                track_id=annotation_path.stem,
                audio_path=str(audio_path.resolve()),
                annotation_path=str(annotation_path.resolve()),
                annotation_format='ikala-midi-lines',
                dataset_name='ikala',
                audio_mode=resolved_audio_mode,
            )
        )
    if not tracks:
        raise FileNotFoundError('ikala auto-discovery found no matching audio / PitchLabel pairs')
    return tracks


def normalized_key(path: Path) -> str:
    stem = path.stem.lower()
    for token in ('pitch', 'annotation', 'annot', 'f0', 'melody', 'notes', 'pyin', 'vocal', 'audio'):
        stem = stem.replace(token, '')
    stem = re.sub(r'[^a-z0-9]+', '', stem)
    return stem


def match_audio_for_annotation(annotation_path: Path, audio_candidates: Sequence[Path]) -> Optional[Path]:
    if not audio_candidates:
        return None
    annotation_stem = annotation_path.stem.lower()
    annotation_key = normalized_key(annotation_path)
    scored: List[Tuple[int, int, Path]] = []
    for index, audio_path in enumerate(audio_candidates):
        audio_stem = audio_path.stem.lower()
        audio_key = normalized_key(audio_path)
        score = 0
        if annotation_stem == audio_stem:
            score = 100
        elif annotation_key and annotation_key == audio_key:
            score = 90
        elif annotation_stem in audio_stem or audio_stem in annotation_stem:
            score = 75
        elif annotation_key and (annotation_key in audio_key or audio_key in annotation_key):
            score = 65
        elif annotation_path.parent.name.lower() == audio_path.parent.name.lower():
            score = 55
        if score > 0:
            scored.append((score, -index, audio_path))
    if not scored:
        return None
    scored.sort(reverse=True)
    top_score = scored[0][0]
    top_matches = [item for item in scored if item[0] == top_score]
    if len(top_matches) > 1:
        return None
    return top_matches[0][2]


def build_medleydb_pitch_tracks(root: Path, default_audio_mode: str) -> List[TrackSpec]:
    audio_files = sorted(path for path in root.rglob('*') if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES)
    pitch_files = sorted(
        path
        for path in root.rglob('*.csv')
        if path.is_file() and 'note' not in path.name.lower() and 'pyin' not in path.name.lower()
    )
    if not audio_files or not pitch_files:
        raise FileNotFoundError('medleydb-pitch auto-discovery needs audio files and pitch csv files under --dataset-root')

    tracks: List[TrackSpec] = []
    for annotation_path in pitch_files:
        audio_path = match_audio_for_annotation(annotation_path, audio_files)
        if audio_path is None:
            continue
        tracks.append(
            TrackSpec(
                track_id=annotation_path.stem,
                audio_path=str(audio_path.resolve()),
                annotation_path=str(annotation_path.resolve()),
                annotation_format='medleydb-pitch',
                dataset_name='medleydb-pitch',
                audio_mode=default_audio_mode,
            )
        )
    if not tracks:
        raise FileNotFoundError('medleydb-pitch auto-discovery found no unique audio / pitch pairs; use --manifest for explicit mapping')
    return tracks


def build_vocadito_tracks(root: Path, default_audio_mode: str) -> List[TrackSpec]:
    audio_dir = find_named_dir(root, ('Audio',))
    f0_dir = root / 'Annotations' / 'F0'
    if audio_dir is None or not f0_dir.is_dir():
        raise FileNotFoundError('vocadito auto-discovery needs Audio and Annotations/F0 directories under --dataset-root')

    tracks: List[TrackSpec] = []
    for audio_path in sorted(path for path in audio_dir.rglob('*') if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES):
        annotation_path = f0_dir / f'{audio_path.stem}_f0.csv'
        if not annotation_path.is_file():
            continue
        tracks.append(
            TrackSpec(
                track_id=audio_path.stem,
                audio_path=str(audio_path.resolve()),
                annotation_path=str(annotation_path.resolve()),
                annotation_format='time-hz',
                dataset_name='vocadito',
                audio_mode=default_audio_mode,
            )
        )
    if not tracks:
        raise FileNotFoundError('vocadito auto-discovery found no Audio/<stem>.wav to Annotations/F0/<stem>_f0.csv pairs')
    return tracks


def resolve_tracks(args: argparse.Namespace) -> List[TrackSpec]:
    tracks: List[TrackSpec]
    if args.dataset == 'manifest':
        if not args.manifest:
            raise ValueError('--manifest is required when --dataset manifest is selected')
        tracks = load_manifest_tracks(Path(args.manifest).resolve(), args.annotation_format, args.audio_mode)
    else:
        if args.manifest:
            tracks = load_manifest_tracks(Path(args.manifest).resolve(), args.annotation_format, args.audio_mode)
            for track in tracks:
                track.dataset_name = args.dataset
                if args.dataset == 'ikala' and track.annotation_format == 'time-hz' and not args.annotation_format:
                    track.annotation_format = 'ikala-midi-lines'
        else:
            if not args.dataset_root:
                raise ValueError('--dataset-root is required unless --manifest is provided')
            dataset_root = Path(args.dataset_root).resolve()
            if args.dataset == 'ikala':
                tracks = build_ikala_tracks(dataset_root, args.audio_mode)
            elif args.dataset == 'vocadito':
                tracks = build_vocadito_tracks(dataset_root, args.audio_mode)
            else:
                tracks = build_medleydb_pitch_tracks(dataset_root, args.audio_mode)

    selected_ids = {str(item).strip() for item in list(args.track_id or []) if str(item).strip()}
    if selected_ids:
        tracks = [track for track in tracks if track.track_id in selected_ids]
    if args.limit and args.limit > 0:
        tracks = tracks[: int(args.limit)]
    if not tracks:
        raise ValueError('no tracks selected for evaluation')
    return tracks


def load_ikala_reference(annotation_path: Path) -> PitchSeries:
    midi_values: List[float] = []
    with annotation_path.open('r', encoding='utf-8-sig') as handle:
        for raw_line in handle:
            numbers = parse_float_tokens(raw_line)
            if not numbers:
                continue
            midi_values.append(float(numbers[0]))
    midi_array = np.asarray(midi_values, dtype=np.float64)
    times = (np.arange(midi_array.size, dtype=np.float64) * IKALA_TIME_STEP_SECONDS) + (IKALA_TIME_STEP_SECONDS / 2.0)
    freqs = midi_to_hz(midi_array)
    return canonicalize_series(times, freqs)


def load_two_column_reference(annotation_path: Path) -> PitchSeries:
    times: List[float] = []
    freqs: List[float] = []
    with annotation_path.open('r', encoding='utf-8-sig') as handle:
        for raw_line in handle:
            numbers = parse_float_tokens(raw_line)
            if len(numbers) < 2:
                continue
            times.append(float(numbers[0]))
            freqs.append(max(0.0, float(numbers[1])))
    return canonicalize_series(times, freqs)


def load_reference_series(track: TrackSpec) -> PitchSeries:
    annotation_path = Path(track.annotation_path)
    if not annotation_path.is_file():
        raise FileNotFoundError(f'annotation file not found: {annotation_path}')
    if track.annotation_format == 'ikala-midi-lines':
        return load_ikala_reference(annotation_path)
    if track.annotation_format in {'medleydb-pitch', 'time-hz'}:
        return load_two_column_reference(annotation_path)
    raise ValueError(f'unsupported annotation_format: {track.annotation_format}')


def prepare_analysis_audio(track: TrackSpec) -> Tuple[str, Optional[str]]:
    audio_path = Path(track.audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(f'audio file not found: {audio_path}')
    audio_mode = str(track.audio_mode or 'auto')
    if track.dataset_name != 'ikala' and audio_mode == 'auto':
        return str(audio_path), None
    if track.dataset_name != 'ikala' and audio_mode != 'auto':
        return str(audio_path), None

    resolved_audio_mode = audio_mode if audio_mode != 'auto' else 'vocal'
    import soundfile as sf

    samples, sample_rate = sf.read(str(audio_path), always_2d=True)
    if samples.ndim != 2 or samples.shape[0] <= 0:
        raise RuntimeError(f'failed to read audio from {audio_path}')
    if resolved_audio_mode == 'vocal':
        channel_index = 1 if samples.shape[1] > 1 else 0
        mono = samples[:, channel_index]
    elif resolved_audio_mode == 'instrumental':
        mono = samples[:, 0]
    elif resolved_audio_mode == 'mix':
        mono = np.sum(samples, axis=1)
    else:
        mono = samples[:, 0]
    temp_file = tempfile.NamedTemporaryFile(prefix='pitch_eval_', suffix='.wav', delete=False)
    temp_file.close()
    sf.write(temp_file.name, mono, sample_rate)
    return temp_file.name, temp_file.name


def extract_estimated_series(app: Any, ui: Any, audio_path: str) -> Tuple[PitchSeries, Dict[str, Any]]:
    try:
        start_ts = time.perf_counter()
        ui._start_offline_onepass(audio_path)
        onepass.wait_qt(app, 50)
        resolved = ui._resolve_technique_analysis_payload()
        elapsed_s = time.perf_counter() - start_ts
        if not bool(resolved.get('ok', False)):
            raise RuntimeError(str(resolved.get('reason', '') or 'failed to resolve technique payload'))
        frames = list(resolved.get('frames', []) or [])
        times: List[float] = []
        freqs: List[float] = []
        for frame in frames:
            timeline_time = safe_float(getattr(frame, 'timeline_time', 0.0), 0.0)
            freq_value = safe_float(
                getattr(frame, 'display_frequency_hz', 0.0) or getattr(frame, 'detected_frequency_hz', 0.0),
                0.0,
            )
            has_pitch = bool(getattr(frame, 'has_pitch', False))
            if not has_pitch or freq_value <= 0.0:
                freq_value = 0.0
            times.append(timeline_time)
            freqs.append(freq_value)
        payload_summary = {
            'analysis_mode': str(resolved.get('analysis_mode', '') or ''),
            'duration_s': safe_float(resolved.get('duration', 0.0), 0.0),
            'frame_count': len(frames),
            'elapsed_s': round(elapsed_s, 6),
        }
        return canonicalize_series(times, freqs), payload_summary
    finally:
        onepass.exit_onepass_mode(ui)
        onepass.wait_qt(app, 20)


def infer_alignment_gap(reference: PitchSeries, estimate: PitchSeries, max_align_gap_s: float) -> float:
    candidates = [safe_float(max_align_gap_s, 0.05), 0.010]
    if reference.times_s.size >= 2:
        ref_step = float(np.median(np.diff(reference.times_s)))
        if math.isfinite(ref_step) and ref_step > 0.0:
            candidates.append(ref_step)
    if estimate.times_s.size >= 2:
        est_step = float(np.median(np.diff(estimate.times_s)))
        if math.isfinite(est_step) and est_step > 0.0:
            candidates.append(est_step)
    return min(max(candidates), 0.250)


def align_estimates_to_reference(reference: PitchSeries, estimate: PitchSeries, max_align_gap_s: float) -> np.ndarray:
    if reference.times_s.size == 0:
        return np.zeros(0, dtype=np.float64)
    if estimate.times_s.size == 0:
        return np.zeros(reference.times_s.shape[0], dtype=np.float64)
    alignment_gap = infer_alignment_gap(reference, estimate, max_align_gap_s)
    est_times = estimate.times_s
    est_freqs = estimate.freqs_hz
    right_indices = np.searchsorted(est_times, reference.times_s, side='left')
    right_indices = np.clip(right_indices, 0, est_times.size - 1)
    left_indices = np.clip(right_indices - 1, 0, est_times.size - 1)

    left_diffs = np.abs(reference.times_s - est_times[left_indices])
    right_diffs = np.abs(reference.times_s - est_times[right_indices])
    use_right = right_diffs < left_diffs
    best_indices = np.where(use_right, right_indices, left_indices)
    best_diffs = np.where(use_right, right_diffs, left_diffs)

    aligned = est_freqs[best_indices].astype(np.float64, copy=True)
    aligned[best_diffs > alignment_gap] = 0.0
    return aligned


def cents_difference(reference_hz: np.ndarray, estimate_hz: np.ndarray) -> np.ndarray:
    return np.abs(1200.0 * np.log2(np.maximum(estimate_hz, 1e-12) / np.maximum(reference_hz, 1e-12)))


def chroma_difference(reference_hz: np.ndarray, estimate_hz: np.ndarray) -> np.ndarray:
    diff_cents = 1200.0 * np.log2(np.maximum(estimate_hz, 1e-12) / np.maximum(reference_hz, 1e-12))
    return np.abs(((diff_cents + 600.0) % 1200.0) - 600.0)


def compute_track_metrics(track: TrackSpec, reference: PitchSeries, estimate: PitchSeries, tolerance_cents: float, max_align_gap_s: float) -> Dict[str, Any]:
    aligned_estimate_hz = align_estimates_to_reference(reference, estimate, max_align_gap_s)
    reference_voiced = reference.freqs_hz > 0.0
    estimate_voiced = aligned_estimate_hz > 0.0

    reference_voiced_count = int(np.count_nonzero(reference_voiced))
    reference_unvoiced_count = int(np.count_nonzero(~reference_voiced))
    estimate_voiced_count = int(np.count_nonzero(estimate_voiced))
    voiced_hits = int(np.count_nonzero(reference_voiced & estimate_voiced))
    false_alarms = int(np.count_nonzero((~reference_voiced) & estimate_voiced))

    shared_voiced_mask = reference_voiced & estimate_voiced
    shared_voiced_count = int(np.count_nonzero(shared_voiced_mask))
    if np.any(shared_voiced_mask):
        ref_voiced_hz = reference.freqs_hz[shared_voiced_mask]
        est_voiced_hz = aligned_estimate_hz[shared_voiced_mask]
        pitch_error_cents = cents_difference(ref_voiced_hz, est_voiced_hz)
        raw_pitch_hits = int(np.count_nonzero(pitch_error_cents <= tolerance_cents))
        raw_chroma_hits = int(np.count_nonzero(chroma_difference(ref_voiced_hz, est_voiced_hz) <= tolerance_cents))
        gross_pitch_errors = int(np.count_nonzero(pitch_error_cents > tolerance_cents))
    else:
        raw_pitch_hits = 0
        raw_chroma_hits = 0
        gross_pitch_errors = 0

    alignment_gap_s = infer_alignment_gap(reference, estimate, max_align_gap_s)
    voicing_recall = safe_rate(voiced_hits, reference_voiced_count)
    voicing_precision = safe_rate(voiced_hits, estimate_voiced_count)
    metrics = {
        'track_id': track.track_id,
        'dataset_name': track.dataset_name,
        'annotation_format': track.annotation_format,
        'audio_mode': track.audio_mode,
        'audio_path': track.audio_path,
        'annotation_path': track.annotation_path,
        'reference_frame_count': int(reference.times_s.size),
        'estimate_frame_count': int(estimate.times_s.size),
        'reference_duration_s': round(safe_float(reference.times_s[-1], 0.0), 6) if reference.times_s.size else 0.0,
        'estimate_duration_s': round(safe_float(estimate.times_s[-1], 0.0), 6) if estimate.times_s.size else 0.0,
        'alignment_gap_s': round(alignment_gap_s, 6),
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
            'raw_pitch_accuracy': round_metric(safe_rate(raw_pitch_hits, reference_voiced_count)),
            'raw_chroma_accuracy': round_metric(safe_rate(raw_chroma_hits, reference_voiced_count)),
            'gross_pitch_error': round_metric(safe_rate(gross_pitch_errors, shared_voiced_count)),
            'voicing_recall': round_metric(voicing_recall),
            'voicing_precision': round_metric(voicing_precision),
            'voicing_f1': round_metric(safe_f1(voicing_precision, voicing_recall)),
            'voicing_false_alarm': round_metric(safe_rate(false_alarms, reference_unvoiced_count)),
        },
    }
    return metrics


def aggregate_results(track_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total_reference_voiced = 0
    total_reference_unvoiced = 0
    total_estimate_voiced = 0
    total_shared_voiced = 0
    total_voiced_hits = 0
    total_false_alarms = 0
    total_raw_pitch_hits = 0
    total_raw_chroma_hits = 0
    total_gross_pitch_errors = 0

    macro_rpa: List[float] = []
    macro_rca: List[float] = []
    macro_gpe: List[float] = []
    macro_vr: List[float] = []
    macro_vp: List[float] = []
    macro_vf1: List[float] = []
    macro_vfa: List[float] = []

    for item in track_results:
        counts = dict(item.get('counts', {}) or {})
        metrics = dict(item.get('metrics', {}) or {})
        total_reference_voiced += int(counts.get('reference_voiced', 0) or 0)
        total_reference_unvoiced += int(counts.get('reference_unvoiced', 0) or 0)
        total_estimate_voiced += int(counts.get('estimate_voiced', 0) or 0)
        total_shared_voiced += int(counts.get('shared_voiced', 0) or 0)
        total_voiced_hits += int(counts.get('voiced_hits', 0) or 0)
        total_false_alarms += int(counts.get('false_alarms', 0) or 0)
        total_raw_pitch_hits += int(counts.get('raw_pitch_hits', 0) or 0)
        total_raw_chroma_hits += int(counts.get('raw_chroma_hits', 0) or 0)
        total_gross_pitch_errors += int(counts.get('gross_pitch_errors', 0) or 0)
        for bucket, key in (
            (macro_rpa, 'raw_pitch_accuracy'),
            (macro_rca, 'raw_chroma_accuracy'),
            (macro_gpe, 'gross_pitch_error'),
            (macro_vr, 'voicing_recall'),
            (macro_vp, 'voicing_precision'),
            (macro_vf1, 'voicing_f1'),
            (macro_vfa, 'voicing_false_alarm'),
        ):
            value = metrics.get(key)
            if value is not None:
                bucket.append(float(value))

    micro_voicing_recall = safe_rate(total_voiced_hits, total_reference_voiced)
    micro_voicing_precision = safe_rate(total_voiced_hits, total_estimate_voiced)

    return {
        'micro': {
            'raw_pitch_accuracy': round_metric(safe_rate(total_raw_pitch_hits, total_reference_voiced)),
            'raw_chroma_accuracy': round_metric(safe_rate(total_raw_chroma_hits, total_reference_voiced)),
            'gross_pitch_error': round_metric(safe_rate(total_gross_pitch_errors, total_shared_voiced)),
            'voicing_recall': round_metric(micro_voicing_recall),
            'voicing_precision': round_metric(micro_voicing_precision),
            'voicing_f1': round_metric(safe_f1(micro_voicing_precision, micro_voicing_recall)),
            'voicing_false_alarm': round_metric(safe_rate(total_false_alarms, total_reference_unvoiced)),
        },
        'macro': {
            'raw_pitch_accuracy': round_metric(float(np.mean(macro_rpa)) if macro_rpa else None),
            'raw_chroma_accuracy': round_metric(float(np.mean(macro_rca)) if macro_rca else None),
            'gross_pitch_error': round_metric(float(np.mean(macro_gpe)) if macro_gpe else None),
            'voicing_recall': round_metric(float(np.mean(macro_vr)) if macro_vr else None),
            'voicing_precision': round_metric(float(np.mean(macro_vp)) if macro_vp else None),
            'voicing_f1': round_metric(float(np.mean(macro_vf1)) if macro_vf1 else None),
            'voicing_false_alarm': round_metric(float(np.mean(macro_vfa)) if macro_vfa else None),
        },
        'counts': {
            'reference_voiced': total_reference_voiced,
            'reference_unvoiced': total_reference_unvoiced,
            'estimate_voiced': total_estimate_voiced,
            'shared_voiced': total_shared_voiced,
            'voiced_hits': total_voiced_hits,
            'false_alarms': total_false_alarms,
            'raw_pitch_hits': total_raw_pitch_hits,
            'raw_chroma_hits': total_raw_chroma_hits,
            'gross_pitch_errors': total_gross_pitch_errors,
        },
    }


def format_metric(value: Optional[float]) -> str:
    if value is None:
        return 'n/a'
    return f'{100.0 * float(value):.2f}%'


def print_console_summary(report: Dict[str, Any]) -> None:
    print(
        f"[pitch-eval] dataset={report.get('dataset')} selected={report.get('selected_track_count')} "
        f"ok={report.get('success_count')} failed={report.get('error_count')}"
    )
    aggregated = dict(report.get('aggregate', {}) or {})
    for name in ('micro', 'macro'):
        metrics = dict(aggregated.get(name, {}) or {})
        print(
            f"  {name} RPA={format_metric(metrics.get('raw_pitch_accuracy'))} "
            f"RCA={format_metric(metrics.get('raw_chroma_accuracy'))} "
            f"GPE={format_metric(metrics.get('gross_pitch_error'))} "
            f"VR={format_metric(metrics.get('voicing_recall'))} "
            f"VF1={format_metric(metrics.get('voicing_f1'))} "
            f"VFA={format_metric(metrics.get('voicing_false_alarm'))}"
        )

    track_results = list(report.get('tracks', []) or [])
    worst_tracks = sorted(
        track_results,
        key=lambda item: float((item.get('metrics', {}) or {}).get('raw_pitch_accuracy') or -1.0),
    )[:3]
    for item in worst_tracks:
        metrics = dict(item.get('metrics', {}) or {})
        print(
            f"  track {item.get('track_id')} RPA={format_metric(metrics.get('raw_pitch_accuracy'))} "
            f"RCA={format_metric(metrics.get('raw_chroma_accuracy'))} "
            f"GPE={format_metric(metrics.get('gross_pitch_error'))} "
            f"VR={format_metric(metrics.get('voicing_recall'))} "
            f"VF1={format_metric(metrics.get('voicing_f1'))} "
            f"VFA={format_metric(metrics.get('voicing_false_alarm'))}"
        )

    errors = list(report.get('errors', []) or [])
    for item in errors[:5]:
        print(f"  error {item.get('track_id')}: {item.get('error')}")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 6)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def main() -> int:
    args = parse_args()
    tracks = resolve_tracks(args)

    track_results: List[Dict[str, Any]] = []
    track_errors: List[Dict[str, Any]] = []

    for index, track in enumerate(tracks, start=1):
        print(f"[pitch-eval] {index}/{len(tracks)} {track.track_id}")
        temp_audio_path: Optional[str] = None
        app = None
        ui = None
        try:
            reference = load_reference_series(track)
            analysis_audio_path, temp_audio_path = prepare_analysis_audio(track)
            app, module, ui, init_log = onepass.load_runtime(show_init_log=bool(args.show_init_log and index == 1))
            if args.show_init_log and index == 1 and init_log:
                print(init_log)
            estimate, runtime_summary = extract_estimated_series(app, ui, analysis_audio_path)
            item = compute_track_metrics(track, reference, estimate, args.tolerance_cents, args.max_align_gap)
            item['runtime'] = runtime_summary
            track_results.append(item)
        except Exception as exc:
            track_errors.append({'track_id': track.track_id, 'error': str(exc), 'track': asdict(track)})
        finally:
            if app is not None and ui is not None:
                try:
                    onepass.close_runtime(app, ui)
                except Exception:
                    pass
            if temp_audio_path:
                try:
                    Path(temp_audio_path).unlink(missing_ok=True)
                except Exception:
                    pass

    aggregate = aggregate_results(track_results)
    report = {
        'dataset': args.dataset,
        'dataset_root': args.dataset_root,
        'manifest': args.manifest,
        'selected_track_count': len(tracks),
        'success_count': len(track_results),
        'error_count': len(track_errors),
        'settings': {
            'audio_mode': args.audio_mode,
            'annotation_format': args.annotation_format,
            'tolerance_cents': round(args.tolerance_cents, 6),
            'max_align_gap': round(args.max_align_gap, 6),
        },
        'aggregate': aggregate,
        'tracks': track_results,
        'errors': track_errors,
    }

    print_console_summary(report)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[pitch-eval] wrote {output_path}')

    if args.fail_on_track_error and track_errors:
        return 1
    return 0 if track_results else 1


if __name__ == '__main__':
    raise SystemExit(main())