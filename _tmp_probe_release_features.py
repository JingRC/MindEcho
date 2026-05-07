import csv
import json
import os
from pathlib import Path

import debug_mix_role_regression as reg
import debug_mix_rule_offline as dbg


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'dataset' / 'curated' / 'mix_binary_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'guarded_calibration_manifest.csv'
CHECKPOINT = ROOT / 'ml_dl_models' / 'gtsinger_multitech' / 'lightweight_training' / 'artifacts' / 'mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_residual_trainadapt_alto_below_threshold_runtimeaware_v1' / 'best_mix_binary_squeezenet.pt'
ITEM_NAMES = [
    'Chinese#ZH-Alto-1#Pharyngeal#小半#Control_Group#0008',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#烟花易冷#Mixed_Voice_Group#0019',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#我们的明天#Mixed_Voice_Group#0006',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#我的歌声里#Mixed_Voice_Group#0015',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#画心#Mixed_Voice_Group#0003',
    'Chinese#ZH-Alto-1#Mixed_Voice_and_Falsetto#剑伤#Mixed_Voice_Group#0009',
]
OUTPUT = ROOT / '_tmp_probe_release_features.json'


def load_rows() -> list[dict]:
    selected = []
    with MANIFEST.open('r', encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if str(row.get('item_name', '') or '').strip() in ITEM_NAMES:
                selected.append(dict(row))
    row_map = {str(row.get('item_name', '') or '').strip(): row for row in selected}
    return [row_map[item_name] for item_name in ITEM_NAMES if item_name in row_map]


def main() -> int:
    rows = load_rows()
    app = None
    try:
        app, module, ui, _ = dbg.load_runtime(False)
        module._MIX_BINARY_CHECKPOINT_CANDIDATES = (CHECKPOINT,)
        results = []
        for row in rows:
            item = reg.analyze_sample(app, module, ui, row)
            sample = dict(item.get('sample', {}) or {})
            analysis = dict(item.get('analysis', {}) or {})
            mix_events = list(analysis.get('mix_events', []) or [])
            released_events = []
            for event in mix_events:
                snapshot = dict(event.get('feature_snapshot', {}) or {})
                if snapshot.get('released_midhigh_supported_softhead_mix'):
                    released_events.append({
                        'event_type': event.get('event_type'),
                        'start_time': event.get('start_time'),
                        'end_time': event.get('end_time'),
                        'confidence': event.get('confidence'),
                        'strength': event.get('strength'),
                        'mean_pitch_hz': event.get('mean_pitch_hz'),
                        'chest_prob': event.get('chest_prob'),
                        'falsetto_prob': event.get('falsetto_prob'),
                        'mix_prob': event.get('mix_prob'),
                        'feature_snapshot': snapshot,
                    })
            results.append({
                'item_name': sample.get('item_name'),
                'binary_role': sample.get('binary_role'),
                'released_events': released_events,
            })
        OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
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