"""Build breath intake training manifest from GTSinger <AP> annotations.

Key difference from the current breath_binary_core:
- breath=1: <AP> (aspirate pause / breath intake) segments
- breath=0: non-AP singing segments (avoiding <AP> regions)
- Uses anchor_ratio to center 2.4s windows at the right position in longer WAV files

Usage:
    python build_breath_intake_manifest.py
    # Output: breath_intake_core/train_manifest.csv, validation_manifest.csv, test_manifest.csv
"""

import csv
import json
import os
import random
import wave
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

RAW = Path(r"d:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\raw")
OUTPUT = Path(r"d:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\breath_intake_core")
WINDOW_SECS = 1.0          # Shorter window for breath intake (transient event)
MIN_WAV_DURATION = 1.2     # Skip WAVs shorter than this
MAX_NEG_PER_FILE = 2       # Max negative samples per WAV file (to keep balance)
NEG_MIN_DISTANCE_AP = 0.3  # Min seconds away from <AP> midpoint for negative anchors
SEED = 42
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15


def get_wav_duration(wav_path: Path) -> float:
    """Get WAV duration in seconds."""
    try:
        with wave.open(str(wav_path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def find_ap_segments(json_data: List[dict]) -> List[Dict]:
    """Find all <AP> (breath intake) segments in a JSON annotation."""
    aps = []
    for item in json_data:
        if item.get("word") == "<AP>":
            start = float(item.get("start_time", 0))
            end = float(item.get("end_time", 0))
            aps.append({
                "start_time": start,
                "end_time": end,
                "midpoint": (start + end) / 2.0,
                "duration": end - start,
            })
    return aps


def find_non_ap_anchors(
    json_data: List[dict],
    ap_segments: List[Dict],
    total_duration: float,
    max_count: int = MAX_NEG_PER_FILE,
) -> List[float]:
    """Find anchor times for non-AP singing segments.

    Returns list of midpoint times (seconds) for safe negative anchors.
    These are word midpoints that don't overlap with any <AP> segment.
    """
    # Collect all word midpoints that aren't <AP>
    candidates = []
    for item in json_data:
        if item.get("word") == "<AP>":
            continue
        start = float(item.get("start_time", 0))
        end = float(item.get("end_time", 0))
        mid = (start + end) / 2.0

        # Check distance to any AP midpoint
        too_close = False
        for ap in ap_segments:
            if abs(mid - ap["midpoint"]) < NEG_MIN_DISTANCE_AP:
                too_close = True
                break
        if too_close:
            continue

        # Check window fits within WAV
        half_win = WINDOW_SECS / 2.0
        if mid - half_win >= 0 and mid + half_win <= total_duration:
            candidates.append(mid)

    if not candidates:
        # Fallback: use equidistant points in safe regions
        safe_regions = []
        prev_end = 0.0
        for ap in sorted(ap_segments, key=lambda a: a["start_time"]):
            gap_start = prev_end + NEG_MIN_DISTANCE_AP
            gap_end = ap["start_time"] - NEG_MIN_DISTANCE_AP
            if gap_end - gap_start >= WINDOW_SECS:
                safe_regions.append((gap_start, gap_end))
            prev_end = ap["end_time"]
        # After last AP
        gap_start = prev_end + NEG_MIN_DISTANCE_AP
        gap_end = total_duration
        if gap_end - gap_start >= WINDOW_SECS:
            safe_regions.append((gap_start, gap_end))

        for gs, ge in safe_regions:
            mid = (gs + ge) / 2.0
            mid = max(WINDOW_SECS / 2, min(total_duration - WINDOW_SECS / 2, mid))
            candidates.append(mid)

    # Limit to max_count, preferring well-separated ones
    if len(candidates) > max_count:
        # Pick evenly spaced
        step = len(candidates) / max_count
        picked = []
        for i in range(max_count):
            idx = int(i * step)
            picked.append(candidates[idx])
        return picked
    return candidates


def process_language(lang: str) -> List[Dict]:
    """Process all JSON/WAV pairs for a language. Returns manifest rows."""
    rows = []
    lang_dir = RAW / lang
    if not lang_dir.exists():
        return rows

    json_files = sorted(lang_dir.rglob("*.json"))
    # Filter out .cache
    json_files = [jf for jf in json_files if ".cache" not in str(jf)]

    for jf in json_files:
        wf = jf.with_suffix(".wav")
        if not wf.exists():
            continue

        total_dur = get_wav_duration(wf)
        if total_dur < MIN_WAV_DURATION:
            continue

        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        if not isinstance(data, list) or len(data) == 0:
            continue

        ap_segments = find_ap_segments(data)

        # Extract metadata
        rel = jf.relative_to(lang_dir)
        parts = rel.parts
        singer = parts[0] if len(parts) > 0 else "unknown"
        technique = parts[1] if len(parts) > 1 else "unknown"
        song_name = parts[2] if len(parts) > 2 else "unknown"

        # Build song key for split
        song_key = f"{lang}/{singer}/{song_name}"

        # Positive samples (breath=1): one per <AP>
        for ap in ap_segments:
            anchor_ratio = ap["midpoint"] / total_dur
            # Clamp to valid range (window must fit)
            half_win_ratio = (WINDOW_SECS / 2.0) / total_dur
            anchor_ratio = max(half_win_ratio, min(1.0 - half_win_ratio, anchor_ratio))

            rows.append({
                "wav_path": str(wf),
                "breath": 1,
                "anchor_ratio": round(anchor_ratio, 6),
                "anchor_time_sec": round(ap["midpoint"], 3),
                "language": lang,
                "singer": singer,
                "song_name": song_name,
                "song_key": song_key,
                "ap_duration_sec": round(ap["duration"], 3),
            })

        # Negative samples (breath=0): from non-AP regions
        neg_anchors = find_non_ap_anchors(data, ap_segments, total_dur)
        for anchor_time in neg_anchors:
            anchor_ratio = anchor_time / total_dur
            half_win_ratio = (WINDOW_SECS / 2.0) / total_dur
            anchor_ratio = max(half_win_ratio, min(1.0 - half_win_ratio, anchor_ratio))

            rows.append({
                "wav_path": str(wf),
                "breath": 0,
                "anchor_ratio": round(anchor_ratio, 6),
                "anchor_time_sec": round(anchor_time, 3),
                "language": lang,
                "singer": singer,
                "song_name": song_name,
                "song_key": song_key,
                "ap_duration_sec": 0.0,
            })

    return rows


def split_by_song(rows: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Split rows by unique songs to prevent data leakage."""
    random.seed(SEED)

    # Group by song_key
    song_groups: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        song_groups[row["song_key"]].append(row)

    songs = list(song_groups.keys())
    random.shuffle(songs)

    n_total = len(songs)
    n_train = int(n_total * TRAIN_RATIO)
    n_val = int(n_total * VAL_RATIO)

    train_songs = set(songs[:n_train])
    val_songs = set(songs[n_train:n_train + n_val])
    test_songs = set(songs[n_train + n_val:])

    train_rows = [row for s in train_songs for row in song_groups[s]]
    val_rows = [row for s in val_songs for row in song_groups[s]]
    test_rows = [row for s in test_songs for row in song_groups[s]]

    return train_rows, val_rows, test_rows


def write_manifest(rows: List[Dict], path: Path, name: str):
    """Write a manifest CSV file."""
    columns = [
        "wav_path", "breath", "anchor_ratio", "anchor_time_sec",
        "language", "singer", "song_name", "song_key", "ap_duration_sec"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["song_key"], r["anchor_time_sec"])):
            writer.writerow(row)
    print(f"  {name}: {len(rows)} rows, "
          f"breath=1: {sum(1 for r in rows if r['breath'] == 1)}, "
          f"breath=0: {sum(1 for r in rows if r['breath'] == 0)}")


def main():
    print("=== Building Breath Intake Manifest (using <AP> annotations) ===\n")

    all_rows = []
    for lang in ["Chinese", "English", "French", "German", "Italian"]:
        print(f"Processing {lang}...")
        rows = process_language(lang)
        pos = sum(1 for r in rows if r["breath"] == 1)
        neg = sum(1 for r in rows if r["breath"] == 0)
        print(f"  {len(rows)} rows (breath=1: {pos}, breath=0: {neg})")
        all_rows.extend(rows)

    print(f"\nTotal: {len(all_rows)} rows")
    total_pos = sum(1 for r in all_rows if r["breath"] == 1)
    total_neg = sum(1 for r in all_rows if r["breath"] == 0)
    print(f"  breath=1: {total_pos}, breath=0: {total_neg}")
    print(f"  Pos/Neg ratio: {total_pos / max(1, total_neg):.2f}")

    # Split by song
    print("\nSplitting by song (70/15/15)...")
    train_rows, val_rows, test_rows = split_by_song(all_rows)

    song_keys_train = set(r["song_key"] for r in train_rows)
    song_keys_val = set(r["song_key"] for r in val_rows)
    song_keys_test = set(r["song_key"] for r in test_rows)

    overlap_tv = song_keys_train & song_keys_val
    overlap_tt = song_keys_train & song_keys_test
    overlap_vt = song_keys_val & song_keys_test

    print(f"  Train songs: {len(song_keys_train)}")
    print(f"  Val songs: {len(song_keys_val)}")
    print(f"  Test songs: {len(song_keys_test)}")
    print(f"  Song overlap check: TV={len(overlap_tv)}, TT={len(overlap_tt)}, VT={len(overlap_vt)} "
          f"({'OK' if not overlap_tv and not overlap_tt and not overlap_vt else 'LEAKAGE!'})")

    # Write manifests
    print("\nWriting manifests...")
    write_manifest(train_rows, OUTPUT / "train_manifest.csv", "Train")
    write_manifest(val_rows, OUTPUT / "validation_manifest.csv", "Val")
    write_manifest(test_rows, OUTPUT / "test_manifest.csv", "Test")

    # Summary
    print(f"\nOutput directory: {OUTPUT}")
    print("Done! Ready to train with:")
    print("  python train_breath_intake_latefusion.py \\")
    print("    --train-manifest breath_intake_core/train_manifest.csv \\")
    print("    --validation-manifest breath_intake_core/validation_manifest.csv \\")
    print("    --test-manifest breath_intake_core/test_manifest.csv")


if __name__ == "__main__":
    main()
