#!/usr/bin/env python3
"""CLI to query local DB for a player's stats in a given season/round.

Example:
    python scripts/query_player.py --name "Tom Hawkins" --season 2017 --round 16
"""
import sys
from pathlib import Path
import argparse

# Ensure `src/` is on sys.path so this script can be run from the repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from afl_predictions.data.query import find_goals_for, get_player_stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True, help='Player name (partial allowed)')
    p.add_argument('--season', type=int, required=True)
    p.add_argument('--round', required=True)
    p.add_argument('--db-url', default=None)
    args = p.parse_args()

    goals = find_goals_for(args.name, args.season, args.round, db_url=args.db_url)
    if goals is not None:
        print(f"{args.name} scored {goals} goals in round {args.round} {args.season}")
        return

    # fallback: print full matching rows
    rows = get_player_stats(args.name, season=args.season, round=args.round, db_url=args.db_url)
    if not rows:
        print('No matching rows found in DB. Make sure you have seeded and parsed cached pages into the DB.')
        return
    for r in rows:
        print('match:', r['match_id'], 'team:', r['team'], 'stats:', r['stats'])


if __name__ == '__main__':
    main()
