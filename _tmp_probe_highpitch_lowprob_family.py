import json
import os
import sys
from pathlib import Path


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import debug_mix_rule_offline as dbg
import debug_mix_role_regression as reg
from ml_dl_models.gtsinger_multitech.lightweight_training import diagnose_mix_rule_selected_samples as diagnose


MANIFEST_PATH = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'guarded_calibration_manifest.csv'
CHECKPOINT_PATH = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'best_mix_binary_squeezenet.pt'
DEFAULT_OUTPUT_PATH = ROOT / '_tmp_mix_rule_highpitch_lowprob_probe.json'
ITEM_NAMES = [
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#演员#Mixed_Voice_Group#0014',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#化身孤岛的鲸#Mixed_Voice_Group#0009',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#演员#Mixed_Voice_Group#0013',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#剑伤#Control_Group#0004',
    'Chinese#ZH-Alto-1#Pharyngeal#听海#Control_Group#0002',
    'Chinese#ZH-Alto-1#Breathy#成都#Control_Group#0001',
    'Chinese#ZH-Alto-1#Glissando#十年#Control_Group#0010',
    'Chinese#ZH-Alto-1#Pharyngeal#大鱼#Control_Group#0002',
    'Chinese#ZH-Alto-1#Pharyngeal#听海#Control_Group#0015',
]


def main() -> None:
    output_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    rows = diagnose.load_selected_rows(MANIFEST_PATH, ITEM_NAMES)
    checkpoint_path = diagnose.resolve_checkpoint(str(CHECKPOINT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    app = None
    try:
        app, module, ui, _ = dbg.load_runtime(False)
        module._MIX_BINARY_CHECKPOINT_CANDIDATES = (checkpoint_path,)
        diagnose.reset_mix_runtime_cache(ui)
        samples = []
        for row in rows:
            item = reg.analyze_sample(app, module, ui, row)
            samples.append(diagnose.diagnose_sample(item))
        report = {
            'manifest': str(MANIFEST_PATH),
            'item_names': [str(row.get('item_name', '') or '') for row in rows],
            'artifacts': [
                {
                    'checkpoint': str(checkpoint_path),
                    'samples': samples,
                }
            ],
        }
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output_path': str(output_path), 'sample_count': len(samples)}, ensure_ascii=False), flush=True)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == '__main__':
    main()