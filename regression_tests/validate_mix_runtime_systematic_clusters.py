import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'
CONFIG_PATH = ROOT / 'regression_tests' / 'mix_runtime_systematic_cluster_config.json'


def parse_args():
    parser = argparse.ArgumentParser(description='Validate the fixed systematic English mix runtime clusters.')
    parser.add_argument('--group', action='append', default=[], help='Optional regression group name to run. May be passed multiple times.')
    return parser.parse_args()


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))


def summarize_by_field(samples, field_name, success_outcomes):
    summary = {}
    for sample in list(samples or []):
        bucket_name = str(sample.get(field_name, '') or '')
        bucket = summary.setdefault(
            bucket_name,
            {
                'sample_count': 0,
                'success_count': 0,
                'outcomes': Counter(),
            },
        )
        outcome = str(sample.get('outcome', '') or '')
        bucket['sample_count'] += 1
        bucket['outcomes'].update([outcome])
        if outcome in success_outcomes:
            bucket['success_count'] += 1
    return summary


def run_probe_group(manifest_path, artifact_path, item_names):
    with tempfile.TemporaryDirectory(prefix='mindecho_mix_runtime_systematic_') as temp_dir:
        output_path = Path(temp_dir) / 'probe_output.json'
        command = [
            sys.executable,
            str(DIAGNOSE_SCRIPT),
            '--manifest',
            str(manifest_path),
            '--artifact',
            str(artifact_path),
            '--fresh-process-per-sample',
            '--output',
            str(output_path),
        ]
        for item_name in list(item_names or []):
            command.extend(['--item-name', str(item_name)])
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            check=False,
            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        )
        if completed.returncode != 0:
            raise RuntimeError(f'diagnose systematic runtime regression failed: rc={completed.returncode} manifest={manifest_path}')
        return json.loads(output_path.read_text(encoding='utf-8'))


def main():
    args = parse_args()
    assert_true(DIAGNOSE_SCRIPT.exists(), f'missing diagnose script: {DIAGNOSE_SCRIPT}')
    assert_true(CONFIG_PATH.exists(), f'missing config file: {CONFIG_PATH}')

    config = load_config()
    artifact_path = ROOT / str(config.get('artifact_dir', '') or '')
    assert_true(artifact_path.exists(), f'missing artifact dir: {artifact_path}')

    requested_groups = {str(name or '').strip() for name in list(args.group or []) if str(name or '').strip()}
    groups = list(config.get('groups', []) or [])
    if requested_groups:
        groups = [group for group in groups if str(group.get('name', '') or '') in requested_groups]
        assert_true(groups, f'no regression groups matched: {sorted(requested_groups)}')

    for group in groups:
        group_name = str(group.get('name', '') or '')
        manifest_path = ROOT / str(group.get('manifest', '') or '')
        item_names = list(group.get('item_names', []) or [])
        success_outcomes = {str(item) for item in list(group.get('success_outcomes', []) or [])}

        assert_true(manifest_path.exists(), f'{group_name}: missing manifest: {manifest_path}')
        assert_true(item_names, f'{group_name}: no item_names configured')
        assert_true(success_outcomes, f'{group_name}: no success_outcomes configured')

        payload = run_probe_group(manifest_path, artifact_path, item_names)
        artifacts = list(payload.get('artifacts', []) or [])
        assert_true(len(artifacts) == 1, f'{group_name}: expected exactly one artifact result, got {len(artifacts)}')
        samples = list(artifacts[0].get('samples', []) or [])
        assert_true(
            len(samples) == int(group.get('expected_sample_count', 0) or 0),
            f'{group_name}: expected {group.get("expected_sample_count", 0)} samples, got {len(samples)}',
        )

        success_count = sum(1 for sample in samples if str(sample.get('outcome', '') or '') in success_outcomes)
        minimum_success_count = int(group.get('minimum_success_count', 0) or 0)
        assert_true(
            success_count >= minimum_success_count,
            f'{group_name}: expected at least {minimum_success_count} successful outcomes, got {success_count}',
        )

        song_summary = summarize_by_field(samples, 'song_name', success_outcomes)
        role_summary = summarize_by_field(samples, 'binary_role', success_outcomes)

        for expectation in list(group.get('song_expectations', []) or []):
            song_name = str(expectation.get('song_name', '') or '')
            minimum_song_success = int(expectation.get('minimum_success_count', 0) or 0)
            bucket = song_summary.get(song_name, {'sample_count': 0, 'success_count': 0, 'outcomes': Counter()})
            assert_true(
                int(bucket['success_count']) >= minimum_song_success,
                f'{group_name}: song {song_name} expected at least {minimum_song_success} successes, '
                f'got {bucket["success_count"]} / {bucket["sample_count"]} with outcomes {dict(bucket["outcomes"])}',
            )

        for expectation in list(group.get('role_expectations', []) or []):
            role_name = str(expectation.get('binary_role', '') or '')
            minimum_role_success = int(expectation.get('minimum_success_count', 0) or 0)
            bucket = role_summary.get(role_name, {'sample_count': 0, 'success_count': 0, 'outcomes': Counter()})
            assert_true(
                int(bucket['success_count']) >= minimum_role_success,
                f'{group_name}: role {role_name} expected at least {minimum_role_success} successes, '
                f'got {bucket["success_count"]} / {bucket["sample_count"]} with outcomes {dict(bucket["outcomes"])}',
            )

        print(
            json.dumps(
                {
                    'group': group_name,
                    'sample_count': len(samples),
                    'success_count': success_count,
                    'success_outcomes': sorted(success_outcomes),
                },
                ensure_ascii=False,
            )
        )

    print('OK: validate_mix_runtime_systematic_clusters passed')


if __name__ == '__main__':
    main()