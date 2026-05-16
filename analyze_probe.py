import json
path = r'd:\-MindEcho-main\_tmp_vocadito_public_eval_20260512\probe_vocadito_21_current.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
targets = data.get('targets', [{}])[0]
summaries = targets.get('window_summaries', [])

def check(f, k):
    return f.get(k) is True

for i, s in enumerate(summaries):
    frames = s.get('frames', [])
    res_low = [f for f in frames if check(f, 'residual_octave_low_pull')]
    hist_low = [f for f in frames if check(f, 'history_anchored_low_pull')]
    strong_eq = [f for f in frames if check(f, 'strong_current_candidate') and f.get('post_refine_display') == f.get('pre_refine_display')]
    pull_eq = [f for f in frames if (check(f, 'residual_octave_low_pull') or check(f, 'history_anchored_low_pull')) and f.get('post_refine_display') == f.get('pre_refine_display')]
    
    print('Win %d (%.2fs): ResLow=%d, HistLow=%d, StrongEq=%d, PullEq=%d' % (i, s.get('window_start_time',0), len(res_low), len(hist_low), len(strong_eq), len(pull_eq)))

    print('Samples for Win %d:' % i)
    all_res = res_low[:2]
    all_hist = hist_low[:2]
    all_strong = strong_eq[:2]
    
    unique_samples = {f.get('timeline_time'): f for f in (all_res + all_hist + all_strong)}.values()
    for f in unique_samples:
        print(' T:%.3f Pre:%.1f Post:%.1f Ref:%.1f LC:%.1f HR:%.3f CLR:%.4f LG:%s' % (f.get('timeline_time',0), f.get('pre_refine_display',0), f.get('post_refine_display',0), f.get('reference_frequency',0), f.get('lower_candidate',0), f.get('harmonic_ratio',0), f.get('current_lower_ratio',0), f.get('later_guard')))
