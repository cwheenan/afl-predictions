"""Parse cached tokens listed in a manifest CSV.

Usage:
  python scripts/run_parse_for_manifest.py data/raw/cache/manifest_1992.csv
"""
import sys, os
import csv
from afl_predictions.data import load_data

if len(sys.argv) < 2:
    print('usage: python scripts/run_parse_for_manifest.py <manifest.csv>')
    sys.exit(1)

manifest = sys.argv[1]
cache_dir = os.path.join('data', 'raw', 'cache')

if not os.path.exists(manifest):
    print('manifest not found:', manifest)
    sys.exit(1)

with open(manifest, newline='', encoding='utf8') as fh:
    reader = csv.reader(fh)
    rows = list(reader)
    urls = [r[0] for r in rows[1:] if r]

print('Found', len(urls), 'urls in manifest', manifest)

df = load_data.list_cached_matches(cache_dir)
if df.empty:
    print('No cached matches found; aborting')
    sys.exit(1)

url_to_token = {row['url']: row['token'] for _, row in df.iterrows()}

tokens = [url_to_token.get(u) for u in urls if url_to_token.get(u)]
print('Mapped to', len(tokens), 'tokens (missing', len(urls)-len(tokens), 'urls)')

if not tokens:
    sys.exit(0)

# call parse_matches.py with tokens
cmd = ['python', os.path.join('scripts','parse_matches.py'), '--cache-dir', cache_dir, '--tokens'] + tokens
print('Running parse subprocess (this may take a while)...')
import subprocess
subprocess.run(cmd)
print('Done')
