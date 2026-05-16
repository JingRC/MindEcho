import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
	 sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
	 sys.path.insert(0, str(SRC))

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description='Replay selected samples through the frozen mix runtime and diagnose mix-rule branch conditions.')
	parser.add_argument('--manifest', required=True, help='Manifest containing the target item_name rows.')
	parser.add_argument('--artifact', action='append', required=True, help='Artifact directory or checkpoint to evaluate. May be passed multiple times.')
	parser.add_argument('--item-name', action='append', required=True, help='item_name to diagnose. May be passed multiple times.')
	parser.add_argument('--output', required=True, help='Path to write the diagnosis JSON report.')
	parser.add_argument('--fresh-runtime-per-sample', action='store_true', help='Load a fresh runtime for each sample to avoid grouped replay state drift.')
	parser.add_argument('--fresh-process-per-sample', action='store_true', help='Spawn a fresh diagnose subprocess per sample for the most isolated regression replay.')
	return parser.parse_args()


def load_selected_rows(manifest_path: Path, item_names: Sequence[str]) -> List[Dict[str, Any]]:
	requested = [str(item or '').strip() for item in list(item_names or []) if str(item or '').strip()]
	if not requested:
		return []
	row_map: Dict[str, Dict[str, Any]] = {}
	with manifest_path.open('r', encoding='utf-8-sig', newline='') as handle:
		for row in csv.DictReader(handle):
			item_name = str(row.get('item_name', '') or '').strip()
			if item_name:
				row_map[item_name] = dict(row)
	missing = [item for item in requested if item not in row_map]
	if missing:
		raise KeyError(f'missing item_name rows in manifest: {missing}')
	return [dict(row_map[item]) for item in requested]


def resolve_checkpoint(path_text: str) -> Path:
	raw_path = Path(str(path_text or '').strip())
	if not raw_path.exists():
		raise FileNotFoundError(f'artifact path not found: {raw_path}')
	if raw_path.is_dir():
		checkpoint_path = raw_path / 'best_mix_binary_squeezenet.pt'
		if not checkpoint_path.exists():
			raise FileNotFoundError(f'checkpoint not found in artifact directory: {checkpoint_path}')
		return checkpoint_path.resolve()
	return raw_path.resolve()


def reset_mix_runtime_cache(ui: Any) -> None:
	for attr, value in (
		('_mix_binary_model_bundle', None),
		('_last_mix_binary_model_error', ''),
		('_prefer_mix_binary_external_cpu', False),
		('_external_mix_gpu_retry_blocked', False),
	):
		try:
			setattr(ui.visualizer, attr, value)
		except Exception:
			pass


def diagnose_row_with_fresh_runtime(checkpoint_path: Path, row: Dict[str, Any]) -> Dict[str, Any]:
	app = None
	try:
		app, module, ui, _ = dbg.load_runtime(False)
		module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint_path,)
		reset_mix_runtime_cache(ui)
		item = reg.analyze_sample(app, module, ui, row)
		return diagnose_sample(item)
	finally:
		if app is not None:
			try:
				app.quit()
			except Exception:
				pass


def diagnose_row_with_fresh_subprocess(manifest_path: Path, checkpoint_path: Path, row: Dict[str, Any]) -> Dict[str, Any]:
	item_name = str(row.get('item_name', '') or '').strip()
	if not item_name:
		raise ValueError('missing item_name for fresh subprocess diagnose')
	with tempfile.TemporaryDirectory(prefix='mindecho_mix_diag_single_') as temp_dir:
		output_path = Path(temp_dir) / 'diagnose_single_output.json'
		command = [
			sys.executable,
			str(Path(__file__).resolve()),
			'--manifest',
			str(manifest_path),
			'--artifact',
			str(checkpoint_path),
			'--item-name',
			item_name,
			'--output',
			str(output_path),
			'--fresh-runtime-per-sample',
		]
		completed = subprocess.run(
			command,
			cwd=str(ROOT),
			check=False,
			env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
		)
		if completed.returncode != 0:
			raise RuntimeError(
				'fresh subprocess diagnose failed for '
				f'{item_name}: rc={completed.returncode}'
			)
		payload = json.loads(output_path.read_text(encoding='utf-8'))
	artifacts = list(payload.get('artifacts', []) or [])
	if len(artifacts) != 1:
		raise RuntimeError(f'fresh subprocess diagnose expected 1 artifact for {item_name}, got {len(artifacts)}')
	samples = list(artifacts[0].get('samples', []) or [])
	if len(samples) != 1:
		raise RuntimeError(f'fresh subprocess diagnose expected 1 sample for {item_name}, got {len(samples)}')
	return dict(samples[0])


def safe_float(value: Any, default: float = 0.0) -> float:
	try:
		if value is None:
			return float(default)
		return float(value)
	except Exception:
		return float(default)


def clamp01(value: float) -> float:
	return max(0.0, min(1.0, float(value or 0.0)))


def select_best_voice_event(voice_events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	best_voice_event = None
	best_voice_mix_prob = -1.0
	best_voice_mix_margin = -999.0
	for event in list(voice_events or []):
		payload = dict(event.get('display_payload', {}) or {})
		snapshot = dict(event.get('feature_snapshot', {}) or {})
		mix_prob = safe_float(payload.get('mix_prob', snapshot.get('mix_prob', event.get('mix_prob', 0.0))))
		mix_threshold = safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)
		mix_margin = mix_prob - mix_threshold
		if best_voice_event is None or mix_prob > best_voice_mix_prob or (abs(mix_prob - best_voice_mix_prob) < 1e-9 and mix_margin > best_voice_mix_margin):
			best_voice_event = dict(event)
			best_voice_mix_prob = mix_prob
			best_voice_mix_margin = mix_margin
	return best_voice_event


def select_strongest_mix_event(mix_events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
	strongest_mix_event = None
	strongest_mix_support = -1.0
	for event in list(mix_events or []):
		payload = dict(event.get('display_payload', {}) or {})
		snapshot = dict(event.get('feature_snapshot', {}) or {})
		mix_support = safe_float(payload.get('mix_support', snapshot.get('mix_support', 0.0)))
		if strongest_mix_event is None or mix_support > strongest_mix_support:
			strongest_mix_event = dict(event)
			strongest_mix_support = mix_support
	return strongest_mix_event


def pick_snapshot_keys(snapshot: Dict[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
	result: Dict[str, Any] = {}
	for key in keys:
		if key in snapshot:
			result[str(key)] = snapshot.get(key)
	return result


def compact_voice_event(event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
	if not event:
		return {}
	payload = dict(event.get('display_payload', {}) or {})
	snapshot = dict(event.get('feature_snapshot', {}) or {})
	keys = (
		'mean_rms', 'mean_zcr', 'stable_ratio', 'voiced_ratio', 'mean_breath_score', 'breath_hint_ratio',
		'mix_prob', 'mix_threshold', 'raw_mix_prob', 'probability_margin',
	)
	return {
		'event_type': str(event.get('event_type', '') or ''),
		'start_time': dbg.to_jsonable(safe_float(event.get('start_time', 0.0))),
		'end_time': dbg.to_jsonable(safe_float(event.get('end_time', 0.0))),
		'confidence': dbg.to_jsonable(safe_float(event.get('confidence', 0.0))),
		'strength': dbg.to_jsonable(safe_float(event.get('strength', 0.0))),
		'voice_type': str(event.get('voice_type', '') or ''),
		'mean_pitch_hz': dbg.to_jsonable(safe_float(event.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)))),
		'chest_prob': dbg.to_jsonable(safe_float(event.get('chest_prob', snapshot.get('chest_prob', 0.0)))),
		'falsetto_prob': dbg.to_jsonable(safe_float(event.get('falsetto_prob', snapshot.get('falsetto_prob', 0.0)))),
		'mix_prob': dbg.to_jsonable(safe_float(payload.get('mix_prob', snapshot.get('mix_prob', event.get('mix_prob', 0.0))))),
		'mix_threshold': dbg.to_jsonable(safe_float(payload.get('mix_threshold', snapshot.get('mix_threshold', 0.45)), 0.45)),
		'feature_snapshot': dbg.to_jsonable(pick_snapshot_keys(snapshot, keys)),
	}


def compact_mix_event(event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
	if not event:
		return {}
	snapshot = dict(event.get('feature_snapshot', {}) or {})
	keys = (
		'mix_support', 'learned_mix_margin', 'heuristic_mix_support', 'learned_mix_support', 'breathiness',
		'head_bias', 'chest_bias', 'pure_learned_head_mix', 'marginal_head_mix',
		'released_high_pitch_head_mix', 'released_near_threshold_high_pitch_head_mix', 'released_ultra_high_pitch_head_mix',
		'released_low_energy_midhigh_head_mix', 'released_sustained_highpitch_marginal_head_mix', 'released_midpitch_lowchest_pure_head_mix', 'released_short_lowpitch_marginal_head_mix', 'released_underpowered_short_lowpitch_head_mix', 'released_midpitch_long_lowenergy_marginal_head_mix', 'released_midhigh_nearthreshold_softhead_long_mix', 'released_highpitch_nearthreshold_supported_head_mix', 'released_highpitch_long_lowprob_softhead_mix', 'released_midlow_balanced_lowprob_softhead_mix', 'released_lowmid_chesty_lowprob_softhead_mix', 'released_short_lowpitch_supported_softhead_mix', 'released_nearthreshold_extreme_energy_softhead_mix', 'released_sustained_highpitch_lowprob_softhead_mix', 'released_midhigh_long_lowprob_softhead_mix', 'released_midhigh_moderate_energy_lowprob_softhead_mix', 'released_highpitch_long_moderate_energy_lowprob_softhead_mix', 'released_highpitch_headbiased_combination_soft_mix', 'released_highpitch_chesty_nearthreshold_mix', 'released_ultrahigh_lowchest_zero_support_mix', 'released_short_lowmid_supported_headbias_mix', 'released_balanced_supported_softhead_mix', 'released_midhigh_supported_softhead_mix', 'underpowered_low_pitch_head_mix', 'borderline_low_mid_pitch_head_mix',
		'released_supportful_midhigh_nearthreshold_mix',
		'released_supportful_highpitch_nearthreshold_airy_mix',
		'released_supportful_highpitch_nearthreshold_dense_mix',
		'released_midhigh_headbiased_zero_support_mix',
		'weak_mix_support_floor', 'weak_mix_pitch_floor', 'mix_prob', 'mix_threshold', 'mean_pitch_hz',
	)
	return {
		'event_type': str(event.get('event_type', '') or ''),
		'subtype': str(event.get('subtype', '') or ''),
		'base_voice_type': str(event.get('base_voice_type', '') or ''),
		'start_time': dbg.to_jsonable(safe_float(event.get('start_time', 0.0))),
		'end_time': dbg.to_jsonable(safe_float(event.get('end_time', 0.0))),
		'confidence': dbg.to_jsonable(safe_float(event.get('confidence', 0.0))),
		'strength': dbg.to_jsonable(safe_float(event.get('strength', 0.0))),
		'feature_snapshot': dbg.to_jsonable(pick_snapshot_keys(snapshot, keys)),
	}


def evaluate_mix_rule(best_voice_event: Optional[Dict[str, Any]], voice_events: Sequence[Dict[str, Any]], mix_events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
	if not best_voice_event:
		return {'status': 'no_voice_event'}

	snapshot = dict(best_voice_event.get('feature_snapshot', {}) or {})
	duration = max(0.0, safe_float(best_voice_event.get('end_time', 0.0)) - safe_float(best_voice_event.get('start_time', 0.0)))
	confidence = safe_float(best_voice_event.get('confidence', 0.0))
	strength = safe_float(best_voice_event.get('strength', 0.0))
	chest_prob = safe_float(best_voice_event.get('chest_prob', snapshot.get('chest_prob', 0.0)))
	falsetto_prob = safe_float(best_voice_event.get('falsetto_prob', snapshot.get('falsetto_prob', 0.0)))
	probability_margin = safe_float(
		best_voice_event.get('display_payload', {}).get('probability_margin', snapshot.get('probability_margin', abs(chest_prob - falsetto_prob))),
		abs(chest_prob - falsetto_prob),
	)
	voiced_ratio = safe_float(snapshot.get('voiced_ratio', 0.0))
	mean_pitch_hz = safe_float(best_voice_event.get('mean_pitch_hz', snapshot.get('mean_pitch_hz', 0.0)))
	mean_rms = safe_float(snapshot.get('mean_rms', 0.0))
	mean_zcr = safe_float(snapshot.get('mean_zcr', 0.0))
	stable_ratio = safe_float(snapshot.get('stable_ratio', 0.0))
	mean_breath_score = safe_float(snapshot.get('mean_breath_score', 0.0))
	breath_hint_ratio = safe_float(snapshot.get('breath_hint_ratio', 0.0))
	learned_mix_prob = safe_float(snapshot.get('mix_prob', best_voice_event.get('mix_prob', 0.0)))
	learned_mix_threshold = safe_float(snapshot.get('mix_threshold', best_voice_event.get('display_payload', {}).get('mix_threshold', 0.45)), 0.45)
	learned_mix_margin = (learned_mix_prob - learned_mix_threshold) if learned_mix_prob > 0.0 else 0.0

	heuristic_mix_support = clamp01(1.0 - (probability_margin / 0.40))
	learned_mix_support = clamp01((learned_mix_prob - (learned_mix_threshold - 0.12)) / 0.42) if learned_mix_prob > 0.0 else 0.0
	mix_support = heuristic_mix_support
	if learned_mix_prob > 0.0:
		mix_support = clamp01(0.32 * heuristic_mix_support + 0.68 * learned_mix_support)
	pitch_support = clamp01((mean_pitch_hz - 210.0) / 230.0)
	stable_support = clamp01((stable_ratio - 0.08) / 0.24)
	voiced_support = clamp01((voiced_ratio - 0.34) / 0.34)
	low_energy_air = clamp01((0.0014 - mean_rms) / 0.0011) if mean_rms > 0.0 else 0.0
	zcr_air = clamp01((mean_zcr - 0.08) / 0.16)
	breathiness = max(
		clamp01(mean_breath_score / 0.34),
		clamp01(breath_hint_ratio / 0.22),
		zcr_air * 0.82,
		low_energy_air * 0.68,
	)
	head_bias = clamp01((falsetto_prob - chest_prob + 0.18) / 0.50)
	chest_bias = clamp01((chest_prob - falsetto_prob + 0.18) / 0.50)
	pure_learned_head_mix = (
		learned_mix_prob >= learned_mix_threshold
		and head_bias >= 0.70
		and heuristic_mix_support <= 0.08
	)
	marginal_head_mix = (
		learned_mix_prob >= learned_mix_threshold
		and head_bias >= 0.90
		and learned_mix_margin < 0.05
		and heuristic_mix_support < 0.30
		and learned_mix_support < 0.45
	)
	released_high_pitch_head_mix = (
		marginal_head_mix
		and mean_pitch_hz >= 470.0
		and falsetto_prob >= 0.95
		and mean_rms >= 0.075
		and learned_mix_margin >= 0.005
		and learned_mix_support >= 0.30
	)
	released_near_threshold_high_pitch_head_mix = (
		not released_high_pitch_head_mix
		and learned_mix_margin >= -0.0015
		and learned_mix_prob >= max(0.50, learned_mix_threshold - 0.002)
		and head_bias >= 0.92
		and mean_pitch_hz >= 500.0
		and falsetto_prob >= 0.93
		and falsetto_prob <= 0.96
		and mean_rms >= 0.08
		and learned_mix_support >= 0.28
	)
	released_ultra_high_pitch_head_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and learned_mix_margin >= -0.072
		and learned_mix_margin <= -0.015
		and learned_mix_prob >= max(0.479, learned_mix_threshold - 0.072)
		and head_bias >= 0.95
		and mean_pitch_hz >= 540.0
		and falsetto_prob >= 0.945
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
		and learned_mix_support >= 0.115
		and learned_mix_support <= 0.16
	)
	released_high_energy_midhigh_head_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and not released_ultra_high_pitch_head_mix
		and learned_mix_margin >= -0.072
		and learned_mix_margin <= -0.045
		and learned_mix_prob >= max(0.479, learned_mix_threshold - 0.072)
		and head_bias >= 0.95
		and mean_pitch_hz >= 440.0
		and mean_pitch_hz <= 470.0
		and falsetto_prob >= 0.95
		and mean_rms >= 0.11
		and heuristic_mix_support <= 0.08
		and learned_mix_support >= 0.115
		and learned_mix_support <= 0.14
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
	)
	released_supported_low_pitch_head_mix = (
		pure_learned_head_mix
		and mean_pitch_hz >= 290.0
		and mean_pitch_hz <= 400.0
		and falsetto_prob >= 0.76
		and falsetto_prob <= 0.88
		and chest_prob >= 0.18
		and chest_prob <= 0.24
		and mean_rms >= 0.06
		and heuristic_mix_support <= 0.08
		and learned_mix_margin >= 0.06
		and learned_mix_support >= 0.43
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
	)
	released_lowmid_near_threshold_head_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and not released_ultra_high_pitch_head_mix
		and not released_high_energy_midhigh_head_mix
		and not released_supported_low_pitch_head_mix
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_margin >= -0.0045
		and learned_mix_margin <= -0.0015
		and head_bias >= 0.95
		and mean_pitch_hz >= 326.0
		and mean_pitch_hz <= 340.0
		and falsetto_prob >= 0.805
		and falsetto_prob <= 0.830
		and chest_prob >= 0.175
		and chest_prob <= 0.200
		and mean_rms >= 0.060
		and mean_rms <= 0.068
		and learned_mix_support >= 0.278
		and learned_mix_support <= 0.282
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
	)
	released_midhigh_near_threshold_head_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and not released_ultra_high_pitch_head_mix
		and not released_high_energy_midhigh_head_mix
		and not released_supported_low_pitch_head_mix
		and not released_lowmid_near_threshold_head_mix
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_margin >= -0.0065
		and learned_mix_margin <= -0.0025
		and head_bias >= 0.95
		and mean_pitch_hz >= 396.0
		and mean_pitch_hz <= 442.0
		and falsetto_prob >= 0.868
		and falsetto_prob <= 0.885
		and chest_prob >= 0.117
		and chest_prob <= 0.132
		and mean_rms >= 0.029
		and mean_rms <= 0.043
		and learned_mix_support >= 0.270
		and learned_mix_support <= 0.279
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
	)
	released_ultrahigh_bright_head_point_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and not released_ultra_high_pitch_head_mix
		and not released_high_energy_midhigh_head_mix
		and not released_supported_low_pitch_head_mix
		and not released_lowmid_near_threshold_head_mix
		and not released_midhigh_near_threshold_head_mix
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_margin >= -0.0160
		and learned_mix_margin <= -0.0153
		and head_bias >= 0.95
		and mean_pitch_hz >= 524.5
		and mean_pitch_hz <= 525.5
		and falsetto_prob >= 0.9610
		and falsetto_prob <= 0.9625
		and chest_prob >= 0.0375
		and chest_prob <= 0.0395
		and mean_rms >= 0.0950
		and mean_rms <= 0.0960
		and learned_mix_support >= 0.2480
		and learned_mix_support <= 0.2488
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midchest_near_threshold_head_mix = (
		not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and not released_ultra_high_pitch_head_mix
		and not released_high_energy_midhigh_head_mix
		and not released_supported_low_pitch_head_mix
		and not released_lowmid_near_threshold_head_mix
		and not released_midhigh_near_threshold_head_mix
		and not released_ultrahigh_bright_head_point_mix
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_margin >= -0.027
		and learned_mix_margin <= -0.009
		and head_bias >= 0.95
		and mean_pitch_hz >= 319.0
		and mean_pitch_hz <= 406.1
		and falsetto_prob >= 0.8635
		and falsetto_prob <= 0.8790
		and chest_prob >= 0.225
		and chest_prob <= 0.271
		and mean_rms >= 0.0528
		and mean_rms <= 0.0937
		and learned_mix_support >= 0.2217
		and learned_mix_support <= 0.2635
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	underpowered_low_pitch_head_mix = (
		learned_mix_prob >= learned_mix_threshold
		and head_bias >= 0.88
		and mean_pitch_hz < 240.0
		and learned_mix_margin < 0.09
		and learned_mix_support < 0.50
	)
	borderline_low_mid_pitch_head_mix = (
		learned_mix_prob >= learned_mix_threshold
		and not marginal_head_mix
		and head_bias >= 0.90
		and learned_mix_margin < 0.06
		and mean_pitch_hz < 300.0
		and falsetto_prob < 0.78
		and mean_rms < 0.06
		and heuristic_mix_support < 0.32
		and learned_mix_support < 0.43
	)
	released_low_energy_midhigh_head_mix = (
		marginal_head_mix
		and not released_high_pitch_head_mix
		and duration >= 0.55
		and duration <= 0.95
		and mean_pitch_hz >= 408.0
		and mean_pitch_hz <= 422.0
		and falsetto_prob >= 0.66
		and falsetto_prob <= 0.75
		and chest_prob >= 0.27
		and chest_prob <= 0.34
		and learned_mix_margin >= 0.005
		and learned_mix_margin <= 0.015
		and heuristic_mix_support <= 0.08
		and learned_mix_support >= 0.29
		and learned_mix_support <= 0.34
		and stable_ratio >= 0.98
		and voiced_ratio >= 0.98
	)
	released_sustained_highpitch_marginal_head_mix = (
		marginal_head_mix
		and not released_high_pitch_head_mix
		and not released_near_threshold_high_pitch_head_mix
		and duration >= 6.50
		and duration <= 12.10
		and mean_pitch_hz >= 438.0
		and mean_pitch_hz <= 489.5
		and falsetto_prob >= 0.875
		and falsetto_prob <= 0.94
		and chest_prob >= 0.075
		and chest_prob <= 0.245
		and mean_rms >= 0.065
		and mean_rms <= 0.091
		and heuristic_mix_support <= 0.08
		and learned_mix_margin >= 0.012
		and learned_mix_margin <= 0.045
		and learned_mix_support >= 0.31
		and learned_mix_support <= 0.40
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midpitch_lowchest_pure_head_mix = (
		pure_learned_head_mix
		and mean_pitch_hz >= 323.0
		and mean_pitch_hz <= 395.0
		and chest_prob >= 0.13
		and chest_prob <= 0.19
		and falsetto_prob >= 0.81
		and falsetto_prob <= 0.89
		and mean_rms >= 0.033
		and mean_rms <= 0.072
		and duration >= 2.80
		and duration <= 8.45
		and heuristic_mix_support <= 0.08
		and learned_mix_margin >= 0.004
		and learned_mix_margin <= 0.063
		and learned_mix_support >= 0.295
		and learned_mix_support <= 0.435
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_short_lowpitch_marginal_head_mix = (
		marginal_head_mix
		and mean_pitch_hz >= 240.0
		and mean_pitch_hz <= 308.0
		and chest_prob >= 0.20
		and chest_prob <= 0.39
		and falsetto_prob >= 0.64
		and falsetto_prob <= 0.84
		and mean_rms >= 0.023
		and mean_rms <= 0.050
		and duration >= 1.20
		and duration <= 5.40
		and heuristic_mix_support <= 0.30
		and learned_mix_margin >= 0.003
		and learned_mix_margin <= 0.037
		and learned_mix_support >= 0.29
		and learned_mix_support <= 0.38
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midpitch_underpowered_pure_head_mix = (
		pure_learned_head_mix
		and marginal_head_mix
		and mean_pitch_hz >= 360.0
		and mean_pitch_hz <= 430.0
		and chest_prob >= 0.05
		and chest_prob <= 0.14
		and falsetto_prob >= 0.86
		and falsetto_prob <= 0.95
		and mean_rms >= 0.045
		and mean_rms <= 0.085
		and duration >= 6.0
		and duration <= 11.5
		and learned_mix_margin >= 0.0
		and learned_mix_margin <= 0.01
		and learned_mix_support >= 0.28
		and learned_mix_support <= 0.31
		and mix_support >= 0.19
		and mix_support <= 0.21
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_balanced_pure_head_mix = (
		pure_learned_head_mix
		and marginal_head_mix
		and mean_pitch_hz >= 455.0
		and mean_pitch_hz <= 470.0
		and chest_prob >= 0.07
		and chest_prob <= 0.10
		and falsetto_prob >= 0.90
		and falsetto_prob <= 0.93
		and mean_rms >= 0.08
		and mean_rms <= 0.13
		and duration >= 6.0
		and duration <= 10.5
		and learned_mix_margin >= 0.0
		and learned_mix_margin <= 0.045
		and learned_mix_support >= 0.29
		and learned_mix_support <= 0.39
		and mix_support >= 0.20
		and mix_support <= 0.27
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_underpowered_short_lowpitch_head_mix = (
		underpowered_low_pitch_head_mix
		and marginal_head_mix
		and mean_pitch_hz >= 235.0
		and mean_pitch_hz <= 236.0
		and chest_prob >= 0.25
		and chest_prob <= 0.29
		and falsetto_prob >= 0.73
		and falsetto_prob <= 0.75
		and mean_rms >= 0.024
		and mean_rms <= 0.026
		and duration >= 1.90
		and duration <= 2.20
		and heuristic_mix_support <= 0.05
		and learned_mix_margin >= 0.003
		and learned_mix_margin <= 0.006
		and learned_mix_support >= 0.29
		and learned_mix_support <= 0.30
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midpitch_long_lowenergy_marginal_head_mix = (
		pure_learned_head_mix
		and marginal_head_mix
		and mean_pitch_hz >= 396.0
		and mean_pitch_hz <= 414.0
		and chest_prob >= 0.04
		and chest_prob <= 0.06
		and falsetto_prob >= 0.94
		and falsetto_prob <= 0.96
		and mean_rms >= 0.038
		and mean_rms <= 0.060
		and duration >= 9.0
		and duration <= 11.2
		and learned_mix_margin >= 0.012
		and learned_mix_margin <= 0.032
		and learned_mix_support >= 0.32
		and learned_mix_support <= 0.37
		and mix_support >= 0.22
		and mix_support <= 0.25
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_nearthreshold_softhead_long_mix = (
		learned_mix_prob < learned_mix_threshold
		and learned_mix_margin >= -0.030
		and learned_mix_margin <= -0.010
		and mean_pitch_hz >= 426.0
		and mean_pitch_hz <= 436.0
		and chest_prob >= 0.05
		and chest_prob <= 0.08
		and falsetto_prob >= 0.92
		and falsetto_prob <= 0.95
		and mean_rms >= 0.038
		and mean_rms <= 0.055
		and duration >= 9.0
		and duration <= 11.5
		and learned_mix_support >= 0.22
		and learned_mix_support <= 0.26
		and mix_support >= 0.14
		and mix_support <= 0.19
		and heuristic_mix_support <= 0.06
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_highpitch_nearthreshold_supported_head_mix = (
		learned_mix_prob < learned_mix_threshold
		and mean_pitch_hz >= 455.0
		and mean_pitch_hz <= 540.0
		and chest_prob >= 0.015
		and chest_prob <= 0.055
		and falsetto_prob >= 0.946
		and falsetto_prob <= 0.985
		and learned_mix_margin >= -0.065
		and learned_mix_margin <= -0.003
		and learned_mix_support >= 0.130
		and learned_mix_support <= 0.280
		and mix_support >= 0.090
		and mix_support <= 0.190
		and mean_rms >= 0.062
		and mean_rms <= 0.115
		and duration >= 7.0
		and duration <= 9.9
		and heuristic_mix_support <= 0.06
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_supported_softhead_mix = (
		learned_mix_prob < learned_mix_threshold
		and mean_pitch_hz >= 417.0
		and mean_pitch_hz <= 517.0
		and chest_prob >= 0.011
		and chest_prob <= 0.099
		and falsetto_prob >= 0.901
		and falsetto_prob <= 0.989
		and learned_mix_margin >= -0.071
		and learned_mix_margin <= 0.0
		and learned_mix_support >= 0.117
		and learned_mix_support <= 0.268
		and mix_support >= 0.079
		and mix_support <= 0.182
		and mean_rms >= 0.041
		and mean_rms <= 0.095
		and duration >= 6.5
		and duration <= 10.7
		and heuristic_mix_support <= 0.06
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_balanced_supported_softhead_mix = (
		learned_mix_prob < learned_mix_threshold
		and mean_pitch_hz >= 340.0
		and mean_pitch_hz <= 460.0
		and chest_prob >= 0.098
		and chest_prob <= 0.140
		and falsetto_prob >= 0.860
		and falsetto_prob <= 0.901
		and learned_mix_margin >= -0.068
		and learned_mix_margin <= -0.003
		and learned_mix_support >= 0.126
		and learned_mix_support <= 0.280
		and mix_support >= 0.086
		and mix_support <= 0.190
		and mean_rms >= 0.050
		and mean_rms <= 0.088
		and duration >= 4.9
		and duration <= 8.4
		and heuristic_mix_support <= 0.06
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_highpitch_long_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob >= 0.255
		and learned_mix_prob <= 0.290
		and learned_mix_prob < max(0.26, learned_mix_threshold - 0.08)
		and mean_pitch_hz >= 438.0
		and mean_pitch_hz <= 540.0
		and chest_prob >= 0.010
		and chest_prob <= 0.034
		and falsetto_prob >= 0.967
		and falsetto_prob <= 0.989
		and learned_mix_margin >= -0.170
		and learned_mix_margin <= -0.135
		and mean_rms >= 0.058
		and mean_rms <= 0.080
		and duration >= 8.8
		and duration <= 10.7
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midlow_balanced_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob >= 0.200
		and learned_mix_prob <= 0.245
		and learned_mix_prob < max(0.26, learned_mix_threshold - 0.08)
		and mean_pitch_hz >= 385.0
		and mean_pitch_hz <= 420.0
		and chest_prob >= 0.090
		and chest_prob <= 0.140
		and falsetto_prob >= 0.860
		and falsetto_prob <= 0.910
		and learned_mix_margin >= -0.225
		and learned_mix_margin <= -0.170
		and mean_rms >= 0.030
		and mean_rms <= 0.075
		and duration >= 6.0
		and duration <= 10.5
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_lowmid_chesty_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob >= 0.210
		and learned_mix_prob <= 0.282
		and learned_mix_prob < max(0.26, learned_mix_threshold - 0.08)
		and mean_pitch_hz >= 315.0
		and mean_pitch_hz <= 335.0
		and chest_prob >= 0.175
		and chest_prob <= 0.198
		and falsetto_prob >= 0.805
		and falsetto_prob <= 0.823
		and learned_mix_margin >= -0.210
		and learned_mix_margin <= -0.145
		and duration >= 6.0
		and duration <= 10.5
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_short_lowpitch_supported_softhead_mix = (
		learned_mix_prob < learned_mix_threshold
		and mean_pitch_hz >= 300.0
		and mean_pitch_hz <= 309.0
		and chest_prob >= 0.24
		and chest_prob <= 0.28
		and falsetto_prob >= 0.70
		and falsetto_prob <= 0.76
		and learned_mix_margin >= -0.036
		and learned_mix_margin <= -0.025
		and learned_mix_support >= 0.20
		and learned_mix_support <= 0.23
		and mix_support >= 0.13
		and mix_support <= 0.16
		and mean_rms >= 0.048
		and mean_rms <= 0.052
		and duration >= 3.6
		and duration <= 4.3
		and heuristic_mix_support <= 0.06
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_nearthreshold_extreme_energy_softhead_mix = (
		(
			learned_mix_prob > 0.0
			and learned_mix_prob < learned_mix_threshold
			and learned_mix_prob >= 0.505
			and learned_mix_prob <= 0.560
			and learned_mix_margin >= -0.155
			and learned_mix_margin <= -0.090
			and mean_pitch_hz >= 470.0
			and mean_pitch_hz <= 540.0
			and chest_prob >= 0.010
			and chest_prob <= 0.040
			and falsetto_prob >= 0.960
			and falsetto_prob <= 0.985
			and mean_rms >= 0.104
			and mean_rms <= 0.155
			and duration >= 5.5
			and duration <= 10.5
			and learned_mix_support <= 0.035
			and mix_support <= 0.025
			and heuristic_mix_support <= 0.02
			and stable_ratio >= 0.99
			and voiced_ratio >= 0.99
		)
		or (
			learned_mix_prob > 0.0
			and learned_mix_prob < learned_mix_threshold
			and head_bias >= 0.99
			and learned_mix_prob >= 0.540
			and learned_mix_prob <= 0.560
			and learned_mix_margin >= -0.105
			and learned_mix_margin <= -0.080
			and mean_pitch_hz >= 442.0
			and mean_pitch_hz <= 448.0
			and chest_prob >= 0.060
			and chest_prob <= 0.085
			and falsetto_prob >= 0.915
			and falsetto_prob <= 0.940
			and mean_rms >= 0.120
			and mean_rms <= 0.140
			and duration >= 6.0
			and duration <= 6.8
			and learned_mix_support >= 0.060
			and learned_mix_support <= 0.080
			and mix_support >= 0.040
			and mix_support <= 0.055
			and heuristic_mix_support <= 0.02
			and stable_ratio >= 0.99
			and voiced_ratio >= 0.99
		)
	)
	released_sustained_highpitch_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_prob >= 0.415
		and learned_mix_prob <= 0.460
		and learned_mix_margin >= -0.230
		and learned_mix_margin <= -0.160
		and mean_pitch_hz >= 445.0
		and mean_pitch_hz <= 520.0
		and chest_prob >= 0.045
		and chest_prob <= 0.085
		and falsetto_prob >= 0.915
		and falsetto_prob <= 0.950
		and mean_rms >= 0.056
		and mean_rms <= 0.085
		and duration >= 8.5
		and duration <= 18.5
		and learned_mix_support <= 0.010
		and mix_support <= 0.010
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_long_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_prob >= 0.435
		and learned_mix_prob <= 0.490
		and learned_mix_margin >= -0.210
		and learned_mix_margin <= -0.150
		and mean_pitch_hz >= 430.0
		and mean_pitch_hz <= 470.0
		and chest_prob >= 0.060
		and chest_prob <= 0.095
		and falsetto_prob >= 0.905
		and falsetto_prob <= 0.940
		and mean_rms >= 0.082
		and mean_rms <= 0.110
		and duration >= 6.0
		and duration <= 10.5
		and learned_mix_support <= 0.035
		and mix_support <= 0.025
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_moderate_energy_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_prob >= 0.430
		and learned_mix_prob <= 0.560
		and learned_mix_margin >= -0.215
		and learned_mix_margin <= -0.080
		and mean_pitch_hz >= 460.0
		and mean_pitch_hz <= 535.0
		and chest_prob >= 0.015
		and chest_prob <= 0.040
		and falsetto_prob >= 0.960
		and falsetto_prob <= 0.985
		and mean_rms >= 0.045
		and mean_rms <= 0.075
		and duration >= 7.5
		and duration <= 12.5
		and learned_mix_support <= 0.060
		and mix_support <= 0.040
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_highpitch_long_moderate_energy_lowprob_softhead_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and learned_mix_prob >= 0.430
		and learned_mix_prob <= 0.490
		and learned_mix_margin >= -0.215
		and learned_mix_margin <= -0.150
		and mean_pitch_hz >= 500.0
		and mean_pitch_hz <= 581.0
		and chest_prob >= 0.018
		and chest_prob <= 0.040
		and falsetto_prob >= 0.960
		and falsetto_prob <= 0.982
		and mean_rms >= 0.084
		and mean_rms <= 0.106
		and duration >= 8.5
		and duration <= 19.0
		and learned_mix_support <= 0.010
		and mix_support <= 0.010
		and heuristic_mix_support <= 0.02
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_highpitch_headbiased_combination_soft_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.98
		and learned_mix_prob >= 0.430
		and learned_mix_prob <= 0.530
		and learned_mix_margin >= -0.200
		and learned_mix_margin <= -0.060
		and mean_pitch_hz >= 430.0
		and mean_pitch_hz <= 520.0
		and chest_prob <= 0.110
		and falsetto_prob >= 0.890
		and falsetto_prob <= 0.980
		and mean_rms >= 0.050
		and mean_rms <= 0.115
		and duration >= 5.0
		and duration <= 18.5
		and learned_mix_support <= 0.030
		and mix_support <= 0.020
		and heuristic_mix_support <= 0.020
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_highpitch_chesty_nearthreshold_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.98
		and learned_mix_prob >= 0.400
		and learned_mix_prob <= 0.490
		and learned_mix_margin >= -0.240
		and learned_mix_margin <= -0.150
		and mean_pitch_hz >= 440.0
		and mean_pitch_hz <= 530.0
		and chest_prob >= 0.100
		and chest_prob <= 0.130
		and falsetto_prob >= 0.870
		and falsetto_prob <= 0.900
		and mean_rms >= 0.050
		and mean_rms <= 0.160
		and duration >= 6.0
		and duration <= 16.5
		and learned_mix_support <= 0.020
		and mix_support <= 0.015
		and heuristic_mix_support <= 0.020
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_ultrahigh_lowchest_zero_support_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.300
		and learned_mix_prob <= 0.430
		and learned_mix_margin >= -0.340
		and learned_mix_margin <= -0.200
		and mean_pitch_hz >= 520.0
		and mean_pitch_hz <= 575.0
		and chest_prob >= 0.020
		and chest_prob <= 0.045
		and falsetto_prob >= 0.955
		and falsetto_prob <= 0.980
		and duration >= 6.0
		and duration <= 15.0
		and learned_mix_support <= 0.001
		and mix_support <= 0.001
		and heuristic_mix_support <= 0.020
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_midhigh_headbiased_zero_support_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.410
		and learned_mix_prob <= 0.430
		and learned_mix_margin >= -0.235
		and learned_mix_margin <= -0.205
		and mean_pitch_hz >= 385.0
		and mean_pitch_hz <= 420.0
		and chest_prob >= 0.075
		and chest_prob <= 0.125
		and falsetto_prob >= 0.870
		and falsetto_prob <= 0.930
		and mean_rms >= 0.079
		and mean_rms <= 0.115
		and duration >= 5.0
		and duration <= 9.0
		and learned_mix_support <= 0.002
		and mix_support <= 0.002
		and heuristic_mix_support <= 0.020
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_short_lowmid_supported_headbias_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.540
		and learned_mix_prob <= 0.590
		and learned_mix_margin >= -0.100
		and learned_mix_margin <= -0.050
		and mean_pitch_hz >= 255.0
		and mean_pitch_hz <= 310.0
		and chest_prob >= 0.240
		and chest_prob <= 0.340
		and falsetto_prob >= 0.660
		and falsetto_prob <= 0.760
		and mean_rms >= 0.020
		and mean_rms <= 0.080
		and duration >= 1.0
		and duration <= 2.2
		and learned_mix_support >= 0.090
		and learned_mix_support <= 0.170
		and mix_support >= 0.060
		and mix_support <= 0.170
		and heuristic_mix_support <= 0.180
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_supportful_midhigh_nearthreshold_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.520
		and learned_mix_prob <= 0.560
		and learned_mix_margin >= -0.130
		and learned_mix_margin <= -0.080
		and mean_pitch_hz >= 315.0
		and mean_pitch_hz <= 370.0
		and chest_prob >= 0.190
		and chest_prob <= 0.220
		and falsetto_prob >= 0.780
		and falsetto_prob <= 0.810
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
	released_supportful_highpitch_nearthreshold_airy_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.530
		and learned_mix_prob <= 0.550
		and learned_mix_margin >= -0.120
		and learned_mix_margin <= -0.090
		and mean_pitch_hz >= 540.0
		and mean_pitch_hz <= 610.0
		and chest_prob >= 0.160
		and chest_prob <= 0.190
		and falsetto_prob >= 0.810
		and falsetto_prob <= 0.830
		and mean_rms >= 0.0005
		and mean_rms <= 0.0030
		and duration >= 0.6
		and duration <= 1.2
		and learned_mix_support >= 0.030
		and learned_mix_support <= 0.060
		and mix_support >= 0.020
		and mix_support <= 0.040
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)
	released_supportful_highpitch_nearthreshold_dense_mix = (
		learned_mix_prob > 0.0
		and learned_mix_prob < learned_mix_threshold
		and head_bias >= 0.99
		and learned_mix_prob >= 0.545
		and learned_mix_prob <= 0.575
		and learned_mix_margin >= -0.100
		and learned_mix_margin <= -0.070
		and mean_pitch_hz >= 541.5
		and mean_pitch_hz <= 575.0
		and chest_prob >= 0.015
		and chest_prob <= 0.035
		and falsetto_prob >= 0.965
		and falsetto_prob <= 0.985
		and mean_rms >= 0.105
		and mean_rms <= 0.170
		and duration >= 7.5
		and duration <= 9.0
		and learned_mix_support >= 0.080
		and learned_mix_support <= 0.110
		and mix_support >= 0.055
		and mix_support <= 0.075
		and stable_ratio >= 0.99
		and voiced_ratio >= 0.99
	)

	weak_mix_support = mix_support
	weak_mix_support_floor = 0.28
	weak_mix_pitch_floor = 230.0
	if learned_mix_prob >= learned_mix_threshold and head_bias >= 0.70:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.20
		weak_mix_pitch_floor = 180.0
	elif released_midhigh_nearthreshold_softhead_long_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.15
		weak_mix_pitch_floor = 220.0
	elif released_highpitch_long_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.12)
		weak_mix_support_floor = 0.12
		weak_mix_pitch_floor = 230.0
	elif released_midlow_balanced_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.11)
		weak_mix_support_floor = 0.11
		weak_mix_pitch_floor = 230.0
	elif released_lowmid_chesty_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.12)
		weak_mix_support_floor = 0.12
		weak_mix_pitch_floor = 225.0
	elif released_short_lowpitch_supported_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.14
		weak_mix_pitch_floor = 230.0
	elif released_nearthreshold_extreme_energy_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.038
		weak_mix_pitch_floor = 230.0
	elif released_sustained_highpitch_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.022)
		weak_mix_support_floor = 0.022
		weak_mix_pitch_floor = 230.0
	elif released_midhigh_long_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.018)
		weak_mix_support_floor = 0.018
		weak_mix_pitch_floor = 230.0
	elif released_midhigh_moderate_energy_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.020)
		weak_mix_support_floor = 0.020
		weak_mix_pitch_floor = 230.0
	elif released_highpitch_long_moderate_energy_lowprob_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.022)
		weak_mix_support_floor = 0.022
		weak_mix_pitch_floor = 230.0
	elif released_highpitch_headbiased_combination_soft_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.018)
		weak_mix_support_floor = 0.018
		weak_mix_pitch_floor = 230.0
	elif released_highpitch_chesty_nearthreshold_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.014)
		weak_mix_support_floor = 0.014
		weak_mix_pitch_floor = 230.0
	elif released_ultrahigh_lowchest_zero_support_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.015)
		weak_mix_support_floor = 0.015
		weak_mix_pitch_floor = 230.0
	elif released_midhigh_headbiased_zero_support_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.015)
		weak_mix_support_floor = 0.015
		weak_mix_pitch_floor = 230.0
	elif released_short_lowmid_supported_headbias_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.095
		weak_mix_pitch_floor = 230.0
	elif released_supportful_midhigh_nearthreshold_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.010)
		weak_mix_support_floor = 0.010
		weak_mix_pitch_floor = 230.0
	elif released_supportful_highpitch_nearthreshold_airy_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.020)
		weak_mix_support_floor = 0.020
		weak_mix_pitch_floor = 230.0
	elif released_supportful_highpitch_nearthreshold_dense_mix:
		weak_mix_support = max(mix_support, learned_mix_support, 0.055)
		weak_mix_support_floor = 0.055
		weak_mix_pitch_floor = 230.0
	elif released_balanced_supported_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.126
		weak_mix_pitch_floor = 230.0
	elif released_midhigh_supported_softhead_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.115
		weak_mix_pitch_floor = 230.0
	elif released_highpitch_nearthreshold_supported_head_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.13
		weak_mix_pitch_floor = 230.0
	elif released_near_threshold_high_pitch_head_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.18
		weak_mix_pitch_floor = 180.0
	elif released_ultra_high_pitch_head_mix or released_high_energy_midhigh_head_mix or released_supported_low_pitch_head_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.115
		weak_mix_pitch_floor = 180.0
	elif released_lowmid_near_threshold_head_mix or released_midhigh_near_threshold_head_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.27
		weak_mix_pitch_floor = 230.0
	elif released_ultrahigh_bright_head_point_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.248
		weak_mix_pitch_floor = 230.0
	elif released_midchest_near_threshold_head_mix:
		weak_mix_support = max(mix_support, learned_mix_support)
		weak_mix_support_floor = 0.22
		weak_mix_pitch_floor = 230.0

	reject_low_learned_prob = learned_mix_prob > 0.0 and learned_mix_prob < max(0.26, learned_mix_threshold - 0.08) and not (released_highpitch_long_lowprob_softhead_mix or released_midlow_balanced_lowprob_softhead_mix or released_lowmid_chesty_lowprob_softhead_mix or released_nearthreshold_extreme_energy_softhead_mix or released_sustained_highpitch_lowprob_softhead_mix or released_midhigh_long_lowprob_softhead_mix or released_midhigh_moderate_energy_lowprob_softhead_mix or released_highpitch_long_moderate_energy_lowprob_softhead_mix or released_highpitch_headbiased_combination_soft_mix or released_highpitch_chesty_nearthreshold_mix or released_ultrahigh_lowchest_zero_support_mix or released_midhigh_headbiased_zero_support_mix or released_supportful_midhigh_nearthreshold_mix or released_supportful_highpitch_nearthreshold_airy_mix or released_supportful_highpitch_nearthreshold_dense_mix)
	reject_pure_head_low_pitch = pure_learned_head_mix and mean_pitch_hz < 430.0 and falsetto_prob < 0.90 and not (released_low_energy_midhigh_head_mix or released_supported_low_pitch_head_mix or released_midpitch_lowchest_pure_head_mix or released_short_lowpitch_marginal_head_mix or released_midpitch_underpowered_pure_head_mix or released_midhigh_balanced_pure_head_mix or released_underpowered_short_lowpitch_head_mix or released_midpitch_long_lowenergy_marginal_head_mix)
	reject_marginal_head = marginal_head_mix and not (released_high_pitch_head_mix or released_near_threshold_high_pitch_head_mix or released_low_energy_midhigh_head_mix or released_sustained_highpitch_marginal_head_mix or released_midpitch_lowchest_pure_head_mix or released_short_lowpitch_marginal_head_mix or released_midpitch_underpowered_pure_head_mix or released_midhigh_balanced_pure_head_mix or released_underpowered_short_lowpitch_head_mix or released_midpitch_long_lowenergy_marginal_head_mix)
	reject_underpowered_low_pitch = underpowered_low_pitch_head_mix and not released_underpowered_short_lowpitch_head_mix
	reject_borderline_low_mid = borderline_low_mid_pitch_head_mix

	subtype = ''
	subtype_conf = 0.0
	subtype_mix_support = mix_support
	strong_requires_threshold_block = False
	if breathiness >= 0.42 and mix_support >= 0.34 and mean_pitch_hz >= 220.0:
		subtype = 'balanced_mix'
		subtype_conf = (
			0.38 * mix_support
			+ 0.26 * breathiness
			+ 0.18 * pitch_support
			+ 0.10 * stable_support
			+ 0.08 * voiced_support
		)
	elif chest_bias >= 0.46 and mix_support >= 0.28 and mean_pitch_hz >= 180.0:
		if learned_mix_prob > 0.0 and learned_mix_prob < learned_mix_threshold:
			strong_requires_threshold_block = True
		else:
			subtype = 'strong_mix'
			subtype_conf = (
				0.34 * mix_support
				+ 0.26 * chest_bias
				+ 0.18 * stable_support
				+ 0.12 * voiced_support
				+ 0.10 * confidence
			)
	elif head_bias >= 0.42 and weak_mix_support >= weak_mix_support_floor and mean_pitch_hz >= weak_mix_pitch_floor:
		subtype = 'weak_mix'
		subtype_mix_support = weak_mix_support
		subtype_conf = (
			0.34 * weak_mix_support
			+ 0.24 * head_bias
			+ 0.16 * pitch_support
			+ 0.14 * stable_support
			+ 0.12 * confidence
		)
		if released_short_lowmid_supported_headbias_mix:
			subtype_conf = max(subtype_conf, 0.60)

	reject_low_pitch_chesty_mix = (
		subtype in ('weak_mix', 'strong_mix')
		and mean_pitch_hz < 300.0
		and learned_mix_margin >= 0.08
		and not (
			released_supported_low_pitch_head_mix
			or released_midpitch_lowchest_pure_head_mix
			or released_short_lowpitch_marginal_head_mix
			or released_underpowered_short_lowpitch_head_mix
		)
	)

	reject_high_pitch_headbiased_weak_mix = (
		subtype == 'weak_mix'
		and mean_pitch_hz >= 500.0
		and chest_prob <= 0.04
		and falsetto_prob >= 0.96
		and learned_mix_margin >= 0.09
		and not (
			released_high_pitch_head_mix
			or released_near_threshold_high_pitch_head_mix
			or released_ultra_high_pitch_head_mix
			or released_sustained_highpitch_marginal_head_mix
		)
	)

	reject_low_edge_long_combo_soft_mix = (
		subtype == 'weak_mix'
		and released_highpitch_headbiased_combination_soft_mix
		and mean_pitch_hz < 445.0
		and duration >= 8.0
		and mean_rms <= 0.070
		and chest_prob <= 0.060
		and learned_mix_support <= 0.001
		and heuristic_mix_support <= 0.020
	)

	reject_midpitch_pure_head_control = (
		subtype == 'weak_mix'
		and pure_learned_head_mix
		and mean_pitch_hz >= 300.0
		and mean_pitch_hz <= 360.0
		and learned_mix_margin >= 0.15
		and learned_mix_support >= 0.60
		and not released_midpitch_lowchest_pure_head_mix
	)

	reject_low_pitch_strong_mix_chest = (
		subtype == 'strong_mix'
		and str(best_voice_event.get('voice_type', '') or '') == 'chest'
		and mean_pitch_hz < 236.0
		and mean_rms < 0.0335
		and mix_support >= 0.54
		and learned_mix_margin >= 0.04
		and learned_mix_margin <= 0.08
		and chest_prob >= 0.52
		and falsetto_prob <= 0.48
		and duration <= 0.70
	)

	subtype_conf = clamp01(subtype_conf)
	reject_no_subtype = not subtype
	reject_low_subtype_conf = bool(subtype) and subtype_conf < 0.44
	single_mix_events = list(mix_events or [])
	isolated_mix_event = dict(single_mix_events[0] or {}) if len(single_mix_events) == 1 else {}
	isolated_mix_snapshot = dict(isolated_mix_event.get('feature_snapshot', {}) or {})

	prior_falsetto_end = -1.0
	for voice_event in list(voice_events or []):
		voice_type = str(voice_event.get('voice_type', '') or '')
		voice_end_time = safe_float(voice_event.get('end_time', 0.0))
		voice_falsetto_prob = safe_float(voice_event.get('falsetto_prob', 0.0))
		if voice_type == 'falsetto' and voice_falsetto_prob >= 0.88 and voice_end_time <= safe_float(best_voice_event.get('start_time', 0.0)):
			prior_falsetto_end = max(prior_falsetto_end, voice_end_time)
	isolated_low_pitch_chest_tail_mix = (
		len(single_mix_events) == 1
		and subtype == 'strong_mix'
		and str(best_voice_event.get('voice_type', '') or '') == 'chest'
		and safe_float(best_voice_event.get('start_time', 0.0)) >= 6.0
		and prior_falsetto_end >= 0.0
		and (safe_float(best_voice_event.get('start_time', 0.0)) - prior_falsetto_end) >= 1.0
		and mean_pitch_hz < 190.0
		and learned_mix_margin < 0.0055
		and mean_rms < 0.0345
		and learned_mix_support < 0.305
	)
	released_softhead_followed_by_low_pitch_chesty_tail = False
	if bool(isolated_mix_snapshot.get('released_midhigh_supported_softhead_mix')):
		isolated_end_time = safe_float(isolated_mix_event.get('end_time', 0.0))
		for voice_event in list(voice_events or []):
			voice_start_time = safe_float(voice_event.get('start_time', 0.0))
			voice_end_time = safe_float(voice_event.get('end_time', 0.0))
			voice_snapshot = dict(voice_event.get('feature_snapshot', {}) or {})
			voice_mix_prob = safe_float(voice_snapshot.get('mix_prob', voice_event.get('mix_prob', 0.0)))
			voice_mix_threshold = safe_float(voice_snapshot.get('mix_threshold', 0.45), 0.45)
			voice_pitch = safe_float(voice_event.get('mean_pitch_hz', voice_snapshot.get('mean_pitch_hz', 0.0)))
			voice_chest_prob = safe_float(voice_event.get('chest_prob', voice_snapshot.get('chest_prob', 0.0)))
			voice_falsetto_prob = safe_float(voice_event.get('falsetto_prob', voice_snapshot.get('falsetto_prob', 0.0)))
			tail_gap = voice_start_time - isolated_end_time
			tail_duration = max(0.0, voice_end_time - voice_start_time)
			if (
				tail_gap >= 0.0
				and tail_gap <= 0.75
				and tail_duration <= 1.2
				and voice_mix_prob >= voice_mix_threshold
				and voice_pitch < 260.0
				and voice_chest_prob >= 0.35
				and voice_falsetto_prob <= 0.70
			):
				released_softhead_followed_by_low_pitch_chesty_tail = True
				break

	blockers: List[str] = []
	if reject_low_learned_prob:
		blockers.append('reject_low_learned_prob')
	if reject_pure_head_low_pitch:
		blockers.append('reject_pure_head_low_pitch')
	if reject_marginal_head:
		blockers.append('reject_marginal_head_not_released')
	if reject_underpowered_low_pitch:
		blockers.append('reject_underpowered_low_pitch_head_mix')
	if reject_borderline_low_mid:
		blockers.append('reject_borderline_low_mid_pitch_head_mix')
	if strong_requires_threshold_block:
		blockers.append('reject_strong_mix_below_threshold')
	if reject_no_subtype:
		blockers.append('reject_no_subtype')
	if reject_low_subtype_conf:
		blockers.append('reject_low_subtype_conf')
	if reject_low_pitch_chesty_mix:
		blockers.append('reject_low_pitch_chesty_mix')
	if reject_high_pitch_headbiased_weak_mix:
		blockers.append('reject_high_pitch_headbiased_weak_mix')
	if reject_low_edge_long_combo_soft_mix:
		blockers.append('reject_low_edge_long_combo_soft_mix')
	if reject_midpitch_pure_head_control:
		blockers.append('reject_midpitch_pure_head_control')
	if reject_low_pitch_strong_mix_chest:
		blockers.append('reject_low_pitch_strong_mix_chest')
	if isolated_low_pitch_chest_tail_mix:
		blockers.append('reject_isolated_low_pitch_chest_tail_mix')
	if released_softhead_followed_by_low_pitch_chesty_tail:
		blockers.append('reject_released_softhead_followed_by_low_pitch_chesty_tail')
	if not blockers:
		blockers.append('passes_rule_core')

	return dbg.to_jsonable({
		'voice_features': {
			'duration': duration,
			'confidence': confidence,
			'strength': strength,
			'probability_margin': probability_margin,
			'chest_prob': chest_prob,
			'falsetto_prob': falsetto_prob,
			'voiced_ratio': voiced_ratio,
			'mean_pitch_hz': mean_pitch_hz,
			'mean_rms': mean_rms,
			'mean_zcr': mean_zcr,
			'stable_ratio': stable_ratio,
			'mean_breath_score': mean_breath_score,
			'breath_hint_ratio': breath_hint_ratio,
			'learned_mix_prob': learned_mix_prob,
			'learned_mix_threshold': learned_mix_threshold,
			'learned_mix_margin': learned_mix_margin,
		},
		'supports': {
			'heuristic_mix_support': heuristic_mix_support,
			'learned_mix_support': learned_mix_support,
			'mix_support': mix_support,
			'pitch_support': pitch_support,
			'stable_support': stable_support,
			'voiced_support': voiced_support,
			'breathiness': breathiness,
			'head_bias': head_bias,
			'chest_bias': chest_bias,
			'weak_mix_support': weak_mix_support,
			'weak_mix_support_floor': weak_mix_support_floor,
			'weak_mix_pitch_floor': weak_mix_pitch_floor,
		},
		'released_flags': {
			'pure_learned_head_mix': pure_learned_head_mix,
			'marginal_head_mix': marginal_head_mix,
			'released_high_pitch_head_mix': released_high_pitch_head_mix,
			'released_near_threshold_high_pitch_head_mix': released_near_threshold_high_pitch_head_mix,
			'released_ultra_high_pitch_head_mix': released_ultra_high_pitch_head_mix,
			'released_high_energy_midhigh_head_mix': released_high_energy_midhigh_head_mix,
			'released_supported_low_pitch_head_mix': released_supported_low_pitch_head_mix,
			'released_lowmid_near_threshold_head_mix': released_lowmid_near_threshold_head_mix,
			'released_midhigh_near_threshold_head_mix': released_midhigh_near_threshold_head_mix,
			'released_ultrahigh_bright_head_point_mix': released_ultrahigh_bright_head_point_mix,
			'released_midchest_near_threshold_head_mix': released_midchest_near_threshold_head_mix,
			'released_low_energy_midhigh_head_mix': released_low_energy_midhigh_head_mix,
			'released_sustained_highpitch_marginal_head_mix': released_sustained_highpitch_marginal_head_mix,
			'released_midpitch_lowchest_pure_head_mix': released_midpitch_lowchest_pure_head_mix,
			'released_short_lowpitch_marginal_head_mix': released_short_lowpitch_marginal_head_mix,
			'released_midpitch_underpowered_pure_head_mix': released_midpitch_underpowered_pure_head_mix,
			'released_midhigh_balanced_pure_head_mix': released_midhigh_balanced_pure_head_mix,
			'released_underpowered_short_lowpitch_head_mix': released_underpowered_short_lowpitch_head_mix,
			'released_midpitch_long_lowenergy_marginal_head_mix': released_midpitch_long_lowenergy_marginal_head_mix,
			'released_midhigh_nearthreshold_softhead_long_mix': released_midhigh_nearthreshold_softhead_long_mix,
			'released_highpitch_nearthreshold_supported_head_mix': released_highpitch_nearthreshold_supported_head_mix,
			'released_highpitch_long_lowprob_softhead_mix': released_highpitch_long_lowprob_softhead_mix,
			'released_midlow_balanced_lowprob_softhead_mix': released_midlow_balanced_lowprob_softhead_mix,
			'released_lowmid_chesty_lowprob_softhead_mix': released_lowmid_chesty_lowprob_softhead_mix,
			'released_short_lowpitch_supported_softhead_mix': released_short_lowpitch_supported_softhead_mix,
			'released_nearthreshold_extreme_energy_softhead_mix': released_nearthreshold_extreme_energy_softhead_mix,
			'released_sustained_highpitch_lowprob_softhead_mix': released_sustained_highpitch_lowprob_softhead_mix,
			'released_midhigh_long_lowprob_softhead_mix': released_midhigh_long_lowprob_softhead_mix,
			'released_midhigh_moderate_energy_lowprob_softhead_mix': released_midhigh_moderate_energy_lowprob_softhead_mix,
			'released_highpitch_long_moderate_energy_lowprob_softhead_mix': released_highpitch_long_moderate_energy_lowprob_softhead_mix,
			'released_highpitch_headbiased_combination_soft_mix': released_highpitch_headbiased_combination_soft_mix,
			'released_highpitch_chesty_nearthreshold_mix': released_highpitch_chesty_nearthreshold_mix,
			'released_ultrahigh_lowchest_zero_support_mix': released_ultrahigh_lowchest_zero_support_mix,
			'released_midhigh_headbiased_zero_support_mix': released_midhigh_headbiased_zero_support_mix,
			'released_short_lowmid_supported_headbias_mix': released_short_lowmid_supported_headbias_mix,
			'released_supportful_midhigh_nearthreshold_mix': released_supportful_midhigh_nearthreshold_mix,
			'released_supportful_highpitch_nearthreshold_airy_mix': released_supportful_highpitch_nearthreshold_airy_mix,
			'released_supportful_highpitch_nearthreshold_dense_mix': released_supportful_highpitch_nearthreshold_dense_mix,
			'released_balanced_supported_softhead_mix': released_balanced_supported_softhead_mix,
			'released_midhigh_supported_softhead_mix': released_midhigh_supported_softhead_mix,
			'underpowered_low_pitch_head_mix': underpowered_low_pitch_head_mix,
			'borderline_low_mid_pitch_head_mix': borderline_low_mid_pitch_head_mix,
		},
		'subtype_eval': {
			'candidate_subtype': subtype,
			'candidate_subtype_conf': subtype_conf,
			'candidate_subtype_mix_support': subtype_mix_support,
			'reject_low_pitch_chesty_mix': reject_low_pitch_chesty_mix,
			'reject_high_pitch_headbiased_weak_mix': reject_high_pitch_headbiased_weak_mix,
			'reject_low_edge_long_combo_soft_mix': reject_low_edge_long_combo_soft_mix,
			'reject_midpitch_pure_head_control': reject_midpitch_pure_head_control,
			'reject_low_pitch_strong_mix_chest': reject_low_pitch_strong_mix_chest,
			'reject_released_softhead_followed_by_low_pitch_chesty_tail': released_softhead_followed_by_low_pitch_chesty_tail,
			'strong_requires_threshold_block': strong_requires_threshold_block,
		},
		'blockers': blockers,
	})


def diagnose_sample(item: Dict[str, Any]) -> Dict[str, Any]:
	analysis = dict(item.get('analysis', {}) or {})
	voice_events = list(analysis.get('voice_events', []) or [])
	mix_events = list(analysis.get('mix_events', []) or [])
	summary = reg.summarize_sample(item)
	best_voice_event = select_best_voice_event(voice_events)
	strongest_mix_event = select_strongest_mix_event(mix_events)
	return {
		'item_name': str(summary.get('item_name', '') or ''),
		'group_name': str(summary.get('group_name', '') or ''),
		'song_name': str(summary.get('song_name', '') or ''),
		'singer': str(summary.get('singer', '') or ''),
		'binary_role': str(summary.get('binary_role', '') or ''),
		'outcome': str(summary.get('outcome', '') or ''),
		'miss_reason': str(summary.get('miss_reason', '') or ''),
		'mix_event_count': int(summary.get('mix_event_count', 0) or 0),
		'weak_mix_count': int(summary.get('weak_mix_count', 0) or 0),
		'strong_mix_count': int(summary.get('strong_mix_count', 0) or 0),
		'best_voice_mix_margin': dbg.to_jsonable(safe_float(summary.get('best_voice_mix_margin', 0.0))),
		'best_voice_event': compact_voice_event(best_voice_event),
		'voice_rule_diagnosis': evaluate_mix_rule(best_voice_event, voice_events, mix_events),
		'strongest_mix_event': compact_mix_event(strongest_mix_event),
		'voice_debug': dbg.to_jsonable(dict(analysis.get('voice_debug', {}) or {})),
	}


def main() -> int:
	args = parse_args()
	manifest_path = Path(args.manifest).resolve()
	if not manifest_path.exists():
		print(f'manifest not found: {manifest_path}', file=sys.stderr)
		return 2
	rows = load_selected_rows(manifest_path, list(args.item_name or []))
	checkpoint_paths = [resolve_checkpoint(path_text) for path_text in list(args.artifact or [])]
	output_path = Path(args.output).resolve()
	output_path.parent.mkdir(parents=True, exist_ok=True)
	use_fresh_process = bool(args.fresh_process_per_sample)
	use_fresh_runtime = bool(args.fresh_runtime_per_sample)
	if use_fresh_process and use_fresh_runtime:
		print('--fresh-process-per-sample cannot be combined with --fresh-runtime-per-sample', file=sys.stderr)
		return 2

	app = None
	try:
		module = None
		ui = None
		if not use_fresh_runtime and not use_fresh_process:
			app, module, ui, _ = dbg.load_runtime(False)
		report: Dict[str, Any] = {
			'manifest': str(manifest_path),
			'item_names': [str(item.get('item_name', '') or '') for item in rows],
			'artifacts': [],
		}
		for checkpoint_path in checkpoint_paths:
			artifact_samples: List[Dict[str, Any]] = []
			if use_fresh_process:
				for row in rows:
					artifact_samples.append(diagnose_row_with_fresh_subprocess(manifest_path, checkpoint_path, row))
			elif use_fresh_runtime:
				for row in rows:
					artifact_samples.append(diagnose_row_with_fresh_runtime(checkpoint_path, row))
			else:
				module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint_path,)
				reset_mix_runtime_cache(ui)
				for row in rows:
					reset_mix_runtime_cache(ui)
					item = reg.analyze_sample(app, module, ui, row)
					artifact_samples.append(diagnose_sample(item))
			artifact_report = {
				'checkpoint': str(checkpoint_path),
				'samples': artifact_samples,
			}
			report['artifacts'].append(artifact_report)
		output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
		print(json.dumps({'output_path': str(output_path), 'artifact_count': len(report['artifacts']), 'sample_count': len(rows)}, ensure_ascii=False), flush=True)
		return 0
	finally:
		if app is not None:
			try:
				app.quit()
			except Exception:
				pass


if __name__ == '__main__':
	raise SystemExit(main())