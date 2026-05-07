import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import debug_mix_rule_offline as dbg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run targeted offline mix regression by binary_role.')
    parser.add_argument('--manifest', default=str(dbg.DEFAULT_MANIFEST), help='CSV manifest to read labeled samples from.')
    parser.add_argument('--binary-role', action='append', dest='binary_roles', required=True, help='binary_role to include. May be provided multiple times.')
    parser.add_argument('--group', action='append', dest='groups', help='Optional group_name filter. May be provided multiple times.')
    parser.add_argument('--limit-per-role', type=int, default=0, help='Maximum samples per binary_role. 0 means all matched samples.')
    parser.add_argument('--skip-per-role', type=int, default=0, help='Number of matched samples to skip per binary_role before taking results.')
    parser.add_argument('--progress-every', type=int, default=1, help='Print a progress line every N processed samples.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    return parser.parse_args()


def load_samples(
    manifest_path: Path,
    *,
    binary_roles: List[str],
    groups: Optional[List[str]] = None,
    limit_per_role: int = 0,
    skip_per_role: int = 0,
) -> List[Dict[str, Any]]:
    role_filter = [str(item or '').strip() for item in list(binary_roles or []) if str(item or '').strip()]
    if not role_filter:
        return []
    role_filter_set = set(role_filter)
    group_filter_set = {str(item or '').strip() for item in list(groups or []) if str(item or '').strip()}
    counts = Counter()
    skipped = Counter()
    seen = set()
    selected: List[Dict[str, Any]] = []

    with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            binary_role = str(row.get('binary_role', '') or '').strip()
            if binary_role not in role_filter_set:
                continue
            if limit_per_role > 0 and counts[binary_role] >= limit_per_role:
                continue

            group_name = str(row.get('group_name', '') or '').strip()
            if group_filter_set and group_name not in group_filter_set:
                continue

            wav_path = str(row.get('wav_path', '') or '').strip()
            if not wav_path or wav_path in seen:
                continue
            if not os.path.exists(wav_path):
                continue

            if skipped[binary_role] < max(0, int(skip_per_role)):
                skipped[binary_role] += 1
                continue

            seen.add(wav_path)
            counts[binary_role] += 1
            selected.append({
                'source': 'manifest',
                'group_name': group_name,
                'item_name': str(row.get('item_name', '') or ''),
                'song_name': str(row.get('song_name', '') or ''),
                'singer': str(row.get('singer', '') or ''),
                'binary_role': binary_role,
                'wav_path': wav_path,
                'mix': int(row.get('mix', 0) or 0),
                'falsetto': int(row.get('falsetto', 0) or 0),
                'breathy': int(row.get('breathy', 0) or 0),
            })

            if limit_per_role > 0 and all(counts[role] >= limit_per_role for role in role_filter):
                break

    return selected


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compact_voice_event(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(event.get('display_payload', {}) or {})
    snapshot = dict(event.get('feature_snapshot', {}) or {})
    mix_prob = _safe_float(payload.get('mix_prob', snapshot.get('mix_prob', event.get('mix_prob', 0.0))))
    return {
        'event_type': str(event.get('event_type', '') or ''),
        'start_time': dbg.to_jsonable(_safe_float(event.get('start_time', 0.0))),
        'end_time': dbg.to_jsonable(_safe_float(event.get('end_time', 0.0))),
        'raw_mix_prob': dbg.to_jsonable(_safe_float(payload.get('raw_mix_prob', snapshot.get('raw_mix_prob', event.get('mix_prob', 0.0))))),
        'mix_prob': dbg.to_jsonable(mix_prob),
        'mix_threshold': dbg.to_jsonable(_safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)),
        'mix_calibration_delta': dbg.to_jsonable(_safe_float(payload.get('mix_calibration_delta', snapshot.get('mix_calibration_delta', 0.0)))),
        'mix_calibration_profile': str(payload.get('mix_calibration_profile', snapshot.get('mix_calibration_profile', '')) or ''),
        'mean_pitch_hz': dbg.to_jsonable(_safe_float(event.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)))),
        'chest_prob': dbg.to_jsonable(_safe_float(event.get('chest_prob', snapshot.get('chest_prob', 0.0)))),
        'falsetto_prob': dbg.to_jsonable(_safe_float(event.get('falsetto_prob', snapshot.get('falsetto_prob', 0.0)))),
        'mean_rms': dbg.to_jsonable(_safe_float(snapshot.get('mean_rms', 0.0))),
        'mean_zcr': dbg.to_jsonable(_safe_float(snapshot.get('mean_zcr', 0.0))),
        'stable_ratio': dbg.to_jsonable(_safe_float(snapshot.get('stable_ratio', 0.0))),
        'voiced_ratio': dbg.to_jsonable(_safe_float(snapshot.get('voiced_ratio', 0.0))),
        'mean_breath_score': dbg.to_jsonable(_safe_float(snapshot.get('mean_breath_score', 0.0))),
        'breath_hint_ratio': dbg.to_jsonable(_safe_float(snapshot.get('breath_hint_ratio', 0.0))),
    }


def _compact_mix_event(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(event.get('display_payload', {}) or {})
    snapshot = dict(event.get('feature_snapshot', {}) or {})
    return {
        'event_type': str(event.get('event_type', '') or ''),
        'start_time': dbg.to_jsonable(_safe_float(event.get('start_time', 0.0))),
        'end_time': dbg.to_jsonable(_safe_float(event.get('end_time', 0.0))),
        'raw_mix_prob': dbg.to_jsonable(_safe_float(payload.get('raw_mix_prob', snapshot.get('raw_mix_prob', event.get('mix_prob', 0.0))))),
        'mix_prob': dbg.to_jsonable(_safe_float(event.get('mix_prob', snapshot.get('mix_prob', 0.0)))),
        'mix_threshold': dbg.to_jsonable(_safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)),
        'mix_support': dbg.to_jsonable(_safe_float(payload.get('mix_support', snapshot.get('mix_support', 0.0)))),
        'mix_calibration_delta': dbg.to_jsonable(_safe_float(payload.get('mix_calibration_delta', snapshot.get('mix_calibration_delta', 0.0)))),
        'mix_calibration_profile': str(payload.get('mix_calibration_profile', snapshot.get('mix_calibration_profile', '')) or ''),
        'mean_pitch_hz': dbg.to_jsonable(_safe_float(event.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)))),
    }


def analyze_sample(app: Any, module: Any, ui: Any, sample: Dict[str, Any]) -> Dict[str, Any]:
    wav_path = str(sample.get('wav_path', '') or '').strip()
    item = {
        'sample': dict(sample),
        'onepass': {},
        'analysis': {},
        'error': '',
    }
    try:
        onepass_payload, worker = dbg.run_onepass_worker(app, module, ui, wav_path)
        audio, sample_rate = dbg.decode_audio_for_analysis(module, ui, worker, wav_path)
        result, events, voice_debug = dbg.run_integrated_analysis(app, ui, onepass_payload, audio, sample_rate)
        serialized_events = [dbg.summarize_event(event) for event in list(events or [])]
        voice_events = [event for event in serialized_events if event.get('event_type') in {'chest_voice', 'falsetto'}]
        mix_events = [event for event in serialized_events if event.get('event_type') in {'strong_mix', 'weak_mix', 'balanced_mix'}]
        item['onepass'] = {
            'duration': dbg.to_jsonable(_safe_float(onepass_payload.get('duration', 0.0))),
            'segment_count': len(list(onepass_payload.get('segments', []) or [])),
            'pitch_record_count': dbg.count_pitch_records(onepass_payload),
            'sample_rate': int(sample_rate),
        }
        item['analysis'] = {
            'summary': dbg.to_jsonable(result),
            'voice_debug': dbg.to_jsonable(voice_debug),
            'voice_events': voice_events,
            'mix_events': mix_events,
        }
    except Exception as exc:
        item['error'] = str(exc)
    return item


def summarize_sample(item: Dict[str, Any]) -> Dict[str, Any]:
    sample = dict(item.get('sample', {}) or {})
    onepass = dict(item.get('onepass', {}) or {})
    analysis = dict(item.get('analysis', {}) or {})
    summary = dict(analysis.get('summary', {}) or {})
    counts = dict(summary.get('counts', {}) or {})
    voice_events = list(analysis.get('voice_events', []) or [])
    mix_events = list(analysis.get('mix_events', []) or [])
    binary_role = str(sample.get('binary_role', '') or '')

    best_voice_event = None
    best_voice_mix_prob = -1.0
    best_voice_mix_margin = -999.0
    voice_segments_ge_threshold = 0
    for event in voice_events:
        payload = dict(event.get('display_payload', {}) or {})
        snapshot = dict(event.get('feature_snapshot', {}) or {})
        mix_prob = _safe_float(payload.get('mix_prob', snapshot.get('mix_prob', event.get('mix_prob', 0.0))))
        mix_threshold = _safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)
        mix_margin = mix_prob - mix_threshold
        if mix_prob >= mix_threshold:
            voice_segments_ge_threshold += 1
        if best_voice_event is None or mix_prob > best_voice_mix_prob or (abs(mix_prob - best_voice_mix_prob) < 1e-9 and mix_margin > best_voice_mix_margin):
            best_voice_event = event
            best_voice_mix_prob = mix_prob
            best_voice_mix_margin = mix_margin

    strongest_mix_event = None
    strongest_mix_support = -1.0
    for event in mix_events:
        payload = dict(event.get('display_payload', {}) or {})
        snapshot = dict(event.get('feature_snapshot', {}) or {})
        mix_support = _safe_float(payload.get('mix_support', snapshot.get('mix_support', 0.0)))
        if strongest_mix_event is None or mix_support > strongest_mix_support:
            strongest_mix_event = event
            strongest_mix_support = mix_support

    has_any_mix = bool(mix_events)
    has_strong_mix = any(str(event.get('event_type', '') or '') == 'strong_mix' for event in mix_events)
    if binary_role == 'positive_mix':
        outcome = 'hit' if has_any_mix else 'miss'
    elif binary_role == 'control_negative':
        outcome = 'false_positive' if has_any_mix else 'clean'
    else:
        outcome = 'has_mix' if has_any_mix else 'no_mix'

    miss_reason = ''
    if outcome == 'miss':
        if not voice_events:
            miss_reason = 'no_voice_events'
        elif voice_segments_ge_threshold > 0:
            miss_reason = 'rule_rejected_after_threshold'
        else:
            miss_reason = 'voice_mix_below_threshold'

    best_voice_payload = dict(best_voice_event.get('display_payload', {}) or {}) if best_voice_event else {}
    best_voice_snapshot = dict(best_voice_event.get('feature_snapshot', {}) or {}) if best_voice_event else {}
    best_voice_raw_mix_prob = _safe_float(
        best_voice_payload.get(
            'raw_mix_prob',
            best_voice_snapshot.get('raw_mix_prob', best_voice_mix_prob if best_voice_event is not None else 0.0),
        )
    )
    best_voice_mix_threshold = _safe_float(
        best_voice_payload.get('mix_threshold', best_voice_snapshot.get('mix_threshold', 0.45)),
        0.45,
    )
    best_voice_mix_calibration_delta = _safe_float(
        best_voice_payload.get('mix_calibration_delta', best_voice_snapshot.get('mix_calibration_delta', 0.0))
    )
    best_voice_mix_calibration_profile = str(
        best_voice_payload.get('mix_calibration_profile', best_voice_snapshot.get('mix_calibration_profile', '')) or ''
    )

    return {
        'item_name': str(sample.get('item_name', '') or ''),
        'group_name': str(sample.get('group_name', '') or ''),
        'song_name': str(sample.get('song_name', '') or ''),
        'singer': str(sample.get('singer', '') or ''),
        'binary_role': binary_role,
        'wav_path': str(sample.get('wav_path', '') or ''),
        'error': str(item.get('error', '') or ''),
        'outcome': outcome,
        'miss_reason': miss_reason,
        'onepass_duration': dbg.to_jsonable(_safe_float(onepass.get('duration', 0.0))),
        'segment_count': int(onepass.get('segment_count', 0) or 0),
        'pitch_record_count': int(onepass.get('pitch_record_count', 0) or 0),
        'event_count': int(summary.get('event_count', 0) or 0),
        'counts': counts,
        'voice_event_count': len(voice_events),
        'mix_event_count': len(mix_events),
        'strong_mix_count': sum(1 for event in mix_events if str(event.get('event_type', '') or '') == 'strong_mix'),
        'weak_mix_count': sum(1 for event in mix_events if str(event.get('event_type', '') or '') == 'weak_mix'),
        'balanced_mix_count': sum(1 for event in mix_events if str(event.get('event_type', '') or '') == 'balanced_mix'),
        'voice_segments_mix_ge_threshold': int(voice_segments_ge_threshold),
        'best_voice_event': _compact_voice_event(best_voice_event or {}),
        'best_voice_raw_mix_prob': dbg.to_jsonable(best_voice_raw_mix_prob),
        'best_voice_mix_prob': dbg.to_jsonable(max(0.0, best_voice_mix_prob)),
        'best_voice_mix_threshold': dbg.to_jsonable(best_voice_mix_threshold),
        'best_voice_mix_margin': dbg.to_jsonable(best_voice_mix_margin if best_voice_event is not None else 0.0),
        'best_voice_mix_calibration_delta': dbg.to_jsonable(best_voice_mix_calibration_delta),
        'best_voice_mix_calibration_profile': best_voice_mix_calibration_profile,
        'strongest_mix_event': _compact_mix_event(strongest_mix_event or {}),
        'voice_debug': dict(analysis.get('voice_debug', {}) or {}),
    }


def build_aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    aggregate: Dict[str, Any] = {
        'sample_count': len(rows),
        'error_count': sum(1 for row in rows if str(row.get('error', '') or '')),
        'binary_roles': {},
    }
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get('binary_role', '') or ''), []).append(row)

    for role_name, role_rows in grouped.items():
        total = len(role_rows)
        with_mix = [row for row in role_rows if int(row.get('mix_event_count', 0) or 0) > 0]
        with_strong_mix = [row for row in role_rows if int(row.get('strong_mix_count', 0) or 0) > 0]
        calibration_rows = [row for row in role_rows if _safe_float(row.get('best_voice_mix_calibration_delta', 0.0)) > 0.0]
        calibration_profile_counts = Counter(
            str(row.get('best_voice_mix_calibration_profile', '') or '').strip()
            for row in calibration_rows
            if str(row.get('best_voice_mix_calibration_profile', '') or '').strip()
        )
        errors = [row for row in role_rows if str(row.get('error', '') or '')]
        if role_name == 'positive_mix':
            outcome_key = 'misses'
            interesting_rows = [row for row in role_rows if str(row.get('outcome', '') or '') == 'miss']
            rate_key = 'sample_level_any_mix_recall_proxy'
            rate_value = (len(with_mix) / total) if total else 0.0
        elif role_name == 'control_negative':
            outcome_key = 'false_positives'
            interesting_rows = [row for row in role_rows if str(row.get('outcome', '') or '') == 'false_positive']
            rate_key = 'sample_level_false_positive_rate'
            rate_value = (len(with_mix) / total) if total else 0.0
        else:
            outcome_key = 'interesting_rows'
            interesting_rows = [row for row in role_rows if int(row.get('mix_event_count', 0) or 0) > 0]
            rate_key = 'sample_level_any_mix_rate'
            rate_value = (len(with_mix) / total) if total else 0.0

        interesting_rows = sorted(
            interesting_rows,
            key=lambda row: (
                -_safe_float(row.get('best_voice_mix_prob', 0.0)),
                -_safe_float(row.get('best_voice_mix_margin', 0.0)),
                str(row.get('wav_path', '') or ''),
            ),
        )

        aggregate['binary_roles'][role_name] = {
            'sample_count': total,
            'error_count': len(errors),
            'samples_with_any_mix_event': len(with_mix),
            'samples_with_strong_mix': len(with_strong_mix),
            'samples_with_best_voice_calibration': len(calibration_rows),
            rate_key: round(float(rate_value), 6),
            'avg_best_voice_raw_mix_prob': round(
                sum(_safe_float(row.get('best_voice_raw_mix_prob', 0.0)) for row in role_rows) / total,
                6,
            ) if total else 0.0,
            'avg_best_voice_mix_prob': round(
                sum(_safe_float(row.get('best_voice_mix_prob', 0.0)) for row in role_rows) / total,
                6,
            ) if total else 0.0,
            'avg_best_voice_mix_calibration_delta': round(
                sum(_safe_float(row.get('best_voice_mix_calibration_delta', 0.0)) for row in role_rows) / total,
                6,
            ) if total else 0.0,
            'best_voice_calibration_profiles': dict(calibration_profile_counts),
            outcome_key: interesting_rows,
        }
    return aggregate


def print_row_summary(index: int, total: int, row: Dict[str, Any]) -> None:
    role = str(row.get('binary_role', '') or '-')
    item_name = str(row.get('item_name', '') or Path(str(row.get('wav_path', '') or '')).stem)
    outcome = str(row.get('outcome', '') or '-')
    if str(row.get('error', '') or ''):
        print(f'[{index}/{total}] role={role} item={item_name} outcome=error error={row.get("error")}', flush=True)
        return
    print(
        f'[{index}/{total}] role={role} item={item_name} outcome={outcome} '
        f'raw_mix={row.get("best_voice_raw_mix_prob")} max_mix={row.get("best_voice_mix_prob")} '
        f'cal_delta={row.get("best_voice_mix_calibration_delta")} margin={row.get("best_voice_mix_margin")} '
        f'mix_events={row.get("mix_event_count")} counts={json.dumps(row.get("counts", {}), ensure_ascii=False)}',
        flush=True,
    )


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f'manifest not found: {manifest_path}', file=sys.stderr)
        return 2

    samples = load_samples(
        manifest_path,
        binary_roles=list(args.binary_roles or []),
        groups=list(args.groups or []),
        limit_per_role=max(0, int(args.limit_per_role)),
        skip_per_role=max(0, int(args.skip_per_role)),
    )
    if not samples:
        print('no samples selected', file=sys.stderr)
        return 2

    role_counts = Counter(str(sample.get('binary_role', '') or '') for sample in samples)
    print(
        'selected_samples',
        json.dumps(
            {
                'count': len(samples),
                'manifest': str(manifest_path),
                'binary_roles': list(args.binary_roles or []),
                'groups': list(args.groups or []),
                'role_counts': dict(role_counts),
                'limit_per_role': int(args.limit_per_role),
                'skip_per_role': int(args.skip_per_role),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    app = None
    ui = None
    rows: List[Dict[str, Any]] = []
    exit_code = 0
    try:
        app, module, ui, _ = dbg.load_runtime(show_init_log=False)
        total = len(samples)
        for index, sample in enumerate(samples, start=1):
            item = analyze_sample(app, module, ui, sample)
            row = summarize_sample(item)
            rows.append(row)
            progress_every = max(1, int(args.progress_every))
            if index == 1 or index == total or (index % progress_every == 0):
                print_row_summary(index, total, row)

        aggregate = build_aggregate(rows)
        payload = {
            'manifest': str(manifest_path),
            'binary_roles': list(args.binary_roles or []),
            'groups': list(args.groups or []),
            'limit_per_role': int(args.limit_per_role),
            'skip_per_role': int(args.skip_per_role),
            'selected_count': len(samples),
            'aggregate': aggregate,
            'rows': rows,
        }
        print('aggregate', json.dumps(aggregate, ensure_ascii=False), flush=True)

        if args.output:
            output_path = Path(args.output).resolve()
            output_path.write_text(json.dumps(dbg.to_jsonable(payload), ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'json_report={output_path}', flush=True)

        exit_code = 1 if int(aggregate.get('error_count', 0) or 0) > 0 else 0
    finally:
        if app is not None and ui is not None:
            dbg.close_runtime(app, ui)
    return int(exit_code)


if __name__ == '__main__':
    raise SystemExit(main())