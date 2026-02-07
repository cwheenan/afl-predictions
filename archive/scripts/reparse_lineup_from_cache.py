"""Re-parse cached tables to extract percent_played and sub markers and update DB.

This script avoids importing the project's `load_data` (which pulls external deps) by
reading the cache sqlite index directly and loading the cached CSV tables.

It will, for each cached token that has a `matches` row, load its tables CSVs,
find player rows, extract percent_played (as float) and sub markers and update
`player_stats` rows for that match where the fields are NULL.

Usage:
  python scripts/reparse_lineup_from_cache.py

Optional flags (future): --limit N
"""
import sqlite3
import json
from pathlib import Path
import csv
import re

CACHE_INDEX = Path('data/raw/cache/index.db')
DB = Path('data/processed/afl.db')
CACHE_DIR = Path('data/raw/cache')

if not CACHE_INDEX.exists():
    print('Cache index not found:', CACHE_INDEX)
    raise SystemExit(1)
if not DB.exists():
    print('DB not found:', DB)
    raise SystemExit(1)

# helper: coerce percent strings to float
def coerce_percent(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.endswith('%'):
        try:
            return float(s.replace('%', '').strip())
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None

# read cache index
idx_conn = sqlite3.connect(str(CACHE_INDEX))
icur = idx_conn.cursor()
icur.execute("SELECT token, tables_json FROM cached_matches")
entries = icur.fetchall()
idx_conn.close()

# map token -> list of table csv paths
token_tables = {}
for token, tables_json in entries:
    try:
        arr = json.loads(tables_json) if tables_json else []
    except Exception:
        arr = []
    token_tables[token] = arr

# open DB connection
conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# get matches map token -> match_id
cur.execute("SELECT match_id, token FROM matches")
matches = {row[1]: row[0] for row in cur.fetchall()}

updated = 0
skipped = 0
for token, tbls in token_tables.items():
    if token not in matches:
        continue
    mid = matches[token]
    # load each CSV and look for player tables
    players_info = []  # tuples(name, percent, sub_on, sub_off)
    for tpath in tbls:
        p = Path(tpath)
        if not p.exists():
            # try relative path within cache
            p2 = CACHE_DIR / 'tables' / Path(tpath).name
            if p2.exists():
                p = p2
            else:
                continue
        try:
            with p.open('r', encoding='utf8', errors='replace') as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
        except Exception:
            continue
        if not rows:
            continue
        # find name column
        cols = rows[0].keys()
        name_col = None
        for c in cols:
            if isinstance(c, str) and re.search(r'player|name|jumper', c, re.IGNORECASE):
                name_col = c
                break
        if name_col is None:
            # fallback: first column
            name_col = next(iter(cols))
        # iterate rows
        for row in rows:
            raw_name = row.get(name_col)
            if raw_name is None:
                continue
            name = str(raw_name).strip()
            if not name:
                continue
            low = name.lower()
            if low in ('player', 'players', 'totals', 'opposition', 'team'):
                continue
            if low.startswith('rushed'):
                continue
            # find percent cell if any: look for column names with % or pct
            pct = None
            sub_on = False
            sub_off = False
            for c in cols:
                try:
                    cc = str(c)
                except Exception:
                    continue
                if '%' in cc or 'pct' in cc.lower() or 'percent' in cc.lower() or 'pct_game' in cc.lower():
                    pct = coerce_percent(row.get(c))
                # detect sub markers in cell or column name
                cell = row.get(c)
                if isinstance(cell, str):
                    if '↑' in cell or '\u2191' in cell:
                        sub_on = True
                    if '↓' in cell or '\u2193' in cell:
                        sub_off = True
                if cc.strip().lower() in ('su', 'sub', '\u2191', '\u2193'):
                    # column heading may indicate sub marker; check cell
                    cell = row.get(c)
                    if isinstance(cell, str):
                        if '↑' in cell or '\u2191' in cell:
                            sub_on = True
                        if '↓' in cell or '\u2193' in cell:
                            sub_off = True
            players_info.append((name, pct, sub_on, sub_off))
    # Now update DB rows for this match
    if not players_info:
        continue
    # fetch all player_stats rows for this match
    cur.execute('SELECT id, player_id, stats_json, percent_played, sub_on, sub_off, team FROM player_stats WHERE match_id=?', (mid,))
    ps_rows = cur.fetchall()
    # build quick map player name -> (id, player_id)
    # also load players table to map names to player_id
    cur.execute('SELECT player_id, name FROM players')
    players_map = {r[1]: r[0] for r in cur.fetchall()}

    for pname, pct, s_on, s_off in players_info:
        # try match by exact player name in players table
        pid = players_map.get(pname)
        target_row = None
        if pid:
            for r in ps_rows:
                if r[1] == pid:
                    target_row = r
                    break
        if not target_row:
            # fallback: search stats_json for name substring
            for r in ps_rows:
                sid, spid, sj, cur_pct, cur_son, cur_soff, team = r
                try:
                    obj = json.loads(sj) if sj else {}
                except Exception:
                    obj = {}
                found = False
                for v in obj.values():
                    try:
                        if isinstance(v, str) and pname in v:
                            found = True
                            break
                    except Exception:
                        continue
                if found:
                    target_row = r
                    break
        if not target_row:
            skipped += 1
            continue
        sid, spid, sj, cur_pct, cur_son, cur_soff, team = target_row
        updates = {}
        if cur_pct in (None, '') and pct is not None:
            updates['percent_played'] = float(pct)
        if (cur_son in (None, 0) or cur_son is None) and s_on:
            updates['sub_on'] = 1
        if (cur_soff in (None, 0) or cur_soff is None) and s_off:
            updates['sub_off'] = 1
        # set named True if not set
        # check existing named value
        cur.execute('SELECT named FROM player_stats WHERE id=?', (sid,))
        existing_named = cur.fetchone()[0]
        if not existing_named:
            updates['named'] = 1
        if updates:
            set_sql = ', '.join([f"{k}=?" for k in updates.keys()])
            params = list(updates.values()) + [sid]
            sql = f"UPDATE player_stats SET {set_sql} WHERE id = ?"
            cur.execute(sql, params)
            updated += 1
    conn.commit()

conn.close()
print('Reparse complete. Rows updated:', updated, 'skipped=', skipped)
