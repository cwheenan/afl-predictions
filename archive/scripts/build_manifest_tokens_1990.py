import json
import glob
import pandas as pd

manifest = 'data/raw/cache/manifest_1990.csv'
out = 'data/raw/cache/manifest_1990_tokens.csv'
urls = pd.read_csv(manifest)['url'].tolist()
meta_files = glob.glob('data/raw/cache/metadata/*.json')
url2token = {}
for mf in meta_files:
    with open(mf, 'r', encoding='utf-8') as f:
        try:
            j = json.load(f)
            u = j.get('url')
            t = j.get('token')
            if u and t:
                url2token[u] = t
        except Exception:
            continue

tokens = [url2token.get(u) for u in urls if url2token.get(u)]
import os
os.makedirs('data/raw/cache', exist_ok=True)
import pandas as pd
pd.DataFrame({'token': tokens}).to_csv(out, index=False)
print(f'wrote {len(tokens)} tokens to {out}')
