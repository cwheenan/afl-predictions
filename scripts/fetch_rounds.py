"""Fetch match pages for specific rounds of a year.

Usage:
  python scripts/fetch_rounds.py --year 2022 --rounds 1,2 --per-round 9

Behavior:
- Reads master list from data/raw/all_urls.txt (or --master-list)
- Filters for match URLs under /afl/stats/games/{year}/
- Iterates through URLs and ensures they are cached (fetching if needed).
- Parses cached pages to determine round number and collects pages for the requested rounds
  until `per_round` matches for each round are collected or the list is exhausted.
- Writes seeds file to data/raw/rounds_{year}_{rounds}.txt with the collected URLs.
"""
import argparse
from pathlib import Path
import time
from collections import defaultdict

# ensure package path if run directly
ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'src'))

from afl_predictions import config
from afl_predictions.data import load_data, parse_match


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--rounds', required=True, help='Comma-separated round numbers, e.g. 1,2')
    p.add_argument('--per-round', type=int, default=9, help='Target matches per round')
    p.add_argument('--master-list', default='data/raw/all_urls.txt')
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR))
    p.add_argument('--rate', type=float, default=config.DEFAULT_RATE_LIMIT)
    p.add_argument('--force', action='store_true')
    return p.parse_args()


def load_master(path):
    p = Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding='utf8').splitlines() if l.strip() and not l.strip().startswith('#')]


def main():
    args = parse_args()
    rounds = set(int(r.strip()) for r in args.rounds.split(','))
    per_round = args.per_round
    cache_dir = args.cache_dir

    urls = load_master(args.master_list)
    # filter for year and games
    cand = [u for u in urls if f'/afl/stats/games/{args.year}/' in u]
    print(f'Found {len(cand)} candidate match URLs for year {args.year} in master list')

    collected = defaultdict(list)
    seen = set()

    for u in cand:
        if all(len(collected[r]) >= per_round for r in rounds):
            break
        if u in seen:
            continue
        seen.add(u)

        # check if already cached
        entry = load_data.get_cache_entry_by_url(cache_dir, u)
        if entry is None or args.force:
            try:
                print('Fetching', u)
                load_data.fetch_and_cache_match(u, cache_dir, sleep_sec=args.rate, force=args.force)
            except PermissionError:
                print('Skipped by robots:', u)
                continue
            except Exception as e:
                print('Failed to fetch', u, e)
                continue
        else:
            print('Already cached:', u)

        # try to parse metadata to get round
        try:
            meta, players = parse_match.parse_match_from_cache(cache_dir, u)
            # meta may contain 'round' or 'round_num'
            rn = None
            if meta.get('round_num'):
                rn = int(meta.get('round_num'))
            else:
                r = meta.get('round') or meta.get('round_num')
                if r:
                    try:
                        rn = int(str(r))
                    except Exception:
                        rn = None
            if rn is None and 'title' in meta and meta.get('title'):
                import re
                m = re.search(r'Round\s*(\d{1,2})', meta.get('title'), re.IGNORECASE)
                if m:
                    rn = int(m.group(1))

            if rn in rounds:
                if u not in collected[rn]:
                    collected[rn].append(u)
                    print(f'Collected round {rn}: {u} (total for round: {len(collected[rn])})')
            else:
                print('Parsed round', rn, 'for', u)

        except Exception as e:
            print('Parse failed for', u, e)
            continue

    # write seeds file
    out = Path(f'data/raw/rounds_{args.year}_{"-".join(str(r) for r in sorted(rounds))}.txt')
    out.parent.mkdir(parents=True, exist_ok=True)
    flattened = []
    for r in sorted(rounds):
        flattened.extend(collected[r])
    out.write_text('\n'.join(flattened), encoding='utf8')
    print(f'Wrote {len(flattened)} urls to {out}')
    for r in sorted(rounds):
        print(f'Round {r}: {len(collected[r])} urls')


if __name__ == '__main__':
    main()
