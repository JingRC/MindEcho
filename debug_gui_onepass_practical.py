import argparse
import io
import json
import math
import os
import sys
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import MethodType

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    import matplotlib

    matplotlib.use('Agg')
except Exception:
    pass


ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
    parser = argparse.ArgumentParser(description='Run practical GUI one-pass validation through the real one-pass entry.')
    parser.add_argument('--wav', action='append', default=[], help='Explicit wav path to analyze. May be passed multiple times.')
    parser.add_argument('--output', default='', help='Optional JSON file path for the full report.')
    parser.add_argument('--show-init-log', action='store_true', help='Print captured interface initialization logs.')
    parser.add_argument('--prefer-mix-cpu', action=argparse.BooleanOptionalAction, default=None, help='Prefer CPU for mix external inference before trying GPU. Omit to keep the GUI default.')
    parser.add_argument('--prefer-voice-cpu', action=argparse.BooleanOptionalAction, default=None, help='Prefer CPU for chest/falsetto external inference before trying GPU. Omit to keep the GUI default.')
    parser.add_argument('--force-external-mix', action='store_true', help='Bypass local mix torch bundle resolution and force external mix inference.')
    parser.add_argument('--force-external-voice', action='store_true', help='Bypass local chest/falsetto torch bundle resolution and force external voice inference.')
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


def count_pitch_records(onepass_payload: dict) -> int:
    total = 0
    for segment in list(onepass_payload.get('segments', []) or []):
        try:
            total += min(len(segment[0] or []), len(segment[1] or []))
        except Exception:
            continue
    return int(total)


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


def install_messagebox_stubs(module) -> None:
    message_log = []
    box = getattr(module, 'QMessageBox', None)
    if box is None:
        return

    def _stub(name):
        def _inner(*args, **kwargs):
            title = ''
            text = ''
            if len(args) >= 2:
                title = str(args[1] or '')
            if len(args) >= 3:
                text = str(args[2] or '')
            elif 'text' in kwargs:
                text = str(kwargs.get('text') or '')
            message_log.append({'kind': name, 'title': title, 'text': text})
            try:
                return box.StandardButton.Ok
            except Exception:
                return 0

        return staticmethod(_inner)

    try:
        box.information = _stub('information')
        box.warning = _stub('warning')
        box.critical = _stub('critical')
        box.question = _stub('question')
    except Exception:
        pass
    setattr(module, '_practical_probe_message_log', message_log)


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
        install_messagebox_stubs(module)
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


def install_backend_probes(ui) -> None:
    viz = getattr(ui, 'visualizer', None)
    if viz is None:
        raise RuntimeError('visualizer unavailable')

    viz._probe_mix_backend_log = []
    viz._probe_voice_backend_log = []

    original_mix_local = viz._predict_mix_binary_local
    original_mix_external = viz._run_mix_binary_external_inference
    original_voice_external = viz._run_chest_falsetto_external_inference
    original_chest_bundle = viz._get_chest_falsetto_model_bundle
    original_mix_bundle = viz._get_mix_binary_model_bundle
    original_breath_builder = viz._build_offline_gap_breath_events
    original_vibrato_builder = viz._build_offline_vibrato_events
    original_voice_builder = viz._build_offline_chest_falsetto_events
    original_mix_rule_builder = viz._build_rule_based_mix_events

    def chest_bundle_wrapper(self):
        if bool(getattr(self, '_probe_force_external_voice', False)):
            print('[probe] chest bundle forced external', flush=True)
            self._last_chest_falsetto_model_error = 'forced_external_probe'
            return None
        print('[probe] chest bundle start', flush=True)
        start_ts = time.perf_counter()
        result = original_chest_bundle()
        elapsed_s = time.perf_counter() - start_ts
        payload = {
            'has_bundle': isinstance(result, dict),
            'backend': str(result.get('backend', '') or '') if isinstance(result, dict) else '',
            'error': str(getattr(self, '_last_chest_falsetto_model_error', '') or ''),
        }
        print(f"[probe] chest bundle done elapsed={elapsed_s:.3f}s payload={payload}", flush=True)
        return result

    def mix_bundle_wrapper(self):
        if bool(getattr(self, '_probe_force_external_mix', False)):
            print('[probe] mix bundle forced external', flush=True)
            self._last_mix_binary_model_error = 'forced_external_probe'
            return None
        print('[probe] mix bundle start', flush=True)
        start_ts = time.perf_counter()
        result = original_mix_bundle()
        elapsed_s = time.perf_counter() - start_ts
        payload = {
            'has_bundle': isinstance(result, dict),
            'force_external': bool(result.get('force_external', False)) if isinstance(result, dict) else False,
            'backbone_name': str(result.get('backbone_name', '') or '') if isinstance(result, dict) else '',
            'error': str(getattr(self, '_last_mix_binary_model_error', '') or ''),
        }
        print(f"[probe] mix bundle done elapsed={elapsed_s:.3f}s payload={payload}", flush=True)
        return result

    def mix_local_wrapper(self, audio_windows, bundle):
        print(f"[probe] mix local start windows={len(list(audio_windows or []))}", flush=True)
        start_ts = time.perf_counter()
        result = original_mix_local(audio_windows, bundle)
        elapsed_s = time.perf_counter() - start_ts
        self._probe_mix_backend_log.append({
            'backend': 'local_torch',
            'window_count': len(list(audio_windows or [])),
            'result_count': len(result) if isinstance(result, list) else None,
            'elapsed_s': to_jsonable(elapsed_s),
            'error': str(getattr(self, '_last_mix_binary_model_error', '') or ''),
        })
        print(
            f"[probe] mix local done elapsed={elapsed_s:.3f}s results={len(result) if isinstance(result, list) else 'None'} error={str(getattr(self, '_last_mix_binary_model_error', '') or '')}",
            flush=True,
        )
        return result

    def mix_external_wrapper(self, audio_windows):
        print(f"[probe] mix external start windows={len(list(audio_windows or []))}", flush=True)
        start_ts = time.perf_counter()
        result = original_mix_external(audio_windows)
        elapsed_s = time.perf_counter() - start_ts
        self._probe_mix_backend_log.append({
            'backend': 'external_python',
            'window_count': len(list(audio_windows or [])),
            'result_count': len(result) if isinstance(result, list) else None,
            'elapsed_s': to_jsonable(elapsed_s),
            'prefer_cpu': bool(getattr(self, '_prefer_mix_binary_external_cpu', False)),
            'error': str(getattr(self, '_last_mix_binary_model_error', '') or ''),
        })
        print(
            f"[probe] mix external done elapsed={elapsed_s:.3f}s results={len(result) if isinstance(result, list) else 'None'} prefer_cpu={bool(getattr(self, '_prefer_mix_binary_external_cpu', False))} error={str(getattr(self, '_last_mix_binary_model_error', '') or '')}",
            flush=True,
        )
        return result

    def voice_external_wrapper(self, audio_windows):
        print(f"[probe] voice external start windows={len(list(audio_windows or []))}", flush=True)
        start_ts = time.perf_counter()
        result = original_voice_external(audio_windows)
        elapsed_s = time.perf_counter() - start_ts
        self._probe_voice_backend_log.append({
            'backend': 'external_python',
            'window_count': len(list(audio_windows or [])),
            'result_count': len(result) if isinstance(result, list) else None,
            'elapsed_s': to_jsonable(elapsed_s),
            'prefer_cpu': bool(getattr(self, '_prefer_chest_falsetto_external_cpu', False)),
            'error': str(getattr(self, '_last_chest_falsetto_model_error', '') or ''),
        })
        print(
            f"[probe] voice external done elapsed={elapsed_s:.3f}s results={len(result) if isinstance(result, list) else 'None'} prefer_cpu={bool(getattr(self, '_prefer_chest_falsetto_external_cpu', False))} error={str(getattr(self, '_last_chest_falsetto_model_error', '') or '')}",
            flush=True,
        )
        return result

    def _wrap_stage(name, func):
        def _inner(self, *args, **kwargs):
            print(f'[probe] {name} start', flush=True)
            stage_start_ts = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_s = time.perf_counter() - stage_start_ts
            try:
                result_count = len(result)
            except Exception:
                result_count = 'na'
            print(f'[probe] {name} done elapsed={elapsed_s:.3f}s result_count={result_count}', flush=True)
            return result

        return _inner

    viz._predict_mix_binary_local = MethodType(mix_local_wrapper, viz)
    viz._run_mix_binary_external_inference = MethodType(mix_external_wrapper, viz)
    viz._run_chest_falsetto_external_inference = MethodType(voice_external_wrapper, viz)
    viz._get_chest_falsetto_model_bundle = MethodType(chest_bundle_wrapper, viz)
    viz._get_mix_binary_model_bundle = MethodType(mix_bundle_wrapper, viz)
    viz._build_offline_gap_breath_events = MethodType(_wrap_stage('breath_builder', original_breath_builder), viz)
    viz._build_offline_vibrato_events = MethodType(_wrap_stage('vibrato_builder', original_vibrato_builder), viz)
    viz._build_offline_chest_falsetto_events = MethodType(_wrap_stage('voice_builder', original_voice_builder), viz)
    viz._build_rule_based_mix_events = MethodType(_wrap_stage('mix_rule_builder', original_mix_rule_builder), viz)


def reset_probe_logs(ui) -> None:
    viz = getattr(ui, 'visualizer', None)
    if viz is None:
        return
    viz._probe_mix_backend_log = []
    viz._probe_voice_backend_log = []


def configure_backend_preferences(
    ui,
    *,
    prefer_mix_cpu,
    prefer_voice_cpu,
    force_external_mix: bool,
    force_external_voice: bool,
) -> None:
    viz = getattr(ui, 'visualizer', None)
    if viz is None:
        return
    if prefer_mix_cpu is not None:
        setattr(viz, '_prefer_mix_binary_external_cpu', bool(prefer_mix_cpu))
    if prefer_voice_cpu is not None:
        setattr(viz, '_prefer_chest_falsetto_external_cpu', bool(prefer_voice_cpu))
    setattr(viz, '_probe_force_external_mix', bool(force_external_mix))
    setattr(viz, '_probe_force_external_voice', bool(force_external_voice))


def exit_onepass_mode(ui) -> None:
    try:
        if hasattr(ui, '_exit_onepass_mode'):
            ui._exit_onepass_mode()
    except Exception:
        pass


def analyze_sample(app, module, ui, wav_path: str) -> dict:
    sample_result = {
        'wav_path': wav_path,
        'onepass': {},
        'analysis': {},
        'messages': [],
        'error': '',
    }
    reset_probe_logs(ui)
    viz = getattr(ui, 'visualizer', None)
    if viz is None:
        sample_result['error'] = 'visualizer unavailable'
        return sample_result
    try:
        setattr(module, '_practical_probe_message_log', [])
    except Exception:
        pass
    try:
        print(f'[probe] sample start path={wav_path}', flush=True)
        start_ts = time.perf_counter()
        ui._start_offline_onepass(wav_path)
        wait_qt(app, 50)
        onepass_elapsed_s = time.perf_counter() - start_ts
        print(f'[probe] onepass done elapsed={onepass_elapsed_s:.3f}s', flush=True)

        onepass_payload = dict(getattr(ui, '_onepass_analysis_payload', {}) or {})
        onepass_duration = float(onepass_payload.get('duration', 0.0) or 0.0)
        segments = list(onepass_payload.get('segments', []) or [])
        pitch_record_count = count_pitch_records(onepass_payload)

        print('[probe] resolve payload start', flush=True)
        resolve_start_ts = time.perf_counter()
        resolved = ui._resolve_technique_analysis_payload()
        resolve_elapsed_s = time.perf_counter() - resolve_start_ts
        print(
            f"[probe] resolve payload done elapsed={resolve_elapsed_s:.3f}s ok={bool(resolved.get('ok', False))} frames={len(list(resolved.get('frames', []) or []))}",
            flush=True,
        )
        if not bool(resolved.get('ok', False)):
            sample_result['error'] = str(resolved.get('reason', '') or 'analysis payload unavailable')
            return sample_result

        frames = list(resolved.get('frames', []) or [])
        audio_samples = resolved.get('audio_samples')
        sample_rate = resolved.get('sample_rate')

        analysis_start_ts = time.perf_counter()
        print('[probe] analysis start', flush=True)
        analysis_result = viz.analyze_technique_frames(frames, audio_samples=audio_samples, sample_rate=sample_rate)
        wait_qt(app, 50)
        analysis_elapsed_s = time.perf_counter() - analysis_start_ts
        print(f'[probe] analysis done elapsed={analysis_elapsed_s:.3f}s', flush=True)

        events = list(getattr(viz, '_technique_events', []) or [])
        try:
            voice_debug = dict(getattr(viz, '_last_voice_type_debug', {}) or {})
        except Exception:
            voice_debug = {}
        mix_bundle = viz._get_mix_binary_model_bundle()
        mix_model = {}
        if isinstance(mix_bundle, dict):
            mix_model = {
                'path': str(mix_bundle.get('path', '') or ''),
                'artifact_name': str(mix_bundle.get('artifact_name', '') or ''),
                'backbone_name': str(mix_bundle.get('backbone_name', '') or ''),
                'force_external': bool(mix_bundle.get('force_external', False)),
                'threshold': to_jsonable(float(mix_bundle.get('threshold', 0.0) or 0.0)),
            }

        sample_result['onepass'] = {
            'elapsed_s': to_jsonable(onepass_elapsed_s),
            'duration_s': to_jsonable(onepass_duration),
            'segment_count': len(segments),
            'pitch_record_count': pitch_record_count,
            'has_playback': bool(getattr(ui, '_onepass_playback', None) is not None),
            'has_panel': bool(getattr(ui, '_onepass_panel', None) is not None),
        }
        sample_result['analysis'] = {
            'elapsed_s': to_jsonable(analysis_elapsed_s),
            'total_elapsed_s': to_jsonable(onepass_elapsed_s + analysis_elapsed_s),
            'summary': to_jsonable(analysis_result),
            'voice_debug': to_jsonable(voice_debug),
            'mix_model': to_jsonable(mix_model),
            'mix_backend_log': to_jsonable(list(getattr(viz, '_probe_mix_backend_log', []) or [])),
            'voice_backend_log': to_jsonable(list(getattr(viz, '_probe_voice_backend_log', []) or [])),
            'last_mix_model_error': str(getattr(viz, '_last_mix_binary_model_error', '') or ''),
            'last_chest_falsetto_model_error': str(getattr(viz, '_last_chest_falsetto_model_error', '') or ''),
            'prefer_mix_external_cpu': bool(getattr(viz, '_prefer_mix_binary_external_cpu', False)),
            'prefer_voice_external_cpu': bool(getattr(viz, '_prefer_chest_falsetto_external_cpu', False)),
            'events': [summarize_event(event) for event in events],
        }
        sample_result['messages'] = to_jsonable(list(getattr(module, '_practical_probe_message_log', []) or []))
    except Exception as exc:
        sample_result['error'] = str(exc)
        print(f"[probe] sample error {type(exc).__name__}: {exc}", flush=True)
    finally:
        exit_onepass_mode(ui)
        wait_qt(app, 50)
    return sample_result


def print_console_summary(sample_result: dict) -> None:
    wav_path = str(sample_result.get('wav_path', '') or '')
    analysis = sample_result.get('analysis', {}) or {}
    onepass = sample_result.get('onepass', {}) or {}
    summary = analysis.get('summary', {}) or {}
    counts = summary.get('counts', {}) or {}
    voice_debug = analysis.get('voice_debug', {}) or {}
    mix_model = analysis.get('mix_model', {}) or {}
    mix_backend_log = analysis.get('mix_backend_log', []) or []
    voice_backend_log = analysis.get('voice_backend_log', []) or []
    print(f'[sample] {Path(wav_path).name}')
    print(f'  path={wav_path}')
    print(
        '  onepass '
        f"elapsed={onepass.get('elapsed_s')}s duration={onepass.get('duration_s')}s "
        f"segments={onepass.get('segment_count')} pitch_records={onepass.get('pitch_record_count')}"
    )
    print(
        '  analysis '
        f"elapsed={analysis.get('elapsed_s')}s total={analysis.get('total_elapsed_s')}s "
        f"event_count={summary.get('event_count')} counts={counts}"
    )
    print(
        '  backend '
        f"voice={voice_debug.get('backend', 'local_or_unknown')} "
        f"mix_force_external={mix_model.get('force_external')} "
        f"mix_backend_calls={mix_backend_log} voice_backend_calls={voice_backend_log}"
    )
    print(
        '  errors '
        f"mix={analysis.get('last_mix_model_error')} chest_falsetto={analysis.get('last_chest_falsetto_model_error')}"
    )
    if sample_result.get('messages'):
        print(f"  messages={sample_result.get('messages')}")
    if sample_result.get('error'):
        print(f"  error={sample_result.get('error')}")


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
    samples = [str(Path(item).resolve()) for item in list(args.wav or []) if str(item or '').strip()]
    if not samples:
        print('no samples selected', file=sys.stderr)
        return 2

    app = None
    ui = None
    try:
        app, module, ui, init_log = load_runtime(show_init_log=bool(args.show_init_log))
        install_backend_probes(ui)
        configure_backend_preferences(
            ui,
            prefer_mix_cpu=args.prefer_mix_cpu,
            prefer_voice_cpu=args.prefer_voice_cpu,
            force_external_mix=bool(args.force_external_mix),
            force_external_voice=bool(args.force_external_voice),
        )
        report = {
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'samples': [],
            'init_log': init_log if args.show_init_log else '',
            'requested_backend_preferences': {
                'prefer_mix_cpu': to_jsonable(args.prefer_mix_cpu),
                'prefer_voice_cpu': to_jsonable(args.prefer_voice_cpu),
                'force_external_mix': bool(args.force_external_mix),
                'force_external_voice': bool(args.force_external_voice),
            },
        }
        for wav_path in samples:
            sample_result = analyze_sample(app, module, ui, wav_path)
            report['samples'].append(sample_result)
            print_console_summary(sample_result)
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