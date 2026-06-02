"""Simulate smart merge on recording."""
import json, sys, numpy as np

fname = sys.argv[1] if len(sys.argv) > 1 else "recordings/analysis_20260602_191954.json"
with open(fname, encoding="utf-8") as f:
    data = json.load(f)

pd = data["pitch_analysis"]["pitch_data"]
base_t = pd[0]["timestamp"]
total_dur_rec = pd[-1]["timestamp"] - base_t

all_frames = [(p["timestamp"] - base_t, p.get("frequency", 0), p.get("confidence", 0)) for p in pd]
# All frames with pitch (no confidence filter here - that's done in the merge step)
valid = [(t, f, c) for t, f, c in all_frames if f > 0]

diffs = [valid[i][0] - valid[i-1][0] for i in range(1, len(valid)) if valid[i][0] - valid[i-1][0] > 0.001]
base_dt = max(0.008, min(0.080, float(np.median(diffs))))

min_gap = max(0.06, base_dt * 1.5)
supp = max(0.07, base_dt * 1.5)
single_m = max(0.09, base_dt * 2.2)

events = []
for i in range(1, len(valid)):
    pt, ct = valid[i-1][0], valid[i][0]; rg = ct - pt
    if rg < min_gap: continue
    ps = valid[i-2][0] - pt if i >= 2 else None
    ns = valid[i+1][0] - ct if i + 1 < len(valid) else None
    hp = ps is not None and ps <= supp; hn = ns is not None and ns <= supp
    if not (hp or hn): continue
    if not (hp and hn) and rg < single_m: continue
    st = max(0.0, pt + base_dt * 0.45); et = max(st, ct - base_dt * 0.45)
    dur = max(0.0, et - st)
    if st < 0.15 or dur < 0.07 or dur > 0.95: continue
    if total_dur_rec > 0 and et > total_dur_rec - 0.40: continue
    suppressed = max(2, int(round(dur / max(base_dt, 1e-3))))
    breath_peak = max(0.58, min(0.92, 0.54 + dur * 0.75))
    confidence = max(0.56, min(0.90, 0.50 + dur * 0.68))
    events.append(dict(st=st, et=et, dur=dur, rg=rg,
                       suppressed=suppressed, breath_peak=breath_peak,
                       confidence=confidence))

# SMART MERGE
if len(events) > 1:
    events.sort(key=lambda e: e["st"])
    # Build frame confidence timeline
    frame_times_conf = [(t, c) for t, f, c in all_frames if f > 0]
    merged = []
    for e in events:
        if merged:
            prev = merged[-1]
            gap = e["st"] - prev["et"]
            should_merge = False
            if gap <= 0.35:
                should_merge = True
            elif gap <= 0.85:
                mid_confs = [c for t, c in frame_times_conf if prev["et"] <= t <= e["st"]]
                if mid_confs:
                    avg_conf = sum(mid_confs) / len(mid_confs)
                    if avg_conf < 0.42:
                        should_merge = True
                else:
                    should_merge = True
            if should_merge:
                prev["et"] = max(prev["et"], e["et"])
                prev["dur"] = prev["et"] - prev["st"]
                prev["confidence"] = max(prev["confidence"], e["confidence"])
                prev["suppressed"] += e["suppressed"]
                continue
        merged.append(e.copy())
    events = merged

# Apply meaningful filter
print(f"Recording: {total_dur_rec:.1f}s, {len(valid)} pitch frames")
print(f"Events after smart merge: {len(events)}")
passed = 0
for e in events:
    dur = e["dur"]
    contextual = True
    airflow_ok = e["breath_peak"] >= 0.48 and e["breath_peak"] >= 0.56
    gap_ok = e["suppressed"] >= 2 or dur >= 0.10
    short_breath_ok = dur >= 0.24 or e["breath_peak"] >= 0.60
    strong = airflow_ok and gap_ok and short_breath_ok
    rms_ok = True  # no audio
    max_dur = 2.00
    ok = (dur >= 0.08 and dur <= max_dur and contextual and rms_ok and strong and e["confidence"] >= 0.52)
    status = "PASS" if ok else "FAIL"
    reasons = []
    if not ok:
        if dur < 0.08: reasons.append(f"dur={dur:.3f}<0.08")
        if dur > max_dur: reasons.append(f"dur={dur:.3f}>{max_dur}")
    print(f"  {e['st']:.1f}-{e['et']:.1f}s dur={dur:.3f}s: {status}" + (f" ({','.join(reasons)})" if reasons else ""))
    if ok: passed += 1

print(f"\nFinal: {passed} breaths in recording")

# Count by gap clusters
import collections
gap_positions = []
for i in range(1, len(valid)):
    g = valid[i][0] - valid[i-1][0]
    if g > 0.04:
        gap_positions.append((valid[i-1][0], valid[i][0], g))

clusters = []
for s, e, g in gap_positions:
    if clusters and s - clusters[-1][-1][1] <= 0.8:
        clusters[-1].append((s, e, g))
    else:
        clusters.append([(s, e, g)])

print(f"\nGap clusters in audio: {len(clusters)}")
for i, cl in enumerate(clusters):
    mid = (cl[0][0] + cl[-1][1]) / 2
    n_gaps = len(cl)
    g_vals = [f"{g:.3f}" for _, _, g in cl]
    print(f"  Cluster {i+1} @ ~{mid:.1f}s: {n_gaps} gaps ({', '.join(g_vals)}s)")
