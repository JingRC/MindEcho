import csv
import json
import os
from pathlib import Path

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'guarded_calibration_manifest.csv'
CHECKPOINT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'best_mix_binary_squeezenet.pt'
OUTPUT = ROOT / '_tmp_control_runtime_probe.json'


def load_rows() -> list[dict]:
    rows = []
    with MANIFEST.open('r', encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if str(row.get('binary_role', '') or '').strip() == 'control_negative':
                rows.append(dict(row))
    return rows


def main() -> int:
    rows = load_rows()
    app = None
    try:
        app, module, ui, _ = dbg.load_runtime(False)
        module._MIX_BINARY_CHECKPOINT_CANDIDATES = (CHECKPOINT,)
        try:
            ui.visualizer._mix_binary_model_bundle = None
            ui.visualizer._last_mix_binary_model_error = ''
            ui.visualizer._prefer_mix_binary_external_cpu = False
            ui.visualizer._external_mix_gpu_retry_blocked = False
        except Exception:
            pass

        sample_rows = []
        for index, row in enumerate(rows, start=1):
            item = reg.analyze_sample(app, module, ui, row)
            summary = reg.summarize_sample(item)
            sample_rows.append(summary)
            print(json.dumps({'progress': f'{index}/{len(rows)}', 'item_name': summary.get('item_name'), 'outcome': summary.get('outcome')}, ensure_ascii=False), flush=True)

        report = {
            'summary': {
                'control_false_positive': sum(1 for row in sample_rows if row.get('outcome') == 'false_positive'),
                'control_total': len(sample_rows),
            },
            'samples': sample_rows,
        }
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(OUTPUT), flush=True)
        os._exit(0)
    finally:
        if app is not None:
            try:
                app.quit()
            except Exception:
                pass


if __name__ == '__main__':
    raise SystemExit(main())