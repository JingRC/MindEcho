import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import regression_tests.evaluate_pitch_dataset_metrics as pitch_eval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build an explicit manifest/index for singing pitch evaluation datasets.'
    )
    parser.add_argument('--dataset', choices=('medleydb-pitch', 'ikala', 'vocadito'), required=True)
    parser.add_argument('--dataset-root', required=True, help='Dataset root used for auto-discovery.')
    parser.add_argument(
        '--output-dir',
        default='',
        help='Output directory for manifest.csv and index.json. Defaults to <dataset-root>/pitch_eval_manifest_<dataset>.',
    )
    parser.add_argument(
        '--audio-mode',
        choices=('auto', 'vocal', 'mix', 'instrumental'),
        default='auto',
        help='Audio interpretation to bake into the manifest rows.',
    )
    parser.add_argument('--track-id', action='append', default=[], help='Restrict to one or more track ids.')
    parser.add_argument('--limit', type=int, default=0, help='Optional maximum number of matched tracks to keep.')
    parser.add_argument('--sample-count', type=int, default=5, help='How many sample rows to include in index.json.')
    return parser.parse_args()


def normalize_output_dir(dataset_root: Path, dataset_name: str, output_dir: str) -> Path:
    if output_dir:
        return Path(output_dir).resolve()
    return (dataset_root / f'pitch_eval_manifest_{dataset_name}').resolve()


def choose_track_id(track_id: str, annotation_path: Path, audio_path: Optional[Path]) -> str:
    if track_id:
        return track_id
    if annotation_path.stem:
        return annotation_path.stem
    if audio_path is not None and audio_path.stem:
        return audio_path.stem
    return annotation_path.name


def discover_ikala(dataset_root: Path, audio_mode: str) -> Tuple[List[pitch_eval.TrackSpec], Dict[str, Any]]:
    pitch_dir = pitch_eval.find_named_dir(dataset_root, ('PitchLabel',))
    audio_dir = pitch_eval.find_named_dir(dataset_root, ('Wavfile', 'WavFile'))
    if pitch_dir is None or audio_dir is None:
        raise FileNotFoundError('ikala auto-discovery needs PitchLabel and Wavfile directories under --dataset-root')

    audio_by_stem: Dict[str, Path] = {}
    for audio_path in audio_dir.rglob('*'):
        if audio_path.is_file() and audio_path.suffix.lower() in pitch_eval.AUDIO_SUFFIXES:
            audio_by_stem[audio_path.stem.lower()] = audio_path.resolve()

    tracks: List[pitch_eval.TrackSpec] = []
    unmatched_annotations: List[str] = []
    duplicate_audio_keys = 0
    seen_audio_keys = set()
    for key in audio_by_stem.keys():
        if key in seen_audio_keys:
            duplicate_audio_keys += 1
        seen_audio_keys.add(key)

    resolved_audio_mode = audio_mode if audio_mode != 'auto' else 'vocal'
    annotation_files = sorted(path for path in pitch_dir.rglob('*') if path.is_file())
    for annotation_path in annotation_files:
        audio_path = audio_by_stem.get(annotation_path.stem.lower())
        if audio_path is None:
            unmatched_annotations.append(str(annotation_path.resolve()))
            continue
        tracks.append(
            pitch_eval.TrackSpec(
                track_id=choose_track_id(annotation_path.stem, annotation_path.resolve(), audio_path),
                audio_path=str(audio_path),
                annotation_path=str(annotation_path.resolve()),
                annotation_format='ikala-midi-lines',
                dataset_name='ikala',
                audio_mode=resolved_audio_mode,
            )
        )

    discovery = {
        'dataset': 'ikala',
        'dataset_root': str(dataset_root),
        'pitch_dir': str(pitch_dir),
        'audio_dir': str(audio_dir),
        'annotation_file_count': len(annotation_files),
        'audio_file_count': len(audio_by_stem),
        'matched_track_count': len(tracks),
        'unmatched_annotation_count': len(unmatched_annotations),
        'duplicate_audio_key_count': int(duplicate_audio_keys),
        'unmatched_annotations': unmatched_annotations,
    }
    return tracks, discovery


def discover_medleydb_pitch(dataset_root: Path, audio_mode: str) -> Tuple[List[pitch_eval.TrackSpec], Dict[str, Any]]:
    audio_files = sorted(
        path.resolve() for path in dataset_root.rglob('*') if path.is_file() and path.suffix.lower() in pitch_eval.AUDIO_SUFFIXES
    )
    pitch_files = sorted(
        path.resolve()
        for path in dataset_root.rglob('*.csv')
        if path.is_file() and 'note' not in path.name.lower() and 'pyin' not in path.name.lower()
    )
    if not audio_files or not pitch_files:
        raise FileNotFoundError('medleydb-pitch auto-discovery needs audio files and pitch csv files under --dataset-root')

    tracks: List[pitch_eval.TrackSpec] = []
    unmatched_annotations: List[str] = []
    ambiguous_annotations: List[Dict[str, Any]] = []

    for annotation_path in pitch_files:
        scored: List[Tuple[int, Path]] = []
        for audio_path in audio_files:
            matched = pitch_eval.match_audio_for_annotation(annotation_path, [audio_path])
            if matched is not None:
                score = 1
                if annotation_path.stem.lower() == audio_path.stem.lower():
                    score = 4
                elif pitch_eval.normalized_key(annotation_path) == pitch_eval.normalized_key(audio_path):
                    score = 3
                elif annotation_path.parent.name.lower() == audio_path.parent.name.lower():
                    score = 2
                scored.append((score, audio_path))
        if not scored:
            unmatched_annotations.append(str(annotation_path))
            continue
        scored.sort(key=lambda item: (-item[0], str(item[1]).lower()))
        top_score = scored[0][0]
        top_candidates = [path for score, path in scored if score == top_score]
        if len(top_candidates) > 1:
            ambiguous_annotations.append(
                {
                    'annotation_path': str(annotation_path),
                    'candidate_count': len(top_candidates),
                    'candidate_audio_paths': [str(path) for path in top_candidates[:10]],
                }
            )
            continue
        audio_path = top_candidates[0]
        tracks.append(
            pitch_eval.TrackSpec(
                track_id=choose_track_id(annotation_path.stem, annotation_path, audio_path),
                audio_path=str(audio_path),
                annotation_path=str(annotation_path),
                annotation_format='medleydb-pitch',
                dataset_name='medleydb-pitch',
                audio_mode=audio_mode,
            )
        )

    discovery = {
        'dataset': 'medleydb-pitch',
        'dataset_root': str(dataset_root),
        'audio_file_count': len(audio_files),
        'annotation_file_count': len(pitch_files),
        'matched_track_count': len(tracks),
        'unmatched_annotation_count': len(unmatched_annotations),
        'ambiguous_annotation_count': len(ambiguous_annotations),
        'unmatched_annotations': unmatched_annotations,
        'ambiguous_annotations': ambiguous_annotations,
    }
    return tracks, discovery


def discover_vocadito(dataset_root: Path, audio_mode: str) -> Tuple[List[pitch_eval.TrackSpec], Dict[str, Any]]:
    audio_dir = pitch_eval.find_named_dir(dataset_root, ('Audio',))
    f0_dir = dataset_root / 'Annotations' / 'F0'
    if audio_dir is None or not f0_dir.is_dir():
        raise FileNotFoundError('vocadito auto-discovery needs Audio and Annotations/F0 directories under --dataset-root')

    audio_files = sorted(
        path.resolve() for path in audio_dir.rglob('*') if path.is_file() and path.suffix.lower() in pitch_eval.AUDIO_SUFFIXES
    )
    tracks: List[pitch_eval.TrackSpec] = []
    unmatched_audio: List[str] = []
    annotation_file_count = 0
    for path in f0_dir.rglob('*.csv'):
        if path.is_file():
            annotation_file_count += 1

    for audio_path in audio_files:
        annotation_path = (f0_dir / f'{audio_path.stem}_f0.csv').resolve()
        if not annotation_path.is_file():
            unmatched_audio.append(str(audio_path))
            continue
        tracks.append(
            pitch_eval.TrackSpec(
                track_id=audio_path.stem,
                audio_path=str(audio_path),
                annotation_path=str(annotation_path),
                annotation_format='time-hz',
                dataset_name='vocadito',
                audio_mode=audio_mode,
            )
        )

    discovery = {
        'dataset': 'vocadito',
        'dataset_root': str(dataset_root),
        'audio_dir': str(audio_dir),
        'f0_dir': str(f0_dir),
        'audio_file_count': len(audio_files),
        'annotation_file_count': annotation_file_count,
        'matched_track_count': len(tracks),
        'unmatched_audio_count': len(unmatched_audio),
        'unmatched_audio': unmatched_audio,
        'ambiguous_annotation_count': 0,
        'unmatched_annotation_count': max(0, annotation_file_count - len(tracks)),
    }
    return tracks, discovery


def apply_filters(
    tracks: Sequence[pitch_eval.TrackSpec],
    discovery: Dict[str, Any],
    selected_ids: Sequence[str],
    limit: int,
) -> Tuple[List[pitch_eval.TrackSpec], Dict[str, Any]]:
    filtered = list(tracks)
    selected_set = {str(item).strip() for item in selected_ids if str(item).strip()}
    if selected_set:
        filtered = [track for track in filtered if track.track_id in selected_set]
    if limit and limit > 0:
        filtered = filtered[: int(limit)]
    updated = dict(discovery)
    updated['selected_track_count'] = len(filtered)
    updated['selected_track_ids'] = [track.track_id for track in filtered]
    return filtered, updated


def write_manifest(path: Path, tracks: Sequence[pitch_eval.TrackSpec]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=['track_id', 'audio_path', 'annotation_path', 'annotation_format', 'audio_mode', 'dataset_name'],
        )
        writer.writeheader()
        for track in tracks:
            writer.writerow(asdict(track))


def make_index_payload(
    dataset_name: str,
    dataset_root: Path,
    output_dir: Path,
    manifest_path: Path,
    tracks: Sequence[pitch_eval.TrackSpec],
    discovery: Dict[str, Any],
    sample_count: int,
) -> Dict[str, Any]:
    rows = [asdict(track) for track in tracks]
    return {
        'dataset': dataset_name,
        'dataset_root': str(dataset_root),
        'output_dir': str(output_dir),
        'manifest_path': str(manifest_path),
        'track_count': len(tracks),
        'discovery': discovery,
        'sample_rows': rows[: max(0, int(sample_count))],
    }


def print_summary(index_payload: Dict[str, Any]) -> None:
    discovery = dict(index_payload.get('discovery', {}) or {})
    print(
        f"[pitch-manifest] dataset={index_payload.get('dataset')} matched={discovery.get('matched_track_count')} "
        f"selected={discovery.get('selected_track_count')}"
    )
    if 'unmatched_annotation_count' in discovery:
        print(f"  unmatched_annotations={discovery.get('unmatched_annotation_count')}")
    if 'ambiguous_annotation_count' in discovery:
        print(f"  ambiguous_annotations={discovery.get('ambiguous_annotation_count')}")
    print(f"  manifest={index_payload.get('manifest_path')}")
    print(f"  index={Path(index_payload.get('output_dir', '')) / 'index.json'}")


def main() -> int:
    args = parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    output_dir = normalize_output_dir(dataset_root, args.dataset, args.output_dir)
    if args.dataset == 'ikala':
        tracks, discovery = discover_ikala(dataset_root, args.audio_mode)
    elif args.dataset == 'vocadito':
        tracks, discovery = discover_vocadito(dataset_root, args.audio_mode)
    else:
        tracks, discovery = discover_medleydb_pitch(dataset_root, args.audio_mode)

    tracks, discovery = apply_filters(tracks, discovery, args.track_id, args.limit)
    if not tracks:
        raise SystemExit('no tracks matched after discovery/filtering')

    manifest_path = output_dir / 'manifest.csv'
    index_path = output_dir / 'index.json'
    write_manifest(manifest_path, tracks)
    index_payload = make_index_payload(args.dataset, dataset_root, output_dir, manifest_path, tracks, discovery, args.sample_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print_summary(index_payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())