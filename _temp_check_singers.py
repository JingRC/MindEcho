import json, sys
from collections import Counter

for lang in ['Chinese', 'English']:
    path = f'ml_dl_models/gtsinger_multitech/dataset/processed/{lang}/metadata.json'
    data = json.load(open(path, 'r', encoding='utf-8'))
    singer_songs = {}
    for item in data:
        parts = item['wav_fn'].replace('\\', '/').split('/')
        singer = parts[1]
        song = parts[3]
        tech = parts[2]
        singer_songs.setdefault(singer, {}).setdefault(song, set()).add(tech)

    print(f'=== {lang} ({len(data)} clips) ===')
    for singer, songs in sorted(singer_songs.items()):
        total = sum(len(v) for v in songs.values())
        print(f'{singer}: {len(songs)} songs, {total} technique-clips')
        for song in sorted(songs.keys()):
            print(f'  {song}: {sorted(songs[song])}')
    print()
