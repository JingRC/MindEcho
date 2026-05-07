import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg


DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run frozen GUI guarded runtime regression for one or more mix checkpoints.')
    parser.add_argument('--manifest', required=True, help='Guarded calibration manifest to replay through the frozen runtime.')
    parser.add_argument('--artifact', action='append', required=True, help='Artifact directory or checkpoint file to evaluate. May be passed multiple times.')
    parser.add_argument('--output', required=True, help='Path to write the combined JSON regression report.')
    return parser.parse_args()


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


def load_manifest_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


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


def summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        'positive_hits': sum(1 for row in rows if row.get('binary_role') == 'positive_mix' and row.get('outcome') == 'hit'),
        'positive_total': sum(1 for row in rows if row.get('binary_role') == 'positive_mix'),
        'control_false_positive': sum(1 for row in rows if row.get('binary_role') == 'control_negative' and row.get('outcome') == 'false_positive'),
        'control_total': sum(1 for row in rows if row.get('binary_role') == 'control_negative'),
    }


def run_isolated_item_regression(
    manifest_path: Path,
    checkpoint_paths: List[Path],
    item_name: str,
    output_path: Path,
) -> Dict[str, Any]:
    env = dict(os.environ)
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')

    command = [
        sys.executable,
        str(DIAGNOSE_SCRIPT),
        '--manifest',
        str(manifest_path),
        '--output',
        str(output_path),
    ]
    for checkpoint_path in checkpoint_paths:
        command.extend(['--artifact', str(checkpoint_path)])
    command.extend(['--item-name', item_name])

    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            'isolated guarded runtime regression failed '
            f'for {item_name}: exit={completed.returncode}'
        )
    if not output_path.exists():
        raise RuntimeError(f'isolated guarded runtime regression did not write output for {item_name}: {output_path}')

    with output_path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f'manifest not found: {manifest_path}', file=sys.stderr)
        return 2

    samples = load_manifest_rows(manifest_path)
    checkpoint_paths = [resolve_checkpoint(path_text) for path_text in list(args.artifact or [])]
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    artifact_reports = [
        {
            'checkpoint': str(checkpoint_path),
            'summary': {},
            'samples': [],
        }
        for checkpoint_path in checkpoint_paths
    ]

    with tempfile.TemporaryDirectory(prefix='guarded_mix_runtime_', dir=str(output_path.parent)) as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        total = len(samples)
        for index, sample in enumerate(samples, start=1):
            item_name = str(sample.get('item_name', '') or '').strip()
            if not item_name:
                raise ValueError(f'manifest row missing item_name at index {index}')

            print(json.dumps({'progress': f'{index}/{total}', 'item_name': item_name}, ensure_ascii=False), flush=True)
            item_output_path = temp_dir / f'item_{index:04d}.json'
            item_report = run_isolated_item_regression(manifest_path, checkpoint_paths, item_name, item_output_path)
            item_artifacts = list(item_report.get('artifacts', []) or [])
            if len(item_artifacts) != len(artifact_reports):
                raise RuntimeError(
                    f'unexpected artifact count for {item_name}: expected {len(artifact_reports)}, got {len(item_artifacts)}'
                )

            for artifact_index, artifact_payload in enumerate(item_artifacts):
                sample_rows = list(artifact_payload.get('samples', []) or [])
                if len(sample_rows) != 1:
                    raise RuntimeError(
                        f'unexpected sample count for {item_name} / artifact {artifact_reports[artifact_index]["checkpoint"]}: '
                        f'expected 1, got {len(sample_rows)}'
                    )
                artifact_reports[artifact_index]['samples'].append(dict(sample_rows[0]))

    report = {
        'manifest': str(manifest_path),
        'artifacts': artifact_reports,
    }
    for artifact_report in artifact_reports:
        artifact_report['summary'] = summarize_rows(list(artifact_report.get('samples', []) or []))
        print(json.dumps({'checkpoint': artifact_report['checkpoint'], 'summary': artifact_report['summary']}, ensure_ascii=False), flush=True)

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output_path': str(output_path), 'artifact_count': len(report['artifacts'])}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())