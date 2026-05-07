import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


RELEVANT_TECHNIQUES = (
    'mix',
    'falsetto',
    'breathy',
    'vibrato',
)

TECH_SCORE = {
    'mix': 5,
    'falsetto': 5,
    'breathy': 5,
    'vibrato': 2,
    'glissando': 1,
    'pharyngeal': 1,
}


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


def has_positive(meta: dict, name: str) -> int:
    values = meta.get(f'{name}_tech', [])
    return int(any(values))


def score_item(meta: dict) -> int:
    score = 0
    for name, weight in TECH_SCORE.items():
        if has_positive(meta, name):
            score += weight
    return score


def build_rows(metadata: list[dict]) -> tuple[list[dict], Counter]:
    by_song = defaultdict(list)
    selected_song_keys = set()
    technique_counter = Counter()

    for meta in metadata:
        parsed = parse_item_name(meta['item_name'])
        song_key = (parsed['singer'], parsed['song_name'])
        row = {
            'item_name': meta['item_name'],
            'wav_fn': meta['wav_fn'],
            'singer': parsed['singer'],
            'song_name': parsed['song_name'],
            'group_name': parsed['group_name'],
            'mix': has_positive(meta, 'mix'),
            'falsetto': has_positive(meta, 'falsetto'),
            'breathy': has_positive(meta, 'breathy'),
            'vibrato': has_positive(meta, 'vibrato'),
            'glissando': has_positive(meta, 'glissando'),
            'pharyngeal': has_positive(meta, 'pharyngeal'),
            'priority_score': score_item(meta),
            'download_reason': '',
        }
        by_song[song_key].append(row)
        if any(row[name] for name in RELEVANT_TECHNIQUES):
            selected_song_keys.add(song_key)
            for name in RELEVANT_TECHNIQUES:
                if row[name]:
                    technique_counter[name] += 1

    candidates: list[dict] = []
    for song_key in sorted(selected_song_keys):
        rows = by_song[song_key]
        for row in rows:
            if row['group_name'] == 'Control_Group':
                row['download_reason'] = 'matched_control_for_target_song'
                row['priority_score'] = max(row['priority_score'], 2)
                candidates.append(row)
                continue
            if any(row[name] for name in RELEVANT_TECHNIQUES):
                active = [name for name in RELEVANT_TECHNIQUES if row[name]]
                row['download_reason'] = 'target_techniques:' + ','.join(active)
                candidates.append(row)

    candidates.sort(
        key=lambda row: (
            -row['priority_score'],
            row['singer'],
            row['song_name'],
            row['group_name'],
            row['item_name'],
        )
    )
    return candidates, technique_counter


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        'item_name',
        'wav_fn',
        'singer',
        'song_name',
        'group_name',
        'mix',
        'falsetto',
        'breathy',
        'vibrato',
        'glissando',
        'pharyngeal',
        'priority_score',
        'download_reason',
    ]
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict], technique_counter: Counter) -> None:
    group_counter = Counter(row['group_name'] for row in rows)
    singer_counter = Counter(row['singer'] for row in rows)
    lines = [
        '# English Download Candidates',
        '',
        f'- candidate_items: {len(rows)}',
        f'- unique_singers: {len(singer_counter)}',
        '',
        '## Relevant Technique Counts',
        '',
    ]
    for name, count in technique_counter.most_common():
        lines.append(f'- {name}: {count}')
    lines.extend([
        '',
        '## Group Counts',
        '',
    ])
    for name, count in group_counter.most_common():
        lines.append(f'- {name}: {count}')
    lines.extend([
        '',
        '## Top Singers By Candidate Count',
        '',
    ])
    for singer, count in singer_counter.most_common(10):
        lines.append(f'- {singer}: {count}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    metadata_path = base_dir / 'dataset' / 'processed' / 'English' / 'metadata.json'
    output_dir = base_dir / 'dataset' / 'curated'
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / 'english_download_candidates.csv'
    summary_path = output_dir / 'english_download_candidates_summary.md'

    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    rows, technique_counter = build_rows(metadata)
    write_csv(csv_path, rows)
    write_summary(summary_path, rows, technique_counter)

    print(f'wrote {csv_path}')
    print(f'wrote {summary_path}')
    print(f'candidate_count={len(rows)}')


if __name__ == '__main__':
    main()