"""Download French, German, Italian: robust per-directory approach using requests."""
import json, time, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter

try:
    import requests
except ImportError:
    print("Need 'requests' library. Install: pip install requests")
    sys.exit(1)

MIRROR_API = 'https://hf-mirror.com/api/datasets/GTSinger/GTSinger/tree/main'
MIRROR_RAW = 'https://hf-mirror.com/datasets/GTSinger/GTSinger/resolve/main'
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = BASE_DIR / 'dataset' / 'raw'
PROCESSED_ROOT = BASE_DIR / 'dataset' / 'processed'

NEW_LANGUAGES = {
    'French': ['FR-Soprano-1', 'FR-Tenor-1'],
    'German': ['DE-Soprano-1', 'DE-Tenor-1'],
    'Italian': ['IT-Bass-1', 'IT-Bass-2', 'IT-Soprano-1'],
}

RELEVANT_TECHNIQUES = {'Mixed_Voice_and_Falsetto', 'Breathy', 'Vibrato', 'Glissando', 'Pharyngeal'}

WORKERS = 8
TIMEOUT = 30
RETRIES = 3
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0'})


def api_list(path: str) -> list[dict]:
    """List a directory on HF, with retry and rate-limit backoff."""
    url = f'{MIRROR_API}/{path}' if path else MIRROR_API.rstrip('/tree/main')
    for attempt in range(RETRIES):
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f'    rate-limited, waiting {wait}s...')
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(0.3)  # polite delay between API calls
            return r.json()
        except Exception as e:
            if attempt == RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return []


def download_file(rel_path: str) -> str:
    """Download a single file. Returns status string."""
    dest = RAW_ROOT / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return 'exists'

    url = f'{MIRROR_RAW}/{rel_path}'
    for attempt in range(RETRIES):
        try:
            r = SESSION.get(url, timeout=120, stream=True)
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + '.part')
            with tmp.open('wb') as f:
                for chunk in r.iter_content(chunk_size=256*1024):
                    if chunk:
                        f.write(chunk)
            tmp.replace(dest)
            return 'downloaded'
        except Exception:
            try:
                tmp = dest.with_suffix(dest.suffix + '.part')
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            if attempt < RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    return 'failed'


def collect_files_for_language(language: str, entries: list[str]) -> tuple[list[str], list[str]]:
    """Return (json_paths, wav_paths) for a language by walking tree."""
    json_paths = []
    wav_paths = []
    base = language

    for entry in entries:
        # List technique folders
        try:
            tech_items = api_list(f'{base}/{entry}')
        except Exception as e:
            print(f'    WARNING: {base}/{entry} listing failed: {e}')
            continue

        for item in tech_items:
            if item.get('type') != 'directory':
                continue
            tech = item['path'].split('/')[-1]
            if tech not in RELEVANT_TECHNIQUES:
                continue

            # List songs
            try:
                song_items = api_list(f'{base}/{entry}/{tech}')
            except Exception as e:
                print(f'    WARNING: {base}/{entry}/{tech} listing failed: {e}')
                continue

            for song_item in song_items:
                if song_item.get('type') != 'directory':
                    continue
                song = song_item['path'].split('/')[-1]

                # List groups
                try:
                    group_items = api_list(f'{base}/{entry}/{tech}/{song}')
                except Exception as e:
                    print(f'    WARNING: {base}/{entry}/{tech}/{song} listing failed: {e}')
                    continue

                for group_item in group_items:
                    if group_item.get('type') != 'directory':
                        continue
                    group = group_item['path'].split('/')[-1]

                    # List files
                    try:
                        file_items = api_list(f'{base}/{entry}/{tech}/{song}/{group}')
                    except Exception as e:
                        print(f'    WARNING: {base}/{entry}/{tech}/{song}/{group} listing failed: {e}')
                        continue

                    for fi in file_items:
                        fpath = fi.get('path', '')
                        if fpath.endswith('.json'):
                            json_paths.append(fpath)
                        elif fpath.endswith('.wav'):
                            wav_paths.append(fpath)

    return json_paths, wav_paths


def build_metadata_from_json(json_path: Path, rel_path: str) -> dict | None:
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None

    parts = rel_path.replace('\\', '/').split('/')
    if len(parts) < 6:
        return None
    language, singer, technique_folder, song_name, group_name = parts[:5]
    clip_id = parts[5].rsplit('.', 1)[0]
    item_name = f'{language}#{singer}#{technique_folder}#{song_name}#{group_name}#{clip_id}'
    wav_fn = rel_path.rsplit('.', 1)[0] + '.wav'

    all_ph, all_ph_durs = [], []
    all_mix, all_falsetto, all_breathy = [], [], []
    all_pharyngeal, all_vibrato, all_glissando, all_tech, words = [], [], [], [], []
    total_dur = 0.0

    for word in data:
        phs = word.get('ph', [])
        ph_starts = word.get('ph_start', [])
        ph_ends = word.get('ph_end', [])
        if not phs:
            continue
        for i in range(len(phs)):
            dur = float(ph_ends[i]) - float(ph_starts[i]) if i < len(ph_ends) and i < len(ph_starts) else 0.0
            all_ph.append(str(phs[i]))
            all_ph_durs.append(max(0.0, dur))
            all_mix.append(int(float(word.get('mix', ['0']*len(phs))[i])) if i < len(word.get('mix', [])) else 0)
            all_falsetto.append(int(float(word.get('falsetto', ['0']*len(phs))[i])) if i < len(word.get('falsetto', [])) else 0)
            all_breathy.append(int(float(word.get('breathy', ['0']*len(phs))[i])) if i < len(word.get('breathy', [])) else 0)
            all_pharyngeal.append(int(float(word.get('pharyngeal', ['0']*len(phs))[i])) if i < len(word.get('pharyngeal', [])) else 0)
            all_vibrato.append(int(float(word.get('vibrato', ['0']*len(phs))[i])) if i < len(word.get('vibrato', [])) else 0)
            all_glissando.append(int(float(word.get('glissando', ['0']*len(phs))[i])) if i < len(word.get('glissando', [])) else 0)
            all_tech.append(str(word.get('tech', ['0']*len(phs))[i]) if i < len(word.get('tech', [])) else '0')
        words.append(str(word.get('word', '')))
        total_dur += max(0.0, float(word.get('end_time', 0)) - float(word.get('start_time', 0)))

    return {
        'item_name': item_name, 'txt': words, 'ph': all_ph, 'ph_durs': all_ph_durs,
        'mix_tech': all_mix, 'falsetto_tech': all_falsetto, 'breathy_tech': all_breathy,
        'pharyngeal_tech': all_pharyngeal, 'vibrato_tech': all_vibrato, 'glissando_tech': all_glissando,
        'tech': all_tech, 'wav_fn': wav_fn, 'language': language, 'singer': singer,
        'song_name': song_name, 'group_name': group_name,
        'emotion': data[0].get('emotion', '') if data else '',
        'singing_method': data[0].get('singing_method', '') if data else '',
        'pace': data[0].get('pace', '') if data else '',
        'range': data[0].get('range', '') if data else '',
        'total_duration_s': total_dur,
    }


def main():
    print('=== Download New Languages ===')
    print(f'Languages: {list(NEW_LANGUAGES.keys())}')

    for language, entries in NEW_LANGUAGES.items():
        print(f'\n{"="*60}')
        print(f'[{language}] Entries: {entries}')
        t0 = time.time()

        # Step 1: Collect file paths
        print(f'  Listing directories...')
        try:
            jps, wps = collect_files_for_language(language, entries)
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()
            continue
        print(f'  Found {len(jps)} JSONs + {len(wps)} WAVs in {time.time()-t0:.1f}s')

        if not jps:
            print(f'  No files, skipping')
            continue

        # Step 2: Download JSONs (small, fast)
        print(f'  Downloading {len(jps)} JSONs...')
        done = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(download_file, p): p for p in jps}
            for f in as_completed(futures):
                with lock:
                    done += 1
                if done % 300 == 0:
                    print(f'    JSONs: {done}/{len(jps)}')

        # Step 3: Build metadata
        print(f'  Building metadata...')
        metadata = []
        skipped = 0
        for jp in jps:
            fp = RAW_ROOT / jp
            if not fp.exists():
                skipped += 1
                continue
            item = build_metadata_from_json(fp, jp)
            if item:
                metadata.append(item)
            else:
                skipped += 1

        processed_dir = PROCESSED_ROOT / language
        processed_dir.mkdir(parents=True, exist_ok=True)
        meta_path = processed_dir / 'metadata.json'
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  Metadata: {len(metadata)} items, skipped={skipped}, {meta_path.stat().st_size/1024/1024:.1f} MB')

        # Stats
        mix_pos = sum(1 for m in metadata if any(m['mix_tech']))
        groups = Counter(m.get('group_name', '?') for m in metadata)
        singers = Counter(m.get('singer', '?') for m in metadata)
        print(f'  Mix: {mix_pos}, Groups: {dict(groups)}, Singers: {dict(singers)}')

        # Step 4: Download WAVs
        if wps:
            print(f'  Downloading {len(wps)} WAVs...')
            wdone = 0
            wnew = 0
            lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futures = {ex.submit(download_file, p): p for p in wps}
                for f in as_completed(futures):
                    _, status = f.result()
                    with lock:
                        wdone += 1
                        if status == 'downloaded':
                            wnew += 1
                    if wdone % 200 == 0:
                        print(f'    WAVs: {wdone}/{len(wps)} (new={wnew})')
            print(f'  WAVs done: {wdone} total, {wnew} downloaded')

    print(f'\n{"="*60}')
    print('All done!')


if __name__ == '__main__':
    main()
