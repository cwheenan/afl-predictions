"""CLI to list cached AFLTables matches from the sqlite index.

Usage:
    python scripts/list_cache.py --cache-dir data/raw/cache --team "Carlton" --since 2024-01-01 --limit 20

Options:
 - --cache-dir: path to cache (defaults to config.DEFAULT_CACHE_DIR)
 - --team: substring filter applied to URL or tables paths (simple heuristic)
 - --since: ISO date (YYYY-MM-DD) to filter fetched_at >= that date
 - --limit: maximum rows to print
 - --json: print JSON output rather than a table
"""
import argparse
from pathlib import Path
import json
from datetime import datetime

import pandas as pd
from afl_predictions.data.load_data import list_cached_matches
from afl_predictions import config


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR), help='Cache directory to read index from')
    p.add_argument('--team', default=None, help='Filter entries by team substring (matches in URL or table paths)')
    p.add_argument('--since', default=None, help='ISO date YYYY-MM-DD to filter fetched_at')
    p.add_argument('--limit', type=int, default=None, help='Max number of rows to show')
    p.add_argument('--json', action='store_true', help='Output JSON')
    return p.parse_args()


def filter_df(df: pd.DataFrame, team: str = None, since: str = None) -> pd.DataFrame:
    if df.empty:
        return df
    if team:
        term = team.lower()
        mask = df['url'].str.lower().str.contains(term) | df['tables'].apply(lambda lst: any(term in p.lower() for p in lst))
        df = df[mask]
    if since:
        # parse date into timestamp
        try:
            dt = datetime.fromisoformat(since)
            ts = int(dt.timestamp())
            df = df[df['fetched_at'] >= ts]
        except Exception:
            print('Warning: failed to parse --since date; ignoring')
    return df


def main():
    args = parse_args()
    df = list_cached_matches(args.cache_dir)
    if df.empty:
        print('No cached matches found in', args.cache_dir)
        return

    df = filter_df(df, team=args.team, since=args.since)
    if args.limit:
        df = df.head(args.limit)

    if args.json:
        print(df.to_json(orient='records'))
    else:
        # show a concise table: fetched_at (ISO), token, url
        df2 = df.copy()
        df2['fetched_at'] = df2['fetched_at'].apply(lambda x: datetime.utcfromtimestamp(int(x)).isoformat())
        print(df2[['fetched_at', 'token', 'url']].to_string(index=False))


if __name__ == '__main__':
    main()
