#!/usr/bin/env python
"""Build a token-only manifest CSV from a URL-style manifest.
Usage:
  python scripts/build_manifest_tokens.py --manifest data/raw/cache/manifest_1991.csv --out data/raw/cache/manifest_1991_tokens.csv
"""
import argparse
import json
from pathlib import Path
import glob
import pandas as pd

p = argparse.ArgumentParser()
p.add_argument('--manifest', required=True)
p.add_argument('--out', required=True)
args = p.parse_args()

manifest = args.manifest
out = args.out

urls = pd.read_csv(manifest)['url'].tolist()
meta_files = glob.glob('data/raw/cache/metadata/*.json')
url2token = {}
for mf in meta_files:
    try:
        with open(mf, 'r', encoding='utf-8') as f:
            j = json.load(f)
            u = j.get('url')
            t = j.get('token')
            if u and t:
                url2token[u] = t
    except Exception:
        continue

tokens = [url2token.get(u) for u in urls if url2token.get(u)]
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
import pandas as pd
pd.DataFrame({'token': tokens}).to_csv(args.out, index=False)
print(f'wrote {len(tokens)} tokens to {out}')
