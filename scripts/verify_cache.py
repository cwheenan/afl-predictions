"""Verify that URLs (match pages, umpire pages, team pages, etc.) are cached locally.

Usage:
    python scripts/verify_cache.py urls.txt --cache-dir data/raw/cache --fetch-missing

Options:
 - urls.txt: a newline-separated list of URLs to verify
 - --cache-dir: cache directory (defaults to config.DEFAULT_CACHE_DIR)
 - --fetch-missing: if set, attempt to fetch missing URLs and cache them (polite)
 - --dry-run: if set with --fetch-missing, show what would be fetched but don't perform network calls
"""
import argparse
from pathlib import Path
from afl_predictions import config
from afl_predictions.data import load_data


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('urls_file', help='Text file with one URL per line')
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR), help='Cache directory')
    p.add_argument('--fetch-missing', action='store_true', help='Fetch missing URLs and cache them')
    p.add_argument('--dry-run', action='store_true', help='When fetching missing, do not make network requests')
    p.add_argument('--rate', type=float, default=None, help='Override rate limit (seconds)')
    return p.parse_args()


def main():
    args = parse_args()
    urls_path = Path(args.urls_file)
    if not urls_path.exists():
        raise SystemExit(f'URLs file not found: {urls_path}')
    urls = [l.strip() for l in urls_path.read_text(encoding='utf8').splitlines() if l.strip()]

    cache_dir = args.cache_dir
    missing = []
    present = []
    for url in urls:
        if load_data.is_url_cached(cache_dir, url):
            present.append(url)
        else:
            missing.append(url)

    print(f'Present: {len(present)}; Missing: {len(missing)}')
    if present:
        for u in present[:20]:
            print('  OK:', u)
    if missing:
        for u in missing[:20]:
            print('  MISSING:', u)

    if args.fetch_missing and missing:
        if args.dry_run:
            print('Dry-run: would fetch', len(missing), 'urls')
            return
        # fetch missing politely
        rate = args.rate if args.rate is not None else config.DEFAULT_RATE_LIMIT
        for url in missing:
            try:
                print('Fetching', url)
                load_data.fetch_and_cache_match(url, cache_dir, sleep_sec=rate)
            except Exception as e:
                print('Failed to fetch', url, e)

if __name__ == '__main__':
    main()
