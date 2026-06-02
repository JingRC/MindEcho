"""Evaluate gap-based breath detector against GTSinger <AP> ground truth.

Simulates the gap detection logic from _build_offline_gap_breath_events
using the annotated note timestamps to check if each <AP> would be detected.
"""

import csv
import json
import os
import wave
from pathlib import Path
from collections import defaultdict
import numpy as np

MANIFEST = Path(r"d:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\breath_intake_core\test_manifest.csv")

# Mirror the detector parameters (POST-optimization values)
MIN_GAP_FACTOR = 1.5       # raw_gap < max(0.06, base_dt * MIN_GAP_FACTOR)
MIN_GAP_ABS = 0.06         # absolute minimum gap
SUPPORT_FACTOR = 1.5       # support_gap_limit = max(0.07, base_dt * SUPPORT_FACTOR)
SUPPORT_ABS = 0.07         # absolute support limit
SINGLE_SUPPORT_FACTOR = 2.2  # single_support gap = max(0.09, base_dt * SINGLE_SUPPORT_FACTOR)
SINGLE_SUPPORT_ABS = 0.09
STARTUP_GUARD = 0.30       # skip first N seconds
MIN_DURATION = 0.07        # min breath duration
MAX_DURATION = 0.95        # max breath duration

# OLD values for comparison
OLD_MIN_GAP_FACTOR = 1.8
OLD_MIN_GAP_ABS = 0.07
OLD_SUPPORT_FACTOR = 1.7
OLD_SUPPORT_ABS = 0.09
OLD_SINGLE_SUPPORT_FACTOR = 3.0
OLD_SINGLE_SUPPORT_ABS = 0.12
OLD_STARTUP_GUARD = 0.50
OLD_MIN_DURATION = 0.09


def get_wav_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def extract_gaps_from_json(json_path: str):
    """Extract inter-note gaps from a GTSinger JSON. Returns list of gaps with metadata."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []

    # Collect all note boundaries
    note_events = []  # (time, type, is_ap)
    for item in data:
        word = item.get("word", "")
        is_ap = word == "<AP>"
        note_starts = item.get("note_start", [])
        note_ends = item.get("note_end", [])
        for ns in note_starts:
            note_events.append((float(ns), "start", is_ap))
        for ne in note_ends:
            note_events.append((float(ne), "end", is_ap))

    note_events.sort(key=lambda x: x[0])

    # Build timeline: when does singing stop and resume?
    # A "note frame" exists when we're inside a note (between start and end)
    # The gap detector works on "has_pitch" frames

    # Actually, let's use a simpler model:
    # Each note creates pitch frames from note_start to note_end
    # Gaps exist between consecutive note_end and next note_start
    # <AP> segments are between notes

    gaps = []
    for i in range(len(data)):
        item = data[i]
        word = item.get("word", "")
        note_starts = [float(x) for x in item.get("note_start", [])]
        note_ends = [float(x) for x in item.get("note_end", [])]

        # Get previous note's end time
        prev_end = 0.0
        if i > 0:
            prev_item = data[i - 1]
            prev_ends = [float(x) for x in prev_item.get("note_end", [])]
            prev_end = prev_ends[-1] if prev_ends else prev_end

        # Get next note's start time
        next_start = float("inf")
        if i + 1 < len(data):
            next_item = data[i + 1]
            next_starts = [float(x) for x in next_item.get("note_start", [])]
            next_start = next_starts[0] if next_starts else next_start

        gap_before = float(note_starts[0]) - prev_end if note_starts else 0.0
        gap_after = next_start - float(note_ends[-1]) if note_ends else 0.0

        gaps.append({
            "word": word,
            "is_ap": word == "<AP>",
            "start_time": float(item.get("start_time", 0)),
            "end_time": float(item.get("end_time", 0)),
            "prev_gap": max(0.0, gap_before),
            "next_gap": max(0.0, gap_after),
            "ap_duration": float(item.get("end_time", 0)) - float(item.get("start_time", 0)),
        })

    return gaps


def evaluate_detector(gaps_list, json_data, total_duration, use_old_params=False):
    """Apply gap detector logic to frame-level note timeline and check <AP> detection."""

    if use_old_params:
        min_gap_factor = OLD_MIN_GAP_FACTOR
        min_gap_abs = OLD_MIN_GAP_ABS
        support_factor = OLD_SUPPORT_FACTOR
        support_abs = OLD_SUPPORT_ABS
        single_factor = OLD_SINGLE_SUPPORT_FACTOR
        single_abs = OLD_SINGLE_SUPPORT_ABS
        startup_guard = OLD_STARTUP_GUARD
        min_duration = OLD_MIN_DURATION
    else:
        min_gap_factor = MIN_GAP_FACTOR
        min_gap_abs = MIN_GAP_ABS
        support_factor = SUPPORT_FACTOR
        support_abs = SUPPORT_ABS
        single_factor = SINGLE_SUPPORT_FACTOR
        single_abs = SINGLE_SUPPORT_ABS
        startup_guard = STARTUP_GUARD
        min_duration = MIN_DURATION

    # Build pitch FRAME timeline (simulating CREPE-like 10ms hop from note annotations)
    # Each note_start→note_end period has continuous pitch at ~10ms intervals
    # Gaps only exist BETWEEN notes (where there's no singing)
    FRAME_HOP = 0.01  # 10ms like CREPE

    frame_times = []
    note_regions = []  # (start, end) of each note

    for item in json_data:
        note_starts = [float(x) for x in item.get("note_start", [])]
        note_ends = [float(x) for x in item.get("note_end", [])]
        notes = item.get("note", [])
        for j, (ns, ne) in enumerate(zip(note_starts, note_ends)):
            note_val = int(notes[j]) if j < len(notes) else -1
            # Skip note=0 (AP/breath segments have no pitch)
            if ne > ns and note_val != 0:
                note_regions.append((ns, ne))

    note_regions.sort()

    # Merge overlapping note regions (e.g., melismas where notes overlap)
    merged = []
    for ns, ne in note_regions:
        if merged and ns <= merged[-1][1] + FRAME_HOP:
            merged[-1] = (merged[-1][0], max(merged[-1][1], ne))
        else:
            merged.append((ns, ne))
    note_regions = merged

    # Generate frames within each note region at FRAME_HOP intervals
    for ns, ne in note_regions:
        t = ns
        while t <= ne + FRAME_HOP * 0.5:
            frame_times.append(t)
            t += FRAME_HOP

    if len(frame_times) < 3:
        return {"tp": 0, "fp": 0, "fn": 0, "total_ap": 0, "total_dets": 0, "detected_aps": []}

    # Compute base_dt (median gap between frames)
    diffs = []
    for i in range(1, len(frame_times)):
        gap = frame_times[i] - frame_times[i - 1]
        if gap > 0.001:
            diffs.append(gap)

    if not diffs:
        return {"tp": 0, "fp": 0, "fn": 0, "total_ap": 0, "total_dets": 0, "detected_aps": []}

    base_dt = max(0.008, min(0.080, float(np.median(diffs))))

    # Detect gaps
    detected_times = []  # (start_time, end_time) of detected breaths
    for i in range(1, len(frame_times)):
        prev_t = frame_times[i - 1]
        cur_t = frame_times[i]
        raw_gap = cur_t - prev_t

        if raw_gap < max(min_gap_abs, base_dt * min_gap_factor):
            continue

        # Check adjacent support
        prev_support_gap = None
        next_support_gap = None
        if i >= 2:
            prev_support_gap = prev_t - frame_times[i - 2]
        if i + 1 < len(frame_times):
            next_support_gap = frame_times[i + 1] - cur_t

        support_gap_limit = max(support_abs, base_dt * support_factor)
        has_prev = prev_support_gap is not None and prev_support_gap <= support_gap_limit
        has_next = next_support_gap is not None and next_support_gap <= support_gap_limit
        both = has_prev and has_next
        single = (has_prev or has_next) and not both

        if not (both or single):
            continue

        if single and raw_gap < max(single_abs, base_dt * single_factor):
            continue

        start_time = max(0.0, prev_t + base_dt * 0.45)
        end_time = max(start_time, cur_t - base_dt * 0.45)
        duration = max(0.0, end_time - start_time)

        if start_time < startup_guard:
            continue

        if duration < min_duration or duration > MAX_DURATION:
            continue

        detected_times.append((start_time, end_time))

    # Match detected breaths against <AP> ground truth
    tp = 0
    fp = 0
    fn = 0
    detected_aps = []

    ap_segments = [(g["start_time"], g["end_time"]) for g in gaps_list if g["is_ap"]]
    matched_ap = set()

    for dt_start, dt_end in detected_times:
        # Check if this detected breath overlaps with any <AP>
        matched = False
        for ap_idx, (ap_start, ap_end) in enumerate(ap_segments):
            if ap_idx in matched_ap:
                continue
            # Check overlap: detected breath overlaps with AP
            overlap = max(0.0, min(dt_end, ap_end) - max(dt_start, ap_start))
            if overlap > 0.0 and overlap >= min(dt_end - dt_start, ap_end - ap_start) * 0.3:
                matched = True
                matched_ap.add(ap_idx)
                break
        if matched:
            tp += 1
        else:
            fp += 1

    fn = len(ap_segments) - len(matched_ap)

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "total_ap": len(ap_segments),
        "detected_aps": list(matched_ap),
        "total_dets": len(detected_times),
    }


def main():
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))

    # Group by WAV (each WAV has multiple rows with different anchors)
    wav_groups = defaultdict(list)
    for row in rows:
        wav_groups[row["wav_path"]].append(row)

    print(f"Evaluating on {len(wav_groups)} unique WAVs from test set...\n")

    # Process each WAV once
    results_new = {"tp": 0, "fp": 0, "fn": 0, "total_ap": 0, "total_dets": 0}
    results_old = {"tp": 0, "fp": 0, "fn": 0, "total_ap": 0, "total_dets": 0}

    skipped = 0
    processed = 0
    ap_wavs_with_detection = 0
    total_ap_wavs = 0

    for wav_path, wav_rows in wav_groups.items():
        json_path = wav_path.replace(".wav", ".json")
        if not os.path.exists(json_path):
            skipped += 1
            continue

        # Extract gaps and load JSON data
        try:
            all_gaps = extract_gaps_from_json(json_path)
            total_dur = get_wav_duration(wav_path)
            with open(json_path, encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception:
            skipped += 1
            continue

        if total_dur <= 0:
            total_dur = max(
                max((float(item.get("end_time", 0)) for item in json_data if item.get("end_time")), default=5.0),
                5.0
            )

        # Test with new parameters
        r_new = evaluate_detector(all_gaps, json_data, total_dur, use_old_params=False)
        # Test with old parameters
        r_old = evaluate_detector(all_gaps, json_data, total_dur, use_old_params=True)

        for k in results_new:
            results_new[k] += r_new[k]
        for k in results_old:
            results_old[k] += r_old[k]

        if r_new["total_ap"] > 0:
            total_ap_wavs += 1
            if r_new["tp"] > 0:
                ap_wavs_with_detection += 1

        processed += 1

    print(f"Processed: {processed} WAVs, Skipped: {skipped}")
    print(f"WAVs with <AP>: {total_ap_wavs}")
    print()

    def print_metrics(name, r, label):
        tp, fp, fn = r["tp"], r["fp"], r["fn"]
        total = r["total_ap"]
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(0.001, precision + recall)

        print(f"=== {name} ===")
        print(f"  Ground truth <AP>: {total}")
        print(f"  Detected breaths:  {r['total_dets']}")
        print(f"  True Positives:    {tp}")
        print(f"  False Positives:   {fp}")
        print(f"  False Negatives:   {fn}")
        print(f"  Precision: {precision:.3f} ({precision*100:.1f}%)")
        print(f"  Recall:    {recall:.3f} ({recall*100:.1f}%)")
        print(f"  F1 Score:  {f1:.3f}")
        print()

    print_metrics("NEW parameters (optimized)", results_new, "new")
    print_metrics("OLD parameters (before optimization)", results_old, "old")

    recall_improvement = (results_new["tp"] / max(1, results_new["total_ap"]) -
                          results_old["tp"] / max(1, results_old["total_ap"])) * 100
    precision_change = (results_new["tp"] / max(1, results_new["tp"] + results_new["fp"]) -
                        results_old["tp"] / max(1, results_old["tp"] + results_old["fp"])) * 100

    print(f"Recall improvement: {recall_improvement:+.1f}pp")
    print(f"Precision change:  {precision_change:+.1f}pp")
    print(f"WAV-level detection rate: {ap_wavs_with_detection}/{total_ap_wavs} ({ap_wavs_with_detection/max(1,total_ap_wavs)*100:.1f}%)")


if __name__ == "__main__":
    main()
