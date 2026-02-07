"""Examine cached match HTML and tables."""
from afl_predictions.data import load_data
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

token = '091420220625.html_b28f262d'
cache_dir = 'data/raw/cache'

# Load the cached data
import sqlite3
index_db_path = Path(cache_dir) / 'index.db'
index_db = sqlite3.connect(str(index_db_path))
cur = index_db.cursor()
cur.execute('SELECT html_path, tables_json FROM cached_matches WHERE token = ?', (token,))
row = cur.fetchone()

if row:
    html_path, tables_json = row
    
    print('=== HTML EXCERPT ===')
    html = Path(html_path).read_text(encoding='utf8')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Look for score tables
    for i, table in enumerate(soup.find_all('table')[:3]):
        print(f'\nTable {i}:')
        print(table.get_text()[:500])
        print('...\n')
    
    print('\n=== PARSED TABLES ===')
    import json
    tables_data = json.loads(tables_json) if tables_json else []
    print(f'Number of tables: {len(tables_data)}')
    
    # Use pandas read_html on the actual HTML
    print('\n=== Using pandas.read_html ===')
    dfs = pd.read_html(html)
    print(f'Number of DataFrames: {len(dfs)}')
    
    for i, df in enumerate(dfs[:3]):
        print(f'\nDataFrame {i}:')
        print(f'Shape: {df.shape}')
        print(f'Columns: {list(df.columns)}')
        print(df.head())
        print()
else:
    print('Token not found in cache')
