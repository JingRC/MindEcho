import json, numpy as np, sys

fname = sys.argv[1] if len(sys.argv) > 1 else "recordings/analysis_20260602_191120.json"
with open(fname, encoding="utf-8") as f:
    data = json.load(f)

pd = data["pitch_analysis"]["pitch_data"]
base_t = pd[0]["timestamp"]
valid = [(p["timestamp"] - base_t, p.get("frequency", 0)) for p in pd if p.get("frequency", 0) > 0]

diffs = [valid[i][0] - valid[i-1][0] for i in range(1, len(valid)) if valid[i][0] - valid[i-1][0] > 0.001]
base_dt = max(0.008, min(0.080, float(np.median(diffs))))

min_gap = max(0.06, base_dt * 1.5)
supp = max(0.07, base_dt * 1.5)
single_m = max(0.09, base_dt * 2.2)

events = []
for i in range(1, len(valid)):
    pt, ct = valid[i-1][0], valid[i][0]
    rg = ct - pt
    if rg < min_gap:
        continue
    ps = valid[i-2][0] - pt if i >= 2 else None
    ns = valid[i+1][0] - ct if i + 1 < len(valid) else None
    hp = ps is not None and ps <= supp
    hn = ns is not None and ns <= supp
    if not (hp or hn):
        continue
    if not (hp and hn) and rg < single_m:
        continue
    st = max(0.0, pt + base_dt * 0.45)
    et = max(st, ct - base_dt * 0.45)
    dur = max(0.0, et - st)
    if st < 0.15 or dur < 0.07 or dur > 0.95:
        continue
    suppressed = max(2, int(round(dur / max(base_dt, 1e-3))))
    breath_peak = max(0.58, min(0.92, 0.54 + dur * 0.75))
    confidence = max(0.56, min(0.90, 0.50 + dur * 0.68))
    events.append(dict(st=st, et=et, dur=dur, rg=rg, suppressed=suppressed,
                       breath_peak=breath_peak, confidence=confidence,
                       mean_rms=0.0, mean_zcr=0.0,
                       pre_pitch=220.0, post_pitch=220.0,
                       source_layer="offline_gap_breath"))

# Merge
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

# Apply fixed filter
print(f"Merged events: {len(events)}")
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
    if not (dur >= min_d): reasons.append("dur<min")
    if not (dur <= max_dur): reasons.append("dur>max")
    if not contextual: reasons.append("!ctx")
    if not rms_ok: reasons.append("!rms")
    if not strong_airflow: reasons.append("!airflow")
    if not (e["confidence"] >= 0.52): reasons.append("!conf")
    reason_str = ",".join(reasons) if reasons else ""

    print(f"  {e['st']:.1f}-{e['et']:.1f}s dur={dur:.3f}s: {status}" + (f" ({reason_str})" if reason_str else ""))
    if ok:
        passed += 1

print(f"\nFinal: {passed} breaths pass filter (user expects 4)")
if passed < 4:
    print("Still missing some. Checking raw gaps for undetected breath locations...")
