import argparse
import json
import os
import sys
from pathlib import Path

import debug_mix_rule_offline as dbg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Batch summary for integrated mix-rule offline validation.')
    parser.add_argument('--group', action='append', dest='groups', required=True, help='Manifest group name. May be provided multiple times.')
    parser.add_argument('--binary-role', action='append', dest='binary_roles', help='Optional binary_role filter. May be provided multiple times.')
    parser.add_argument('--per-group', type=int, default=1, help='Number of samples to pick per group.')
    parser.add_argument('--skip', type=int, default=0, help='Number of samples to skip within each group before taking per-group items.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    return parser.parse_args()


def pick_samples(groups, per_group: int, skip: int, binary_roles=None):
    combined = []
    seen = set()
    for group in groups:
        group_samples = dbg.pick_manifest_samples(
            dbg.DEFAULT_MANIFEST,
            (group,),
            max(per_group + max(0, skip), per_group),
            binary_roles=binary_roles,
        )
        for sample in group_samples[max(0, int(skip)):max(0, int(skip)) + per_group]:
            wav_path = str(sample.get('wav_path', '') or '')
            if not wav_path or wav_path in seen:
                continue
            seen.add(wav_path)
            combined.append(sample)
    return combined


def summarize_sample(item: dict) -> dict:
    sample = dict(item.get('sample', {}) or {})
    analysis = dict(item.get('analysis', {}) or {})
    summary = dict(analysis.get('summary', {}) or {})
    mix_events = list(analysis.get('mix_events', []) or [])
    voice_events = list(analysis.get('voice_events', []) or [])
    strong_mix_events = [event for event in mix_events if str(event.get('event_type', '') or '') == 'strong_mix']
    weak_mix_events = [event for event in mix_events if str(event.get('event_type', '') or '') == 'weak_mix']
    balanced_mix_events = [event for event in mix_events if str(event.get('event_type', '') or '') == 'balanced_mix']

    total_voice_duration = 0.0
    strong_mix_duration = 0.0
    max_mix_prob = 0.0
    voice_segments_ge_threshold = 0
    for event in voice_events:
        try:
            duration = float(event.get('end_time', 0.0) or 0.0) - float(event.get('start_time', 0.0) or 0.0)
        except Exception:
            duration = 0.0
        total_voice_duration += max(0.0, duration)
        try:
            mix_prob = float(event.get('mix_prob', 0.0) or 0.0)
        except Exception:
            mix_prob = 0.0
        try:
            threshold = float((event.get('display_payload', {}) or {}).get('mix_threshold', 0.45) or 0.45)
        except Exception:
            threshold = 0.45
        max_mix_prob = max(max_mix_prob, mix_prob)
        if mix_prob >= threshold:
            voice_segments_ge_threshold += 1
    for event in strong_mix_events:
        try:
            duration = float(event.get('end_time', 0.0) or 0.0) - float(event.get('start_time', 0.0) or 0.0)
        except Exception:
            duration = 0.0
        strong_mix_duration += max(0.0, duration)

    return {
        'item_name': sample.get('item_name', ''),
        'group_name': sample.get('group_name', ''),
        'song_name': sample.get('song_name', ''),
        'binary_role': sample.get('binary_role', ''),
        'event_count': int(summary.get('event_count', 0) or 0),
        'counts': summary.get('counts', {}) or {},
        'voice_event_count': len(voice_events),
        'mix_event_count': len(mix_events),
        'strong_mix_count': len(strong_mix_events),
        'weak_mix_count': len(weak_mix_events),
        'balanced_mix_count': len(balanced_mix_events),
        'voice_segments_mix_ge_threshold': voice_segments_ge_threshold,
        'max_mix_prob': round(max_mix_prob, 6),
        'strong_mix_duration': round(strong_mix_duration, 6),
        'voice_duration': round(total_voice_duration, 6),
        'strong_mix_coverage': round((strong_mix_duration / total_voice_duration) if total_voice_duration > 0.0 else 0.0, 6),
    }


def build_aggregate(rows: list[dict]) -> dict:
    sample_count = len(rows)
    samples_with_any_mix = sum(1 for row in rows if int(row.get('mix_event_count', 0) or 0) > 0)
    samples_with_strong_mix = sum(1 for row in rows if int(row.get('strong_mix_count', 0) or 0) > 0)
    voice_segments_total = sum(int(row.get('voice_event_count', 0) or 0) for row in rows)
    voice_segments_mix_ge_threshold = sum(int(row.get('voice_segments_mix_ge_threshold', 0) or 0) for row in rows)
    avg_max_mix_prob = (sum(float(row.get('max_mix_prob', 0.0) or 0.0) for row in rows) / sample_count) if sample_count else 0.0
    avg_strong_mix_coverage = (sum(float(row.get('strong_mix_coverage', 0.0) or 0.0) for row in rows) / sample_count) if sample_count else 0.0
    avg_strong_mix_duration = (sum(float(row.get('strong_mix_duration', 0.0) or 0.0) for row in rows) / sample_count) if sample_count else 0.0
    return {
        'sample_count': sample_count,
        'samples_with_any_mix_event': samples_with_any_mix,
        'samples_with_strong_mix': samples_with_strong_mix,
        'sample_level_any_mix_recall_proxy': round((samples_with_any_mix / sample_count) if sample_count else 0.0, 6),
        'sample_level_strong_mix_recall_proxy': round((samples_with_strong_mix / sample_count) if sample_count else 0.0, 6),
        'voice_segments_total': voice_segments_total,
        'voice_segments_mix_ge_threshold': voice_segments_mix_ge_threshold,
        'voice_segment_mix_hit_ratio': round((voice_segments_mix_ge_threshold / voice_segments_total) if voice_segments_total else 0.0, 6),
        'avg_max_mix_prob': round(avg_max_mix_prob, 6),
        'avg_strong_mix_coverage': round(avg_strong_mix_coverage, 6),
        'avg_strong_mix_duration': round(avg_strong_mix_duration, 6),
    }


def main() -> int:
    args = parse_args()
    samples = pick_samples(
        args.groups or [],
        max(1, int(args.per_group)),
        max(0, int(args.skip)),
        binary_roles=args.binary_roles,
    )
    if not samples:
        print('no samples selected', file=sys.stderr)
        return 2

    app, module, ui, _ = dbg.load_runtime(show_init_log=False)
    try:
        report = dbg.build_report(samples, app, module, ui)
    finally:
        dbg.close_runtime(app, ui)

    rows = [summarize_sample(item) for item in list(report.get('samples', []) or [])]
    aggregate = build_aggregate(rows)
    payload = {
        'groups': list(args.groups or []),
        'binary_roles': list(args.binary_roles or []),
        'per_group': int(args.per_group),
        'skip': int(args.skip),
        'aggregate': aggregate,
        'rows': rows,
    }

    print('aggregate', json.dumps(aggregate, ensure_ascii=False))
    for row in rows:
        print('row', json.dumps(row, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(json.dumps(dbg.to_jsonable(payload), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'json_report={output_path}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())