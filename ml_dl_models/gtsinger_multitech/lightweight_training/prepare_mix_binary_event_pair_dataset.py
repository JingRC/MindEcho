import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.io import wavfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg
import train_mix_binary_squeezenet as mix_train


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build a runtime-event anchored pair dataset for targeted mix micro-tuning.'
    )
    parser.add_argument('--input-manifest', required=True, help='Source manifest containing the selected clips to convert.')
    parser.add_argument('--output-dir', required=True, help='Directory to write snippets, manifests, and plan summary into.')
    parser.add_argument('--base-validation-manifest', default='', help='Optional validation manifest to copy into the output dataset.')
    parser.add_argument('--base-test-manifest', default='', help='Optional test manifest to copy into the output dataset.')
    parser.add_argument('--anchor-source', choices=('best_voice', 'strongest_mix', 'best_voice_or_mix'), default='best_voice')
    parser.add_argument('--clip-secs', type=float, default=2.4, help='Fixed snippet duration in seconds.')
    parser.add_argument('--target-sample-rate', type=int, default=22050, help='Snippet sample rate.')
    parser.add_argument('--positive-repeat', type=int, default=20, help='Repeat count for positive rows in train_manifest.csv.')
    parser.add_argument('--negative-repeat', type=int, default=3, help='Repeat count for negative rows in train_manifest.csv.')
    parser.add_argument('--positive-window-count', type=int, default=1, help='Target number of event-centered windows to emit per positive source sample.')
    parser.add_argument('--negative-window-count', type=int, default=1, help='Target number of event-centered windows to emit per negative source sample.')
    parser.add_argument('--max-distinct-events', type=int, default=2, help='Max number of distinct runtime events to use before adding extra shifted windows.')
    parser.add_argument('--limit', type=int, default=0, help='Optional max number of unique source rows to process.')
    return parser.parse_args()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _slugify_for_path(index: int, item_name: str) -> str:
    digest = hashlib.sha1(str(item_name or '').encode('utf-8', errors='ignore')).hexdigest()[:10]
    return f'{index:03d}_{digest}'


def normalize_manifest_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in dict(row or {}).items():
        clean_key = str(key or '').lstrip('\ufeff').strip().strip('"').strip()
        normalized[clean_key] = value
    return normalized


def load_unique_rows(path: Path, limit: int = 0) -> List[Dict[str, Any]]:
    rows = [normalize_manifest_row(row) for row in mix_train.load_manifest(path)]
    unique_rows: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for row in rows:
        wav_path = str(row.get('wav_path', '') or '').strip()
        item_name = str(row.get('item_name', '') or '').strip()
        key = (wav_path, item_name)
        if not wav_path or key in seen:
            continue
        seen.add(key)
        unique_rows.append(dict(row))
        if limit > 0 and len(unique_rows) >= limit:
            break
    return unique_rows


def _event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    return dict(event.get('display_payload', {}) or {})


def _event_snapshot(event: Dict[str, Any]) -> Dict[str, Any]:
    return dict(event.get('feature_snapshot', {}) or {})


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get('event_type', '') or '').strip()


def _event_start_time(event: Dict[str, Any]) -> float:
    return _safe_float(event.get('start_time', 0.0), 0.0)


def _event_end_time(event: Dict[str, Any]) -> float:
    return _safe_float(event.get('end_time', 0.0), 0.0)


def _event_duration(event: Dict[str, Any]) -> float:
    return max(0.0, _event_end_time(event) - _event_start_time(event))


def _event_mix_prob(event: Dict[str, Any]) -> float:
    payload = _event_payload(event)
    snapshot = _event_snapshot(event)
    return _safe_float(payload.get('mix_prob', snapshot.get('mix_prob', event.get('mix_prob', 0.0))), 0.0)


def _event_mix_threshold(event: Dict[str, Any], default: float = 0.45) -> float:
    payload = _event_payload(event)
    snapshot = _event_snapshot(event)
    return _safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', default)), default)


def _event_mix_margin(event: Dict[str, Any], default_threshold: float = 0.45) -> float:
    return _event_mix_prob(event) - _event_mix_threshold(event, default=default_threshold)


def _event_mix_support(event: Dict[str, Any]) -> float:
    payload = _event_payload(event)
    snapshot = _event_snapshot(event)
    return _safe_float(payload.get('mix_support', snapshot.get('mix_support', 0.0)), 0.0)


def _event_mean_pitch_hz(event: Dict[str, Any]) -> float:
    snapshot = _event_snapshot(event)
    return _safe_float(event.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)), 0.0)


def _event_chest_prob(event: Dict[str, Any]) -> float:
    snapshot = _event_snapshot(event)
    return _safe_float(event.get('chest_prob', snapshot.get('chest_prob', 0.0)), 0.0)


def _event_falsetto_prob(event: Dict[str, Any]) -> float:
    snapshot = _event_snapshot(event)
    return _safe_float(event.get('falsetto_prob', snapshot.get('falsetto_prob', 0.0)), 0.0)


def _event_stable_ratio(event: Dict[str, Any]) -> float:
    snapshot = _event_snapshot(event)
    return _safe_float(snapshot.get('stable_ratio', 0.0), 0.0)


def _event_voiced_ratio(event: Dict[str, Any]) -> float:
    snapshot = _event_snapshot(event)
    return _safe_float(snapshot.get('voiced_ratio', 0.0), 0.0)


def _event_overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    left_start = _event_start_time(left)
    left_end = _event_end_time(left)
    right_start = _event_start_time(right)
    right_end = _event_end_time(right)
    left_duration = max(0.0, left_end - left_start)
    right_duration = max(0.0, right_end - right_start)
    min_duration = min(left_duration, right_duration)
    if min_duration <= 1e-9:
        return 0.0
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    return overlap / min_duration


def _window_variant_name(center_ratio: float) -> str:
    rounded = round(float(center_ratio), 2)
    if abs(rounded - 0.5) <= 1e-6:
        return 'center'
    if abs(rounded - 0.25) <= 1e-6:
        return 'early'
    if abs(rounded - 0.75) <= 1e-6:
        return 'late'
    if rounded < 0.5:
        return f'left{int(round(rounded * 100)):02d}'
    return f'right{int(round(rounded * 100)):02d}'


def rank_voice_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for event in list(events or []):
        event_type = _event_type(event)
        if event_type not in {'chest_voice', 'falsetto'}:
            continue
        ranked.append({
            'event': dict(event),
            'event_family': 'voice',
            'event_type': event_type,
            'mix_prob': _event_mix_prob(event),
            'mix_margin': _event_mix_margin(event),
            'duration': _event_duration(event),
            'stable_ratio': _event_stable_ratio(event),
            'voiced_ratio': _event_voiced_ratio(event),
            'mean_pitch_hz': _event_mean_pitch_hz(event),
        })
    ranked.sort(
        key=lambda item: (
            item['mix_margin'] >= 0.0,
            item['mix_prob'],
            item['mix_margin'],
            item['stable_ratio'],
            item['voiced_ratio'],
            item['duration'],
        ),
        reverse=True,
    )
    return ranked


def rank_mix_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for event in list(events or []):
        event_type = _event_type(event)
        if event_type not in {'strong_mix', 'weak_mix', 'balanced_mix'}:
            continue
        ranked.append({
            'event': dict(event),
            'event_family': 'mix',
            'event_type': event_type,
            'mix_prob': _event_mix_prob(event),
            'mix_margin': _event_mix_margin(event),
            'mix_support': _event_mix_support(event),
            'duration': _event_duration(event),
            'mean_pitch_hz': _event_mean_pitch_hz(event),
        })
    ranked.sort(
        key=lambda item: (
            item['mix_support'],
            item['mix_prob'],
            item['mix_margin'],
            item['duration'],
        ),
        reverse=True,
    )
    return ranked


def choose_anchor_candidates(
    analyzed: Dict[str, Any],
    summary: Dict[str, Any],
    *,
    anchor_source: str,
    max_distinct_events: int,
) -> List[Dict[str, Any]]:
    analysis = dict(analyzed.get('analysis', {}) or {})
    voice_events = rank_voice_events(list(analysis.get('voice_events', []) or []))
    mix_events = rank_mix_events(list(analysis.get('mix_events', []) or []))
    binary_role = str(summary.get('binary_role', '') or '')
    mode = str(anchor_source or 'best_voice').strip().lower()

    if mode == 'strongest_mix':
        candidate_pool = mix_events + voice_events
    elif mode == 'best_voice_or_mix':
        if binary_role == 'positive_mix':
            candidate_pool = mix_events + voice_events
        else:
            candidate_pool = voice_events + mix_events
    else:
        candidate_pool = voice_events + mix_events

    selected: List[Dict[str, Any]] = []
    for candidate in candidate_pool:
        event = dict(candidate.get('event', {}) or {})
        if not _event_type(event):
            continue
        if any(_event_overlap_ratio(event, existing.get('event', {})) >= 0.65 for existing in selected):
            continue
        selected.append(dict(candidate))
        if len(selected) >= max(1, int(max_distinct_events)):
            break

    if not selected and candidate_pool:
        selected.append(dict(candidate_pool[0]))

    for rank, candidate in enumerate(selected, start=1):
        candidate['event_rank'] = rank
    return selected


def expand_anchor_windows(candidates: List[Dict[str, Any]], desired_windows: int) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    target_count = max(1, int(desired_windows))
    windows: List[Dict[str, Any]] = []
    base_candidates = list(candidates[:target_count])
    for candidate in base_candidates:
        windows.append({
            'candidate': dict(candidate),
            'center_ratio': 0.5,
            'window_variant': _window_variant_name(0.5),
        })
        if len(windows) >= target_count:
            return windows

    extra_candidates = list(candidates[:max(1, min(len(candidates), 2))])
    extra_ratios = (0.25, 0.75, 0.15, 0.85)
    for ratio in extra_ratios:
        for candidate in extra_candidates:
            if len(windows) >= target_count:
                break
            windows.append({
                'candidate': dict(candidate),
                'center_ratio': float(ratio),
                'window_variant': _window_variant_name(ratio),
            })
        if len(windows) >= target_count:
            break
    return windows[:target_count]


def choose_anchor_event(summary: Dict[str, Any], anchor_source: str) -> tuple[Dict[str, Any], str]:
    best_voice = dict(summary.get('best_voice_event', {}) or {})
    strongest_mix = dict(summary.get('strongest_mix_event', {}) or {})

    def has_event(event: Dict[str, Any]) -> bool:
        return bool(str(event.get('event_type', '') or '').strip())

    mode = str(anchor_source or 'best_voice').strip().lower()
    if mode == 'strongest_mix':
        if has_event(strongest_mix):
            return strongest_mix, 'strongest_mix_event'
        if has_event(best_voice):
            return best_voice, 'best_voice_event_fallback'
        return {}, ''
    if mode == 'best_voice_or_mix':
        if has_event(best_voice):
            return best_voice, 'best_voice_event'
        if has_event(strongest_mix):
            return strongest_mix, 'strongest_mix_event_fallback'
        return {}, ''
    if has_event(best_voice):
        return best_voice, 'best_voice_event'
    if has_event(strongest_mix):
        return strongest_mix, 'strongest_mix_event_fallback'
    return {}, ''


def assign_pair_positive(
    record: Dict[str, Any],
    positive_records: List[Dict[str, Any]],
) -> tuple[str, float]:
    item_name = str(record.get('item_name', '') or '')
    binary_role = str(record.get('binary_role', '') or '')
    if binary_role == 'positive_mix':
        return item_name, 0.0
    if not positive_records:
        return '', 0.0

    event_pitch = _safe_float(record.get('event_mean_pitch_hz', 0.0))
    event_duration = _safe_float(record.get('event_duration', 0.0), 0.0)
    event_mix_prob = _safe_float(record.get('event_mix_prob', 0.0), 0.0)

    best_positive = positive_records[0]
    best_distance = float('inf')
    for candidate in positive_records:
        candidate_pitch = _safe_float(candidate.get('event_mean_pitch_hz', 0.0), 0.0)
        candidate_duration = _safe_float(candidate.get('event_duration', 0.0), 0.0)
        candidate_mix_prob = _safe_float(candidate.get('event_mix_prob', 0.0), 0.0)
        pitch_term = abs(event_pitch - candidate_pitch) / max(80.0, candidate_pitch, event_pitch, 1.0)
        duration_term = abs(event_duration - candidate_duration) / max(0.15, candidate_duration, event_duration, 0.15)
        mix_term = abs(event_mix_prob - candidate_mix_prob)
        distance = (0.6 * pitch_term) + (0.2 * duration_term) + (0.2 * mix_term)
        if distance < best_distance:
            best_positive = candidate
            best_distance = distance
    return str(best_positive.get('item_name', '') or ''), round(float(best_distance), 6)


def extract_centered_clip(
    audio: np.ndarray,
    *,
    sample_rate: int,
    clip_secs: float,
    event_start_time: float,
    event_end_time: float,
    anchor_center_time: float | None = None,
) -> Dict[str, Any]:
    clip_len = max(1, int(round(float(sample_rate) * float(clip_secs))))
    source = np.asarray(audio, dtype=np.float32).reshape(-1)
    total_len = int(source.shape[0])
    event_start_idx = max(0, int(round(max(0.0, event_start_time) * float(sample_rate))))
    event_end_idx = max(event_start_idx + 1, int(round(max(event_end_time, event_start_time) * float(sample_rate))))
    if anchor_center_time is None:
        center_idx = int(round((event_start_idx + event_end_idx) * 0.5))
    else:
        center_idx = int(round(max(0.0, float(anchor_center_time)) * float(sample_rate)))

    if total_len >= clip_len:
        clip_source_start = max(0, min(center_idx - (clip_len // 2), total_len - clip_len))
        clip_source_end = clip_source_start + clip_len
        pad_before = 0
        clip = source[clip_source_start:clip_source_end].copy()
    else:
        clip_source_start = 0
        clip_source_end = total_len
        pad_before = max(0, (clip_len - total_len) // 2)
        clip = np.zeros((clip_len,), dtype=np.float32)
        clip[pad_before:pad_before + total_len] = source

    event_offset_start_idx = max(0, event_start_idx - clip_source_start + pad_before)
    event_offset_end_idx = min(clip_len, event_end_idx - clip_source_start + pad_before)
    overlap_start = max(event_start_idx, clip_source_start)
    overlap_end = min(event_end_idx, clip_source_end)
    overlap_len = max(0, overlap_end - overlap_start)
    event_len = max(1, event_end_idx - event_start_idx)

    return {
        'audio': clip,
        'clip_start_time': round(float(clip_source_start) / float(sample_rate), 6),
        'clip_end_time': round(float(clip_source_end) / float(sample_rate), 6),
        'event_offset_start_time': round(float(event_offset_start_idx) / float(sample_rate), 6),
        'event_offset_end_time': round(float(event_offset_end_idx) / float(sample_rate), 6),
        'event_coverage_ratio': round(float(overlap_len) / float(event_len), 6),
    }


def write_wav(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    wavfile.write(str(path), int(sample_rate), (pcm * 32767.0).astype(np.int16))


def copy_manifest_if_present(source: str, target: Path) -> None:
    src = Path(str(source or '').strip())
    if not str(source or '').strip():
        return
    if not src.exists():
        raise FileNotFoundError(f'manifest not found: {src}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, target)


def build_manifest_rows(
    records: List[Dict[str, Any]],
    *,
    output_dir: Path,
    sample_rate: int,
    clip_secs: float,
) -> List[Dict[str, Any]]:
    manifest_rows: List[Dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        row = dict(record.get('source_row', {}) or {})
        slug = _slugify_for_path(index, str(record.get('item_name', '') or ''))
        role = str(record.get('binary_role', '') or 'unknown')
        snippet_path = output_dir / 'snippets' / role / f'{slug}.wav'
        audio = mix_train.read_audio(Path(str(record.get('source_wav_path', '') or '')), sample_rate, target_length=None, train=False)
        clip_info = extract_centered_clip(
            audio,
            sample_rate=sample_rate,
            clip_secs=clip_secs,
            event_start_time=_safe_float(record.get('event_start_time', 0.0)),
            event_end_time=_safe_float(record.get('event_end_time', 0.0)),
            anchor_center_time=_safe_float(record.get('anchor_center_time', 0.0)),
        )
        write_wav(snippet_path, sample_rate, clip_info['audio'])
        try:
            wav_fn = str(snippet_path.relative_to(ROOT)).replace('\\', '/')
        except Exception:
            wav_fn = str(snippet_path).replace('\\', '/')

        row.update({
            'item_name': f"{row.get('item_name', '')}#eventpair#{record.get('anchor_label', 'event')}",
            'wav_path': str(snippet_path),
            'wav_fn': wav_fn,
            'source_item_name': str(record.get('item_name', '') or ''),
            'source_wav_path': str(record.get('source_wav_path', '') or ''),
            'anchor_label': str(record.get('anchor_label', '') or ''),
            'anchor_event_family': str(record.get('anchor_event_family', '') or ''),
            'anchor_event_type': str(record.get('anchor_event_type', '') or ''),
            'anchor_window_variant': str(record.get('anchor_window_variant', '') or ''),
            'anchor_center_time': record.get('anchor_center_time', 0.0),
            'anchor_center_ratio': record.get('anchor_center_ratio', 0.0),
            'source_event_rank': record.get('source_event_rank', 0),
            'event_start_time': record.get('event_start_time', 0.0),
            'event_end_time': record.get('event_end_time', 0.0),
            'event_duration': record.get('event_duration', 0.0),
            'event_mix_prob': record.get('event_mix_prob', 0.0),
            'event_mix_margin': record.get('event_mix_margin', 0.0),
            'event_mean_pitch_hz': record.get('event_mean_pitch_hz', 0.0),
            'event_chest_prob': record.get('event_chest_prob', 0.0),
            'event_falsetto_prob': record.get('event_falsetto_prob', 0.0),
            'clip_start_time': clip_info['clip_start_time'],
            'clip_end_time': clip_info['clip_end_time'],
            'event_offset_start_time': clip_info['event_offset_start_time'],
            'event_offset_end_time': clip_info['event_offset_end_time'],
            'event_coverage_ratio': clip_info['event_coverage_ratio'],
            'pair_positive_item_name': str(record.get('pair_positive_item_name', '') or ''),
            'pair_distance': record.get('pair_distance', 0.0),
        })
        manifest_rows.append(row)
    return manifest_rows


def write_manifest(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            name = str(key)
            if name not in seen:
                seen.add(name)
                fieldnames.append(name)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    input_manifest = Path(args.input_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_manifest.exists():
        print(f'input manifest not found: {input_manifest}', file=sys.stderr)
        return 2

    source_rows = load_unique_rows(input_manifest, limit=max(0, int(args.limit)))
    if not source_rows:
        print('no unique rows selected from input manifest', file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    analyzed_records: List[Dict[str, Any]] = []
    source_reports: List[Dict[str, Any]] = []
    analysis_errors: List[Dict[str, Any]] = []
    started_at = time.strftime('%Y-%m-%d %H:%M:%S')

    app = None
    try:
        app, module, ui, _ = dbg.load_runtime(False)
        for index, row in enumerate(source_rows, start=1):
            item_name = str(row.get('item_name', '') or '').strip()
            if not item_name:
                item_name = Path(str(row.get('wav_path', '') or '')).stem
            sample = {
                'group_name': str(row.get('group_name', '') or ''),
                'item_name': item_name,
                'song_name': str(row.get('song_name', '') or ''),
                'singer': str(row.get('singer', '') or ''),
                'binary_role': str(row.get('binary_role', '') or ''),
                'wav_path': str(row.get('wav_path', '') or ''),
                'mix': _safe_int(row.get('mix', 0)),
                'falsetto': _safe_int(row.get('falsetto', 0)),
                'breathy': _safe_int(row.get('breathy', 0)),
            }
            analyzed = reg.analyze_sample(app, module, ui, sample)
            summary = reg.summarize_sample(analyzed)
            desired_windows = max(1, int(args.positive_window_count)) if sample['binary_role'] == 'positive_mix' else max(1, int(args.negative_window_count))
            anchor_candidates = choose_anchor_candidates(
                analyzed,
                summary,
                anchor_source=args.anchor_source,
                max_distinct_events=max(1, int(args.max_distinct_events)),
            )
            anchor_windows = expand_anchor_windows(anchor_candidates, desired_windows)
            if str(summary.get('error', '') or '').strip() or not anchor_windows:
                failure = {
                    'item_name': sample['item_name'],
                    'wav_path': sample['wav_path'],
                    'error': str(summary.get('error', '') or 'missing_anchor_event'),
                    'binary_role': sample['binary_role'],
                }
                analysis_errors.append(failure)
                print(json.dumps({'index': index, 'status': 'error', **failure}, ensure_ascii=False), flush=True)
                continue

            source_anchor_records: List[Dict[str, Any]] = []
            for anchor_window in anchor_windows:
                candidate = dict(anchor_window.get('candidate', {}) or {})
                anchor_event = dict(candidate.get('event', {}) or {})
                center_ratio = float(anchor_window.get('center_ratio', 0.5) or 0.5)
                event_start_time = _event_start_time(anchor_event)
                event_end_time = _event_end_time(anchor_event)
                anchor_center_time = event_start_time + (max(0.0, event_end_time - event_start_time) * center_ratio)
                source_event_rank = _safe_int(candidate.get('event_rank', 0), 0)
                anchor_label = f"{candidate.get('event_family', 'event')}_event{max(1, source_event_rank)}_{anchor_window.get('window_variant', 'center')}"
                record = {
                    'item_name': sample['item_name'],
                    'song_name': sample['song_name'],
                    'singer': sample['singer'],
                    'group_name': sample['group_name'],
                    'binary_role': sample['binary_role'],
                    'source_wav_path': sample['wav_path'],
                    'source_row': dict(row),
                    'analysis_summary': dict(summary),
                    'anchor_label': anchor_label,
                    'anchor_event_family': str(candidate.get('event_family', '') or ''),
                    'anchor_event_type': str(anchor_event.get('event_type', '') or ''),
                    'anchor_window_variant': str(anchor_window.get('window_variant', '') or ''),
                    'anchor_center_time': round(anchor_center_time, 6),
                    'anchor_center_ratio': round(center_ratio, 6),
                    'source_event_rank': source_event_rank,
                    'event_start_time': round(event_start_time, 6),
                    'event_end_time': round(event_end_time, 6),
                    'event_duration': round(_event_duration(anchor_event), 6),
                    'event_mix_prob': round(_event_mix_prob(anchor_event), 6),
                    'event_mix_margin': round(_event_mix_margin(anchor_event), 6),
                    'event_mean_pitch_hz': round(_event_mean_pitch_hz(anchor_event), 6),
                    'event_chest_prob': round(_event_chest_prob(anchor_event), 6),
                    'event_falsetto_prob': round(_event_falsetto_prob(anchor_event), 6),
                    'mix_event_count': _safe_int(summary.get('mix_event_count', 0)),
                    'voice_event_count': _safe_int(summary.get('voice_event_count', 0)),
                    'outcome': str(summary.get('outcome', '') or ''),
                    'miss_reason': str(summary.get('miss_reason', '') or ''),
                }
                analyzed_records.append(record)
                source_anchor_records.append({
                    'anchor_label': record['anchor_label'],
                    'anchor_event_family': record['anchor_event_family'],
                    'anchor_event_type': record['anchor_event_type'],
                    'anchor_window_variant': record['anchor_window_variant'],
                    'anchor_center_time': record['anchor_center_time'],
                    'event_start_time': record['event_start_time'],
                    'event_end_time': record['event_end_time'],
                    'event_mix_prob': record['event_mix_prob'],
                    'event_mix_margin': record['event_mix_margin'],
                    'event_mean_pitch_hz': record['event_mean_pitch_hz'],
                })

            source_reports.append({
                'item_name': sample['item_name'],
                'binary_role': sample['binary_role'],
                'outcome': str(summary.get('outcome', '') or ''),
                'miss_reason': str(summary.get('miss_reason', '') or ''),
                'voice_event_count': _safe_int(summary.get('voice_event_count', 0)),
                'mix_event_count': _safe_int(summary.get('mix_event_count', 0)),
                'selected_anchor_count': len(source_anchor_records),
                'anchors': source_anchor_records,
            })
            print(
                json.dumps(
                    {
                        'index': index,
                        'status': 'ok',
                        'item_name': sample['item_name'],
                        'binary_role': sample['binary_role'],
                        'anchor_count': len(source_anchor_records),
                        'anchor_labels': [entry['anchor_label'] for entry in source_anchor_records],
                        'top_mix_prob': source_anchor_records[0]['event_mix_prob'] if source_anchor_records else 0.0,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        if app is not None:
            try:
                app.quit()
            except Exception:
                pass

    if analysis_errors:
        print(json.dumps({'analysis_errors': analysis_errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    positive_records = [row for row in analyzed_records if str(row.get('binary_role', '') or '') == 'positive_mix']
    if not positive_records:
        print('no positive_mix rows available for pairing', file=sys.stderr)
        return 1

    for record in analyzed_records:
        pair_positive_item_name, pair_distance = assign_pair_positive(record, positive_records)
        record['pair_positive_item_name'] = pair_positive_item_name
        record['pair_distance'] = pair_distance

    manifest_rows = build_manifest_rows(
        analyzed_records,
        output_dir=output_dir,
        sample_rate=max(8000, int(args.target_sample_rate)),
        clip_secs=max(0.5, float(args.clip_secs)),
    )
    training_increment_manifest = output_dir / 'training_increment_manifest.csv'
    event_eval_manifest = output_dir / 'event_eval_manifest.csv'
    train_manifest = output_dir / 'train_manifest.csv'
    validation_manifest = output_dir / 'validation_manifest.csv'
    test_manifest = output_dir / 'test_manifest.csv'
    analysis_report_path = output_dir / 'pair_analysis.json'
    plan_summary_path = output_dir / 'plan_summary.json'

    write_manifest(training_increment_manifest, manifest_rows)
    write_manifest(event_eval_manifest, manifest_rows)

    train_rows: List[Dict[str, Any]] = []
    for row in manifest_rows:
        repeat = max(1, int(args.positive_repeat)) if _safe_int(row.get('mix', 0)) == 1 else max(1, int(args.negative_repeat))
        for _ in range(repeat):
            train_rows.append(dict(row))
    write_manifest(train_manifest, train_rows)

    copy_manifest_if_present(args.base_validation_manifest, validation_manifest)
    copy_manifest_if_present(args.base_test_manifest, test_manifest)

    analysis_report = {
        'generated_at': started_at,
        'input_manifest': str(input_manifest),
        'anchor_source': str(args.anchor_source),
        'clip_secs': round(float(args.clip_secs), 6),
        'target_sample_rate': int(args.target_sample_rate),
        'window_config': {
            'positive_window_count': max(1, int(args.positive_window_count)),
            'negative_window_count': max(1, int(args.negative_window_count)),
            'max_distinct_events': max(1, int(args.max_distinct_events)),
        },
        'source_records': source_reports,
        'records': analyzed_records,
    }
    analysis_report_path.write_text(json.dumps(analysis_report, ensure_ascii=False, indent=2), encoding='utf-8')

    pair_counter = Counter(str(row.get('pair_positive_item_name', '') or '') for row in analyzed_records if str(row.get('binary_role', '') or '') != 'positive_mix')
    source_role_counts = Counter(str(row.get('binary_role', '') or '') for row in source_rows)
    anchor_count_per_source = {
        str(row.get('item_name', '') or ''): _safe_int(row.get('selected_anchor_count', 0), 0)
        for row in source_reports
    }
    summary = {
        'input_manifest': str(input_manifest),
        'output_dir': str(output_dir),
        'anchor_source': str(args.anchor_source),
        'clip_secs': round(float(args.clip_secs), 6),
        'target_sample_rate': int(args.target_sample_rate),
        'window_config': {
            'positive_window_count': max(1, int(args.positive_window_count)),
            'negative_window_count': max(1, int(args.negative_window_count)),
            'max_distinct_events': max(1, int(args.max_distinct_events)),
        },
        'repeat_config': {
            'positive_repeat': int(args.positive_repeat),
            'negative_repeat': int(args.negative_repeat),
        },
        'counts': {
            'source_unique': len(source_rows),
            'increment_unique': len(manifest_rows),
            'train_rows': len(train_rows),
            'positive_source_unique': sum(1 for row in source_rows if _safe_int(row.get('mix', 0)) == 1),
            'negative_source_unique': sum(1 for row in source_rows if _safe_int(row.get('mix', 0)) == 0),
            'positive_unique': sum(1 for row in manifest_rows if _safe_int(row.get('mix', 0)) == 1),
            'negative_unique': sum(1 for row in manifest_rows if _safe_int(row.get('mix', 0)) == 0),
        },
        'source_binary_role_counts': dict(source_role_counts),
        'binary_role_counts': dict(Counter(str(row.get('binary_role', '') or '') for row in manifest_rows)),
        'anchor_count_per_source': anchor_count_per_source,
        'pair_positive_counts': dict(pair_counter),
        'manifests': {
            'training_increment_manifest': str(training_increment_manifest),
            'event_eval_manifest': str(event_eval_manifest),
            'train_manifest': str(train_manifest),
            'validation_manifest': str(validation_manifest) if validation_manifest.exists() else '',
            'test_manifest': str(test_manifest) if test_manifest.exists() else '',
            'analysis_report': str(analysis_report_path),
        },
        'records': [
            {
                'item_name': str(row.get('item_name', '') or ''),
                'binary_role': str(row.get('binary_role', '') or ''),
                'anchor_label': str(row.get('anchor_label', '') or ''),
                'anchor_event_family': str(row.get('anchor_event_family', '') or ''),
                'anchor_event_type': str(row.get('anchor_event_type', '') or ''),
                'anchor_window_variant': str(row.get('anchor_window_variant', '') or ''),
                'anchor_center_time': row.get('anchor_center_time', 0.0),
                'anchor_center_ratio': row.get('anchor_center_ratio', 0.0),
                'source_event_rank': row.get('source_event_rank', 0),
                'event_start_time': row.get('event_start_time', 0.0),
                'event_end_time': row.get('event_end_time', 0.0),
                'event_duration': row.get('event_duration', 0.0),
                'event_mix_prob': row.get('event_mix_prob', 0.0),
                'event_mean_pitch_hz': row.get('event_mean_pitch_hz', 0.0),
                'pair_positive_item_name': str(row.get('pair_positive_item_name', '') or ''),
                'pair_distance': row.get('pair_distance', 0.0),
                'source_wav_path': str(row.get('source_wav_path', '') or ''),
            }
            for row in analyzed_records
        ],
        'rationale': [
            'Use runtime-ranked event windows instead of full clips so training pressure lands on the same local structures that drive GUI decisions.',
            'Allow 2-3 windows per source sample so long positive falsetto spans are not collapsed into a single midpoint crop.',
            'Keep output as ordinary wav manifests so existing mix training and probe code can be reused without touching the core trainer.',
            'Record pair assignments and event statistics in JSON so future runtime regressions can be compared against the exact anchored segments.',
        ],
    }
    plan_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())