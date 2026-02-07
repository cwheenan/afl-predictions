"""Driver to perform a metadata-only dry-run across a range of seasons.

Counts match URLs per year (optionally limited by round range) and writes a
manifest CSV if requested. This is safe for estimating total pages before a
full polite crawl.

Usage:
  python scripts/ingest_dry_run_all.py --start-year 1990 --end-year 2024 --rounds 1-23 --manifest manifest.csv
"""
import argparse
from collections import defaultdict
import importlib.util
import os

_THIS_DIR = os.path.dirname(__file__)
ingest_season_path = os.path.join(_THIS_DIR, 'ingest_season.py')
spec = importlib.util.spec_from_file_location('ingest_season', ingest_season_path)
ingest_season = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest_season)


def parse_years_arg(s: str):
    if '-' in s:
        a, b = s.split('-', 1)
        return int(a), int(b)
    return int(s), int(s)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start-year', type=int, default=1990)
    p.add_argument('--end-year', type=int, default=2024)
    p.add_argument('--rounds', default='1-23')
    p.add_argument('--manifest', default=None)
    args = p.parse_args()

    rounds = ingest_season.parse_rounds_arg(args.rounds)
    per_year = defaultdict(list)
    total = 0
    years = range(args.start_year, args.end_year + 1)
    for y in years:
        try:
            urls = ingest_season.run(y, rounds, cache_dir=None, rate=1.0, max_pages=99999)
            if urls:
                per_year[y] = urls
                total += len(urls)
            print(f'Year {y}: {len(urls)} URLs')
        except Exception as e:
            print('Failed to enumerate year', y, e)

    print('Total URLs across years:', total)
    if args.manifest:
        import csv
        with open(args.manifest, 'w', newline='', encoding='utf8') as fh:
            w = csv.writer(fh)
            w.writerow(['year', 'url'])
            for y, urls in per_year.items():
                for u in urls:
                    w.writerow([y, u])
        print('Wrote manifest to', args.manifest)


if __name__ == '__main__':
    main()
