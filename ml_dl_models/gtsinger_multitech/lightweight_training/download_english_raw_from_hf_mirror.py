import argparse
import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


DEFAULT_BASE_URL = 'https://hf-mirror.com/datasets/GTSinger/GTSinger/resolve/main'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Download missing English GTSinger wav files from a mirror into dataset/raw/English.')
    parser.add_argument(
        '--metadata',
        default='',
        help='Optional metadata.json path. Defaults to dataset/processed/English/metadata.json.',
    )
    parser.add_argument(
        '--raw-root',
        default='',
        help='Optional raw dataset root. Defaults to dataset/raw.',
    )
    parser.add_argument(
        '--base-url',
        default=DEFAULT_BASE_URL,
        help='Mirror base URL pointing at the dataset resolve/main root.',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=6,
        help='Concurrent download workers.',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=60.0,
        help='Per-request timeout in seconds.',
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=3,
        help='Retry count per file.',
    )
    parser.add_argument(
        '--retry-wait',
        type=float,
        default=1.5,
        help='Wait time between retries in seconds.',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Optional cap on number of files to process.',
    )
    parser.add_argument(
        '--progress-log',
        default='',
        help='Optional progress log path. Defaults to dataset/english_progress.log.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be downloaded without transferring files.',
    )
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    base_dir = Path(__file__).resolve().parents[1]
    metadata_path = Path(args.metadata).resolve() if args.metadata else (base_dir / 'dataset' / 'processed' / 'English' / 'metadata.json')
    raw_root = Path(args.raw_root).resolve() if args.raw_root else (base_dir / 'dataset' / 'raw')
    progress_log = Path(args.progress_log).resolve() if args.progress_log else (base_dir / 'dataset' / 'english_progress.log')
    return metadata_path, raw_root, progress_log


def collect_wav_paths(metadata_path: Path) -> list[str]:
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    seen: set[str] = set()
    ordered: list[str] = []
    for item in metadata:
        rel_path = str(item.get('wav_fn', '') or '').strip().replace('\\', '/')
        if not rel_path or not rel_path.startswith('English/'):
            continue
        if rel_path in seen:
            continue
        seen.add(rel_path)
        ordered.append(rel_path)
    return ordered


def append_progress(progress_log: Path, completed: int, total: int) -> None:
    progress_log.parent.mkdir(parents=True, exist_ok=True)
    pct = 0.0 if total <= 0 else (100.0 * float(completed) / float(total))
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with progress_log.open('a', encoding='utf-8') as handle:
        handle.write(f'{stamp} count={completed} total={total} pct={pct:.2f}\n')


def build_url(base_url: str, rel_path: str) -> str:
    quoted = urllib.parse.quote(rel_path, safe='/')
    return str(base_url.rstrip('/')) + '/' + quoted


def download_one(
    rel_path: str,
    *,
    raw_root: Path,
    base_url: str,
    timeout: float,
    retries: int,
    retry_wait: float,
) -> tuple[str, str]:
    destination = raw_root / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return rel_path, 'exists'

    url = build_url(base_url, rel_path)
    last_error = 'unknown'
    for attempt in range(max(1, int(retries))):
        temp_path = destination.with_suffix(destination.suffix + '.part')
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=timeout) as response, temp_path.open('wb') as handle:
                while True:
                    chunk = response.read(1024 * 256)
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
            if attempt + 1 < max(1, int(retries)):
                time.sleep(max(0.0, float(retry_wait)))
    return rel_path, 'failed:' + last_error


def main() -> None:
    args = parse_args()
    metadata_path, raw_root, progress_log = resolve_paths(args)
    rel_paths = collect_wav_paths(metadata_path)
    if args.limit and int(args.limit) > 0:
        rel_paths = rel_paths[: int(args.limit)]

    total = len(rel_paths)
    print(f'metadata={metadata_path}')
    print(f'raw_root={raw_root}')
    print(f'progress_log={progress_log}')
    print(f'file_count={total}')
    print(f'base_url={args.base_url}')

    if args.dry_run:
        preview = rel_paths[: min(10, total)]
        for item in preview:
            status = 'exists' if (raw_root / item).exists() else 'missing'
            print(f'{status}|{item}|{build_url(args.base_url, item)}')
        return

    completed = 0
    downloaded = 0
    existing = 0
    failed: list[tuple[str, str]] = []
    lock = threading.Lock()
    append_progress(progress_log, completed, total)

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
        future_map = {
            executor.submit(
                download_one,
                rel_path,
                raw_root=raw_root,
                base_url=args.base_url,
                timeout=float(args.timeout),
                retries=int(args.retries),
                retry_wait=float(args.retry_wait),
            ): rel_path
            for rel_path in rel_paths
        }
        for future in as_completed(future_map):
            rel_path, status = future.result()
            with lock:
                completed += 1
                if status == 'downloaded':
                    downloaded += 1
                elif status == 'exists':
                    existing += 1
                else:
                    failed.append((rel_path, status))
                if completed == total or completed % 25 == 0:
                    append_progress(progress_log, completed, total)
                    print(f'progress {completed}/{total} downloaded={downloaded} exists={existing} failed={len(failed)}', flush=True)

    print(f'completed={completed}')
    print(f'downloaded={downloaded}')
    print(f'exists={existing}')
    print(f'failed={len(failed)}')
    if failed:
        for rel_path, status in failed[:50]:
            print(f'failed_item|{rel_path}|{status}')


if __name__ == '__main__':
    main()