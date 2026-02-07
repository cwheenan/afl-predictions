"""Debug score extraction."""
from afl_predictions.data import load_data
import pandas as pd
from pathlib import Path
import re

token = '091420220625.html_b28f262d'
cache_dir = 'data/raw/cache'

# Load HTML
import sqlite3
index_db_path = Path(cache_dir) / 'index.db'
index_db = sqlite3.connect(str(index_db_path))
cur = index_db.cursor()
cur.execute('SELECT html_path FROM cached_matches WHERE token = ?', (token,))
row = cur.fetchone()

if row:
    html_path = row[0]
    html = Path(html_path).read_text(encoding='utf8')
    dfs = pd.read_html(html)
    
    print('First DataFrame:')
    ndf = dfs[0]
    print(f'Shape: {ndf.shape}')
    print(ndf)
    
    print('\n\nAnalyzing rows:')
    for idx in range(min(5, len(ndf))):
        row = ndf.iloc[idx]
        print(f'\nRow {idx}:')
        for col_idx, val in enumerate(row):
            print(f'  Col {col_idx}: "{val}"')
            
            # Check for score pattern
            val_str = str(val).strip()
            score_match = re.search(r'(\d+)\.(\d+)\.(\d+)$', val_str)
            if score_match:
                print(f'    -> SCORE FOUND: {score_match.group(3)}')
