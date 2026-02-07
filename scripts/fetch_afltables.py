"""Simple CLI to fetch and cache a list of AFLTables match URLs.

Usage:
    python scripts/fetch_afltables.py urls.txt --cache-dir data/raw/cache --rate 2.0

`urls.txt` should contain one URL per line. The script will respect robots.txt where possible
and sleep between requests to be considerate of the remote server.
"""
import argparse
from pathlib import Path
from afl_predictions.data.load_data import fetch_many
from afl_predictions import config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls_file', help='Text file with one URL per line')
    parser.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR), help='Directory to store cached HTML and tables')
    parser.add_argument('--rate', type=float, default=config.DEFAULT_RATE_LIMIT, help='Seconds to wait between requests')
    parser.add_argument('--force', action='store_true', help='Force re-download even if cached')
    args = parser.parse_args()

    urls_path = Path(args.urls_file)
    if not urls_path.exists():
        raise SystemExit(f'URLs file not found: {urls_path}')

    urls = [l.strip() for l in urls_path.read_text(encoding='utf8').splitlines() if l.strip()]
    fetch_many(urls, args.cache_dir, rate_limit_sec=args.rate, force=args.force)

if __name__ == '__main__':
    main()
