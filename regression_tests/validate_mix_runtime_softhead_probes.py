import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSE_SCRIPT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'diagnose_mix_rule_selected_samples.py'
ARTIFACT_DIR = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_efficientnet_b0_img256_mel160_mean3_h0f4_proxy_english_singer_holdout_negfocus_threshcap640_v1'

PROBE_GROUPS = (
    {
        'manifest': ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_english_singer_holdout_v1' / 'validation_manifest.csv',
        'probe_items': (
            'English#EN-Tenor-1#Glissando#I Knew You Were Trouble#Glissando_Group#0003',
            'English#EN-Tenor-1#Glissando#Stay#Control_Group#0010',
            'English#EN-Tenor-1#Vibrato#What Was I Made For？#Control_Group#0002',
            'English#EN-Tenor-1#Mixed_Voice_and_Falsetto#Summertime Sadness#Mixed_Voice_Group#0002',
            'English#EN-Tenor-1#Vibrato#Always Remember Us This Way#Control_Group#0011',
            'English#EN-Tenor-1#Breathy#Stay#Control_Group#0008',
            'English#EN-Tenor-1#Vibrato#Stay#Control_Group#0009',
            'English#EN-Tenor-1#Glissando#I Knew You Were Trouble#Glissando_Group#0002',
            'English#EN-Tenor-1#Mixed_Voice_and_Falsetto#Look What You Make Me Do#Control_Group#0001',
        ),
        'expectations': (
            {
                'item_name': 'English#EN-Tenor-1#Vibrato#Always Remember Us This Way#Control_Group#0011',
                'expected_outcome': 'hit',
                'expected_min_mix_events': 1,
            },
            {
                'item_name': 'English#EN-Tenor-1#Mixed_Voice_and_Falsetto#Look What You Make Me Do#Control_Group#0001',
                'expected_outcome': 'clean',
                'expected_max_mix_events': 0,
            },
        ),
    },
    {
        'manifest': ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_english_singer_holdout_v1' / 'test_manifest.csv',
        'probe_items': (
            'English#EN-Alto-2#Vibrato#Someone Like You#Control_Group#0002',
            'English#EN-Alto-2#Vibrato#Someone Like You#Control_Group#0001',
            'English#EN-Alto-2#Mixed_Voice_and_Falsetto#Let It Go#Mixed_Voice_Group#0003',
            'English#EN-Alto-2#Glissando#My Heart Will Go On#Glissando_Group#0006',
            'English#EN-Alto-2#Vibrato#Easy On Me#Vibrato_Group#0005',
            'English#EN-Alto-2#Vibrato#Easy On Me#Vibrato_Group#0004',
            'English#EN-Alto-2#Breathy#Someone Like You#Control_Group#0003',
            'English#EN-Alto-2#Glissando#You Raise Me Up#Control_Group#0003',
            'English#EN-Alto-2#Mixed_Voice_and_Falsetto#Hello#Control_Group#0003',
            'English#EN-Alto-2#Mixed_Voice_and_Falsetto#Lemon Tree#Falsetto_Group#0001',
        ),
        'expectations': (
            {
                'item_name': 'English#EN-Alto-2#Vibrato#Someone Like You#Control_Group#0001',
                'expected_outcome': 'hit',
                'expected_min_mix_events': 1,
            },
            {
                'item_name': 'English#EN-Alto-2#Vibrato#Easy On Me#Vibrato_Group#0004',
                'expected_outcome': 'hit',
                'expected_min_mix_events': 1,
            },
            {
                'item_name': 'English#EN-Alto-2#Mixed_Voice_and_Falsetto#Hello#Control_Group#0003',
                'expected_outcome': 'clean',
                'expected_max_mix_events': 0,
            },
            {
                'item_name': 'English#EN-Alto-2#Mixed_Voice_and_Falsetto#Lemon Tree#Falsetto_Group#0001',
                'expected_outcome': 'no_mix',
                'expected_max_mix_events': 0,
            },
        ),
    },
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_probe_group(manifest_path: Path, probe_items: tuple[str, ...]) -> dict:
    with tempfile.TemporaryDirectory(prefix='mindecho_mix_runtime_probe_') as temp_dir:
        output_path = Path(temp_dir) / 'probe_output.json'
        command = [
            sys.executable,
            str(DIAGNOSE_SCRIPT),
            '--manifest',
            str(manifest_path),
            '--artifact',
            str(ARTIFACT_DIR),
            '--fresh-runtime-per-sample',
            '--output',
            str(output_path),
        ]
        for item_name in probe_items:
            command.extend(['--item-name', str(item_name)])
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            check=False,
            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        )
        if completed.returncode != 0:
            raise RuntimeError(f'diagnose runtime probe failed: rc={completed.returncode} manifest={manifest_path}')
        return json.loads(output_path.read_text(encoding='utf-8'))


def main() -> None:
    assert_true(DIAGNOSE_SCRIPT.exists(), f'missing diagnose script: {DIAGNOSE_SCRIPT}')
    assert_true(ARTIFACT_DIR.exists(), f'missing artifact dir: {ARTIFACT_DIR}')

    for group in PROBE_GROUPS:
        manifest_path = Path(group['manifest'])
        payload = run_probe_group(manifest_path, tuple(group['probe_items']))
        sample_map = {}
        for artifact in payload.get('artifacts', []):
            for sample in artifact.get('samples', []):
                item_name = str(sample.get('item_name', '') or '')
                if item_name:
                    sample_map[item_name] = sample

        for expectation in group['expectations']:
            item_name = str(expectation['item_name'])
            assert_true(item_name in sample_map, f'missing probe sample in diagnosis output: {item_name}')
            sample = sample_map[item_name]
            actual_outcome = str(sample.get('outcome', '') or '')
            expected_outcome = str(expectation.get('expected_outcome', '') or '')
            assert_true(actual_outcome == expected_outcome, f'{item_name}: expected outcome {expected_outcome}, got {actual_outcome}')

            mix_event_count = int(sample.get('mix_event_count', 0) or 0)
            if 'expected_min_mix_events' in expectation:
                expected_min = int(expectation['expected_min_mix_events'])
                assert_true(mix_event_count >= expected_min, f'{item_name}: expected at least {expected_min} mix events, got {mix_event_count}')
            if 'expected_max_mix_events' in expectation:
                expected_max = int(expectation['expected_max_mix_events'])
                assert_true(mix_event_count <= expected_max, f'{item_name}: expected at most {expected_max} mix events, got {mix_event_count}')

    print('OK: validate_mix_runtime_softhead_probes passed')


if __name__ == '__main__':
    main()