import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Extract a runtime false-positive family from a guarded regression report and build a runtime-aware curated entry.'
    )
    parser.add_argument('--runtime-report', required=True, help='Guarded runtime regression JSON report.')
    parser.add_argument('--artifact-substring', default='', help='Substring used to select the target artifact checkpoint inside the runtime report.')
    parser.add_argument('--base-curated-dir', default='', help='Optional curated dir providing guarded_calibration_manifest.csv to reuse positives and guards.')
    parser.add_argument('--output-dir', required=True, help='Output curated directory.')
    parser.add_argument('--family-binary-role', default='control_negative', help='Sample binary_role to extract from the runtime report.')
    parser.add_argument('--family-outcome', default='false_positive', help='Sample outcome to extract from the runtime report.')
    parser.add_argument('--top-k', type=int, default=0, help='Keep only the top-k family rows after sorting. 0 keeps all rows.')
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def load_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            name = str(key)
            if name not in seen:
                seen.add(name)
                fieldnames.append(name)
    if not fieldnames:
        fieldnames = ['item_name']
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def pick_artifact_report(report: Dict[str, Any], artifact_substring: str) -> Dict[str, Any]:
    artifacts = list(report.get('artifacts', []) or [])
    if not artifacts:
        raise ValueError('runtime report does not contain any artifacts')
    needle = str(artifact_substring or '').strip()
    if needle:
        matches = [artifact for artifact in artifacts if needle in str(artifact.get('checkpoint', '') or '')]
        if len(matches) != 1:
            raise ValueError(f'artifact substring matched {len(matches)} artifacts: {needle}')
        return dict(matches[0])
    if len(artifacts) == 1:
        return dict(artifacts[0])
    raise ValueError('runtime report contains multiple artifacts; pass --artifact-substring to disambiguate')


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def numeric_stats(values: Iterable[float]) -> Dict[str, float]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {'min': 0.0, 'median': 0.0, 'max': 0.0}
    return {
        'min': round(min(numbers), 6),
        'median': round(float(median(numbers)), 6),
        'max': round(max(numbers), 6),
    }


def sample_sort_key(sample: Dict[str, Any]) -> Any:
    best_voice_event = dict(sample.get('best_voice_event', {}) or {})
    return (
        -as_float(sample.get('best_voice_mix_margin', 0.0)),
        -as_float(best_voice_event.get('mix_prob', 0.0)),
        -int(sample.get('mix_event_count', 0) or 0),
        str(sample.get('item_name', '') or ''),
    )


def extract_annotations(sample: Dict[str, Any]) -> Dict[str, Any]:
    diagnosis = dict(sample.get('voice_rule_diagnosis', {}) or {})
    voice_features = dict(diagnosis.get('voice_features', {}) or {})
    supports = dict(diagnosis.get('supports', {}) or {})
    subtype_eval = dict(diagnosis.get('subtype_eval', {}) or {})
    blockers = [str(item or '') for item in list(diagnosis.get('blockers', []) or []) if str(item or '')]
    released_flags = dict(diagnosis.get('released_flags', {}) or {})
    strongest_mix_event = dict(sample.get('strongest_mix_event', {}) or {})
    best_voice_event = dict(sample.get('best_voice_event', {}) or {})
    return {
        'family_primary_blocker': str(blockers[0] if blockers else ''),
        'family_blockers': '|'.join(blockers),
        'family_released_flags': '|'.join(sorted(key for key, value in released_flags.items() if value)),
        'family_candidate_subtype': str(subtype_eval.get('candidate_subtype', '') or ''),
        'family_candidate_subtype_conf': round(as_float(subtype_eval.get('candidate_subtype_conf', 0.0)), 6),
        'family_mix_support': round(as_float(supports.get('mix_support', 0.0)), 6),
        'family_head_bias': round(as_float(supports.get('head_bias', 0.0)), 6),
        'family_weak_mix_support': round(as_float(supports.get('weak_mix_support', 0.0)), 6),
        'family_mean_pitch_hz': round(as_float(voice_features.get('mean_pitch_hz', 0.0)), 6),
        'family_best_voice_mix_prob': round(as_float(best_voice_event.get('mix_prob', 0.0)), 6),
        'family_best_voice_mix_margin': round(as_float(sample.get('best_voice_mix_margin', 0.0)), 6),
        'family_best_voice_type': str(best_voice_event.get('event_type', '') or ''),
        'family_strongest_mix_event_type': str(strongest_mix_event.get('event_type', '') or ''),
        'family_strongest_mix_subtype': str(strongest_mix_event.get('subtype', '') or ''),
        'family_strongest_mix_base_voice_type': str(strongest_mix_event.get('base_voice_type', '') or ''),
    }


def build_bucket_summary(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    primary_blocker = Counter()
    blocker_sets = Counter()
    candidate_subtypes = Counter()
    strongest_mix_subtypes = Counter()
    strongest_mix_signatures = Counter()
    released_flags = Counter()
    mix_event_counts = Counter()
    weak_mix_counts = Counter()
    strong_mix_counts = Counter()

    margins: List[float] = []
    mix_probs: List[float] = []
    mix_supports: List[float] = []
    head_biases: List[float] = []
    pitches: List[float] = []

    for sample in samples:
        annotations = extract_annotations(sample)
        primary_blocker[str(annotations.get('family_primary_blocker', '') or 'none')] += 1
        blocker_sets[str(annotations.get('family_blockers', '') or 'none')] += 1
        candidate_subtypes[str(annotations.get('family_candidate_subtype', '') or 'none')] += 1
        strongest_mix_subtypes[str(annotations.get('family_strongest_mix_subtype', '') or annotations.get('family_strongest_mix_event_type', '') or 'none')] += 1
        signature = '|'.join(
            [
                str(annotations.get('family_strongest_mix_event_type', '') or 'none'),
                str(annotations.get('family_strongest_mix_subtype', '') or 'none'),
                str(annotations.get('family_strongest_mix_base_voice_type', '') or 'none'),
            ]
        )
        strongest_mix_signatures[signature] += 1
        for flag in str(annotations.get('family_released_flags', '') or '').split('|'):
            token = str(flag or '').strip()
            if token:
                released_flags[token] += 1
        mix_event_counts[str(int(sample.get('mix_event_count', 0) or 0))] += 1
        weak_mix_counts[str(int(sample.get('weak_mix_count', 0) or 0))] += 1
        strong_mix_counts[str(int(sample.get('strong_mix_count', 0) or 0))] += 1

        margins.append(as_float(sample.get('best_voice_mix_margin', 0.0)))
        mix_probs.append(as_float(annotations.get('family_best_voice_mix_prob', 0.0)))
        mix_supports.append(as_float(annotations.get('family_mix_support', 0.0)))
        head_biases.append(as_float(annotations.get('family_head_bias', 0.0)))
        pitches.append(as_float(annotations.get('family_mean_pitch_hz', 0.0)))

    return {
        'primary_blocker': dict(primary_blocker),
        'blocker_sets': dict(blocker_sets),
        'candidate_subtypes': dict(candidate_subtypes),
        'strongest_mix_subtypes': dict(strongest_mix_subtypes),
        'strongest_mix_signatures': dict(strongest_mix_signatures),
        'released_flags': dict(released_flags),
        'mix_event_counts': dict(mix_event_counts),
        'weak_mix_counts': dict(weak_mix_counts),
        'strong_mix_counts': dict(strong_mix_counts),
        'best_voice_mix_margin_stats': numeric_stats(margins),
        'best_voice_mix_prob_stats': numeric_stats(mix_probs),
        'mix_support_stats': numeric_stats(mix_supports),
        'head_bias_stats': numeric_stats(head_biases),
        'mean_pitch_hz_stats': numeric_stats(pitches),
    }


def enrich_base_row(base_row: Dict[str, Any], sample: Dict[str, Any], *, bucket_name: str) -> Dict[str, Any]:
    result = dict(base_row)
    result['family_bucket'] = str(bucket_name)
    result.update(extract_annotations(sample))
    return result


def dedupe_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item_name = str(row.get('item_name', '') or '').strip()
        key = item_name or json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(row))
    return deduped


def main() -> int:
    args = parse_args()
    runtime_report_path = Path(args.runtime_report).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_report = load_json(runtime_report_path)
    artifact_report = pick_artifact_report(runtime_report, str(args.artifact_substring or ''))
    samples = list(artifact_report.get('samples', []) or [])
    family_samples = [
        dict(sample)
        for sample in samples
        if str(sample.get('binary_role', '') or '') == str(args.family_binary_role)
        and str(sample.get('outcome', '') or '') == str(args.family_outcome)
    ]
    family_samples.sort(key=sample_sort_key)
    top_k = max(0, int(args.top_k or 0))
    if top_k > 0:
        family_samples = family_samples[:top_k]

    enriched_family_samples = []
    for sample in family_samples:
        enriched = dict(sample)
        enriched.update(extract_annotations(sample))
        enriched_family_samples.append(enriched)

    family_manifest_path = output_dir / 'runtime_false_positive_family_manifest.csv'
    family_diagnosis_path = output_dir / 'runtime_false_positive_family_diagnosis.json'
    bucket_summary_path = output_dir / 'runtime_false_positive_bucket_summary.json'
    plan_summary_path = output_dir / 'plan_summary.json'

    write_rows(family_manifest_path, enriched_family_samples)
    write_json(family_diagnosis_path, enriched_family_samples)

    bucket_summary = build_bucket_summary(family_samples)
    write_json(bucket_summary_path, bucket_summary)

    base_curated_dir = Path(str(args.base_curated_dir or '')).resolve() if str(args.base_curated_dir or '').strip() else None
    training_increment_path = None
    guarded_manifest_output_path = None
    clean_guard_manifest_path = None
    positive_source_manifest_path = None
    training_increment_rows: List[Dict[str, Any]] = []
    guarded_rows: List[Dict[str, Any]] = []
    clean_guard_rows: List[Dict[str, Any]] = []
    positive_rows: List[Dict[str, Any]] = []

    if base_curated_dir is not None:
        base_guarded_manifest_path = base_curated_dir / 'guarded_calibration_manifest.csv'
        if not base_guarded_manifest_path.exists():
            raise FileNotFoundError(f'missing guarded calibration manifest: {base_guarded_manifest_path}')
        guarded_rows = load_rows(base_guarded_manifest_path)
        guarded_row_map = {
            str(row.get('item_name', '') or '').strip(): dict(row)
            for row in guarded_rows
            if str(row.get('item_name', '') or '').strip()
        }
        missing = [str(sample.get('item_name', '') or '') for sample in family_samples if str(sample.get('item_name', '') or '') not in guarded_row_map]
        if missing:
            raise KeyError(f'family rows missing from base guarded manifest: {missing}')

        positive_rows = [dict(row) for row in guarded_rows if str(row.get('binary_role', '') or '') == 'positive_mix']
        family_guard_rows = [
            enrich_base_row(guarded_row_map[str(sample.get('item_name', '') or '')], sample, bucket_name='runtime_false_positive_family')
            for sample in family_samples
        ]
        family_item_names = {str(row.get('item_name', '') or '').strip() for row in family_guard_rows}
        clean_guard_rows = [
            dict(row)
            for row in guarded_rows
            if str(row.get('binary_role', '') or '') == 'control_negative'
            and str(row.get('item_name', '') or '').strip() not in family_item_names
        ]

        training_increment_rows = dedupe_rows(list(positive_rows) + list(family_guard_rows))

        training_increment_path = output_dir / 'training_increment_manifest.csv'
        guarded_manifest_output_path = output_dir / 'guarded_calibration_manifest.csv'
        clean_guard_manifest_path = output_dir / 'retained_clean_guard_manifest.csv'
        positive_source_manifest_path = output_dir / 'positive_source_manifest.csv'

        write_rows(training_increment_path, training_increment_rows)
        write_rows(guarded_manifest_output_path, guarded_rows)
        write_rows(clean_guard_manifest_path, clean_guard_rows)
        write_rows(positive_source_manifest_path, positive_rows)

    summary = {
        'runtime_report': str(runtime_report_path),
        'selected_artifact_checkpoint': str(artifact_report.get('checkpoint', '') or ''),
        'selected_artifact_summary': dict(artifact_report.get('summary', {}) or {}),
        'base_curated_dir': str(base_curated_dir) if base_curated_dir is not None else '',
        'selection_policy': 'select all control_negative false_positive rows from the chosen runtime guarded report and, when a base curated dir is provided, merge them with the base guarded positives into a runtime-aware training increment',
        'counts': {
            'family_rows': len(family_samples),
            'positive_source_rows': len(positive_rows),
            'clean_guard_rows': len(clean_guard_rows),
            'training_increment_rows': len(training_increment_rows),
            'guarded_rows': len(guarded_rows),
        },
        'bucket_summary': bucket_summary,
        'top_family_examples': [
            {
                'item_name': str(sample.get('item_name', '') or ''),
                'song_name': str(sample.get('song_name', '') or ''),
                'best_voice_mix_margin': round(as_float(sample.get('best_voice_mix_margin', 0.0)), 6),
                'best_voice_mix_prob': round(as_float(dict(sample.get('best_voice_event', {}) or {}).get('mix_prob', 0.0)), 6),
                'primary_blocker': str(extract_annotations(sample).get('family_primary_blocker', '') or ''),
                'candidate_subtype': str(extract_annotations(sample).get('family_candidate_subtype', '') or ''),
                'strongest_mix_subtype': str(extract_annotations(sample).get('family_strongest_mix_subtype', '') or ''),
            }
            for sample in family_samples[:12]
        ],
        'artifacts': {
            'runtime_false_positive_family_manifest': str(family_manifest_path),
            'runtime_false_positive_family_diagnosis': str(family_diagnosis_path),
            'runtime_false_positive_bucket_summary': str(bucket_summary_path),
            'training_increment_manifest': str(training_increment_path) if training_increment_path is not None else '',
            'guarded_calibration_manifest': str(guarded_manifest_output_path) if guarded_manifest_output_path is not None else '',
            'retained_clean_guard_manifest': str(clean_guard_manifest_path) if clean_guard_manifest_path is not None else '',
            'positive_source_manifest': str(positive_source_manifest_path) if positive_source_manifest_path is not None else '',
        },
        'rationale': [
            'This entry stops threshold-only iteration and turns the observed runtime false-positive family into explicit guard negatives for the next trainadapt pass.',
            'The family rows are taken after rule application, so the bucket summary reflects actual frozen-runtime reopen paths instead of raw model-only confusion.',
            'Keeping the base guarded calibration manifest unchanged preserves the strict acceptance gate while the new training increment concentrates on the reopened control family.',
        ],
    }
    write_json(plan_summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())