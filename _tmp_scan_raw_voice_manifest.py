import argparse
import csv
import json
from pathlib import Path

import debug_mix_rule_offline as dbg


def load_manifest_rows(manifest_path: Path):
    with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def build_raw_voice_events(app, ui, module, wav_path: str):
    onepass_payload, worker = dbg.run_onepass_worker(app, module, ui, wav_path)
    audio, sample_rate = dbg.decode_audio_for_analysis(module, ui, worker, wav_path)
    ui._onepass_analysis_payload = {
        'segments': list(onepass_payload.get('segments', []) or []),
        'duration': float(onepass_payload.get('duration', 0.0) or 0.0),
    }
    ui._in_onepass_mode = True
    resolved = ui._resolve_technique_analysis_payload()
    frames = list(resolved.get('frames', []) or [])
    voice_events = ui.visualizer._build_offline_chest_falsetto_events(frames, audio_samples=audio, sample_rate=sample_rate)
    return list(voice_events or [])


def event_to_row(item_name: str, binary_role: str, wav_path: str, event) -> dict:
    snapshot = dict(getattr(event, 'feature_snapshot', {}) or {})
    return {
        'item_name': item_name,
        'binary_role': binary_role,
        'wav_path': wav_path,
        'event_type': str(getattr(event, 'event_type', '') or ''),
        'start_time': round(float(getattr(event, 'start_time', 0.0) or 0.0), 6),
        'end_time': round(float(getattr(event, 'end_time', 0.0) or 0.0), 6),
        'confidence': round(float(getattr(event, 'confidence', 0.0) or 0.0), 6),
        'mean_pitch_hz': round(float(getattr(event, 'mean_pitch_hz', 0.0) or 0.0), 6),
        'chest_prob': round(float(getattr(event, 'chest_prob', 0.0) or 0.0), 6),
        'falsetto_prob': round(float(getattr(event, 'falsetto_prob', 0.0) or 0.0), 6),
        'mix_prob': round(float(snapshot.get('mix_prob', getattr(event, 'mix_prob', 0.0) or 0.0) or 0.0), 6),
        'mix_threshold': round(float(snapshot.get('mix_threshold', 0.45) or 0.45), 6),
        'probability_margin': round(float(getattr(event, 'probability_margin', 0.0) or 0.0), 6),
        'mean_rms': round(float(snapshot.get('mean_rms', 0.0) or 0.0), 6),
        'stable_ratio': round(float(snapshot.get('stable_ratio', 0.0) or 0.0), 6),
        'voiced_ratio': round(float(getattr(event, 'voiced_ratio', 0.0) or 0.0), 6),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    rows = load_manifest_rows(manifest_path)
    app, module, ui, _ = dbg.load_runtime(False)

    collected = []
    for row in rows:
        wav_path = str(row.get('wav_path', '') or '').strip()
        if not wav_path:
            continue
        try:
            voice_events = build_raw_voice_events(app, ui, module, wav_path)
            for event in voice_events:
                collected.append(
                    event_to_row(
                        str(row.get('item_name', '') or ''),
                        str(row.get('binary_role', '') or ''),
                        wav_path,
                        event,
                    )
                )
        except Exception as exc:
            collected.append(
                {
                    'item_name': str(row.get('item_name', '') or ''),
                    'binary_role': str(row.get('binary_role', '') or ''),
                    'wav_path': wav_path,
                    'error': f'{type(exc).__name__}',
                }
            )

    Path(args.output).write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(args.output))