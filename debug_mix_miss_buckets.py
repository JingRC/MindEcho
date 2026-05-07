import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Filter mix regression rows and bucket remaining misses by singer and pitch band.')
    parser.add_argument('--input', required=True, help='Path to a debug_mix_role_regression JSON report.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    parser.add_argument('--csv-output', default='', help='Optional CSV output path for the matched rows.')
    parser.add_argument('--binary-role', action='append', dest='binary_roles', help='Optional binary_role filter. May be provided multiple times.')
    parser.add_argument('--group', action='append', dest='groups', help='Optional group_name filter. May be provided multiple times.')
    parser.add_argument('--outcome', action='append', dest='outcomes', help='Optional outcome filter. May be provided multiple times.')
    parser.add_argument('--min-mix-prob', type=float, default=-1.0, help='Minimum best_voice_mix_prob to include.')
    parser.add_argument('--max-mix-prob', type=float, default=2.0, help='Maximum best_voice_mix_prob to include.')
    parser.add_argument('--pitch-cuts', default='380,460,540', help='Comma-separated pitch cut points in Hz. Default: 380,460,540.')
    return parser.parse_args()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_text(value: Any) -> str:
    return str(value or '').strip()


def _parse_pitch_cuts(text: str) -> List[float]:
    values: List[float] = []
    for chunk in str(text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        values.append(float(chunk))
    cleaned = sorted(set(value for value in values if value > 0.0))
    if not cleaned:
        cleaned = [380.0, 460.0, 540.0]
    return cleaned


def _pitch_band_labels(cuts: Sequence[float]) -> List[str]:
    labels: List[str] = []
    lower = 0.0
    for upper in list(cuts or []):
        if lower <= 0.0:
            labels.append(f'lt{int(upper)}')
        else:
            labels.append(f'{int(lower)}to{int(upper)}')
        lower = float(upper)
    labels.append(f'ge{int(lower)}')
    return labels


def _resolve_pitch_band(pitch_hz: float, cuts: Sequence[float], labels: Sequence[str]) -> str:
    value = _safe_float(pitch_hz, 0.0)
    for index, upper in enumerate(list(cuts or [])):
        if value < float(upper):
            return str(labels[index])
    return str(labels[-1]) if labels else 'unknown'


def _iter_rows(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    rows = payload.get('rows', [])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                yield row


def _match_filters(row: Dict[str, Any], args: argparse.Namespace) -> bool:
    if _safe_text(row.get('error')):
        return False
    binary_roles = {_safe_text(item) for item in list(args.binary_roles or []) if _safe_text(item)}
    groups = {_safe_text(item) for item in list(args.groups or []) if _safe_text(item)}
    outcomes = {_safe_text(item) for item in list(args.outcomes or []) if _safe_text(item)}
    if binary_roles and _safe_text(row.get('binary_role')) not in binary_roles:
        return False
    if groups and _safe_text(row.get('group_name')) not in groups:
        return False
    if outcomes and _safe_text(row.get('outcome')) not in outcomes:
        return False
    mix_prob = _safe_float(row.get('best_voice_mix_prob', 0.0), 0.0)
    if mix_prob < float(args.min_mix_prob):
        return False
    if mix_prob > float(args.max_mix_prob):
        return False
    return True


def _build_match_row(row: Dict[str, Any], cuts: Sequence[float], labels: Sequence[str]) -> Dict[str, Any]:
    best_voice_event = dict(row.get('best_voice_event', {}) or {})
    pitch_hz = _safe_float(best_voice_event.get('mean_pitch_hz', 0.0), 0.0)
    mix_prob = _safe_float(row.get('best_voice_mix_prob', 0.0), 0.0)
    match = {
        'item_name': _safe_text(row.get('item_name')),
        'group_name': _safe_text(row.get('group_name')),
        'song_name': _safe_text(row.get('song_name')),
        'singer': _safe_text(row.get('singer')),
        'binary_role': _safe_text(row.get('binary_role')),
        'outcome': _safe_text(row.get('outcome')),
        'miss_reason': _safe_text(row.get('miss_reason')),
        'wav_path': _safe_text(row.get('wav_path')),
        'best_voice_mix_prob': round(mix_prob, 6),
        'best_voice_mix_margin': round(_safe_float(row.get('best_voice_mix_margin', 0.0), 0.0), 6),
        'mean_pitch_hz': round(pitch_hz, 6),
        'pitch_band': _resolve_pitch_band(pitch_hz, cuts, labels),
        'event_type': _safe_text(best_voice_event.get('event_type')),
        'chest_prob': round(_safe_float(best_voice_event.get('chest_prob', 0.0), 0.0), 6),
        'falsetto_prob': round(_safe_float(best_voice_event.get('falsetto_prob', 0.0), 0.0), 6),
        'mean_rms': round(_safe_float(best_voice_event.get('mean_rms', 0.0), 0.0), 6),
        'stable_ratio': round(_safe_float(best_voice_event.get('stable_ratio', 0.0), 0.0), 6),
        'voiced_ratio': round(_safe_float(best_voice_event.get('voiced_ratio', 0.0), 0.0), 6),
    }
    return match


def _summarize_bucket(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    if total <= 0:
        return {
            'count': 0,
            'avg_mix_prob': 0.0,
            'avg_mix_margin': 0.0,
            'avg_pitch_hz': 0.0,
            'avg_mean_rms': 0.0,
            'items': [],
        }
    return {
        'count': total,
        'avg_mix_prob': round(sum(_safe_float(row.get('best_voice_mix_prob', 0.0), 0.0) for row in rows) / total, 6),
        'avg_mix_margin': round(sum(_safe_float(row.get('best_voice_mix_margin', 0.0), 0.0) for row in rows) / total, 6),
        'avg_pitch_hz': round(sum(_safe_float(row.get('mean_pitch_hz', 0.0), 0.0) for row in rows) / total, 6),
        'avg_mean_rms': round(sum(_safe_float(row.get('mean_rms', 0.0), 0.0) for row in rows) / total, 6),
        'items': [
            {
                'item_name': _safe_text(row.get('item_name')),
                'song_name': _safe_text(row.get('song_name')),
                'best_voice_mix_prob': round(_safe_float(row.get('best_voice_mix_prob', 0.0), 0.0), 6),
                'mean_pitch_hz': round(_safe_float(row.get('mean_pitch_hz', 0.0), 0.0), 6),
                'mean_rms': round(_safe_float(row.get('mean_rms', 0.0), 0.0), 6),
                'wav_path': _safe_text(row.get('wav_path')),
            }
            for row in rows
        ],
    }


def build_report(payload: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    cuts = _parse_pitch_cuts(args.pitch_cuts)
    labels = _pitch_band_labels(cuts)
    matches = [
        _build_match_row(row, cuts, labels)
        for row in _iter_rows(payload)
        if _match_filters(row, args)
    ]
    matches.sort(
        key=lambda row: (
            _safe_text(row.get('singer')),
            _safe_text(row.get('pitch_band')),
            -_safe_float(row.get('best_voice_mix_prob', 0.0), 0.0),
            _safe_text(row.get('item_name')),
        )
    )

    by_singer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_pitch_band: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_singer_pitch: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in matches:
        singer = _safe_text(row.get('singer')) or 'unknown'
        pitch_band = _safe_text(row.get('pitch_band')) or 'unknown'
        by_singer[singer].append(row)
        by_pitch_band[pitch_band].append(row)
        by_singer_pitch[(singer, pitch_band)].append(row)

    singer_pitch_summary: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for (singer, pitch_band), rows in sorted(by_singer_pitch.items()):
        singer_pitch_summary[singer][pitch_band] = _summarize_bucket(rows)

    report = {
        'source_report': _safe_text(args.input),
        'filters': {
            'binary_roles': list(args.binary_roles or []),
            'groups': list(args.groups or []),
            'outcomes': list(args.outcomes or []),
            'min_mix_prob': round(float(args.min_mix_prob), 6),
            'max_mix_prob': round(float(args.max_mix_prob), 6),
            'pitch_cuts_hz': [round(float(item), 6) for item in cuts],
            'pitch_bands': list(labels),
        },
        'match_count': len(matches),
        'singer_counts': dict(sorted(Counter(_safe_text(row.get('singer')) or 'unknown' for row in matches).items())),
        'pitch_band_counts': dict(sorted(Counter(_safe_text(row.get('pitch_band')) or 'unknown' for row in matches).items())),
        'by_singer': {singer: _summarize_bucket(rows) for singer, rows in sorted(by_singer.items())},
        'by_pitch_band': {pitch_band: _summarize_bucket(rows) for pitch_band, rows in sorted(by_pitch_band.items())},
        'by_singer_pitch_band': {singer: buckets for singer, buckets in sorted(singer_pitch_summary.items())},
        'matches': matches,
    }
    return report


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    fieldnames = [
        'item_name',
        'song_name',
        'singer',
        'group_name',
        'binary_role',
        'outcome',
        'miss_reason',
        'pitch_band',
        'best_voice_mix_prob',
        'best_voice_mix_margin',
        'mean_pitch_hz',
        'mean_rms',
        'chest_prob',
        'falsetto_prob',
        'stable_ratio',
        'voiced_ratio',
        'wav_path',
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f'input report not found: {input_path}')
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise RuntimeError('input report must be a JSON object')

    report = build_report(payload, args)
    print(json.dumps({
        'match_count': report.get('match_count', 0),
        'singer_counts': report.get('singer_counts', {}),
        'pitch_band_counts': report.get('pitch_band_counts', {}),
    }, ensure_ascii=False, indent=2), flush=True)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'json_report={output_path}', flush=True)
    if args.csv_output:
        csv_path = Path(args.csv_output).resolve()
        _write_csv(csv_path, list(report.get('matches', [])))
        print(f'csv_report={csv_path}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())