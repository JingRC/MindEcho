import argparse
import csv
import gc
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from diagnose_mix_rule_selected_samples import diagnose_sample, reset_mix_runtime_cache, resolve_checkpoint
from prepare_mix_binary_manifests import read_manifest, row_priority, score_rows_with_artifact

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg


POSITIVE_FAMILY_MARGINAL = 'reject_marginal_head_not_released'
POSITIVE_FAMILY_NO_SUBTYPE = 'reject_no_subtype'
RELEASED_POSITIVE_FLAGS = (
	'released_high_pitch_head_mix',
	'released_near_threshold_high_pitch_head_mix',
	'released_ultra_high_pitch_head_mix',
	'released_low_energy_midhigh_head_mix',
)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description='Mine split train-side voice-event families and emit a conservative marginal-plus-control increment.'
	)
	parser.add_argument('--train-manifest', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_core\train_manifest.csv')
	parser.add_argument('--artifact-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu')
	parser.add_argument('--output-dir', required=True)
	parser.add_argument('--preselect-count', type=int, default=96)
	parser.add_argument('--preselect-sort-mode', choices=['threshold_proximity', 'lowest_mix_prob'], default='threshold_proximity')
	parser.add_argument('--preselect-max-per-singer', type=int, default=32)
	parser.add_argument('--preselect-max-per-song', type=int, default=8)
	parser.add_argument('--preselect-max-per-singer-song', type=int, default=4)
	parser.add_argument('--marginal-keep-count', type=int, default=24)
	parser.add_argument('--no-subtype-keep-count', type=int, default=24)
	parser.add_argument('--min-pitch-hz', type=float, default=430.0)
	parser.add_argument('--min-head-bias', type=float, default=0.92)
	parser.add_argument('--runtime-margin-min', type=float, default=-0.10)
	parser.add_argument('--runtime-margin-max', type=float, default=0.03)
	parser.add_argument('--allow-blocker', action='append', dest='allow_blockers', default=[])
	parser.add_argument('--max-per-singer', type=int, default=12)
	parser.add_argument('--max-per-song', type=int, default=4)
	parser.add_argument('--max-per-singer-song', type=int, default=2)
	parser.add_argument('--control-preselect-count', type=int, default=96)
	parser.add_argument('--control-preselect-sort-mode', choices=['highest_mix_prob', 'highest_margin', 'threshold_proximity'], default='highest_mix_prob')
	parser.add_argument('--control-preselect-max-per-singer', type=int, default=32)
	parser.add_argument('--control-preselect-max-per-song', type=int, default=8)
	parser.add_argument('--control-preselect-max-per-singer-song', type=int, default=4)
	parser.add_argument('--control-keep-count', type=int, default=24)
	parser.add_argument('--control-min-head-bias', type=float, default=0.70)
	parser.add_argument('--control-runtime-margin-min', type=float, default=0.0)
	parser.add_argument('--control-runtime-margin-max', type=float, default=0.18)
	parser.add_argument('--control-allow-blocker', action='append', dest='control_allow_blockers', default=[])
	parser.add_argument('--control-max-per-singer', type=int, default=12)
	parser.add_argument('--control-max-per-song', type=int, default=4)
	parser.add_argument('--control-max-per-singer-song', type=int, default=2)
	parser.add_argument('--combined-positive-family', choices=['marginal_only', 'both'], default='marginal_only')
	parser.add_argument('--eval-window-count', type=int, default=3)
	parser.add_argument('--eval-window-aggregation', default='mean')
	parser.add_argument('--eval-window-consistency-penalty', type=float, default=0.0)
	parser.add_argument('--eval-window-support-threshold', type=float, default=0.40)
	parser.add_argument('--eval-window-min-support-windows', type=int, default=2)
	parser.add_argument('--eval-window-high-support-threshold', type=float, default=0.55)
	parser.add_argument('--eval-window-min-high-support-windows', type=int, default=1)
	parser.add_argument('--score-batch-size', type=int, default=16)
	parser.add_argument('--score-row-chunk-size', type=int, default=256)
	parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
	parser.add_argument('--runtime-chunk-size', type=int, default=12)
	parser.add_argument('--no-cache-reuse', action='store_true')
	return parser.parse_args()


def derive_fieldnames(*row_groups: Sequence[Dict[str, Any]]) -> List[str]:
	fieldnames: List[str] = []
	seen: set[str] = set()
	for rows in row_groups:
		for row in rows:
			for key in row.keys():
				name = str(key)
				if name.startswith('_'):
					continue
				if name not in seen:
					seen.add(name)
					fieldnames.append(name)
	if not fieldnames:
		fieldnames = ['item_name']
	return fieldnames


def write_rows(path: Path, rows: Sequence[Dict[str, Any]], *, reference_rows: Sequence[Dict[str, Any]] = ()) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = derive_fieldnames(rows, reference_rows)
	with path.open('w', encoding='utf-8', newline='') as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		for row in rows:
			writer.writerow({key: value for key, value in row.items() if not str(key).startswith('_')})


def strip_internal_fields(row: Dict[str, Any]) -> Dict[str, Any]:
	return {key: value for key, value in dict(row or {}).items() if not str(key).startswith('_')}


def payload_with_diagnosis(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
	return [strip_internal_fields(row) | {'diagnosis': dict(row.get('_diagnosis', {}) or {})} for row in rows]


def as_float(row: Dict[str, Any], key: str) -> float:
	try:
		return float(row.get(key, 0.0) or 0.0)
	except Exception:
		return 0.0


def row_cache_key(row: Dict[str, Any]) -> str:
	item_name = str(row.get('item_name', '') or '').strip()
	if item_name:
		return item_name
	return json.dumps(strip_internal_fields(row), ensure_ascii=False, sort_keys=True)


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def release_process_memory() -> None:
	gc.collect()
	try:
		import torch
		if torch.cuda.is_available():
			torch.cuda.empty_cache()
	except Exception:
		pass


def score_rows_with_cache(
	rows: Sequence[Dict[str, Any]],
	*,
	cache_manifest_path: Path,
	cache_meta_path: Path,
	expected_cache_meta: Dict[str, Any],
	reuse_cache: bool,
	artifact_dir: Path,
	eval_window_count: int,
	eval_window_aggregation: str,
	eval_window_consistency_penalty: float,
	eval_window_support_threshold: float,
	eval_window_min_support_windows: int,
	eval_window_high_support_threshold: float,
	eval_window_min_high_support_windows: int,
	score_batch_size: int,
	score_row_chunk_size: int,
	device: str,
) -> List[Dict[str, Any]]:
	def load_cache_prefix() -> List[Dict[str, Any]]:
		if not cache_manifest_path.exists() or not cache_meta_path.exists():
			return []
		try:
			cached_meta = json.loads(cache_meta_path.read_text(encoding='utf-8'))
			if cached_meta != expected_cache_meta:
				return []
			cached_rows = read_manifest(cache_manifest_path)
		except Exception:
			return []
		prefix_length = min(len(cached_rows), len(rows))
		for index in range(prefix_length):
			if row_cache_key(cached_rows[index]) != row_cache_key(rows[index]):
				return []
		return cached_rows[:prefix_length]

	resolved_chunk_size = max(1, int(score_row_chunk_size or len(rows) or 1))
	cached_rows: List[Dict[str, Any]] = load_cache_prefix() if reuse_cache else []
	if cached_rows:
		if len(cached_rows) >= len(rows):
			print(f'phase_cache_hit name={cache_manifest_path.stem} rows={len(rows)}', flush=True)
			return cached_rows[:len(rows)]
		print(
			f'phase_cache_resume name={cache_manifest_path.stem} cached_rows={len(cached_rows)} total_rows={len(rows)} chunk_size={resolved_chunk_size}',
			flush=True,
		)
	else:
		print(
			f'phase_cache_miss name={cache_manifest_path.stem} rows={len(rows)} chunk_size={resolved_chunk_size}',
			flush=True,
		)

	for start_idx in range(len(cached_rows), len(rows), resolved_chunk_size):
		end_idx = min(start_idx + resolved_chunk_size, len(rows))
		chunk_rows = list(rows[start_idx:end_idx])
		print(
			f'phase_cache_scoring_chunk name={cache_manifest_path.stem} rows={start_idx + 1}-{end_idx}/{len(rows)}',
			flush=True,
		)
		chunk_scores = score_rows_with_artifact(
			chunk_rows,
			artifact_dir=artifact_dir,
			eval_window_count=int(eval_window_count),
			eval_window_aggregation=str(eval_window_aggregation),
			eval_window_consistency_penalty=float(eval_window_consistency_penalty),
			eval_window_support_threshold=float(eval_window_support_threshold),
			eval_window_min_support_windows=int(eval_window_min_support_windows),
			eval_window_high_support_threshold=float(eval_window_high_support_threshold),
			eval_window_min_high_support_windows=int(eval_window_min_high_support_windows),
			batch_size=int(score_batch_size),
			device_override=str(device),
		)
		cached_rows.extend(chunk_scores)
		write_rows(cache_manifest_path, [strip_internal_fields(row) for row in cached_rows], reference_rows=rows)
		write_json(cache_meta_path, expected_cache_meta)
		release_process_memory()

	return cached_rows[:len(rows)]


def load_diagnosis_cache(cache_path: Path, checkpoint_path: Path) -> Dict[str, Dict[str, Any]]:
	if not cache_path.exists():
		return {}
	try:
		payload = json.loads(cache_path.read_text(encoding='utf-8'))
	except Exception:
		return {}
	if str(payload.get('checkpoint_path', '') or '') != str(checkpoint_path):
		return {}
	cached_rows: Dict[str, Dict[str, Any]] = {}
	for cached in list(payload.get('rows', []) or []):
		item = strip_internal_fields(dict(cached or {}))
		item.pop('diagnosis', None)
		item['_diagnosis'] = dict(cached.get('diagnosis', {}) or {})
		cached_rows[row_cache_key(item)] = item
	return cached_rows


def save_diagnosis_cache(cache_path: Path, checkpoint_path: Path, rows: Sequence[Dict[str, Any]]) -> None:
	write_json(
		cache_path,
		{
			'checkpoint_path': str(checkpoint_path),
			'rows': payload_with_diagnosis(rows),
		},
	)


def select_diverse_rows(
	rows: Iterable[Dict[str, Any]],
	keep_count: int,
	*,
	max_per_singer: int,
	max_per_song: int,
	max_per_singer_song: int,
) -> List[Dict[str, Any]]:
	selected: List[Dict[str, Any]] = []
	singer_counts: Counter[str] = Counter()
	song_counts: Counter[str] = Counter()
	singer_song_counts: Counter[tuple[str, str]] = Counter()
	for row in rows:
		singer = str(row.get('singer', '') or '')
		song_name = str(row.get('song_name', '') or '')
		singer_key = singer
		song_key = song_name
		singer_song_key = (singer, song_name)
		if singer_counts[singer_key] >= max_per_singer:
			continue
		if song_counts[song_key] >= max_per_song:
			continue
		if singer_song_counts[singer_song_key] >= max_per_singer_song:
			continue
		selected.append(dict(row))
		singer_counts[singer_key] += 1
		song_counts[song_key] += 1
		singer_song_counts[singer_song_key] += 1
		if len(selected) >= keep_count:
			break
	return selected


def load_artifact_threshold(artifact_dir: Path) -> float:
	summary_path = artifact_dir / 'training_summary.json'
	try:
		payload = json.loads(summary_path.read_text(encoding='utf-8'))
		return float(payload.get('best_threshold', 0.45) or 0.45)
	except Exception:
		return 0.45


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
	return {
		'items': len(rows),
		'labels': dict(Counter(str(int(float(row.get('mix', 0) or 0))) for row in rows)),
		'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
		'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
		'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
		'branches': dict(Counter(str(row.get('family_branch', '') or '') for row in rows)),
		'blockers': dict(Counter(str(row.get('family_primary_blocker', '') or '') for row in rows)),
	}


def positive_sort_key(row: Dict[str, Any], mode: str) -> tuple:
	sort_mode = str(mode or 'threshold_proximity').strip().lower()
	if sort_mode == 'lowest_mix_prob':
		return (
			as_float(row, 'mined_mix_prob'),
			*row_priority(row),
		)
	return (
		abs(as_float(row, 'mined_mix_margin')),
		as_float(row, 'mined_mix_prob'),
		*row_priority(row),
	)


def control_preselect_sort_key(row: Dict[str, Any], mode: str) -> tuple:
	sort_mode = str(mode or 'highest_mix_prob').strip().lower()
	if sort_mode == 'highest_margin':
		return (
			-as_float(row, 'mined_mix_margin'),
			-as_float(row, 'mined_mix_prob'),
			*row_priority(row),
		)
	if sort_mode == 'threshold_proximity':
		return (
			abs(as_float(row, 'mined_mix_margin')),
			-as_float(row, 'mined_mix_prob'),
			*row_priority(row),
		)
	return (
		-as_float(row, 'mined_mix_prob'),
		-as_float(row, 'mined_mix_margin'),
		*row_priority(row),
	)


def positive_family_sort_key(row: Dict[str, Any]) -> tuple:
	return (
		abs(as_float(row, 'family_runtime_margin')),
		-as_float(row, 'family_runtime_pitch_hz'),
		-as_float(row, 'family_runtime_head_bias'),
		as_float(row, 'mined_mix_prob'),
		*row_priority(row),
	)


def control_guard_sort_key(row: Dict[str, Any]) -> tuple:
	blockers = set(str(token or '') for token in str(row.get('family_blockers', '') or '').split('|') if str(token or ''))
	if 'reject_pure_head_low_pitch' in blockers:
		blocker_priority = 0
	elif POSITIVE_FAMILY_MARGINAL in blockers:
		blocker_priority = 1
	elif POSITIVE_FAMILY_NO_SUBTYPE in blockers:
		blocker_priority = 2
	else:
		blocker_priority = 3
	return (
		blocker_priority,
		-as_float(row, 'family_runtime_margin'),
		-as_float(row, 'family_runtime_head_bias'),
		-as_float(row, 'mined_mix_prob'),
		*row_priority(row),
	)


def get_rule_context(diagnosis: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], List[str], Dict[str, Any]]:
	rule = dict(diagnosis.get('voice_rule_diagnosis', {}) or {})
	voice_features = dict(rule.get('voice_features', {}) or {})
	supports = dict(rule.get('supports', {}) or {})
	flags = dict(rule.get('released_flags', {}) or {})
	blockers = [str(token or '') for token in list(rule.get('blockers', []) or []) if str(token or '')]
	best_voice_event = dict(diagnosis.get('best_voice_event', {}) or {})
	return rule, voice_features, supports, flags, blockers, best_voice_event


def resolve_positive_family_branch(diagnosis: Dict[str, Any]) -> str:
	_rule, _voice_features, _supports, flags, blockers, _best_voice_event = get_rule_context(diagnosis)
	if bool(flags.get('marginal_head_mix', False)) and not any(bool(flags.get(name, False)) for name in RELEASED_POSITIVE_FLAGS):
		return POSITIVE_FAMILY_MARGINAL
	if POSITIVE_FAMILY_NO_SUBTYPE in blockers:
		return POSITIVE_FAMILY_NO_SUBTYPE
	return str(blockers[0] if blockers else '')


def enrich_with_family_fields(row: Dict[str, Any], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
	item = dict(row)
	rule, voice_features, supports, flags, blockers, best_voice_event = get_rule_context(diagnosis)
	subtype_eval = dict(rule.get('subtype_eval', {}) or {})
	item['family_best_voice_mix_margin'] = f'{float(diagnosis.get("best_voice_mix_margin", 0.0) or 0.0):.6f}'
	item['family_runtime_margin'] = f'{float(voice_features.get("learned_mix_margin", 0.0) or 0.0):.6f}'
	item['family_runtime_pitch_hz'] = f'{float(voice_features.get("mean_pitch_hz", 0.0) or 0.0):.6f}'
	item['family_runtime_head_bias'] = f'{float(supports.get("head_bias", 0.0) or 0.0):.6f}'
	item['family_runtime_mix_support'] = f'{float(supports.get("mix_support", 0.0) or 0.0):.6f}'
	item['family_runtime_learned_mix_support'] = f'{float(supports.get("learned_mix_support", 0.0) or 0.0):.6f}'
	item['family_runtime_mix_event_count'] = str(int(diagnosis.get('mix_event_count', 0) or 0))
	item['family_primary_blocker'] = str(blockers[0] if blockers else '')
	item['family_blockers'] = '|'.join(blockers)
	item['family_branch'] = resolve_positive_family_branch(diagnosis)
	item['family_candidate_subtype'] = str(subtype_eval.get('candidate_subtype', '') or '')
	item['family_candidate_subtype_conf'] = f'{float(subtype_eval.get("candidate_subtype_conf", 0.0) or 0.0):.6f}'
	item['family_best_voice_event_type'] = str(best_voice_event.get('event_type', '') or '')
	item['family_released_flags'] = '|'.join(sorted(key for key, value in flags.items() if value))
	item['family_flag_pure_learned_head_mix'] = '1' if bool(flags.get('pure_learned_head_mix', False)) else '0'
	item['family_flag_marginal_head_mix'] = '1' if bool(flags.get('marginal_head_mix', False)) else '0'
	item['family_flag_released_high_pitch_head_mix'] = '1' if bool(flags.get('released_high_pitch_head_mix', False)) else '0'
	item['family_flag_released_near_threshold_high_pitch_head_mix'] = '1' if bool(flags.get('released_near_threshold_high_pitch_head_mix', False)) else '0'
	item['family_flag_released_ultra_high_pitch_head_mix'] = '1' if bool(flags.get('released_ultra_high_pitch_head_mix', False)) else '0'
	item['family_flag_released_low_energy_midhigh_head_mix'] = '1' if bool(flags.get('released_low_energy_midhigh_head_mix', False)) else '0'
	return item


def diagnose_rows_with_runtime(
	rows: Sequence[Dict[str, Any]],
	checkpoint_path: Path,
	*,
	chunk_size: int,
	cache_path: Path,
	reuse_cache: bool,
) -> List[Dict[str, Any]]:
	ordered_keys = [row_cache_key(row) for row in rows]
	cached_rows = load_diagnosis_cache(cache_path, checkpoint_path) if reuse_cache else {}
	pending_rows = [dict(row) for row in rows if row_cache_key(row) not in cached_rows]
	resolved_chunk_size = max(1, int(chunk_size or 1))
	if pending_rows:
		total_chunks = (len(pending_rows) + resolved_chunk_size - 1) // resolved_chunk_size
		for chunk_index, start_idx in enumerate(range(0, len(pending_rows), resolved_chunk_size), start=1):
			chunk_rows = pending_rows[start_idx:start_idx + resolved_chunk_size]
			app = None
			try:
				print(
					f'runtime_diagnosis_chunk={chunk_index}/{total_chunks} rows={len(chunk_rows)} checkpoint={checkpoint_path.parent.name}',
					flush=True,
				)
				app, module, ui, _ = dbg.load_runtime(False)
				module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint_path,)
				reset_mix_runtime_cache(ui)
				for row in chunk_rows:
					item = reg.analyze_sample(app, module, ui, row)
					diagnosis = diagnose_sample(item)
					enriched = enrich_with_family_fields(row, diagnosis)
					enriched['_diagnosis'] = diagnosis
					cached_rows[row_cache_key(row)] = enriched
			finally:
				if app is not None:
					try:
						app.quit()
					except Exception:
						pass
				release_process_memory()
			save_diagnosis_cache(
				cache_path,
				checkpoint_path,
				[cached_rows[key] for key in ordered_keys if key in cached_rows],
			)
	result: List[Dict[str, Any]] = []
	for row, key in zip(rows, ordered_keys):
		cached = cached_rows.get(key)
		if cached is None:
			raise RuntimeError(f'missing runtime diagnosis cache for {row.get("item_name", "") or key}')
		result.append(dict(cached))
	return result


def filter_positive_family_rows(rows: Sequence[Dict[str, Any]], args: argparse.Namespace, *, branch_name: str, allow_blockers: Sequence[str]) -> List[Dict[str, Any]]:
	selected: List[Dict[str, Any]] = []
	for row in rows:
		diagnosis = dict(row.get('_diagnosis', {}) or {})
		_rule, voice_features, supports, flags, blockers, best_voice_event = get_rule_context(diagnosis)
		if str(diagnosis.get('binary_role', '') or '') != 'positive_mix':
			continue
		if int(diagnosis.get('mix_event_count', 0) or 0) != 0:
			continue
		if str(diagnosis.get('outcome', '') or '') == 'hit':
			continue
		if str(best_voice_event.get('event_type', '') or '') != 'falsetto':
			continue
		if float(voice_features.get('mean_pitch_hz', 0.0) or 0.0) < float(args.min_pitch_hz):
			continue
		if float(supports.get('head_bias', 0.0) or 0.0) < float(args.min_head_bias):
			continue
		margin = float(voice_features.get('learned_mix_margin', 0.0) or 0.0)
		if margin < float(args.runtime_margin_min) or margin > float(args.runtime_margin_max):
			continue
		resolved_branch = resolve_positive_family_branch(diagnosis)
		if branch_name == POSITIVE_FAMILY_MARGINAL:
			if resolved_branch != POSITIVE_FAMILY_MARGINAL:
				continue
			if not bool(flags.get('marginal_head_mix', False)):
				continue
			if any(bool(flags.get(name, False)) for name in RELEASED_POSITIVE_FLAGS):
				continue
		elif branch_name == POSITIVE_FAMILY_NO_SUBTYPE:
			if resolved_branch != POSITIVE_FAMILY_NO_SUBTYPE:
				continue
			if bool(flags.get('marginal_head_mix', False)):
				continue
			if POSITIVE_FAMILY_NO_SUBTYPE not in blockers:
				continue
		else:
			continue
		if allow_blockers and resolved_branch not in allow_blockers and not any(blocker in allow_blockers for blocker in blockers):
			continue
		selected.append(dict(row))
	selected.sort(key=positive_family_sort_key)
	return selected


def filter_control_guard_rows(rows: Sequence[Dict[str, Any]], args: argparse.Namespace, *, allow_blockers: Sequence[str]) -> List[Dict[str, Any]]:
	selected: List[Dict[str, Any]] = []
	for row in rows:
		diagnosis = dict(row.get('_diagnosis', {}) or {})
		_rule, voice_features, supports, flags, blockers, best_voice_event = get_rule_context(diagnosis)
		if str(diagnosis.get('binary_role', '') or '') != 'control_negative':
			continue
		if int(diagnosis.get('mix_event_count', 0) or 0) != 0:
			continue
		if str(diagnosis.get('outcome', '') or '') not in {'clean', 'no_mix', 'miss'}:
			continue
		if str(best_voice_event.get('event_type', '') or '') != 'falsetto':
			continue
		if not bool(flags.get('pure_learned_head_mix', False)):
			continue
		if float(supports.get('head_bias', 0.0) or 0.0) < float(args.control_min_head_bias):
			continue
		margin = float(voice_features.get('learned_mix_margin', 0.0) or 0.0)
		if margin < float(args.control_runtime_margin_min) or margin > float(args.control_runtime_margin_max):
			continue
		if allow_blockers and not any(blocker in allow_blockers for blocker in blockers):
			continue
		selected.append(dict(row))
	selected.sort(key=control_guard_sort_key)
	return selected


def tag_rows(rows: Sequence[Dict[str, Any]], bucket_name: str) -> List[Dict[str, Any]]:
	tagged: List[Dict[str, Any]] = []
	for row in rows:
		item = dict(row)
		item['family_bucket'] = str(bucket_name)
		tagged.append(item)
	return tagged


def dedupe_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
	result: List[Dict[str, Any]] = []
	seen: set[str] = set()
	for row in rows:
		item_name = str(row.get('item_name', '') or '').strip()
		key = item_name or json.dumps(strip_internal_fields(row), ensure_ascii=False, sort_keys=True)
		if key in seen:
			continue
		seen.add(key)
		result.append(dict(row))
	return result


def main() -> int:
	args = parse_args()
	train_manifest = Path(args.train_manifest).resolve()
	artifact_dir = Path(args.artifact_dir).resolve()
	output_dir = Path(args.output_dir).resolve()
	if not train_manifest.exists():
		raise FileNotFoundError(f'train manifest not found: {train_manifest}')
	if not artifact_dir.exists():
		raise FileNotFoundError(f'artifact dir not found: {artifact_dir}')
	output_dir.mkdir(parents=True, exist_ok=True)
	cache_dir = output_dir / '_cache'
	cache_dir.mkdir(parents=True, exist_ok=True)
	reuse_cache = not bool(args.no_cache_reuse)

	train_rows = read_manifest(train_manifest)
	train_row_count = len(train_rows)
	artifact_threshold = load_artifact_threshold(artifact_dir)
	positive_source_rows = [
		dict(row)
		for row in train_rows
		if int(float(row.get('mix', 0) or 0)) == 1 and str(row.get('binary_role', '') or '') == 'positive_mix'
	]
	positive_rows = score_rows_with_cache(
		positive_source_rows,
		cache_manifest_path=cache_dir / 'positive_scored_manifest.csv',
		cache_meta_path=cache_dir / 'positive_scored_manifest.meta.json',
		expected_cache_meta={
			'role': 'positive_mix',
			'train_manifest': str(train_manifest),
			'artifact_dir': str(artifact_dir),
			'row_count': len(positive_source_rows),
			'eval_window_count': int(args.eval_window_count),
			'eval_window_aggregation': str(args.eval_window_aggregation),
			'eval_window_consistency_penalty': float(args.eval_window_consistency_penalty),
			'eval_window_support_threshold': float(args.eval_window_support_threshold),
			'eval_window_min_support_windows': int(args.eval_window_min_support_windows),
			'eval_window_high_support_threshold': float(args.eval_window_high_support_threshold),
			'eval_window_min_high_support_windows': int(args.eval_window_min_high_support_windows),
			'score_batch_size': int(args.score_batch_size),
			'device': str(args.device),
		},
		reuse_cache=reuse_cache,
		artifact_dir=artifact_dir,
		eval_window_count=int(args.eval_window_count),
		eval_window_aggregation=str(args.eval_window_aggregation),
		eval_window_consistency_penalty=float(args.eval_window_consistency_penalty),
		eval_window_support_threshold=float(args.eval_window_support_threshold),
		eval_window_min_support_windows=int(args.eval_window_min_support_windows),
		eval_window_high_support_threshold=float(args.eval_window_high_support_threshold),
		eval_window_min_high_support_windows=int(args.eval_window_min_high_support_windows),
		score_batch_size=int(args.score_batch_size),
			score_row_chunk_size=int(args.score_row_chunk_size),
		device=str(args.device),
	)
	for row in positive_rows:
		row['mined_mix_margin'] = f'{(float(row.get("mined_mix_prob", 0.0) or 0.0) - artifact_threshold):.6f}'
	positive_rows.sort(key=lambda row: positive_sort_key(row, str(args.preselect_sort_mode)))
	positive_pool_count = len(positive_rows)
	preselected_positive_rows = select_diverse_rows(
		positive_rows,
		int(args.preselect_count),
		max_per_singer=int(args.preselect_max_per_singer),
		max_per_song=int(args.preselect_max_per_song),
		max_per_singer_song=int(args.preselect_max_per_singer_song),
	)
	positive_rows = []
	positive_source_rows = []
	release_process_memory()

	control_source_rows = [
		dict(row)
		for row in train_rows
		if int(float(row.get('mix', 0) or 0)) == 0 and str(row.get('binary_role', '') or '') == 'control_negative'
	]
	train_rows = []
	release_process_memory()
	control_rows = score_rows_with_cache(
		control_source_rows,
		cache_manifest_path=cache_dir / 'control_scored_manifest.csv',
		cache_meta_path=cache_dir / 'control_scored_manifest.meta.json',
		expected_cache_meta={
			'role': 'control_negative',
			'train_manifest': str(train_manifest),
			'artifact_dir': str(artifact_dir),
			'row_count': len(control_source_rows),
			'eval_window_count': int(args.eval_window_count),
			'eval_window_aggregation': str(args.eval_window_aggregation),
			'eval_window_consistency_penalty': float(args.eval_window_consistency_penalty),
			'eval_window_support_threshold': float(args.eval_window_support_threshold),
			'eval_window_min_support_windows': int(args.eval_window_min_support_windows),
			'eval_window_high_support_threshold': float(args.eval_window_high_support_threshold),
			'eval_window_min_high_support_windows': int(args.eval_window_min_high_support_windows),
			'score_batch_size': int(args.score_batch_size),
			'device': str(args.device),
		},
		reuse_cache=reuse_cache,
		artifact_dir=artifact_dir,
		eval_window_count=int(args.eval_window_count),
		eval_window_aggregation=str(args.eval_window_aggregation),
		eval_window_consistency_penalty=float(args.eval_window_consistency_penalty),
		eval_window_support_threshold=float(args.eval_window_support_threshold),
		eval_window_min_support_windows=int(args.eval_window_min_support_windows),
		eval_window_high_support_threshold=float(args.eval_window_high_support_threshold),
		eval_window_min_high_support_windows=int(args.eval_window_min_high_support_windows),
		score_batch_size=int(args.score_batch_size),
			score_row_chunk_size=int(args.score_row_chunk_size),
		device=str(args.device),
	)
	for row in control_rows:
		row['mined_mix_margin'] = f'{(float(row.get("mined_mix_prob", 0.0) or 0.0) - artifact_threshold):.6f}'
	control_rows.sort(key=lambda row: control_preselect_sort_key(row, str(args.control_preselect_sort_mode)))
	control_pool_count = len(control_rows)
	preselected_control_rows = select_diverse_rows(
		control_rows,
		int(args.control_preselect_count),
		max_per_singer=int(args.control_preselect_max_per_singer),
		max_per_song=int(args.control_preselect_max_per_song),
		max_per_singer_song=int(args.control_preselect_max_per_singer_song),
	)
	control_rows = []
	control_source_rows = []
	release_process_memory()

	checkpoint_path = resolve_checkpoint(str(artifact_dir))
	diagnosed_positive_rows = diagnose_rows_with_runtime(
		preselected_positive_rows,
		checkpoint_path,
		chunk_size=int(args.runtime_chunk_size),
		cache_path=cache_dir / 'positive_preselected_diagnosis_cache.json',
		reuse_cache=reuse_cache,
	)
	release_process_memory()
	diagnosed_control_rows = diagnose_rows_with_runtime(
		preselected_control_rows,
		checkpoint_path,
		chunk_size=int(args.runtime_chunk_size),
		cache_path=cache_dir / 'control_preselected_diagnosis_cache.json',
		reuse_cache=reuse_cache,
	)
	release_process_memory()
	diagnosed_rows = list(diagnosed_positive_rows) + list(diagnosed_control_rows)

	positive_allow_blockers = tuple(args.allow_blockers or [POSITIVE_FAMILY_MARGINAL, POSITIVE_FAMILY_NO_SUBTYPE])
	control_allow_blockers = tuple(args.control_allow_blockers or ['reject_pure_head_low_pitch', POSITIVE_FAMILY_MARGINAL, POSITIVE_FAMILY_NO_SUBTYPE])

	marginal_family_pool = filter_positive_family_rows(
		diagnosed_positive_rows,
		args,
		branch_name=POSITIVE_FAMILY_MARGINAL,
		allow_blockers=positive_allow_blockers,
	)
	no_subtype_family_pool = filter_positive_family_rows(
		diagnosed_positive_rows,
		args,
		branch_name=POSITIVE_FAMILY_NO_SUBTYPE,
		allow_blockers=positive_allow_blockers,
	)
	control_guard_pool = filter_control_guard_rows(
		diagnosed_control_rows,
		args,
		allow_blockers=control_allow_blockers,
	)

	selected_marginal_rows = select_diverse_rows(
		tag_rows(marginal_family_pool, 'positive_marginal'),
		int(args.marginal_keep_count),
		max_per_singer=int(args.max_per_singer),
		max_per_song=int(args.max_per_song),
		max_per_singer_song=int(args.max_per_singer_song),
	)
	selected_no_subtype_rows = select_diverse_rows(
		tag_rows(no_subtype_family_pool, 'positive_no_subtype'),
		int(args.no_subtype_keep_count),
		max_per_singer=int(args.max_per_singer),
		max_per_song=int(args.max_per_song),
		max_per_singer_song=int(args.max_per_singer_song),
	)
	selected_control_guard_rows = select_diverse_rows(
		tag_rows(control_guard_pool, 'control_pure_head_guard'),
		int(args.control_keep_count),
		max_per_singer=int(args.control_max_per_singer),
		max_per_song=int(args.control_max_per_song),
		max_per_singer_song=int(args.control_max_per_singer_song),
	)

	combined_positive_rows = list(selected_marginal_rows)
	if str(args.combined_positive_family) == 'both':
		combined_positive_rows.extend(selected_no_subtype_rows)
	combined_increment_rows = dedupe_rows(list(combined_positive_rows) + list(selected_control_guard_rows))

	training_increment_manifest = output_dir / 'training_increment_manifest.csv'
	positive_marginal_manifest = output_dir / 'positive_marginal_manifest.csv'
	positive_no_subtype_manifest = output_dir / 'positive_no_subtype_manifest.csv'
	control_guard_manifest = output_dir / 'control_pure_head_guard_manifest.csv'
	preselected_diagnosis_path = output_dir / 'preselected_diagnosis.json'
	selected_diagnosis_path = output_dir / 'selected_family_diagnosis.json'
	positive_marginal_diagnosis_path = output_dir / 'positive_marginal_diagnosis.json'
	positive_no_subtype_diagnosis_path = output_dir / 'positive_no_subtype_diagnosis.json'
	control_guard_diagnosis_path = output_dir / 'control_pure_head_guard_diagnosis.json'
	summary_path = output_dir / 'plan_summary.json'

	write_rows(training_increment_manifest, [strip_internal_fields(row) for row in combined_increment_rows], reference_rows=diagnosed_rows)
	write_rows(positive_marginal_manifest, [strip_internal_fields(row) for row in selected_marginal_rows], reference_rows=diagnosed_positive_rows)
	write_rows(positive_no_subtype_manifest, [strip_internal_fields(row) for row in selected_no_subtype_rows], reference_rows=diagnosed_positive_rows)
	write_rows(control_guard_manifest, [strip_internal_fields(row) for row in selected_control_guard_rows], reference_rows=diagnosed_control_rows)

	preselected_diagnosis_path.write_text(json.dumps(payload_with_diagnosis(diagnosed_rows), ensure_ascii=False, indent=2), encoding='utf-8')
	selected_diagnosis_path.write_text(json.dumps(payload_with_diagnosis(combined_increment_rows), ensure_ascii=False, indent=2), encoding='utf-8')
	positive_marginal_diagnosis_path.write_text(json.dumps(payload_with_diagnosis(selected_marginal_rows), ensure_ascii=False, indent=2), encoding='utf-8')
	positive_no_subtype_diagnosis_path.write_text(json.dumps(payload_with_diagnosis(selected_no_subtype_rows), ensure_ascii=False, indent=2), encoding='utf-8')
	control_guard_diagnosis_path.write_text(json.dumps(payload_with_diagnosis(selected_control_guard_rows), ensure_ascii=False, indent=2), encoding='utf-8')

	summary = {
		'train_manifest': str(train_manifest),
		'artifact_dir': str(artifact_dir),
		'artifact_threshold': float(artifact_threshold),
		'output_dir': str(output_dir),
		'selection_config': {
			'preselect_count': int(args.preselect_count),
			'preselect_sort_mode': str(args.preselect_sort_mode),
			'preselect_max_per_singer': int(args.preselect_max_per_singer),
			'preselect_max_per_song': int(args.preselect_max_per_song),
			'preselect_max_per_singer_song': int(args.preselect_max_per_singer_song),
			'marginal_keep_count': int(args.marginal_keep_count),
			'no_subtype_keep_count': int(args.no_subtype_keep_count),
			'min_pitch_hz': float(args.min_pitch_hz),
			'min_head_bias': float(args.min_head_bias),
			'runtime_margin_min': float(args.runtime_margin_min),
			'runtime_margin_max': float(args.runtime_margin_max),
			'allow_blockers': list(positive_allow_blockers),
			'max_per_singer': int(args.max_per_singer),
			'max_per_song': int(args.max_per_song),
			'max_per_singer_song': int(args.max_per_singer_song),
			'control_preselect_count': int(args.control_preselect_count),
			'control_preselect_sort_mode': str(args.control_preselect_sort_mode),
			'control_preselect_max_per_singer': int(args.control_preselect_max_per_singer),
			'control_preselect_max_per_song': int(args.control_preselect_max_per_song),
			'control_preselect_max_per_singer_song': int(args.control_preselect_max_per_singer_song),
			'control_keep_count': int(args.control_keep_count),
			'control_min_head_bias': float(args.control_min_head_bias),
			'control_runtime_margin_min': float(args.control_runtime_margin_min),
			'control_runtime_margin_max': float(args.control_runtime_margin_max),
			'control_allow_blockers': list(control_allow_blockers),
			'control_max_per_singer': int(args.control_max_per_singer),
			'control_max_per_song': int(args.control_max_per_song),
			'control_max_per_singer_song': int(args.control_max_per_singer_song),
			'combined_positive_family': str(args.combined_positive_family),
			'eval_window_count': int(args.eval_window_count),
			'eval_window_aggregation': str(args.eval_window_aggregation),
			'eval_window_consistency_penalty': float(args.eval_window_consistency_penalty),
			'eval_window_support_threshold': float(args.eval_window_support_threshold),
			'eval_window_min_support_windows': int(args.eval_window_min_support_windows),
			'eval_window_high_support_threshold': float(args.eval_window_high_support_threshold),
			'eval_window_min_high_support_windows': int(args.eval_window_min_high_support_windows),
			'score_batch_size': int(args.score_batch_size),
			'score_row_chunk_size': int(args.score_row_chunk_size),
			'device': str(args.device),
			'runtime_chunk_size': int(args.runtime_chunk_size),
			'cache_reuse_enabled': bool(reuse_cache),
		},
		'counts': {
			'train_rows': int(train_row_count),
			'positive_pool': positive_pool_count,
			'positive_preselected_rows': len(preselected_positive_rows),
			'control_pool': control_pool_count,
			'control_preselected_rows': len(preselected_control_rows),
			'marginal_family_pool_rows': len(marginal_family_pool),
			'no_subtype_family_pool_rows': len(no_subtype_family_pool),
			'control_guard_pool_rows': len(control_guard_pool),
			'selected_marginal_rows': len(selected_marginal_rows),
			'selected_no_subtype_rows': len(selected_no_subtype_rows),
			'selected_control_guard_rows': len(selected_control_guard_rows),
			'combined_increment_rows': len(combined_increment_rows),
		},
		'rationale': [
			'Split the train-side positive family into marginal-head and no-subtype branches instead of collapsing both failure modes into one increment bucket.',
			'Emit a conservative default increment that keeps only marginal-head positives for adaptation and adds explicit pure_learned_head_mix control guards to resist the K-style control reopening path.',
			'Keep the no-subtype branch as a separate artifact for analysis instead of feeding it into the next trainadapt candidate by default.',
		],
		'summaries': {
			'positive_preselected_rows': summarize_rows(diagnosed_positive_rows),
			'control_preselected_rows': summarize_rows(diagnosed_control_rows),
			'marginal_family_pool': summarize_rows(marginal_family_pool),
			'no_subtype_family_pool': summarize_rows(no_subtype_family_pool),
			'control_guard_pool': summarize_rows(control_guard_pool),
			'selected_marginal_rows': summarize_rows(selected_marginal_rows),
			'selected_no_subtype_rows': summarize_rows(selected_no_subtype_rows),
			'selected_control_guard_rows': summarize_rows(selected_control_guard_rows),
			'combined_increment_rows': summarize_rows(combined_increment_rows),
		},
		'artifacts': {
			'training_increment_manifest': str(training_increment_manifest),
			'positive_marginal_manifest': str(positive_marginal_manifest),
			'positive_no_subtype_manifest': str(positive_no_subtype_manifest),
			'control_pure_head_guard_manifest': str(control_guard_manifest),
			'preselected_diagnosis': str(preselected_diagnosis_path),
			'selected_family_diagnosis': str(selected_diagnosis_path),
			'positive_marginal_diagnosis': str(positive_marginal_diagnosis_path),
			'positive_no_subtype_diagnosis': str(positive_no_subtype_diagnosis_path),
			'control_pure_head_guard_diagnosis': str(control_guard_diagnosis_path),
			'cache_dir': str(cache_dir),
		},
	}
	summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
	print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
	return 0


if __name__ == '__main__':
	raise SystemExit(main())