"""Map manifest URLs to cached tokens and parse/upsert them into DB.

Usage: run from repo root with PYTHONPATH set so package imports work.
"""
import csv, os
from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session
import subprocess

MANIFEST = os.path.join('data', 'raw', 'cache', 'manifest_1995.csv')
CACHE_DIR = os.path.join('data', 'raw', 'cache')


def read_manifest_urls(manifest_path):
    if not os.path.exists(manifest_path):
        return []
    with open(manifest_path, newline='', encoding='utf8') as fh:
        reader = csv.reader(fh)
        rows = list(reader)
        urls = [r[0] for r in rows[1:] if r]
    return urls


def map_urls_to_tokens(urls, cache_dir):
    df = load_data.list_cached_matches(cache_dir)
    if df.empty:
        return {}
    url_to_token = {row['url']: row['token'] for _, row in df.iterrows()}
    mapping = {u: url_to_token.get(u) for u in urls}
    return mapping


if __name__ == '__main__':
    urls = read_manifest_urls(MANIFEST)
    print(f'Found {len(urls)} urls in manifest')
    mapping = map_urls_to_tokens(urls, CACHE_DIR)
    tokens = [mapping.get(u) for u in urls if mapping.get(u)]
    print(f'Will parse {len(tokens)} tokens (missing: {len(urls) - len(tokens)})')
    if not tokens:
        print('No tokens to parse; exiting')
    else:
        # call the existing parse_matches.py script with the tokens list
        cmd = ['python', os.path.join('scripts', 'parse_matches.py'), '--cache-dir', CACHE_DIR, '--tokens'] + tokens
        print('Running:', ' '.join(cmd[:6]), '...')
        # run in the repo root so imports resolve; rely on caller setting PYTHONPATH if needed
        subprocess.run(cmd, check=False)
        print('Parsing subprocess finished')
