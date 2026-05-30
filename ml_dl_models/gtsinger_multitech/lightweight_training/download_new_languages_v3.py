"""Download new languages using root API siblings list (fast, single API call per language group)."""
import json, time, urllib.parse, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter

BASE_URL = 'https://hf-mirror.com/datasets/GTSinger/GTSinger/resolve/main'
API_ROOT = 'https://hf-mirror.com/api/datasets/GTSinger/GTSinger'
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = BASE_DIR / 'dataset' / 'raw'
PROCESSED_ROOT = BASE_DIR / 'dataset' / 'processed'

NEW_LANGUAGES = ['French', 'German', 'Italian']

# Only download technique folders relevant to mix binary
RELEVANT_TECHNIQUES = {
    'Mixed_Voice_and_Falsetto', 'Breathy', 'Vibrato', 'Glissando', 'Pharyngeal'
}

WORKERS = 8
TIMEOUT = 120.0
RETRIES = 3
RETRY_WAIT = 2.0


def get_all_files() -> dict[str, list[dict]]:
    """Get ALL files from the HF API root siblings (with pagination support)."""
    lang_files: dict[str, list[dict]] = {lang: [] for lang in NEW_LANGUAGES}
    url = API_ROOT
    page = 0

    while url:
        page += 1
        encoded = urllib.parse.quote(url, safe='/:?=&')
        req = urllib.request.Request(encoded, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

        siblings = data.get('siblings', [])
        for item in siblings:
            rpath = item.get('rfilename', '')
            if not rpath:
                continue
            parts = rpath.split('/')
            if len(parts) < 1:
                continue
            lang = parts[0]
            if lang in NEW_LANGUAGES:
                ext = rpath.rsplit('.', 1)[-1].lower() if '.' in rpath else ''
                if ext in ('json', 'wav'):
                    # Filter by technique folder
                    if len(parts) >= 3:
                        tech_folder = parts[2]
                        if tech_folder not in RELEVANT_TECHNIQUES:
                            continue
                    lang_files[lang].append({
                        'path': rpath,
                        'size': item.get('size', 0),
                        'ext': ext,
                    })

        # Check for next page
        link_header = resp.headers.get('Link', '')
        url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(','):
                if 'rel="next"' in part:
                    url = part.split(';')[0].strip(' <>')
                    break

        if page % 5 == 0:
            total = sum(len(v) for v in lang_files.values())
            print(f'  Page {page}: {total} files collected so far...')

    return lang_files


def download_one(rel_path: str) -> tuple[str, str]:
    destination = RAW_ROOT / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return rel_path, 'exists'

    url = BASE_URL.rstrip('/') + '/' + urllib.parse.quote(rel_path, safe='/')
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
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt + 1 < RETRIES:
                time.sleep(RETRY_WAIT)
    return rel_path, 'failed'


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
    language, singer, technique_folder, song_name, group_name = parts[0], parts[1], parts[2], parts[3], parts[4]
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
    print('=== Step 1: Collecting all file paths from HF API (paginated) ===')
    t0 = time.time()
    lang_files = get_all_files()
    print(f'Collected in {time.time()-t0:.1f}s')
    for lang, files in lang_files.items():
        js = [f for f in files if f['ext'] == 'json']
        ws = [f for f in files if f['ext'] == 'wav']
        print(f'  {lang}: {len(js)} JSONs, {len(ws)} WAVs')

    for language in NEW_LANGUAGES:
        files = lang_files.get(language, [])
        if not files:
            print(f'\n{language}: No files found, skipping')
            continue

        json_files = [f for f in files if f['ext'] == 'json']
        wav_files = [f for f in files if f['ext'] == 'wav']

        print(f'\n{"="*60}')
        print(f'[{language}] {len(json_files)} JSONs + {len(wav_files)} WAVs')

        # Download JSONs
        print(f'  Downloading JSONs...')
        completed = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(download_one, f['path']): f for f in json_files}
            for future in as_completed(futures):
                _, status = future.result()
                with lock:
                    completed += 1
                if completed % 500 == 0:
                    print(f'    JSONs: {completed}/{len(json_files)}')

        # Build metadata
        print(f'  Building metadata...')
        metadata = []
        skipped = 0
        for jf in json_files:
            fp = RAW_ROOT / jf['path']
            if not fp.exists():
                skipped += 1
                continue
            item = build_metadata_from_json(fp, jf['path'])
            if item:
                metadata.append(item)
            else:
                skipped += 1

        processed_dir = PROCESSED_ROOT / language
        processed_dir.mkdir(parents=True, exist_ok=True)
        meta_path = processed_dir / 'metadata.json'
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  Metadata: {len(metadata)} items (skipped {skipped}), {meta_path.stat().st_size/1024/1024:.1f} MB')

        # Stats
        mix_pos = sum(1 for m in metadata if any(m['mix_tech']))
        groups = Counter(m.get('group_name', '?') for m in metadata)
        singers = Counter(m.get('singer', '?') for m in metadata)
        print(f'  Mix pos: {mix_pos}, Groups: {dict(groups)}, Singers: {dict(singers)}')

        # Download WAVs
        if wav_files:
            print(f'  Downloading {len(wav_files)} WAVs...')
            wav_completed = 0
            wav_downloaded = 0
            lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                futures = {executor.submit(download_one, f['path']): f for f in wav_files}
                for future in as_completed(futures):
                    _, status = future.result()
                    with lock:
                        wav_completed += 1
                        if status == 'downloaded':
                            wav_downloaded += 1
                    if wav_completed % 500 == 0:
                        print(f'    WAVs: {wav_completed}/{len(wav_files)} (new={wav_downloaded})')
            print(f'  WAVs done: {wav_completed} total, {wav_downloaded} newly downloaded')

    print(f'\nDone!')


if __name__ == '__main__':
    main()
