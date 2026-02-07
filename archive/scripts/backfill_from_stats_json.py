"""Backfill PlayerStats explicit columns and team from stats_json.

Heuristics:
- For each match_id, locate a header-like stats_json row where many values are strings
  and include known abbreviations (KI, GL, MK, etc.). Use that row to map stats_json keys
  to canonical abbreviations.
- For each player row in the match, use that mapping to set explicit columns (goals, kicks,...)
  and set the team name by extracting the prefix before 'Match Statistics' from any key.

Run:
  python scripts/backfill_from_stats_json.py

This modifies the DB in-place; it's idempotent (will overwrite NULL explicit columns only).
"""

import sqlite3
import json
import re
from collections import Counter

DB = r'c:\dev\afl\data\processed\afl.db'
KNOWN = {
    'GL': 'goals',
    'G': 'goals',
    'Goals': 'goals',
    'BH': 'behinds',
    'B': 'behinds',
    'KI': 'kicks',
    'K': 'kicks',
    'MK': 'marks',
    'M': 'marks',
    'HB': 'handballs',
    'H': 'handballs',
    'DI': 'disposals',
    'D': 'disposals',
    'TK': 'tackles',
    'T': 'tackles',
    'HO': 'hitouts',
    'FF': 'frees_for',
    'FA': 'frees_against',
    'RB': 'rb',
    'IF': 'ifc',
    'CL': 'cl',
    'CG': 'cg',
    'BR': 'br',
    'CP': 'cp',
    'UP': 'up',
    'CM': 'cm',
    'MI': 'mi',
}
CANONICALS = set(KNOWN.values())

int_like = re.compile(r"^\s*-?\d+\s*$")

def coerce_int(v):
    if v is None:
        return None
    if isinstance(v, (int,)):
        return int(v)
    s = str(v).strip()
    if s == '':
        return None
    if int_like.match(s):
        try:
            return int(s)
        except Exception:
            return None
    # try float->int
    try:
        fv = float(s.replace(',',''))
        if fv.is_integer():
            return int(fv)
    except Exception:
        pass
    return None


def extract_team_from_keys(keys):
    # look for any key containing 'Match Statistics' and return the prefix
    for k in keys:
        if 'Match Statistics' in k:
            prefix = k.split('Match Statistics')[0].strip()
            # cleanup like trailing '['
            prefix = re.sub(r"\[.*$", "", prefix).strip()
            if prefix:
                return prefix
    return None


def build_header_map(rows_stats):
    """Given list of stats_json dicts for a match, try to find a header row and map abbrev->key.
    Return dict mapping canonical abbreviation -> key name in stats_json.
    """
    candidate = None
    best_score = -1
    # Look for row where many values are strings and match known ABBs
    for sj in rows_stats:
        if not sj:
            continue
        values = list(sj.values())
        str_count = sum(1 for v in values if isinstance(v, str))
        # count how many of those strings equal known abbreviations
        abb_count = 0
        for v in values:
            if isinstance(v, str):
                vs = v.strip()
                if vs in KNOWN:
                    abb_count += 1
                # sometimes header uses full word like 'Player' or 'Goals'
                if vs in KNOWN.keys():
                    abb_count += 0
        score = abb_count * 10 + str_count
        if score > best_score:
            best_score = score
            candidate = sj
    if not candidate:
        return {}
    # Build mapping: for each key, take candidate[key] as header label
    mapping = {}
    inverse = {}
    for k, v in candidate.items():
        if not isinstance(v, str):
            continue
        label = v.strip()
        # direct match
        if label in KNOWN:
            mapping[label] = k
            inverse[k] = KNOWN[label]
        else:
            # sometimes label is full name like 'Goals' or 'Kicks'
            up = label.upper()
            for abb, canon in KNOWN.items():
                if abb.upper() == up or abb.upper() == up[:len(abb)]:
                    mapping[abb] = k
                    inverse[k] = canon
                    break
            # sometimes the label is 'Player' or 'Player Name' -- skip
    # Return mapping from canonical column name -> key
    out = {}
    for abb, key in mapping.items():
        canon = KNOWN.get(abb)
        if canon:
            out[canon] = key
    return out


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute('SELECT DISTINCT match_id FROM player_stats')
    matches = [r[0] for r in cur.fetchall()]
    print(f'Found {len(matches)} matches in player_stats')

    total_updates = 0
    for mid in matches:
        cur.execute('SELECT id, team, stats_json FROM player_stats WHERE match_id=? ORDER BY id', (mid,))
        rows = cur.fetchall()
        if not rows:
            continue
        # parse stats_json for all rows
        rows_stats = []
        for r in rows:
            try:
                sj = json.loads(r[2]) if r[2] else {}
            except Exception:
                sj = {}
            rows_stats.append(sj)
        # build header map
        header_map = build_header_map(rows_stats)
        # extract team candidate
        team_cand = None
        # keys set across all rows
        all_keys = set()
        for sj in rows_stats:
            all_keys.update(sj.keys())
        team_cand = extract_team_from_keys(all_keys)

        if not header_map:
            # try heuristic: if keys are of the form '... .2' and values in first row are short strings like 'KI'
            # we already attempted; skip if not found
            # print(f'No header map for match {mid} (rows {len(rows)}).')
            continue

        # perform updates per row
        for idx, r in enumerate(rows):
            pid = r[0]
            team = r[1]
            sj = rows_stats[idx]
            updates = {}
            # set team if missing
            if (not team) and team_cand:
                updates['team'] = team_cand
            # for each canonical column, if NULL in DB, try to set from sj
            for canon, key in header_map.items():
                val = sj.get(key)
                ival = coerce_int(val)
                if ival is not None:
                    updates[canon] = ival
            if not updates:
                continue
            # build SQL SET clause, but only set columns that exist in player_stats
            sets = []
            params = []
            for col, val in updates.items():
                sets.append(f"{col}=?")
                params.append(val)
            params.append(pid)
            sql = f"UPDATE player_stats SET {', '.join(sets)} WHERE id=?"
            cur.execute(sql, params)
            total_updates += 1
        conn.commit()
    conn.close()
    print('Backfill complete. Rows updated:', total_updates)

if __name__ == '__main__':
    main()
