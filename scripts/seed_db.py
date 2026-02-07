"""Seed the application database from the cache index.

Usage:
    python scripts/seed_db.py --cache-dir data/raw/cache --limit 100
"""
import sys
from pathlib import Path
import argparse

# ensure src/ is on sys.path when running from repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from afl_predictions import config
from afl_predictions.db import seed_pages_from_cache


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR), help='Cache directory')
    p.add_argument('--db-url', default=None, help='Optional DB URL override')
    p.add_argument('--limit', type=int, default=None, help='Limit number of pages to seed')
    return p.parse_args()


def main():
    args = parse_args()
    count = seed_pages_from_cache(cache_dir=args.cache_dir, db_url=args.db_url, limit=args.limit)
    print(f'Seeded {count} pages into DB')


if __name__ == '__main__':
    main()
