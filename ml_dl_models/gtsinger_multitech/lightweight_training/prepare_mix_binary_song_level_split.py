"""
Prepare mix binary manifests with SONG-LEVEL 70/15/15 split.

Key difference from the original prepare_mix_binary_manifests.py:
  - Original: inherits clip-level random split from multitech_core
    (same song appears in train/val/test = data leakage)
  - This script: all clips from a given (singer, song) go to the SAME split
    (tests generalization to unseen songs, not unseen clips from known songs)

Combines Chinese + English data and uses the same mix_binary negative
sampling logic so training remains compatible.
"""

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split


TARGET_LABEL = 'mix'
LABEL_NAMES = ['mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal']
HARD_NEGATIVE_GROUPS = ('Falsetto_Group', 'Breathy_Group')
OTHER_NEGATIVE_GROUPS = ('Pharyngeal_Group', 'Vibrato_Group', 'Glissando_Group')

SEED = 42


# ── metadata → rows ─────────────────────────────────────────────────────

def parse_item_name(item_name: str) -> dict:
    language, singer, technique, song_name, group_name, clip_id = item_name.split('#', 5)
    return {
        'language': language,
        'singer': singer,
        'technique': technique,
        'song_name': song_name,
        'group_name': group_name,
        'clip_id': clip_id,
    }


def get_flag(meta: dict, name: str) -> int:
    return int(any(meta.get(f'{name}_tech', [])))


def build_rows(metadata: list[dict], raw_root: Path) -> list[dict]:
    rows = []
    for meta in metadata:
        wav_path = raw_root / meta['wav_fn']
        if not wav_path.exists():
            continue
        parsed = parse_item_name(meta['item_name'])
        row = {
            'item_name': meta['item_name'],
            'wav_path': str(wav_path),
            'wav_fn': meta['wav_fn'],
            'language': parsed['language'],
            'singer': parsed['singer'],
            'song_name': parsed['song_name'],
            'group_name': parsed['group_name'],
        }
        for label_name in LABEL_NAMES:
            row[label_name] = get_flag(meta, label_name)
        row['any_tech'] = int(any(row[label_name] for label_name in LABEL_NAMES))
        if row['mix'] and row['breathy']:
            row['mix_variant'] = 'breathy_mix'
        elif row['mix'] and row['falsetto']:
            row['mix_variant'] = 'head_mix'
        elif row['mix']:
            row['mix_variant'] = 'clear_mix'
        else:
            row['mix_variant'] = 'non_mix'
        signature = ''.join(str(row[label_name]) for label_name in LABEL_NAMES)
        row['label_signature'] = signature
        rows.append(row)
    return rows


# ── song-level split ─────────────────────────────────────────────────────

def build_song_key(row: dict) -> str:
    """Unique song identity = singer + song_name."""
    return f"{row['singer']}|||{row['song_name']}"


def build_song_stratum(song_rows: list[dict]) -> str:
    """Build a stratification label for a song based on its technique profile."""
    has_mix = any(r['mix'] for r in song_rows)
    has_falsetto = any(r['falsetto'] for r in song_rows)
    has_breathy = any(r['breathy'] for r in song_rows)
    singer = song_rows[0]['singer']
    language = song_rows[0]['language']
    # Combine language + singer + technique profile for stratification
    tech_profile = f"{'M' if has_mix else 'm'}{'F' if has_falsetto else 'f'}{'B' if has_breathy else 'b'}"
    return f"{language}|{singer}|{tech_profile}"


def split_songs(all_rows: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict], list[dict]]:
    """Split by unique SONGS at 70/15/15, not by clips."""
    # Group clips by song
    song_groups: dict[str, list[dict]] = {}
    for row in all_rows:
        key = build_song_key(row)
        song_groups.setdefault(key, []).append(row)

    print(f"Total clips: {len(all_rows)}, unique songs: {len(song_groups)}")

    # Build per-song summary for stratification
    song_keys = list(song_groups.keys())
    song_strata = [build_song_stratum(song_groups[k]) for k in song_keys]

    # Count stratum frequencies to ensure we only use strata with >= 3 songs
    stratum_counts = Counter(song_strata)
    safe_strata = []
    for s in song_strata:
        if stratum_counts[s] >= 3:
            safe_strata.append(s)
        else:
            safe_strata.append('_fallback_')

    print(f"Strata: {len(set(safe_strata))} unique, min count: {min(Counter(safe_strata).values())}")

    # First split: train (70%) vs temp (30%)
    train_indices, temp_indices = train_test_split(
        range(len(song_keys)),
        test_size=0.30,
        random_state=seed,
        stratify=safe_strata,
    )

    # Second split: val (50% of temp = 15%) vs test (50% of temp = 15%)
    temp_strata = [safe_strata[i] for i in temp_indices]
    temp_stratum_counts = Counter(temp_strata)
    temp_safe_strata = []
    for s in temp_strata:
        if temp_stratum_counts[s] >= 3:
            temp_safe_strata.append(s)
        else:
            temp_safe_strata.append('_fallback_')

    val_rel_indices, test_rel_indices = train_test_split(
        range(len(temp_indices)),
        test_size=0.50,
        random_state=seed,
        stratify=temp_safe_strata,
    )

    val_indices = [temp_indices[i] for i in val_rel_indices]
    test_indices = [temp_indices[i] for i in test_rel_indices]

    # Collect clips for each split
    def collect(indices):
        rows = []
        for i in indices:
            rows.extend(song_groups[song_keys[i]])
        return rows

    train_rows = collect(train_indices)
    val_rows = collect(val_indices)
    test_rows = collect(test_indices)

    # Report
    train_songs = len({build_song_key(r) for r in train_rows})
    val_songs = len({build_song_key(r) for r in val_rows})
    test_songs = len({build_song_key(r) for r in test_rows})

    train_singers = set(r['singer'] for r in train_rows)
    val_singers = set(r['singer'] for r in val_rows)
    test_singers = set(r['singer'] for r in test_rows)

    print(f"Train: {len(train_rows)} clips, {train_songs} songs, singers={train_singers}")
    print(f"Val:   {len(val_rows)} clips, {val_songs} songs, singers={val_singers}")
    print(f"Test:  {len(test_rows)} clips, {test_songs} songs, singers={test_singers}")

    # Verify no song overlap
    train_song_set = {build_song_key(r) for r in train_rows}
    val_song_set = {build_song_key(r) for r in val_rows}
    test_song_set = {build_song_key(r) for r in test_rows}
    assert not (train_song_set & val_song_set), f"Song overlap train-val: {len(train_song_set & val_song_set)}"
    assert not (train_song_set & test_song_set), f"Song overlap train-test: {len(train_song_set & test_song_set)}"
    assert not (val_song_set & test_song_set), f"Song overlap val-test: {len(val_song_set & test_song_set)}"
    print("Song-level split verified: zero overlap across splits.")

    return train_rows, val_rows, test_rows


# ── mix_binary sampling (same logic as prepare_mix_binary_manifests.py) ──

def is_mix_positive(row: dict) -> bool:
    return int(float(row[TARGET_LABEL])) == 1


def negative_bucket(row: dict) -> str:
    group_name = str(row.get('group_name', '') or '')
    if is_mix_positive(row):
        return 'positive_mix'
    if group_name == 'Control_Group':
        return 'control_negative'
    if group_name in HARD_NEGATIVE_GROUPS:
        return f'{group_name.lower()}'
    return 'other_negative'


def row_priority(row: dict) -> tuple:
    falsetto = int(float(row.get('falsetto', 0) or 0))
    breathy = int(float(row.get('breathy', 0) or 0))
    vibrato = int(float(row.get('vibrato', 0) or 0))
    glissando = int(float(row.get('glissando', 0) or 0))
    pharyngeal = int(float(row.get('pharyngeal', 0) or 0))
    hard_negative_hits = falsetto + breathy
    other_hits = vibrato + glissando + pharyngeal
    group_name = str(row.get('group_name', '') or '')
    group_rank = {
        'Falsetto_Group': 0,
        'Breathy_Group': 1,
        'Control_Group': 2,
        'Pharyngeal_Group': 3,
        'Vibrato_Group': 4,
        'Glissando_Group': 5,
    }.get(group_name, 9)
    return (
        -hard_negative_hits,
        -other_hits,
        group_rank,
        str(row.get('singer', '') or ''),
        str(row.get('song_name', '') or ''),
        str(row.get('item_name', '') or ''),
    )


def sample_rows(rows: list[dict], keep_count: int, seed: int) -> list[dict]:
    if keep_count <= 0:
        return []
    if len(rows) <= keep_count:
        return sorted(rows, key=row_priority)
    rnd = random.Random(seed)
    pool = list(rows)
    rnd.shuffle(pool)
    pool.sort(key=row_priority)
    return pool[:keep_count]


def attach_role(rows: list[dict]) -> list[dict]:
    enriched = []
    for row in rows:
        item = dict(row)
        item['binary_role'] = negative_bucket(row)
        enriched.append(item)
    return enriched


def build_mix_binary_split(
    rows: list[dict],
    *,
    keep_control_ratio: float,
    keep_falsetto_ratio: float,
    keep_breathy_ratio: float,
    keep_other_negative_ratio: float,
    seed: int,
) -> list[dict]:
    positives = [dict(row) for row in rows if is_mix_positive(row)]
    control_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Control_Group']
    falsetto_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Falsetto_Group']
    breathy_negatives = [dict(row) for row in rows if (not is_mix_positive(row)) and row.get('group_name') == 'Breathy_Group']
    other_negatives = [
        dict(row)
        for row in rows
        if (not is_mix_positive(row)) and row.get('group_name') in OTHER_NEGATIVE_GROUPS
    ]

    positive_count = len(positives)
    selected = []
    selected.extend(attach_role(sorted(positives, key=row_priority)))
    selected.extend(attach_role(sample_rows(control_negatives, int(round(positive_count * keep_control_ratio)), seed=seed)))
    selected.extend(attach_role(sample_rows(falsetto_negatives, int(round(positive_count * keep_falsetto_ratio)), seed=seed + 1)))
    selected.extend(attach_role(sample_rows(breathy_negatives, int(round(positive_count * keep_breathy_ratio)), seed=seed + 2)))
    selected.extend(attach_role(sample_rows(other_negatives, int(round(positive_count * keep_other_negative_ratio)), seed=seed + 3)))
    for row in selected:
        row.setdefault('mined_mix_prob', '')
        row.setdefault('control_stratum', '')
    selected.sort(key=lambda row: (str(row.get('group_name', '') or ''), str(row.get('singer', '') or ''), str(row.get('song_name', '') or ''), str(row.get('item_name', '') or '')))
    return selected


def summarize(rows: list[dict]) -> dict:
    return {
        'items': len(rows),
        'mix_positive': sum(1 for row in rows if is_mix_positive(row)),
        'mix_negative': sum(1 for row in rows if not is_mix_positive(row)),
        'binary_roles': dict(Counter(str(row.get('binary_role', '') or '') for row in rows)),
        'groups': dict(Counter(str(row.get('group_name', '') or '') for row in rows)),
        'singers': dict(Counter(str(row.get('singer', '') or '') for row in rows)),
        'languages': dict(Counter(str(row.get('language', '') or '') for row in rows)),
        'mix_variants': dict(Counter(str(row.get('mix_variant', '') or '') for row in rows if is_mix_positive(row))),
        'songs': len(set(build_song_key(r) for r in rows)),
    }


# ── I/O ──────────────────────────────────────────────────────────────────

FIELD_NAMES = [
    'item_name', 'wav_path', 'wav_fn', 'language', 'singer', 'song_name',
    'group_name', 'mix', 'falsetto', 'breathy', 'vibrato', 'glissando',
    'pharyngeal', 'any_tech', 'mix_variant', 'label_signature',
    'binary_role', 'mined_mix_prob', 'control_stratum',
]


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'No rows to write for {path}')
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, splits: dict, params: dict) -> None:
    lines = [
        '# Mix Binary Song-Level Split Summary',
        '',
        '- split_method: song_level_70_15_15',
        f'- keep_control_ratio: {params["keep_control_ratio"]}',
        f'- keep_falsetto_ratio: {params["keep_falsetto_ratio"]}',
        f'- keep_breathy_ratio: {params["keep_breathy_ratio"]}',
        f'- keep_other_negative_ratio: {params["keep_other_negative_ratio"]}',
        f'- seed: {params["seed"]}',
        '',
        '## Key Difference from Original',
        '',
        '- Split is by SONG, not by clip.',
        '- All clips from a given (singer, song) pair go to exactly one split.',
        '- Zero song overlap between train/val/test.',
        '- Tests generalization to UNSEEN songs, not unseen clips from known songs.',
        '',
    ]
    for split_name, rows in splits.items():
        stats = summarize(rows)
        positive_rate = (stats['mix_positive'] / stats['items']) if stats['items'] else 0.0
        lines.append(f'## {split_name.title()}')
        lines.append('')
        lines.append(f'- items: {stats["items"]}')
        lines.append(f'- songs: {stats["songs"]}')
        lines.append(f'- mix_positive: {stats["mix_positive"]}')
        lines.append(f'- mix_negative: {stats["mix_negative"]}')
        lines.append(f'- mix_positive_rate: {positive_rate:.4f}')
        for role_name, count in sorted(stats['binary_roles'].items()):
            lines.append(f'- role_{role_name}: {count}')
        for group_name, count in sorted(stats['groups'].items()):
            lines.append(f'- group_{group_name}: {count}')
        for singer_name, count in sorted(stats['singers'].items()):
            lines.append(f'- singer_{singer_name}: {count}')
        for lang_name, count in sorted(stats['languages'].items()):
            lines.append(f'- language_{lang_name}: {count}')
        for variant_name, count in sorted(stats['mix_variants'].items()):
            lines.append(f'- mix_variant_{variant_name}: {count}')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


# ── main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Prepare mix binary manifests with song-level split.')
    parser.add_argument('--output-dir', default=r'd:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\mix_binary_song_level_v1')
    parser.add_argument('--keep-control-ratio', type=float, default=0.55)
    parser.add_argument('--keep-falsetto-ratio', type=float, default=0.55)
    parser.add_argument('--keep-breathy-ratio', type=float, default=0.35)
    parser.add_argument('--keep-other-negative-ratio', type=float, default=0.25)
    parser.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    base_dir = Path(__file__).resolve().parents[1]
    raw_root = base_dir / 'dataset' / 'raw'

    # Load metadata for all available languages
    all_rows: list[dict] = []
    lang_dirs = sorted([
        d for d in (base_dir / 'dataset' / 'processed').iterdir()
        if d.is_dir() and (d / 'metadata.json').exists()
    ])
    for lang_dir in lang_dirs:
        language = lang_dir.name
        meta_path = lang_dir / 'metadata.json'
        metadata = json.loads(meta_path.read_text(encoding='utf-8'))
        rows = build_rows(metadata, raw_root)
        all_rows.extend(rows)
        print(f'{language}: {len(rows)} valid clips (from {len(metadata)} metadata entries)')

    print(f'Combined: {len(all_rows)} clips from {len(lang_dirs)} languages')

    # Song-level split
    train_rows, val_rows, test_rows = split_songs(all_rows, seed=args.seed)

    # Apply mix_binary sampling to each split
    print('\n--- Applying mix_binary sampling ---')
    splits = {}
    for split_name, rows in [('train', train_rows), ('validation', val_rows), ('test', test_rows)]:
        print(f'Sampling {split_name}...')
        split_rows = build_mix_binary_split(
            rows,
            keep_control_ratio=args.keep_control_ratio,
            keep_falsetto_ratio=args.keep_falsetto_ratio,
            keep_breathy_ratio=args.keep_breathy_ratio,
            keep_other_negative_ratio=args.keep_other_negative_ratio,
            seed=args.seed + {'train': 0, 'validation': 17, 'test': 34}[split_name],
        )
        splits[split_name] = split_rows
        stats = summarize(split_rows)
        print(f'  {split_name}: {stats["items"]} items, {stats["songs"]} songs, '
              f'mix_pos={stats["mix_positive"]}, mix_neg={stats["mix_negative"]}, '
              f'singers={sorted(stats["singers"].keys())}')

    # Write output
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for split_name, rows in splits.items():
        write_manifest(output_dir / f'{split_name}_manifest.csv', rows)

    params = {
        'keep_control_ratio': args.keep_control_ratio,
        'keep_falsetto_ratio': args.keep_falsetto_ratio,
        'keep_breathy_ratio': args.keep_breathy_ratio,
        'keep_other_negative_ratio': args.keep_other_negative_ratio,
        'seed': args.seed,
    }
    write_summary(output_dir / 'manifest_summary.md', splits, params)

    print(f'\nWrote manifests to {output_dir}')


if __name__ == '__main__':
    main()
