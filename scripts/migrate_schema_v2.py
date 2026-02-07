"""Schema migration v2

- Normalize players: add name_norm, dedupe players by normalized name, update player_stats to canonical player_id.
- Add matches.date_iso (ISO string) and round_num (integer), try to parse from existing date or pages.url.
- Add extra stat columns discovered in headers and backfill them.
- Enforce uniqueness on player_stats (match_id, player_id) by rebuilding the table (keep one row per pair).

Run:
  python scripts/migrate_schema_v2.py
"""
from pathlib import Path
import sqlite3
import re
from dateutil import parser as dparser
import json

DB = Path('data/processed/afl.db')
if not DB.exists():
    print('DB not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# --- 1) Normalize players: add name_norm column, populate, dedupe ---
print('Step 1: normalize players')
cur.execute("PRAGMA foreign_keys=OFF")
conn.commit()

cur.execute("PRAGMA table_info('players')")
existing = [r[1] for r in cur.fetchall()]
if 'name_norm' not in existing:
    cur.execute("ALTER TABLE players ADD COLUMN name_norm VARCHAR")
    conn.commit()

# populate name_norm
cur.execute("SELECT player_id, name FROM players")
players = cur.fetchall()
for pid, name in players:
    if name is None:
        norm = None
    else:
        norm = re.sub(r"\s+", ' ', name.strip()).lower()
    cur.execute("UPDATE players SET name_norm = ? WHERE player_id = ?", (norm, pid))
conn.commit()

# dedupe: map name_norm -> canonical player_id (smallest id)
cur.execute("SELECT name_norm, GROUP_CONCAT(player_id) FROM players GROUP BY name_norm HAVING COUNT(*) > 1 AND name_norm IS NOT NULL")
dups = cur.fetchall()
print('Found duplicate name_norm groups:', len(dups))
for name_norm, group_csv in dups:
    ids = [int(x) for x in group_csv.split(',')]
    ids.sort()
    canonical = ids[0]
    others = ids[1:]
    # update player_stats to canonical
    for oid in others:
        cur.execute("UPDATE player_stats SET player_id = ? WHERE player_id = ?", (canonical, oid))
    # delete duplicate player rows
    cur.execute("DELETE FROM players WHERE player_id IN (%s)" % ','.join('?'*len(others)), others)
    conn.commit()

# create unique index on name_norm
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_players_name_norm ON players (name_norm)")
conn.commit()
print('Players deduped; unique index on name_norm created')

# also create unique index on token if not existing
cur.execute("PRAGMA index_list('players')")
idxs = [r[1] for r in cur.fetchall()]
# create index on token if not present
cur.execute("CREATE INDEX IF NOT EXISTS ix_players_token ON players (token)")
conn.commit()

# --- 2) Normalize matches.date and add round_num ---
print('Step 2: normalize matches.date -> date_iso and round_num')
cur.execute("PRAGMA table_info('matches')")
mcols = [r[1] for r in cur.fetchall()]
if 'date_iso' not in mcols:
    cur.execute("ALTER TABLE matches ADD COLUMN date_iso VARCHAR")
if 'round_num' not in mcols:
    cur.execute("ALTER TABLE matches ADD COLUMN round_num INTEGER")
conn.commit()

# populate date_iso: try parsing matches.date, else try pages.url
cur.execute("SELECT match_id, date, token FROM matches")
for mid, dateval, token in cur.fetchall():
    date_iso = None
    # try parse dateval
    if dateval:
        try:
            dt = dparser.parse(str(dateval), dayfirst=True, fuzzy=True)
            date_iso = dt.date().isoformat()
        except Exception:
            date_iso = None
    if not date_iso:
        # try pages table url
        cur.execute("SELECT url FROM pages WHERE token = ?", (token,))
        row = cur.fetchone()
        if row and row[0]:
            url = row[0]
            m = re.search(r"/(20\d{2})/", url)
            if m:
                # fall back to year-only (set first Jan)
                try:
                    y = int(m.group(1))
                    date_iso = f"{y}-01-01"
                except Exception:
                    date_iso = None
    if date_iso:
        cur.execute("UPDATE matches SET date_iso = ? WHERE match_id = ?", (date_iso, mid))
    # round_num from matches.round
    round_num = None
    cur.execute("SELECT round FROM matches WHERE match_id = ?", (mid,))
    rrow = cur.fetchone()
    if rrow and rrow[0]:
        try:
            m2 = re.search(r"(\d+)", str(rrow[0]))
            if m2:
                round_num = int(m2.group(1))
        except Exception:
            round_num = None
    if round_num is not None:
        cur.execute("UPDATE matches SET round_num = ? WHERE match_id = ?", (round_num, mid))
conn.commit()
print('Matches normalized (date_iso/round_num) where possible')

# --- 3) Add extra stat columns and backfill ---
print('Step 3: add extra stat columns and backfill')
extra_cols = ['rb','ifc','cl','cg','br','cp','up','cm','mi']
# map to SQL-friendly names (if is keyword) use ifc for IF
cur.execute("PRAGMA table_info('player_stats')")
ps_cols = [r[1] for r in cur.fetchall()]
for col in extra_cols:
    if col not in ps_cols:
        cur.execute(f"ALTER TABLE player_stats ADD COLUMN {col} INTEGER")
conn.commit()

# Reuse header-detection backfill logic similar to prior migration
print('Backfilling extra stat columns from stats_json')
cur.execute("SELECT id, match_id, stats_json FROM player_stats")
rows = cur.fetchall()
from collections import defaultdict
by_match = defaultdict(list)
for rid, mid, j in rows:
    by_match[mid].append((rid, j))

# candidate key map: map canonical names to possible header labels
key_map = {
    'goals': ['GL','Goals','G','goals','gl'],
    'behinds': ['BH','B','Behinds','behinds','b'],
    'kicks': ['KI','K','Kicks','kicks','ki'],
    'handballs': ['HB','H','Handballs','handballs','hb'],
    'disposals': ['DI','D','Disp','Disposals','disposals','d'],
    'marks': ['MK','M','Marks','marks','mk'],
    'tackles': ['TK','T','Tackles','tackles','tk'],
    'hitouts': ['HO','HitOuts','hitouts','ho'],
    'frees_for': ['FF','Ff','Frees For','frees_for','ff'],
    'frees_against': ['FA','Frees Against','frees_against','fa'],
    'rb': ['RB','Rebound','RBs','rb'],
    'ifc': ['IF','IFC','IFs','if','ifc'],
    'cl': ['CL','Clark','cl'],
    'cg': ['CG','CGs','cg'],
    'br': ['BR','BRs','br'],
    'cp': ['CP','cp'],
    'up': ['UP','up'],
    'cm': ['CM','cm'],
    'mi': ['MI','mi'],
}

updated = 0
for mid, items in by_match.items():
    header_obj = None
    header_keys = None
    for rid, j in items:
        if not j:
            continue
        try:
            obj = json.loads(j)
        except Exception:
            continue
        # heuristic: header contains many short alpha strings
        alpha_count = sum(1 for v in obj.values() if isinstance(v, str) and any(c.isalpha() for c in v))
        num_count = sum(1 for v in obj.values() if isinstance(v, (int,float)) or (isinstance(v,str) and v.replace(',','').strip().isdigit()))
        if alpha_count >= max(3, num_count//2):
            header_obj = obj
            header_keys = list(obj.keys())
            break
    if header_obj is None:
        # fallback to first item
        try:
            header_obj = json.loads(items[0][1])
            header_keys = list(header_obj.keys())
        except Exception:
            continue
    # build mapping
    key_to_canon = {}
    # header_obj maps header_key -> label (like 'GL', 'KI' etc.) in many cases
    for hk, hv in header_obj.items():
        if not hv:
            continue
        lbl = str(vh_label := hv).strip()
        for canon, labs in key_map.items():
            if lbl in labs or lbl.upper() in [x.upper() for x in labs]:
                key_to_canon[hk] = canon
                break
    if not key_to_canon:
        continue
    for rid, j in items:
        if not j:
            continue
        try:
            obj = json.loads(j)
        except Exception:
            continue
        updates = {}
        for hk, canon in key_to_canon.items():
            if hk in obj and obj[hk] is not None:
                try:
                    v = obj[hk]
                    if isinstance(v, str):
                        v = v.replace(',','').strip()
                        if v.endswith('%') or v == '':
                            continue
                        v = float(v)
                    updates[canon] = int(v)
                except Exception:
                    continue
        if updates:
            set_sql = ', '.join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [rid]
            cur.execute(f"UPDATE player_stats SET {set_sql} WHERE id = ?", params)
            updated += 1
conn.commit()
print('Extra stat backfilled rows:', updated)

# --- 4) Enforce uniqueness on player_stats (match_id, player_id) ---
print('Step 4: enforce uniqueness on player_stats (match_id, player_id)')
# create new table with unique constraint
cur.execute('''
CREATE TABLE IF NOT EXISTS player_stats_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    player_id INTEGER,
    team VARCHAR,
    stats_json TEXT,
    goals INTEGER,
    behinds INTEGER,
    kicks INTEGER,
    handballs INTEGER,
    disposals INTEGER,
    marks INTEGER,
    tackles INTEGER,
    hitouts INTEGER,
    frees_for INTEGER,
    frees_against INTEGER,
    rb INTEGER,
    ifc INTEGER,
    cl INTEGER,
    cg INTEGER,
    br INTEGER,
    cp INTEGER,
    up INTEGER,
    cm INTEGER,
    mi INTEGER,
    UNIQUE(match_id, player_id)
)
''')
conn.commit()

# copy distinct rows: prefer lowest id per pair (keeps first)
cur.execute('''
INSERT OR IGNORE INTO player_stats_new (
    id, match_id, player_id, team, stats_json, goals, behinds, kicks, handballs, disposals,
    marks, tackles, hitouts, frees_for, frees_against, rb, ifc, cl, cg, br, cp, up, cm, mi
)
SELECT MIN(id) as id, match_id, player_id, team, stats_json, goals, behinds, kicks, handballs, disposals,
    marks, tackles, hitouts, frees_for, frees_against, rb, ifc, cl, cg, br, cp, up, cm, mi
FROM player_stats
GROUP BY match_id, player_id
''')
conn.commit()

# drop old table and rename
cur.execute('DROP TABLE player_stats')
cur.execute('ALTER TABLE player_stats_new RENAME TO player_stats')
conn.commit()

# recreate indexes
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_player_match ON player_stats (player_id, match_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_player ON player_stats (player_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_player_stats_match ON player_stats (match_id)")
conn.commit()

# re-enable foreign keys
cur.execute("PRAGMA foreign_keys=ON")
conn.commit()
conn.close()
print('Migration v2 complete')
