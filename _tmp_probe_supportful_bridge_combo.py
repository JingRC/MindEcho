import json
from pathlib import Path
from types import MethodType
from typing import Any, Dict, List, Sequence

import debug_mix_role_regression as reg
import ml_dl_models.gtsinger_multitech.lightweight_training.diagnose_mix_rule_selected_samples as diag


TARGET_GROUP_ITEMS = {
    'validation_fn_systematic': [
        'English#EN-Tenor-1#Breathy#Someone Like You#Breathy_Group#0004',
        'English#EN-Tenor-1#Breathy#Stay#Breathy_Group#0003',
    ],
    'validation_fp_systematic': [
        'English#EN-Tenor-1#Mixed_Voice_and_Falsetto#Look What You Make Me Do#Control_Group#0001',
        'English#EN-Tenor-1#Pharyngeal#Million Reasons#Pharyngeal_Group#0003',
        'English#EN-Tenor-1#Pharyngeal#Stay#Pharyngeal_Group#0002',
        'English#EN-Tenor-1#Vibrato#All I Ask#Vibrato_Group#0001',
        'English#EN-Tenor-1#Mixed_Voice_and_Falsetto#Blank Space#Control_Group#0000',
    ],
}

ORIGINAL_SUPPORTFUL_SPEC = {
    'mean_pitch_hz_min': 315.0,
    'mean_pitch_hz_max': 370.0,
    'chest_prob_min': 0.190,
    'chest_prob_max': 0.220,
    'falsetto_prob_min': 0.780,
    'falsetto_prob_max': 0.810,
}

RELAXED_STAY_SUPPORTFUL_SPEC = {
    'mean_pitch_hz_min': 305.0,
    'mean_pitch_hz_max': 370.0,
    'chest_prob_min': 0.190,
    'chest_prob_max': 0.226,
    'falsetto_prob_min': 0.774,
    'falsetto_prob_max': 0.810,
}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def load_target_rows(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    groups = {group['name']: group for group in config.get('groups', [])}
    for group_name, item_names in TARGET_GROUP_ITEMS.items():
        group = groups[group_name]
        manifest_path = Path(group['manifest']).resolve()
        selected_rows = diag.load_selected_rows(manifest_path, item_names)
        for row in selected_rows:
            enriched = dict(row)
            enriched['_probe_group'] = group_name
            rows.append(enriched)
    return rows


def patch_visualizer_for_supportful_combo(visualizer: Any, module: Any, spec: Dict[str, float], source_suffix: str) -> None:
    original_build = visualizer._build_rule_based_mix_events
    original_meaningful = visualizer._technique_event_meaningful

    def supportful_bridge(self: Any, frames: List[Any], voice_events: List[Any]) -> List[Any]:
        mix_events = list(original_build(frames, voice_events) or [])
        for voice_event in list(voice_events or []):
            if not isinstance(voice_event, module.VoiceTypeEvent):
                continue
            snapshot = dict(getattr(voice_event, 'feature_snapshot', {}) or {})
            duration = float(getattr(voice_event, 'duration', 0.0) or 0.0)
            confidence = float(getattr(voice_event, 'confidence', 0.0) or 0.0)
            strength = float(getattr(voice_event, 'strength', 0.0) or 0.0)
            probability_margin = float(getattr(voice_event, 'probability_margin', 0.0) or 0.0)
            chest_prob = float(getattr(voice_event, 'chest_prob', 0.0) or 0.0)
            falsetto_prob = float(getattr(voice_event, 'falsetto_prob', 0.0) or 0.0)
            voiced_ratio = float(getattr(voice_event, 'voiced_ratio', 0.0) or 0.0)
            mean_pitch_hz = float(getattr(voice_event, 'mean_pitch_hz', 0.0) or 0.0)
            mean_rms = float(snapshot.get('mean_rms', 0.0) or 0.0)
            mean_zcr = float(snapshot.get('mean_zcr', 0.0) or 0.0)
            stable_ratio = float(snapshot.get('stable_ratio', 0.0) or 0.0)
            mean_breath_score = float(snapshot.get('mean_breath_score', 0.0) or 0.0)
            breath_hint_ratio = float(snapshot.get('breath_hint_ratio', 0.0) or 0.0)
            learned_mix_prob = float(snapshot.get('mix_prob', getattr(voice_event, 'mix_prob', 0.0) or 0.0) or 0.0)
            learned_mix_threshold = float(snapshot.get('mix_threshold', 0.45) or 0.45)
            learned_mix_margin = (learned_mix_prob - learned_mix_threshold) if learned_mix_prob > 0.0 else 0.0

            heuristic_mix_support = clamp(1.0 - (probability_margin / 0.40))
            learned_mix_support = clamp((learned_mix_prob - (learned_mix_threshold - 0.12)) / 0.42) if learned_mix_prob > 0.0 else 0.0
            mix_support = clamp(0.32 * heuristic_mix_support + 0.68 * learned_mix_support) if learned_mix_prob > 0.0 else heuristic_mix_support
            pitch_support = clamp((mean_pitch_hz - 210.0) / 230.0)
            stable_support = clamp((stable_ratio - 0.08) / 0.24)
            head_bias = clamp((falsetto_prob - chest_prob + 0.18) / 0.50)

            released_supportful = (
                learned_mix_prob > 0.0
                and learned_mix_prob < learned_mix_threshold
                and head_bias >= 0.99
                and learned_mix_prob >= 0.520
                and learned_mix_prob <= 0.560
                and learned_mix_margin >= -0.130
                and learned_mix_margin <= -0.080
                and mean_pitch_hz >= float(spec['mean_pitch_hz_min'])
                and mean_pitch_hz <= float(spec['mean_pitch_hz_max'])
                and chest_prob >= float(spec['chest_prob_min'])
                and chest_prob <= float(spec['chest_prob_max'])
                and falsetto_prob >= float(spec['falsetto_prob_min'])
                and falsetto_prob <= float(spec['falsetto_prob_max'])
                and mean_rms >= 0.045
                and mean_rms <= 0.065
                and duration >= 5.0
                and duration <= 8.5
                and learned_mix_support >= 0.010
                and learned_mix_support <= 0.080
                and mix_support >= 0.010
                and mix_support <= 0.050
                and stable_ratio >= 0.99
                and voiced_ratio >= 0.99
            )
            if not released_supportful:
                continue

            overlaps_existing = False
            voice_start = float(getattr(voice_event, 'start_time', 0.0) or 0.0)
            voice_end = float(getattr(voice_event, 'end_time', 0.0) or 0.0)
            for mix_event in list(mix_events or []):
                mix_start = float(getattr(mix_event, 'start_time', 0.0) or 0.0)
                mix_end = float(getattr(mix_event, 'end_time', 0.0) or 0.0)
                overlap = min(voice_end, mix_end) - max(voice_start, mix_start)
                if overlap > 0.0:
                    overlaps_existing = True
                    break
            if overlaps_existing:
                continue

            weak_mix_support = max(mix_support, learned_mix_support, 0.010)
            subtype_conf = clamp(
                0.34 * weak_mix_support
                + 0.24 * head_bias
                + 0.16 * pitch_support
                + 0.14 * stable_support
                + 0.12 * confidence
            )
            mix_event = module.MixVoiceEvent(
                event_type='weak_mix',
                start_time=voice_start,
                end_time=voice_end,
                confidence=max(0.46, min(0.92, subtype_conf)),
                strength=max(0.42, min(0.90, 0.55 * subtype_conf + 0.20 * strength + 0.25 * weak_mix_support)),
                center_time=float(getattr(voice_event, 'center_time', 0.0) or 0.0),
                duration=duration,
                source_layer=f'voice_mix_rule_v3_{source_suffix}',
                display_label='弱混声',
                display_color='#8E97F5',
                feature_snapshot={
                    'mean_pitch_hz': mean_pitch_hz,
                    'chest_prob': chest_prob,
                    'falsetto_prob': falsetto_prob,
                    'mix_prob': learned_mix_prob,
                    'mix_threshold': learned_mix_threshold,
                    'probability_margin': probability_margin,
                    'mean_rms': mean_rms,
                    'mean_zcr': mean_zcr,
                    'stable_ratio': stable_ratio,
                    'voiced_ratio': voiced_ratio,
                    'mean_breath_score': mean_breath_score,
                    'breath_hint_ratio': breath_hint_ratio,
                    'mix_support': weak_mix_support,
                    'learned_mix_margin': learned_mix_margin,
                    'heuristic_mix_support': heuristic_mix_support,
                    'learned_mix_support': learned_mix_support,
                    'head_bias': head_bias,
                    'weak_mix_support_floor': 0.010,
                    'weak_mix_pitch_floor': 230.0,
                    'released_supportful_midhigh_nearthreshold_mix': True,
                    'supportful_probe_variant': source_suffix,
                },
                display_payload={
                    'rule_version': f'mix_rule_v3_{source_suffix}',
                    'derived_from_voice_type': str(getattr(voice_event, 'event_type', '') or ''),
                    'base_voice_type': str(getattr(voice_event, 'voice_type', '') or ''),
                    'mix_prob': learned_mix_prob,
                    'mix_threshold': learned_mix_threshold,
                    'mix_support': weak_mix_support,
                    'released_supportful_midhigh_nearthreshold_mix': True,
                    'supportful_probe_variant': source_suffix,
                },
                subtype='weak_mix',
                base_voice_type=str(getattr(voice_event, 'voice_type', '') or ''),
                mean_pitch_hz=mean_pitch_hz,
                chest_prob=chest_prob,
                falsetto_prob=falsetto_prob,
                mix_prob=learned_mix_prob,
                breathiness_score=0.0,
                mix_support_score=weak_mix_support,
            )
            mix_events.append(mix_event)
        return mix_events

    def meaningful_with_mix_alignment(self: Any, event: Any, cfg: Any) -> bool:
        event_type = str(getattr(event, 'event_type', '') or '')
        if event_type in ('strong_mix', 'weak_mix', 'balanced_mix'):
            duration = max(0.0, float(getattr(event, 'duration', 0.0) or 0.0))
            confidence = max(0.0, float(getattr(event, 'confidence', 0.0) or 0.0))
            return duration >= 0.10 and confidence >= 0.46
        return original_meaningful(event, cfg)

    visualizer._build_rule_based_mix_events = MethodType(supportful_bridge, visualizer)
    visualizer._technique_event_meaningful = MethodType(meaningful_with_mix_alignment, visualizer)


def run_rows(rows: Sequence[Dict[str, Any]], checkpoint: Path, *, enable_combo: bool, spec: Dict[str, float] | None = None, source_suffix: str = '') -> List[Dict[str, Any]]:
    app, module, ui, _ = diag.dbg.load_runtime(False)
    module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint,)
    diag.reset_mix_runtime_cache(ui)
    if enable_combo:
        patch_visualizer_for_supportful_combo(ui.visualizer, module, dict(spec or ORIGINAL_SUPPORTFUL_SPEC), source_suffix or 'supportful_probe')
    reports: List[Dict[str, Any]] = []
    try:
        for row in list(rows or []):
            diag.reset_mix_runtime_cache(ui)
            item = reg.analyze_sample(app, module, ui, row)
            summary = reg.summarize_sample(item)
            analysis = dict(item.get('analysis', {}) or {})
            mix_events = list(analysis.get('mix_events', []) or [])
            voice_events = list(analysis.get('voice_events', []) or [])
            bridge_features: Dict[str, Any] = {}
            if voice_events:
                best_voice = voice_events[0]
                snapshot = dict(best_voice.get('feature_snapshot', {}) or {})
                duration = float(best_voice.get('end_time', 0.0) or 0.0) - float(best_voice.get('start_time', 0.0) or 0.0)
                chest_prob = float(best_voice.get('chest_prob', 0.0) or 0.0)
                falsetto_prob = float(best_voice.get('falsetto_prob', 0.0) or 0.0)
                probability_margin = float(best_voice.get('display_payload', {}).get('probability_margin', best_voice.get('probability_margin', abs(falsetto_prob - chest_prob))) or abs(falsetto_prob - chest_prob))
                voiced_ratio = float(snapshot.get('voiced_ratio', 0.0) or 0.0)
                stable_ratio = float(snapshot.get('stable_ratio', 0.0) or 0.0)
                mean_pitch_hz = float(best_voice.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)) or 0.0)
                mean_rms = float(snapshot.get('mean_rms', 0.0) or 0.0)
                learned_mix_prob = float(snapshot.get('mix_prob', best_voice.get('mix_prob', 0.0)) or 0.0)
                learned_mix_threshold = float(snapshot.get('mix_threshold', 0.45) or 0.45)
                learned_mix_margin = (learned_mix_prob - learned_mix_threshold) if learned_mix_prob > 0.0 else 0.0
                heuristic_mix_support = clamp(1.0 - (probability_margin / 0.40))
                learned_mix_support = clamp((learned_mix_prob - (learned_mix_threshold - 0.12)) / 0.42) if learned_mix_prob > 0.0 else 0.0
                mix_support = clamp(0.32 * heuristic_mix_support + 0.68 * learned_mix_support) if learned_mix_prob > 0.0 else heuristic_mix_support
                head_bias = clamp((falsetto_prob - chest_prob + 0.18) / 0.50)
                bridge_checks = {
                    'head_bias': head_bias >= 0.99,
                    'mix_prob': 0.520 <= learned_mix_prob <= 0.560,
                    'mix_margin': -0.130 <= learned_mix_margin <= -0.080,
                    'mean_pitch_hz': 315.0 <= mean_pitch_hz <= 370.0,
                    'duration': 5.0 <= duration <= 8.5,
                    'mean_rms': 0.045 <= mean_rms <= 0.065,
                    'learned_mix_support': 0.010 <= learned_mix_support <= 0.080,
                    'mix_support': 0.010 <= mix_support <= 0.050,
                    'chest_prob': 0.190 <= chest_prob <= 0.220,
                    'falsetto_prob': 0.780 <= falsetto_prob <= 0.810,
                    'stable_ratio': stable_ratio >= 0.99,
                    'voiced_ratio': voiced_ratio >= 0.99,
                }
                bridge_features = {
                    'duration': duration,
                    'chest_prob': chest_prob,
                    'falsetto_prob': falsetto_prob,
                    'probability_margin': probability_margin,
                    'voiced_ratio': voiced_ratio,
                    'stable_ratio': stable_ratio,
                    'mean_pitch_hz': mean_pitch_hz,
                    'mean_rms': mean_rms,
                    'learned_mix_prob': learned_mix_prob,
                    'learned_mix_threshold': learned_mix_threshold,
                    'learned_mix_margin': learned_mix_margin,
                    'heuristic_mix_support': heuristic_mix_support,
                    'learned_mix_support': learned_mix_support,
                    'mix_support': mix_support,
                    'head_bias': head_bias,
                    'bridge_checks': bridge_checks,
                    'bridge_match': all(bridge_checks.values()),
                }
            reports.append({
                'probe_group': str(row.get('_probe_group', '') or ''),
                'item_name': str(summary.get('item_name', '') or ''),
                'song_name': str(summary.get('song_name', '') or ''),
                'binary_role': str(summary.get('binary_role', '') or ''),
                'outcome': str(summary.get('outcome', '') or ''),
                'miss_reason': str(summary.get('miss_reason', '') or ''),
                'mix_event_count': int(summary.get('mix_event_count', 0) or 0),
                'weak_mix_count': int(summary.get('weak_mix_count', 0) or 0),
                'bridge_features': bridge_features,
                'mix_events': [
                    {
                        'event_type': str(event.get('event_type', '') or ''),
                        'source_layer': str(event.get('source_layer', '') or ''),
                        'start_time': event.get('start_time'),
                        'end_time': event.get('end_time'),
                        'confidence': event.get('confidence'),
                        'mix_prob': event.get('mix_prob'),
                        'mix_support': (event.get('display_payload', {}) or {}).get('mix_support'),
                    }
                    for event in mix_events
                ],
            })
        return reports
    finally:
        app.quit()


def main() -> int:
    config = json.loads(Path('regression_tests/mix_runtime_systematic_cluster_config.json').read_text(encoding='utf-8'))
    checkpoint = diag.resolve_checkpoint(config['artifact_dir'])
    rows = load_target_rows(config)
    baseline = run_rows(rows, checkpoint, enable_combo=False)
    combo = run_rows(rows, checkpoint, enable_combo=True, spec=ORIGINAL_SUPPORTFUL_SPEC, source_suffix='supportful_probe')
    relaxed_combo = run_rows(rows, checkpoint, enable_combo=True, spec=RELAXED_STAY_SUPPORTFUL_SPEC, source_suffix='supportful_stay_relaxed_probe')
    print(json.dumps({
        'checkpoint': str(checkpoint),
        'baseline': baseline,
        'supportful_combo': combo,
        'supportful_stay_relaxed_combo': relaxed_combo,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())