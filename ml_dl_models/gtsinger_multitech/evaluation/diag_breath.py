"""Full breath detection diagnostic on a recording."""
import json, sys, numpy as np

fname = sys.argv[1] if len(sys.argv) > 1 else "recordings/analysis_20260602_191954.json"
with open(fname, encoding="utf-8") as f:
    data = json.load(f)

pd = data["pitch_analysis"]["pitch_data"]
base_t = pd[0]["timestamp"]

print(f"Duration: {pd[-1]['timestamp'] - base_t:.1f}s, frames: {len(pd)}")

# Build frame timeline
frames = []
for p in pd:
    t = p["timestamp"] - base_t
    f = p.get("frequency", 0)
    conf = p.get("confidence", 0)
    frames.append((t, f, conf))

# All pitch frames
has_pitch = [(t, f, c) for t, f, c in frames if f > 0]
print(f"Frames with pitch: {len(has_pitch)}")

# Base dt
diffs = []
for i in range(1, len(has_pitch)):
    g = has_pitch[i][0] - has_pitch[i-1][0]
    if g > 0.001:
        diffs.append(g)
base_dt = max(0.008, min(0.080, float(np.median(diffs))))
print(f"base_dt: {base_dt:.4f}s")

# === Show ALL gaps > 0.04s with context ===
print(f"\n{'='*80}")
print("ALL GAPS > 0.04s (with 5-frame neighborhood context)")
print(f"{'='*80}")
for i in range(1, len(has_pitch)):
    gap = has_pitch[i][0] - has_pitch[i-1][0]
    if gap < 0.04:
        continue
    # Show neighborhood: 3 frames before and after
    ctx_start = max(0, i-1-3)
    ctx_end = min(len(has_pitch), i+1+3)
    print(f"\n--- Gap #{len([1 for j in range(1,i) if has_pitch[j][0]-has_pitch[j-1][0] > 0.04])} : {has_pitch[i-1][0]:.2f}s -> {has_pitch[i][0]:.2f}s, gap={gap:.3f}s ---")
    for j in range(ctx_start, ctx_end):
        marker = ""
        if j == i-1: marker = " <-- before gap"
        if j == i: marker = " <-- after gap"
        f_val = has_pitch[j][1]
        print(f"  frame[{j}] t={has_pitch[j][0]:.3f}s freq={f_val:.1f}Hz conf={has_pitch[j][2]:.3f}{marker}")

# === Gap detector simulation ===
print(f"\n{'='*80}")
print("GAP DETECTOR SIMULATION (current parameters)")
print(f"{'='*80}")

min_gap = max(0.06, base_dt * 1.5)
supp = max(0.07, base_dt * 1.5)
single_m = max(0.09, base_dt * 2.2)

print(f"min_gap={min_gap:.3f}s, support={supp:.3f}s, single_min={single_m:.3f}s")
print(f"startup_guard=0.15s, min_dur=0.07s, max_dur=0.95s\n")

events = []
rejected = []
for i in range(1, len(has_pitch)):
    pt, ct = has_pitch[i-1][0], has_pitch[i][0]
    rg = ct - pt

    if rg < min_gap:
        if rg > 0.04:
            rejected.append((pt, ct, rg, f"gap={rg:.3f} < min_gap={min_gap:.3f}"))
        continue

    ps = has_pitch[i-2][0] - pt if i >= 2 else None
    ns = has_pitch[i+1][0] - ct if i + 1 < len(has_pitch) else None
    hp = ps is not None and ps <= supp
    hn = ns is not None and ns <= supp
    both = hp and hn
    single = (hp or hn) and not both

    if not (both or single):
        rejected.append((pt, ct, rg, f"no_support(prev={ps}, next={ns}, limit={supp:.3f})"))
        continue

    if single and rg < single_m:
        rejected.append((pt, ct, rg, f"single_side gap={rg:.3f} < {single_m:.3f}"))
        continue

    st = max(0.0, pt + base_dt * 0.45)
    et = max(st, ct - base_dt * 0.45)
    dur = max(0.0, et - st)

    if st < 0.15:
        rejected.append((pt, ct, rg, f"startup st={st:.3f} < 0.15"))
        continue
    if dur < 0.07:
        rejected.append((pt, ct, rg, f"duration={dur:.3f} < 0.07"))
        continue
    if dur > 0.95:
        rejected.append((pt, ct, rg, f"duration={dur:.3f} > 0.95"))
        continue

    suppressed = max(2, int(round(dur / max(base_dt, 1e-3))))
    breath_peak = max(0.58, min(0.92, 0.54 + dur * 0.75))
    confidence = max(0.56, min(0.90, 0.50 + dur * 0.68))
    events.append(dict(st=st, et=et, dur=dur, rg=rg, pt=pt, ct=ct,
                       suppressed=suppressed, breath_peak=breath_peak,
                       confidence=confidence,
                       mean_rms=0.0, mean_zcr=0.0,
                       pre_pitch=has_pitch[i-1][1], post_pitch=has_pitch[i][1],
                       source_layer="offline_gap_breath"))

print(f"DETECTED gaps: {len(events)}")
for e in events:
    print(f"  {e['st']:.2f}-{e['et']:.2f}s (raw_gap={e['rg']:.3f}s, dur={e['dur']:.3f}s, conf={e['confidence']:.3f})")

print(f"\nREJECTED gaps: {len(rejected)}")
for pt, ct, rg, reason in rejected:
    print(f"  {pt:.2f}-{ct:.2f}s gap={rg:.3f}s: {reason}")

# === Merge ===
if len(events) > 1:
    events.sort(key=lambda e: e["st"])
    merged = []
    for e in events:
        if merged and e["st"] - merged[-1]["et"] <= 0.60:
            merged[-1]["et"] = max(merged[-1]["et"], e["et"])
            merged[-1]["dur"] = merged[-1]["et"] - merged[-1]["st"]
            merged[-1]["confidence"] = max(merged[-1]["confidence"], e["confidence"])
            merged[-1]["suppressed"] += e["suppressed"]
        else:
            merged.append(e.copy())
    events = merged

print(f"\nAFTER MERGE: {len(events)} breath events")
for e in events:
    print(f"  {e['st']:.2f}-{e['et']:.2f}s (dur={e['dur']:.3f}s, conf={e['confidence']:.3f})")

# === Meaningful filter ===
print(f"\n{'='*80}")
print("MEANINGFUL FILTER (FIXED)")
print(f"{'='*80}")

passed = 0
for e in events:
    dur = e["dur"]
    min_d = 0.08
    contextual = (e["pre_pitch"] > 0) and (e["post_pitch"] > 0)
    airflow_ok = e["breath_peak"] >= 0.48 and (e["mean_zcr"] >= 0.06 or e["breath_peak"] >= 0.56)
    gap_ok = e["suppressed"] >= 2 or dur >= max(0.10, min_d + 0.02)
    short_breath_ok = dur >= 0.24 or e["breath_peak"] >= 0.60
    strong_airflow = airflow_ok and gap_ok and short_breath_ok
    has_audio = e["mean_rms"] > 0.0 or e["mean_zcr"] > 0.0
    rms_ok = (not has_audio) or (0.00008 <= e["mean_rms"] <= 0.0080)
    max_dur = 2.00 if e["source_layer"] == "offline_gap_breath" else 1.10

    ok = (dur >= min_d and dur <= max_dur and contextual and rms_ok and
          strong_airflow and (e["confidence"] >= 0.52))

    status = "PASS" if ok else "FAIL"
    reasons = []
    if not (dur >= min_d): reasons.append(f"dur<{min_d}")
    if not (dur <= max_dur): reasons.append(f"dur>{max_dur}")
    if not contextual: reasons.append("!ctx")
    if not rms_ok: reasons.append("!rms")
    if not strong_airflow: reasons.append("!airflow")
    if not (e["confidence"] >= 0.52): reasons.append("!conf")
    reason_str = ",".join(reasons)

    print(f"  {e['st']:.1f}-{e['et']:.1f}s dur={dur:.3f}s: {status}" + (f" ({reason_str})" if reason_str else ""))
    if ok:
        passed += 1

print(f"\nFINAL: {passed} breaths after all filters")

# Summary: where should breaths be?
print(f"\n{'='*80}")
print("SUMMARY: Gap clusters in recording")
print(f"{'='*80}")
# Find all gaps and cluster them
all_gaps = []
for i in range(1, len(has_pitch)):
    g = has_pitch[i][0] - has_pitch[i-1][0]
    if g > 0.04:
        all_gaps.append((has_pitch[i-1][0], has_pitch[i][0], g))

# Group into clusters (within 0.8s)
clusters = []
for s, e, g in all_gaps:
    if clusters and s - clusters[-1][-1][1] <= 0.8:
        clusters[-1].append((s, e, g))
    else:
        clusters.append([(s, e, g)])

print(f"Gap clusters (within 0.8s): {len(clusters)}")
for i, cl in enumerate(clusters):
    times = [f"{s:.1f}-{e:.1f}s" for s, e, g in cl]
    gaps_str = ", ".join([f"{g:.3f}s" for _, _, g in cl])
    print(f"  Cluster {i+1}: {len(cl)} gaps, {gaps_str} @ {times[0]}..{times[-1]}")
