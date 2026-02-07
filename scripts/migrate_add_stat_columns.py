"""Migration: add explicit stat columns to player_stats and backfill from stats_json.

Usage:
  python scripts/migrate_add_stat_columns.py
"""
from pathlib import Path
import sqlite3
import json

DB = Path('data/processed/afl.db')
if not DB.exists():
    print('DB not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# desired columns and their SQL types
cols = {
    'goals': 'INTEGER',
    'behinds': 'INTEGER',
    'kicks': 'INTEGER',
    'handballs': 'INTEGER',
    'disposals': 'INTEGER',
    'marks': 'INTEGER',
    'tackles': 'INTEGER',
    'hitouts': 'INTEGER',
    'frees_for': 'INTEGER',
    'frees_against': 'INTEGER',
}

# get existing columns
cur.execute("PRAGMA table_info('player_stats')")
existing = [r[1] for r in cur.fetchall()]

for name, typ in cols.items():
    if name in existing:
        print('Column exists:', name)
    else:
        sql = f"ALTER TABLE player_stats ADD COLUMN {name} {typ}"
        print('Adding column:', sql)
        cur.execute(sql)

conn.commit()

# backfill: read stats_json and populate columns
cur.execute("SELECT id, match_id, stats_json FROM player_stats")
rows = cur.fetchall()

# helper mapping: try multiple possible keys used on AFLTables
key_map = {
    'goals': ['GL', 'Goals', 'G', 'goals', 'gl'],
    'behinds': ['B', 'BH', 'Behinds', 'behinds', 'b'],
    'kicks': ['KI', 'K', 'Kicks', 'kicks', 'ki'],
    'handballs': ['HB', 'H', 'Handballs', 'handballs', 'hb'],
    'disposals': ['D', 'DI', 'Disp', 'Disposals', 'disposals', 'd'],
    'marks': ['MK', 'M', 'Marks', 'marks', 'mk'],
    'tackles': ['T', 'TK', 'TA', 'Tackles', 'tackles', 'tk'],
    'hitouts': ['HO', 'HitOuts', 'hitouts', 'ho'],
    'frees_for': ['FF', 'Ff', 'Frees For', 'frees_for', 'ff'],
    'frees_against': ['FA', 'Frees Against', 'frees_against', 'fa'],
}
# Group rows by match_id to find header rows and map column keys -> labels
from collections import defaultdict

by_match = defaultdict(list)
for rid, mid, j in rows:
    by_match[mid].append((rid, j))

updated = 0
for mid, items in by_match.items():
    # find a candidate header row: one whose stats_json values are mostly strings and include known abbreviations
    header_obj = None
    header_keys = None
    for rid, j in items:
        if not j:
            continue
        try:
            obj = json.loads(j)
        except Exception:
            continue
        # count string vs numeric values
        str_count = 0
        num_count = 0
        for v in obj.values():
            if v is None:
                continue
            if isinstance(v, str):
                # if string contains letters, count as string
                if any(c.isalpha() for c in v):
                    str_count += 1
                else:
                    try:
                        float(v)
                        num_count += 1
                    except Exception:
                        str_count += 1
            elif isinstance(v, (int, float)):
                num_count += 1
        if str_count >= max(3, num_count):
            # potential header row
            # check if any known header labels present
            vals = [str(x).strip() for x in obj.values() if x is not None]
            labels_found = 0
            for lablist in key_map.values():
                for lab in lablist:
                    if lab in vals:
                        labels_found += 1
                        break
            if labels_found >= 2:
                header_obj = obj
                header_keys = list(obj.keys())
                break

    if header_obj is None:
        # fallback: try any first row's keys
        try:
            header_obj = json.loads(items[0][1])
            header_keys = list(header_obj.keys())
        except Exception:
            continue

    # build mapping from header key -> canonical stat name
    key_to_label = {}
    for hk, hv in header_obj.items():
        if not hv:
            continue
        lbl = str(hv).strip()
        for canon, labs in key_map.items():
            if lbl in labs or lbl.upper() in [x.upper() for x in labs]:
                key_to_label[hk] = canon
                break

    if not key_to_label:
        continue

    # now for each non-header row, extract values by header keys
    for rid, j in items:
        if not j:
            continue
        try:
            obj = json.loads(j)
        except Exception:
            continue
        updates = {}
        for hk, canon in key_to_label.items():
            if hk in obj and obj[hk] is not None:
                try:
                    v = obj[hk]
                    if isinstance(v, str):
                        v = v.replace(',', '').strip()
                        if v.endswith('%') or v == '':
                            continue
                        v = float(v)
                    updates[canon] = int(v)
                except Exception:
                    continue
        if updates:
            set_sql = ', '.join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [rid]
            sql = f"UPDATE player_stats SET {set_sql} WHERE id = ?"
            cur.execute(sql, params)
            updated += 1

conn.commit()
print('Backfilled rows:', updated)
conn.close()
# create helpful indexes
conn = sqlite3.connect(str(DB))
cur = conn.cursor()
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_player_match ON player_stats (player_id, match_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_player ON player_stats (player_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_match ON player_stats (match_id)")
conn.commit()
conn.close()
