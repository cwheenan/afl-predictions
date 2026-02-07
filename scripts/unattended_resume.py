#!/usr/bin/env python3
"""Unattended resume+parse helper.
Runs iterative resume fetch+parse passes for target seasons until match counts reach expected totals.

Usage: python scripts/unattended_resume.py

It will call the existing scripts in the repo and print progress. Ctrl-C to stop early.
"""
import subprocess
import time
import sys

# targets for seasons: year -> expected match count
TARGETS = {1993: 157, 1994: 158}

def get_counts():
    """Run count_matches_per_season.py and return a dict season->count (ints).
    If the script fails, returns empty dict.
    """
    try:
        out = subprocess.check_output([sys.executable, 'scripts/count_matches_per_season.py'], text=True)
    except subprocess.CalledProcessError as e:
        print('count script failed:', e, file=sys.stderr)
        return {}
    counts = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or ',' not in line:
            continue
        season, cnt = line.split(',', 1)
        season = season.strip()
        cnt = cnt.strip()
        try:
            counts[int(season)] = int(cnt)
        except Exception:
            # ignore non-year lines
            continue
    return counts


def run_pass(year):
    print(f'Running resume fetch for {year} (ingest_season)')
    try:
        subprocess.check_call([sys.executable, 'scripts/ingest_season.py', '--year', str(year), '--rounds', '1-23', '--manifest', f'data/raw/cache/manifest_{year}.csv', '--cache-dir', 'data/raw/cache', '--rate', '1.0', '--resume'])
    except subprocess.CalledProcessError as e:
        print(f'ingest_season.py failed for {year}:', e, file=sys.stderr)
    print(f'Running parse for manifest_{year}.csv')
    try:
        subprocess.check_call([sys.executable, 'scripts/run_parse_for_manifest.py', f'data/raw/cache/manifest_{year}.csv'])
    except subprocess.CalledProcessError as e:
        print(f'run_parse_for_manifest.py failed for {year}:', e, file=sys.stderr)


def main():
    print('Starting unattended resume+parse helper')
    try:
        while TARGETS:
            counts = get_counts()
            for year, target in list(TARGETS.items()):
                cur = counts.get(year, 0)
                print(f'Year {year}: current count = {cur}, target = {target}')
                if cur >= target:
                    print(f'Year {year} reached target ({cur} >= {target}); removing from targets')
                    del TARGETS[year]
                    continue
                # run one pass for this year
                run_pass(year)
                # small sleep to allow filesystem to settle
                time.sleep(1)
            # sleep between full cycles
            if TARGETS:
                print('Sleeping 2s before next cycle')
                time.sleep(2)
        print('All targets reached — exiting')
    except KeyboardInterrupt:
        print('\nInterrupted by user — exiting early')


if __name__ == '__main__':
    main()
