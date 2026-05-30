"""Download French, German, Italian data from HF mirror by traversing directory tree level by level."""
import json, time, urllib.parse, urllib.request, threading, csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter

BASE_URL = 'https://hf-mirror.com/datasets/GTSinger/GTSinger/resolve/main'
API_BASE = 'https://hf-mirror.com/api/datasets/GTSinger/GTSinger'
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = BASE_DIR / 'dataset' / 'raw'
PROCESSED_ROOT = BASE_DIR / 'dataset' / 'processed'

NEW_LANGUAGES = ['French', 'German', 'Italian']

# Technique folders that contain groups relevant to mix binary training
RELEVANT_TECHNIQUE_FOLDERS = {
    'Mixed_Voice_and_Falsetto',  # Contains Mixed_Voice_Group and Falsetto_Group
    'Breathy',
    'Vibrato',
    'Glissando',
    'Pharyngeal',
}

WORKERS = 8
TIMEOUT = 60.0
RETRIES = 3
RETRY_WAIT = 2.0


def api_get(url: str) -> list[dict]:
    """Get JSON from HF API with pagination support."""
    all_items = []
    next_url = url
    while next_url:
        # URL-encode spaces and non-ASCII in the path (HF API expects encoded URLs)
        if ' ' in next_url or any(ord(c) > 127 for c in next_url):
            next_url = urllib.parse.quote(next_url, safe='/:?=&')
        req = urllib.request.Request(next_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            all_items.extend(data)
        elif isinstance(data, dict) and 'siblings' in data:
            all_items.extend(data['siblings'])
        else:
            break
        # Check for next page in Link header (HF API pagination)
        link_header = resp.headers.get('Link', '')
        next_url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(','):
                if 'rel="next"' in part:
                    next_url = part.split(';')[0].strip(' <>')
                    break
        if not next_url:
            break
    return all_items


def build_url(rel_path: str) -> str:
    quoted = urllib.parse.quote(rel_path, safe='/')
    return BASE_URL.rstrip('/') + '/' + quoted


def download_one(rel_path: str) -> tuple[str, str]:
    destination = RAW_ROOT / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return rel_path, 'exists'

    url = build_url(rel_path)
    last_error = 'unknown'
    for attempt in range(RETRIES):
        temp_path = destination.with_suffix(destination.suffix + '.part')
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response, temp_path.open('wb') as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            temp_path.replace(destination)
            return rel_path, 'downloaded'
        except Exception as exc:
            last_error = f'{type(exc).__name__}'
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt + 1 < RETRIES:
                time.sleep(RETRY_WAIT)
    return rel_path, f'failed:{last_error}'


def collect_wav_and_json_paths(language: str) -> tuple[list[str], list[str]]:
    """Walk the HF directory tree to collect all relevant WAV and JSON paths for a language.

    Directory structure: Language/Entry/TechniqueFolder/Song/Group/ClipID.ext
    We filter to RELEVANT_TECHNIQUE_FOLDERS at the TechniqueFolder level.
    """
    json_paths = []
    wav_paths = []

    # Level 1: Entries (e.g., FR-Soprano-1)
    entries = api_get(f'{API_BASE}/tree/main/{language}')
    entry_names = [e['path'].split('/')[-1] for e in entries if e.get('type') == 'directory']
    print(f'    Entries: {entry_names}')

    for entry in entry_names:
        # Level 2: Technique folders
        tech_url = f'{API_BASE}/tree/main/{language}/{entry}'
        tech_items = api_get(tech_url)
        tech_folders = [t['path'].split('/')[-1] for t in tech_items if t.get('type') == 'directory']

        # Filter to relevant technique folders
        relevant_techs = [t for t in tech_folders if t in RELEVANT_TECHNIQUE_FOLDERS]

        for tech in relevant_techs:
            # Level 3: Songs
            song_url = f'{API_BASE}/tree/main/{language}/{entry}/{tech}'
            song_items = api_get(song_url)
            songs = [s['path'].split('/')[-1] for s in song_items if s.get('type') == 'directory']

            for song in songs:
                # Level 4: Groups (we want all groups)
                group_url = f'{API_BASE}/tree/main/{language}/{entry}/{tech}/{song}'
                group_items = api_get(group_url)
                groups = [g['path'].split('/')[-1] for g in group_items if g.get('type') == 'directory']

                for group in groups:
                    # Level 5: Files
                    file_url = f'{API_BASE}/tree/main/{language}/{entry}/{tech}/{song}/{group}'
                    file_items = api_get(file_url)
                    for f_item in file_items:
                        fname = f_item.get('path', '')
                        if fname.endswith('.json'):
                            json_paths.append(fname)
                        elif fname.endswith('.wav'):
                            wav_paths.append(fname)

    print(f'    Found {len(json_paths)} JSONs, {len(wav_paths)} WAVs in relevant technique folders')
    return json_paths, wav_paths


def build_metadata_from_json(json_path: Path, rel_path: str) -> dict | None:
    """Build one metadata item from a raw JSON file."""
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None

    parts = rel_path.replace('\\', '/').split('/')
    if len(parts) < 6:
        return None
    language = parts[0]
    singer = parts[1]
    technique_folder = parts[2]
    song_name = parts[3]
    group_name = parts[4]
    clip_id = parts[5].rsplit('.', 1)[0]

    item_name = f'{language}#{singer}#{technique_folder}#{song_name}#{group_name}#{clip_id}'
    wav_fn = rel_path.rsplit('.', 1)[0] + '.wav'

    all_ph, all_ph_durs = [], []
    all_mix, all_falsetto, all_breathy = [], [], []
    all_pharyngeal, all_vibrato, all_glissando = [], [], []
    all_tech, words = [], []
    total_dur = 0.0

    for word in data:
        phs = word.get('ph', [])
        ph_starts = word.get('ph_start', [])
        ph_ends = word.get('ph_end', [])
        mix_flags = word.get('mix', ['0'] * len(phs))
        fal_flags = word.get('falsetto', ['0'] * len(phs))
        br_flags = word.get('breathy', ['0'] * len(phs))
        pha_flags = word.get('pharyngeal', ['0'] * len(phs))
        vib_flags = word.get('vibrato', ['0'] * len(phs))
        gli_flags = word.get('glissando', ['0'] * len(phs))
        tech_flags = word.get('tech', ['0'] * len(phs))

        for i in range(len(phs)):
            dur = float(ph_ends[i]) - float(ph_starts[i]) if i < len(ph_ends) and i < len(ph_starts) else 0.0
            all_ph.append(str(phs[i]))
            all_ph_durs.append(max(0.0, dur))
            all_mix.append(int(float(mix_flags[i])) if i < len(mix_flags) else 0)
            all_falsetto.append(int(float(fal_flags[i])) if i < len(fal_flags) else 0)
            all_breathy.append(int(float(br_flags[i])) if i < len(br_flags) else 0)
            all_pharyngeal.append(int(float(pha_flags[i])) if i < len(pha_flags) else 0)
            all_vibrato.append(int(float(vib_flags[i])) if i < len(vib_flags) else 0)
            all_glissando.append(int(float(gli_flags[i])) if i < len(gli_flags) else 0)
            all_tech.append(str(tech_flags[i]) if i < len(tech_flags) else '0')

        words.append(str(word.get('word', '')))
        total_dur += max(0.0, float(word.get('end_time', 0)) - float(word.get('start_time', 0)))

    emotion = data[0].get('emotion', '') if data else ''
    singing_method = data[0].get('singing_method', '') if data else ''
    pace = data[0].get('pace', '') if data else ''
    range_val = data[0].get('range', '') if data else ''

    return {
        'item_name': item_name,
        'txt': words,
        'ph': all_ph,
        'ph_durs': all_ph_durs,
        'mix_tech': all_mix,
        'falsetto_tech': all_falsetto,
        'breathy_tech': all_breathy,
        'pharyngeal_tech': all_pharyngeal,
        'vibrato_tech': all_vibrato,
        'glissando_tech': all_glissando,
        'tech': all_tech,
        'wav_fn': wav_fn,
        'language': language,
        'singer': singer,
        'song_name': song_name,
        'group_name': group_name,
        'emotion': emotion,
        'singing_method': singing_method,
        'pace': pace,
        'range': range_val,
        'total_duration_s': total_dur,
    }


def main():
    print(f'=== Multi-Language Download ===')
    print(f'Raw root: {RAW_ROOT}')
    print(f'Languages: {NEW_LANGUAGES}')

    for language in NEW_LANGUAGES:
        print(f'\n{"="*60}')
        print(f'[{language}] Collecting file paths from HF API...')
        t0 = time.time()

        try:
            json_paths, wav_paths = collect_wav_and_json_paths(language)
        except Exception as e:
            print(f'  ERROR collecting paths: {e}')
            import traceback
            traceback.print_exc()
            continue

        print(f'  Collected in {time.time()-t0:.1f}s')

        if not json_paths:
            print(f'  No files found for {language}, skipping')
            continue

        # Download JSONs
        print(f'  Downloading {len(json_paths)} JSONs...')
        completed = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(download_one, p): p for p in json_paths}
            for future in as_completed(futures):
                _, status = future.result()
                with lock:
                    completed += 1
                if completed % 500 == 0:
                    print(f'    JSONs: {completed}/{len(json_paths)}')

        # Build metadata
        print(f'  Building metadata from JSONs...')
        metadata = []
        skipped = 0
        for jp in json_paths:
            json_fp = RAW_ROOT / jp
            if not json_fp.exists():
                skipped += 1
                continue
            item = build_metadata_from_json(json_fp, jp)
            if item:
                metadata.append(item)
            else:
                skipped += 1

        # Save metadata
        processed_dir = PROCESSED_ROOT / language
        processed_dir.mkdir(parents=True, exist_ok=True)
        meta_path = processed_dir / 'metadata.json'
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  Metadata: {len(metadata)} items, skipped={skipped} ({meta_path.stat().st_size/1024/1024:.1f} MB)')

        # Stats
        mix_items = sum(1 for m in metadata if any(m['mix_tech']))
        groups = Counter(m.get('group_name', '?') for m in metadata)
        singers = Counter(m.get('singer', '?') for m in metadata)
        print(f'  Mix pos: {mix_items}, Groups: {dict(groups)}, Singers: {dict(singers)}')

        # Download WAVs (all found)
        print(f'  Downloading {len(wav_paths)} WAVs...')
        wav_completed = 0
        wav_downloaded = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(download_one, p): p for p in wav_paths}
            for future in as_completed(futures):
                _, status = future.result()
                with lock:
                    wav_completed += 1
                    if status == 'downloaded':
                        wav_downloaded += 1
                if wav_completed % 200 == 0:
                    print(f'    WAVs: {wav_completed}/{len(wav_paths)} (new={wav_downloaded})')
        print(f'  WAVs done: {wav_completed} total, {wav_downloaded} newly downloaded')

    print(f'\n{"="*60}')
    print('Done!')


if __name__ == '__main__':
    main()
