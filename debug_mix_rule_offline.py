import argparse
import csv
import io
import json
import math
import os
import sys
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import numpy as np

try:
    import matplotlib

    matplotlib.use('Agg')
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


DEFAULT_MANIFEST = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_core' / 'test_manifest.csv'
DEFAULT_GROUPS = ('Mixed_Voice_Group', 'Falsetto_Group', 'Breathy_Group')
DEFAULT_SELECTED_TYPES = (
    'mix_voice',
    'strong_mix',
    'weak_mix',
    'balanced_mix',
    'falsetto',
    'chest_voice',
    'breath',
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run integrated one-pass offline validation for mix/falsetto/breathy samples.')
    parser.add_argument('--manifest', default=str(DEFAULT_MANIFEST), help='CSV manifest used to pick representative samples.')
    parser.add_argument('--group', action='append', dest='groups', help='Group name to sample. May be passed multiple times.')
    parser.add_argument('--binary-role', action='append', dest='binary_roles', help='Optional binary_role filter when sampling from a manifest. May be passed multiple times.')
    parser.add_argument('--per-group', type=int, default=1, help='How many samples to pick from each group when using a manifest.')
    parser.add_argument('--wav', action='append', default=[], help='Explicit wav path to analyze. May be passed multiple times.')
    parser.add_argument('--output', default='', help='Optional JSON file path for the full report.')
    parser.add_argument('--show-init-log', action='store_true', help='Print captured interface initialization logs.')
    return parser.parse_args()


def wait_qt(app, ms: int = 50) -> None:
    end = time.time() + (max(0, int(ms)) / 1000.0)
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def to_jsonable(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 6)
    if isinstance(value, np.generic):
        return to_jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, '__dataclass_fields__'):
        return {name: to_jsonable(getattr(value, name)) for name in value.__dataclass_fields__.keys()}
    return str(value)


def pick_manifest_samples(manifest_path: Path, groups, per_group: int, binary_roles=None):
    selected = []
    seen = set()
    counts = {group: 0 for group in groups}
    role_filter = {
        str(item or '').strip()
        for item in list(binary_roles or [])
        if str(item or '').strip()
    }
    with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            group_name = str(row.get('group_name', '') or '')
            if group_name not in counts:
                continue
            if counts[group_name] >= per_group:
                continue
            binary_role = str(row.get('binary_role', '') or '')
            if role_filter and binary_role not in role_filter:
                continue
            wav_path = str(row.get('wav_path', '') or '').strip()
            if not wav_path or wav_path in seen:
                continue
            if not os.path.exists(wav_path):
                continue
            counts[group_name] += 1
            seen.add(wav_path)
            selected.append({
                'source': 'manifest',
                'group_name': group_name,
                'item_name': str(row.get('item_name', '') or ''),
                'song_name': str(row.get('song_name', '') or ''),
                'singer': str(row.get('singer', '') or ''),
                'binary_role': str(row.get('binary_role', '') or ''),
                'wav_path': wav_path,
                'mix': int(row.get('mix', 0) or 0),
                'falsetto': int(row.get('falsetto', 0) or 0),
                'breathy': int(row.get('breathy', 0) or 0),
            })
            if all(count >= per_group for count in counts.values()):
                break
    return selected


def normalize_explicit_samples(paths):
    selected = []
    for raw_path in paths:
        wav_path = str(raw_path or '').strip()
        if not wav_path:
            continue
        selected.append({
            'source': 'explicit',
            'group_name': '',
            'item_name': Path(wav_path).stem,
            'song_name': '',
            'singer': '',
            'binary_role': '',
            'wav_path': wav_path,
            'mix': None,
            'falsetto': None,
            'breathy': None,
        })
    return selected


def load_runtime(show_init_log: bool):
    try:
        from PyQt6 import QtWidgets
    except Exception:
        try:
            from PyQt5 import QtWidgets  # type: ignore
        except Exception:
            from qtpy import QtWidgets  # type: ignore

    import importlib

    captured = io.StringIO()
    with ExitStack() as stack:
        if not show_init_log:
            stack.enter_context(redirect_stdout(captured))
            stack.enter_context(redirect_stderr(captured))
        module = importlib.import_module('gui.integrated_recording_interface')
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        ui = module.IntegratedRecordingInterface()
        try:
            ui.hide()
        except Exception:
            pass

    state = module.TechniquePanelState(
        config=module.TechniqueRecognitionConfig(
            enabled=True,
            detect_breath=True,
            detect_vibrato=False,
            show_in_normal_mode=True,
            show_in_professional_mode=True,
        ),
        selected_types=list(DEFAULT_SELECTED_TYPES),
    )
    try:
        state = module._normalize_technique_panel_state(state)
    except Exception:
        pass
    ui._technique_panel_state = state
    ui._sync_technique_panel_state_to_visualizer()
    try:
        ui.visualizer.display_mode.setCurrentText('普通模式')
    except Exception:
        pass
    wait_qt(app, 50)
    return app, module, ui, captured.getvalue()


def run_onepass_worker(app, module, ui, wav_path: str):
    worker = module._OnePassPitchWorker(ui, wav_path)
    payload_holder = []
    errors = []
    worker.finished_ok.connect(lambda obj: payload_holder.append(dict(obj or {})))
    worker.failed.connect(lambda msg: errors.append(str(msg)))
    worker.run()
    wait_qt(app, 50)
    if errors:
        raise RuntimeError(errors[-1])
    if not payload_holder:
        raise RuntimeError('one-pass worker did not produce a payload')
    return payload_holder[-1], worker


def decode_audio_for_analysis(module, ui, worker, wav_path: str):
    data, sample_rate = worker._decode_audio_file(wav_path)
    if data.ndim == 2 and data.shape[1] > 1:
        data = data.mean(axis=1, dtype=np.float64)
    else:
        data = data.squeeze()
    audio = np.asarray(data, dtype=np.float32).reshape(-1)
    sr_target = int(getattr(ui.audio_processor, 'sample_rate', 48000) or 48000)
    if int(sample_rate) != int(sr_target):
        audio = module._LocalFileRealtimeController._resample_linear(audio, int(sample_rate), int(sr_target))
        sample_rate = int(sr_target)
    return np.asarray(audio, dtype=np.float32).reshape(-1), int(sample_rate)


def count_pitch_records(onepass_payload: dict) -> int:
    try:
        raw_pitch_records = list(onepass_payload.get('raw_pitch_records', []) or [])
    except Exception:
        raw_pitch_records = []
    if raw_pitch_records:
        return int(len(raw_pitch_records))
    total = 0
    for segment in list(onepass_payload.get('segments', []) or []):
        try:
            total += min(len(segment[0] or []), len(segment[1] or []))
        except Exception:
            continue
    return int(total)


def run_integrated_analysis(app, ui, onepass_payload: dict, audio: np.ndarray, sample_rate: int):
    try:
        raw_pitch_records = list(onepass_payload.get('raw_pitch_records', []) or [])
    except Exception:
        raw_pitch_records = []
    try:
        pitch_payloads = list(onepass_payload.get('pitch_payloads', []) or [])
    except Exception:
        pitch_payloads = []
    pitch_records = []
    for segment in list(onepass_payload.get('segments', []) or []):
        try:
            seg_times = list(segment[0] or [])
            seg_pitches = list(segment[1] or [])
        except Exception:
            continue
        for t_val, p_val in zip(seg_times, seg_pitches):
            try:
                pitch_records.append((float(t_val), float(p_val), 1.0, None))
            except Exception:
                continue
    ui._onepass_analysis_payload = {
        'segments': list(onepass_payload.get('segments', []) or []),
        'duration': float(onepass_payload.get('duration', 0.0) or 0.0),
        'pitch_records': list(pitch_records),
        'raw_pitch_records': list(raw_pitch_records),
        'pitch_payloads': list(pitch_payloads),
    }
    ui._in_onepass_mode = True
    ui._onepass_playback = SimpleNamespace(
        audio=np.asarray(audio, dtype=np.float32).reshape(-1),
        sr=int(sample_rate),
        total_s=float(onepass_payload.get('duration', 0.0) or 0.0),
    )
    result = ui._run_offline_technique_analysis(show_feedback=False)
    wait_qt(app, 50)
    events = list(getattr(ui.visualizer, '_technique_events', []) or [])
    try:
        voice_debug = dict(getattr(ui.visualizer, '_last_voice_type_debug', {}) or {})
    except Exception:
        voice_debug = {}
    return result, events, voice_debug


def summarize_event(event):
    payload = to_jsonable(getattr(event, 'display_payload', {}) or {})
    snapshot = to_jsonable(getattr(event, 'feature_snapshot', {}) or {})
    return {
        'event_type': str(getattr(event, 'event_type', '') or ''),
        'display_label': str(getattr(event, 'display_label', '') or ''),
        'start_time': to_jsonable(float(getattr(event, 'start_time', 0.0) or 0.0)),
        'end_time': to_jsonable(float(getattr(event, 'end_time', 0.0) or 0.0)),
        'confidence': to_jsonable(float(getattr(event, 'confidence', 0.0) or 0.0)),
        'strength': to_jsonable(float(getattr(event, 'strength', 0.0) or 0.0)),
        'source_layer': str(getattr(event, 'source_layer', '') or ''),
        'voice_type': getattr(event, 'voice_type', None),
        'subtype': getattr(event, 'subtype', None),
        'base_voice_type': getattr(event, 'base_voice_type', None),
        'mean_pitch_hz': to_jsonable(getattr(event, 'mean_pitch_hz', None)),
        'chest_prob': to_jsonable(getattr(event, 'chest_prob', None)),
        'falsetto_prob': to_jsonable(getattr(event, 'falsetto_prob', None)),
        'mix_prob': to_jsonable(getattr(event, 'mix_prob', None)),
        'breathiness_score': to_jsonable(getattr(event, 'breathiness_score', None)),
        'mix_support_score': to_jsonable(getattr(event, 'mix_support_score', None)),
        'display_payload': payload,
        'feature_snapshot': snapshot,
    }


def print_console_summary(sample_result: dict) -> None:
    sample = sample_result['sample']
    analysis = sample_result['analysis']
    onepass = sample_result['onepass']
    summary = analysis.get('summary', {})
    counts = summary.get('counts', {}) or {}
    print(f"[sample] {sample.get('item_name') or Path(sample.get('wav_path', '')).name}")
    print(f"  group={sample.get('group_name') or '-'} binary_role={sample.get('binary_role') or '-'} path={sample.get('wav_path')}")
    print(
        f"  onepass duration={onepass.get('duration')}s segments={onepass.get('segment_count')} pitch_records={onepass.get('pitch_record_count')}"
    )
    print(f"  analysis event_count={summary.get('event_count')} counts={counts}")
    mix_events = analysis.get('mix_events', []) or []
    if mix_events:
        for event in mix_events:
            payload = event.get('display_payload', {}) or {}
            print(
                '  mix '
                f"{event.get('event_type')} {event.get('start_time')}-{event.get('end_time')} "
                f"conf={event.get('confidence')} mix_prob={event.get('mix_prob')} "
                f"thr={payload.get('mix_threshold')} support={payload.get('mix_support')}"
            )
    voice_events = analysis.get('voice_events', []) or []
    if voice_events:
        for event in voice_events:
            print(
                '  voice '
                f"{event.get('event_type')} {event.get('start_time')}-{event.get('end_time')} "
                f"conf={event.get('confidence')} chest={event.get('chest_prob')} "
                f"falsetto={event.get('falsetto_prob')} mix={event.get('mix_prob')}"
            )
    voice_debug = analysis.get('voice_debug', {}) or {}
    if voice_debug:
        print(f"  voice_debug={voice_debug}")


def build_report(samples, app, module, ui):
    report = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'samples': [],
    }
    for sample in samples:
        wav_path = str(sample.get('wav_path', '') or '').strip()
        if not wav_path:
            continue
        sample_result = {
            'sample': dict(sample),
            'onepass': {},
            'analysis': {},
            'error': '',
        }
        try:
            onepass_payload, worker = run_onepass_worker(app, module, ui, wav_path)
            audio, sample_rate = decode_audio_for_analysis(module, ui, worker, wav_path)
            result, events, voice_debug = run_integrated_analysis(app, ui, onepass_payload, audio, sample_rate)
            serialized_events = [summarize_event(event) for event in events]
            sample_result['onepass'] = {
                'duration': to_jsonable(float(onepass_payload.get('duration', 0.0) or 0.0)),
                'segment_count': len(list(onepass_payload.get('segments', []) or [])),
                'pitch_record_count': count_pitch_records(onepass_payload),
                'sample_rate': sample_rate,
            }
            sample_result['analysis'] = {
                'summary': to_jsonable(result),
                'voice_debug': to_jsonable(voice_debug),
                'events': serialized_events,
                'mix_events': [event for event in serialized_events if event.get('event_type') in {'strong_mix', 'weak_mix', 'balanced_mix'}],
                'voice_events': [event for event in serialized_events if event.get('event_type') in {'chest_voice', 'falsetto'}],
            }
        except Exception as exc:
            sample_result['error'] = str(exc)
        report['samples'].append(sample_result)
        print_console_summary(sample_result)
        if sample_result['error']:
            print(f"  error={sample_result['error']}")
    return report


def close_runtime(app, ui) -> None:
    with ExitStack() as stack:
        sink = io.StringIO()
        stack.enter_context(redirect_stdout(sink))
        stack.enter_context(redirect_stderr(sink))
        try:
            ui.close()
        except Exception:
            pass
        wait_qt(app, 20)
        try:
            app.quit()
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    groups = tuple(args.groups or DEFAULT_GROUPS)
    samples = normalize_explicit_samples(args.wav)

    if not samples:
        manifest_path = Path(args.manifest).resolve()
        if not manifest_path.exists():
            print(f'manifest not found: {manifest_path}', file=sys.stderr)
            return 2
        samples = pick_manifest_samples(
            manifest_path,
            groups,
            max(1, int(args.per_group)),
            binary_roles=args.binary_roles,
        )

    if not samples:
        print('no samples selected', file=sys.stderr)
        return 2

    app = None
    ui = None
    try:
        app, module, ui, init_log = load_runtime(show_init_log=bool(args.show_init_log))
        report = build_report(samples, app, module, ui)
        report['init_log'] = init_log if args.show_init_log else ''
        report['sample_count'] = len(report['samples'])
        report['error_count'] = sum(1 for item in report['samples'] if item.get('error'))
        if args.output:
            output_path = Path(args.output).resolve()
            output_path.write_text(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'json_report={output_path}')
        print(f"completed samples={report['sample_count']} errors={report['error_count']}")
        return 1 if report['error_count'] else 0
    finally:
        if app is not None and ui is not None:
            close_runtime(app, ui)


if __name__ == '__main__':
    raise SystemExit(main())