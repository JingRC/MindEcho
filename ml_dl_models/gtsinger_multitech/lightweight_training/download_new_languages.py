"""Download French, German, Italian data from HF mirror: JSONs first, then WAVs for mix-relevant groups."""
import json, time, urllib.parse, urllib.request, threading, csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter, defaultdict

BASE_URL = 'https://hf-mirror.com/datasets/GTSinger/GTSinger/resolve/main'
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = BASE_DIR / 'dataset' / 'raw'
PROCESSED_ROOT = BASE_DIR / 'dataset' / 'processed'

NEW_LANGUAGES = ['French', 'German', 'Italian']

# Only download WAVs for technique groups relevant to mix binary training
RELEVANT_GROUPS = {
    'Mixed_Voice_Group', 'Control_Group', 'Falsetto_Group', 'Breathy_Group',
    'Glissando_Group', 'Pharyngeal_Group', 'Vibrato_Group',
}
RELEVANT_TECHNIQUES = {'mix', 'falsetto', 'breathy', 'vibrato', 'glissando', 'pharyngeal'}

WORKERS = 8
TIMEOUT = 60.0
RETRIES = 3
RETRY_WAIT = 2.0


def build_url(rel_path: str) -> str:
    quoted = urllib.parse.quote(rel_path, safe='/')
    return BASE_URL.rstrip('/') + '/' + quoted


def download_one(rel_path: str, raw_root: Path) -> tuple[str, str]:
    destination = raw_root / rel_path
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
            last_error = f'{type(exc).__name__}:{exc}'
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt + 1 < RETRIES:
                time.sleep(RETRY_WAIT)
    return rel_path, f'failed:{last_error}'


def collect_files_from_hf(language: str) -> list[dict]:
    """Get all files for a language from HF API recursively."""
    url = f'https://hf-mirror.com/api/datasets/GTSinger/GTSinger/tree/main/{language}?recursive=true'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    files = []
    for item in data:
        rpath = item.get('path', '')
        if rpath:
            files.append({
                'path': rpath,
                'size': item.get('size', 0),
                'ext': rpath.rsplit('.', 1)[-1].lower() if '.' in rpath else '',
            })
    return files


def build_metadata_from_json(json_path: Path, rel_path: str) -> dict | None:
    """Build one metadata item from a raw JSON file."""
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None

    # Parse path: French/FR-Soprano-1/Mixed_Voice_and_Falsetto/SongName/Mixed_Voice_Group/0000.json
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

    # Aggregate ph-level technique flags
    total_phs = 0
    mix_count = 0
    falsetto_count = 0
    breathy_count = 0
    pharyngeal_count = 0
    vibrato_count = 0
    glissando_count = 0
    all_ph = []
    all_ph_durs = []
    all_mix = []
    all_falsetto = []
    all_breathy = []
    all_pharyngeal = []
    all_vibrato = []
    all_glissando = []
    all_tech = []
    words = []
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
            all_ph_durs.append(dur)
            all_mix.append(int(float(mix_flags[i])) if i < len(mix_flags) else 0)
            all_falsetto.append(int(float(fal_flags[i])) if i < len(fal_flags) else 0)
            all_breathy.append(int(float(br_flags[i])) if i < len(br_flags) else 0)
            all_pharyngeal.append(int(float(pha_flags[i])) if i < len(pha_flags) else 0)
            all_vibrato.append(int(float(vib_flags[i])) if i < len(vib_flags) else 0)
            all_glissando.append(int(float(gli_flags[i])) if i < len(gli_flags) else 0)
            all_tech.append(str(tech_flags[i]) if i < len(tech_flags) else '0')
            total_phs += 1
            if int(float(mix_flags[i])) if i < len(mix_flags) else 0:
                mix_count += 1
            if int(float(fal_flags[i])) if i < len(fal_flags) else 0:
                falsetto_count += 1
            if int(float(br_flags[i])) if i < len(br_flags) else 0:
                breathy_count += 1
            if int(float(pha_flags[i])) if i < len(pha_flags) else 0:
                pharyngeal_count += 1
            if int(float(vib_flags[i])) if i < len(vib_flags) else 0:
                vibrato_count += 1
            if int(float(gli_flags[i])) if i < len(gli_flags) else 0:
                glissando_count += 1

        words.append(str(word.get('word', '')))
        total_dur += float(word.get('end_time', 0)) - float(word.get('start_time', 0))

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
    print(f'=== Downloading JSONs + building metadata for {NEW_LANGUAGES} ===')
    print(f'Raw root: {RAW_ROOT}')
    print(f'Processed root: {PROCESSED_ROOT}')

    for language in NEW_LANGUAGES:
        print(f'\n{"="*60}')
        print(f'Processing: {language}')

        # Step 1: List all files for this language
        print('  Listing files from HF API...')
        try:
            all_files = collect_files_from_hf(language)
        except Exception as e:
            print(f'  ERROR listing files: {e}')
            continue

        json_files = [f for f in all_files if f['ext'] == 'json']
        wav_files = [f for f in all_files if f['ext'] == 'wav']
        print(f'  Found {len(json_files)} JSONs, {len(wav_files)} WAVs')

        # Step 2: Download JSON files
        print(f'  Downloading {len(json_files)} JSON files...')
        completed = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(download_one, f['path'], RAW_ROOT): f for f in json_files}
            for future in as_completed(futures):
                _, status = future.result()
                completed += 1
                if completed % 500 == 0:
                    print(f'    JSONs: {completed}/{len(json_files)}')

        # Step 3: Build metadata from downloaded JSONs
        print(f'  Building metadata...')
        metadata = []
        skipped = 0
        for f in json_files:
            json_path = RAW_ROOT / f['path']
            if not json_path.exists():
                skipped += 1
                continue
            item = build_metadata_from_json(json_path, f['path'])
            if item:
                metadata.append(item)
            else:
                skipped += 1

        print(f'  Built {len(metadata)} metadata items (skipped {skipped})')

        # Save metadata
        processed_dir = PROCESSED_ROOT / language
        processed_dir.mkdir(parents=True, exist_ok=True)
        meta_path = processed_dir / 'metadata.json'
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  Saved metadata to {meta_path} ({meta_path.stat().st_size / 1024 / 1024:.1f} MB)')

        # Step 4: Stats
        mix_items = sum(1 for m in metadata if any(m['mix_tech']))
        falsetto_items = sum(1 for m in metadata if any(m['falsetto_tech']))
        breathy_items = sum(1 for m in metadata if any(m['breathy_tech']))
        groups = Counter(m.get('group_name', '?') for m in metadata)
        singers = Counter(m.get('singer', '?') for m in metadata)

        print(f'  Stats: total={len(metadata)}, mix={mix_items}, falsetto={falsetto_items}, breathy={breathy_items}')
        print(f'  Groups: {dict(groups.most_common(8))}')
        print(f'  Singers: {dict(singers)}')

        # Step 5: Filter WAVs to download - only relevant groups
        relevant_wavs = []
        for wf in wav_files:
            path_parts = wf['path'].replace('\\', '/').split('/')
            if len(path_parts) >= 5:
                group = path_parts[4]
                if group in RELEVANT_GROUPS:
                    relevant_wavs.append(wf)

        print(f'  Relevant WAVs to download: {len(relevant_wavs)}/{len(wav_files)}')

        # Step 6: Download WAVs
        if relevant_wavs:
            print(f'  Downloading {len(relevant_wavs)} WAVs...')
            wav_completed = 0
            wav_downloaded = 0
            lock = threading.Lock()

            with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                futures = {executor.submit(download_one, wf['path'], RAW_ROOT): wf for wf in relevant_wavs}
                for future in as_completed(futures):
                    _, status = future.result()
                    with lock:
                        wav_completed += 1
                        if status == 'downloaded':
                            wav_downloaded += 1
                    if wav_completed % 200 == 0:
                        print(f'    WAVs: {wav_completed}/{len(relevant_wavs)} (new={wav_downloaded})')
            print(f'  WAVs done: {wav_completed} total, {wav_downloaded} newly downloaded')

    print(f'\n{"="*60}')
    print('Done! All metadata and WAVs downloaded.')
    print(f'Run prepare_mix_binary_song_level_split.py next to rebuild manifests.')


if __name__ == '__main__':
    main()
