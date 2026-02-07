"""Migration: add lineup/sub columns to player_stats and backfill from stats_json.

Usage:
  python scripts/migrate_add_lineup_columns.py
"""
from pathlib import Path
import sqlite3
import json
import re

DB = Path('data/processed/afl.db')
if not DB.exists():
    print('DB not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

cols = {
    'named': 'INTEGER',
    'percent_played': 'INTEGER',
    'sub_on': 'INTEGER',
    'sub_off': 'INTEGER',
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

# Backfill: try to extract percent played and sub markers from stats_json
cur.execute("SELECT id, stats_json FROM player_stats")
rows = cur.fetchall()
updated = 0
for rid, j in rows:
    if not j:
        continue
    try:
        obj = json.loads(j)
    except Exception:
        continue
    updates = {}
    # percent played: look for %P or Pct_game_played or values ending with %
    pct = None
    for k, v in obj.items():
        if k is None:
            continue
        kn = str(k).strip().lower()
        if '%p' in kn or 'pct' in kn or 'percent' in kn or 'pct_game' in kn:
            # found probable percent key
            if isinstance(v, str) and v.endswith('%'):
                try:
                    pct = int(v.replace('%', '').strip())
                except Exception:
                    pass
            else:
                try:
                    pct = int(float(v))
                except Exception:
                    pass
            break
        # also consider values that are like '80%'
        if isinstance(v, str) and v.endswith('%'):
            try:
                pct = int(v.replace('%', '').strip())
                break
            except Exception:
                pass
    if pct is not None:
        updates['percent_played'] = pct
    # sub markers: look for up/down arrows or SU in keys or values
    sub_on = False
    sub_off = False
    for k, v in obj.items():
        if k and isinstance(k, str):
            if '\u2191' in k or '\u2193' in k or 'su' == k.strip().lower() or 'sub' in k.lower():
                # presence of these keys may indicate sub markers; inspect value
                if isinstance(v, str):
                    if '\u2191' in v or 'uparrow' in v or 'subbed on' in v.lower() or '↑' in v:
                        sub_on = True
                    if '\u2193' in v or 'downarrow' in v or 'subbed off' in v.lower() or '↓' in v:
                        sub_off = True
        # also inspect values
        if isinstance(v, str):
            if '↑' in v or '\u2191' in v or v.strip() == '↑':
                sub_on = True
            if '↓' in v or '\u2193' in v or v.strip() == '↓':
                sub_off = True
    if sub_on:
        updates['sub_on'] = 1
    if sub_off:
        updates['sub_off'] = 1
    # named: presence of a non-empty name in stats_json is not reliable here; skip setting named for now
    if updates:
        set_sql = ', '.join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [rid]
        sql = f"UPDATE player_stats SET {set_sql} WHERE id = ?"
        cur.execute(sql, params)
        updated += 1

conn.commit()
print('Backfilled lineup rows:', updated)
conn.close()
