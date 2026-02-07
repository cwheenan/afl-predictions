"""Improved backfill: extract team name and header->canonical mapping from stats_json keys.

This script will:
- For each match in player_stats, attempt to determine the team name from stats_json keys and fill missing `team` values.
- Attempt to discover a header row and map header columns to canonical DB columns (goals, kicks, disposals, marks, etc.).
- Update only NULL canonical columns (do not clobber existing values).

Run with:
  python scripts/backfill_team_and_headers.py

This edits the DB in-place. It's idempotent for NULL-only updates.
"""

import sqlite3
import json
import re
from collections import Counter

DB = r'c:\dev\afl\data\processed\afl.db'

# Canonical DB columns we try to populate
CANONICALS = ['goals', 'behinds', 'kicks', 'handballs', 'disposals', 'marks', 'tackles', 'hitouts', 'frees_for', 'frees_against']

int_like = re.compile(r"^\s*-?\d+\s*$")


def coerce_int(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s == '':
        return None
    if int_like.match(s):
        try:
            return int(s)
        except Exception:
            return None
    try:
        fv = float(s.replace(',', ''))
        if fv.is_integer():
            return int(fv)
    except Exception:
        pass
    return None


def extract_team_from_keys(keys):
    """Look for keys containing 'Match Statistics' and return the prefix (team name)."""
    for k in keys:
        if not isinstance(k, str):
            continue
        if 'Match Statistics' in k:
            prefix = k.split('Match Statistics')[0].strip()
            # strip any trailing bracketed info like '[Season]'
            prefix = re.sub(r"\[.*$", "", prefix).strip()
            # cleanup stray dots or hyphens
            prefix = re.sub(r"[\.|\-]+$", "", prefix).strip()
            if prefix:
                return prefix
    return None


def label_to_canonical(label):
    """Map a label string to one of the CANONICALS using heuristics."""
    if not isinstance(label, str):
        return None
    s = label.strip().lower()
    # simple substring heuristics
    if 'goal' in s and 'assist' not in s:
        return 'goals'
    if 'behind' in s or '\bbh\b' in s:
        return 'behinds'
    if 'kick' in s and 'hit' not in s:
        return 'kicks'
    if 'hand' in s:
        return 'handballs'
    if 'disposal' in s or s == 'di' or s == 'd':
        return 'disposals'
    if s in ('ki', 'k') and 'kick' in s:
        return 'kicks'
    if 'mark' in s and 'contested' not in s:
        return 'marks'
    if 'tackle' in s or s == 'tk' or s == 't':
        return 'tackles'
    if 'hit' in s or 'hitout' in s or s == 'ho':
        return 'hitouts'
    if 'free' in s and 'for' in s:
        return 'frees_for'
    if 'free' in s and 'against' in s:
        return 'frees_against'
    # try short forms
    if s in ('gl', 'g', 'goals'):
        return 'goals'
    if s in ('bh', 'b'):
        return 'behinds'
    if s in ('ki', 'kicks', 'k'):
        return 'kicks'
    if s in ('mk', 'marks', 'm'):
        return 'marks'
    if s in ('hb', 'handballs', 'h'):
        return 'handballs'
    if s in ('di', 'disposals', 'd'):
        return 'disposals'
    if s in ('tk', 't', 'tackles'):
        return 'tackles'
    if s in ('ho', 'hitouts', 'hit_outs', 'hit_out'):
        return 'hitouts'
    if 'frees' in s or s in ('ff', 'fa'):
        # ambiguous; prefer frees_for if 'ff' or 'for' present, frees_against for 'fa'
        if 'fa' in s or 'against' in s:
            return 'frees_against'
        return 'frees_for'
    return None


def build_header_map(rows_stats):
    """Given list of stats_json dicts for a match, try to find a header-like dict and map canonical->json_key."""
    # Legacy single-match heuristic retained for backward-compatibility.
    candidate = None
    best_score = -1
    # heuristic: look for a row with many non-numeric, short-string values
    for sj in rows_stats:
        if not sj:
            continue
        values = list(sj.values())
        # count non-numeric values
        non_num = 0
        short_str = 0
        abb_hits = 0
        for v in values:
            if isinstance(v, str):
                vs = v.strip()
                # header labels are often short (<=8 chars)
                if len(vs) <= 8:
                    short_str += 1
                # treat purely alphabetic short tokens as likely abbreviations
                if re.match(r'^[A-Za-z%\\u2191\\u2193]+$', vs) and len(vs) <= 4:
                    abb_hits += 1
                non_num += 1
            else:
                # possibly numbers
                try:
                    float(v)
                except Exception:
                    non_num += 1
        score = abb_hits * 10 + short_str * 3 + non_num
        if score > best_score:
            best_score = score
            candidate = sj
    if not candidate:
        return {}
    mapping = {}
    # For each json key, map the candidate value -> canonical, if heuristic finds one
    for key, val in candidate.items():
        if not isinstance(val, str):
            continue
        canon = label_to_canonical(val)
        if canon:
            mapping[canon] = key
        else:
            # attempt to extract a trailing short token like '.2' not needed; skip
            # sometimes label is like 'Player' or 'Player Name' -> skip
            pass
    return mapping


def build_prefix_header_maps(rows_stats):
    """Build header mappings per team-prefix found in the stats_json keys.

    Returns a dict: prefix_string -> { canonical_col: full_json_key }
    """
    prefixes = set()
    for sj in rows_stats:
        for k in sj.keys():
            if not isinstance(k, str):
                continue
            if 'Match Statistics' in k:
                p = k.split('Match Statistics')[0].strip()
                p = re.sub(r"\[.*$", "", p).strip()
                p = re.sub(r"[\.|\-]+$", "", p).strip()
                if p:
                    prefixes.add(p)
    if not prefixes:
        return {}

    prefix_maps = {}
    # For each prefix, attempt to find a candidate header row restricted to keys with that prefix
    for p in prefixes:
        # Build per-row dicts containing only keys that start with this prefix
        scoped_rows = []
        for sj in rows_stats:
            small = {k: v for k, v in sj.items() if isinstance(k, str) and k.startswith(p)}
            # remap key names to the full key (we keep full key names for updating)
            if small:
                scoped_rows.append(small)
        if not scoped_rows:
            continue
        # Now use a similar heuristic to pick the best candidate in scoped_rows
        candidate = None
        best_score = -1
        for sj in scoped_rows:
            values = list(sj.values())
            non_num = 0
            short_str = 0
            abb_hits = 0
            for v in values:
                if isinstance(v, str):
                    vs = v.strip()
                    if len(vs) <= 8:
                        short_str += 1
                    if re.match(r'^[A-Za-z%\\u2191\\u2193]+$', vs) and len(vs) <= 4:
                        abb_hits += 1
                    non_num += 1
                else:
                    try:
                        float(v)
                    except Exception:
                        non_num += 1
            score = abb_hits * 10 + short_str * 3 + non_num
            if score > best_score:
                best_score = score
                candidate = sj
        if not candidate:
            continue
        # Build mapping canonical->full_key for this prefix and try to detect player column
        pm = {}
        player_key = None
        for key, val in candidate.items():
            if not isinstance(val, str):
                continue
            v = val.strip()
            # detect player header label
            if v.lower().startswith('player'):
                player_key = key
            canon = label_to_canonical(v)
            if canon:
                pm[canon] = key
        if pm or player_key:
            entry = { 'mapping': pm }
            if player_key:
                entry['player_key'] = player_key
            prefix_maps[p] = entry
    return prefix_maps


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
        rows_stats = []
        for r in rows:
            try:
                sj = json.loads(r[2]) if r[2] else {}
            except Exception:
                sj = {}
            rows_stats.append(sj)
        # aggregate keys
        all_keys = set()
        for sj in rows_stats:
            all_keys.update(sj.keys())
        # Build overall team candidate (fallback) and per-prefix header maps
        team_cand = extract_team_from_keys(all_keys)
        header_map = build_header_map(rows_stats)
        prefix_maps = build_prefix_header_maps(rows_stats)
        # If some prefixes didn't have their own header candidate, try to synthesize mappings
        # by substituting a known prefix's keys with the other prefix string.
        if prefix_maps:
            all_keys_set = set(all_keys)
            # choose a source prefix mapping with the most entries
            src_prefix = max(prefix_maps.keys(), key=lambda k: len(prefix_maps[k]))
            src_map = prefix_maps[src_prefix]
            # derive prefixes present in all_keys
            prefixes_local = set()
            for k in all_keys:
                if not isinstance(k, str):
                    continue
                if 'Match Statistics' in k:
                    p = k.split('Match Statistics')[0].strip()
                    p = re.sub(r"\[.*$", "", p).strip()
                    p = re.sub(r"[\.|\-]+$", "", p).strip()
                    if p:
                        prefixes_local.add(p)
            for pfx in prefixes_local:
                # only synthesize for prefixes not already in prefix_maps
                if pfx in prefix_maps:
                    continue
                synthesized = {}
                for canon, src_key in src_map.items():
                    # only attempt replacement when src_prefix is substring of src_key
                    if src_prefix in src_key:
                        candidate_key = src_key.replace(src_prefix, pfx)
                        if candidate_key in all_keys_set:
                            synthesized[canon] = candidate_key
                if synthesized:
                    prefix_maps[pfx] = synthesized

        # For each player row, prefer using a per-prefix map if we can detect which prefix applies
        for idx, r in enumerate(rows):
            pid = r[0]
            team = r[1]
            updates = {}
            sj = rows_stats[idx]

            # find best matching prefix for this row (most keys starting with prefix)
            chosen_prefix = None
            chosen_map = None
            chosen_player_key = None
            if prefix_maps:
                best_count = 0
                for p, entry in prefix_maps.items():
                    # entry is either a dict mapping (legacy) or our new {'mapping':..., 'player_key':...}
                    pm = entry['mapping'] if isinstance(entry, dict) and 'mapping' in entry else entry
                    cnt = sum(1 for k in sj.keys() if isinstance(k, str) and k.startswith(p))
                    if cnt > best_count:
                        best_count = cnt
                        chosen_prefix = p
                        chosen_map = pm
                        # detect player_key if present
                        if isinstance(entry, dict) and 'player_key' in entry:
                            chosen_player_key = entry['player_key']

            # set team from chosen_prefix if available, else fallback to team_cand
            if (not team) and chosen_prefix:
                updates['team'] = chosen_prefix
            elif (not team) and team_cand:
                updates['team'] = team_cand

            # locate player name for this row to detect header/subtotal rows
            player_name = None
            # prefer chosen_player_key if available
            if chosen_player_key:
                player_name = sj.get(chosen_player_key)
            else:
                # heuristic: find key with many comma-separated values (Last, First) across rows
                # fallback: find key where first row value equals 'Player'
                comma_counts = {}
                for k in sj.keys():
                    vals = sj.get(k)
                    if isinstance(vals, str) and ',' in vals:
                        comma_counts[k] = 1
                if comma_counts:
                    # if current row doesn't have comma, still use key with highest occurrence across sample
                    # choose first comma key
                    player_name = sj.get(next(iter(comma_counts)))
                else:
                    # look for any key where value string equals 'Player' (header)
                    for k in sj.keys():
                        v = sj.get(k)
                        if isinstance(v, str) and v.strip().lower().startswith('player'):
                            player_name = None
                            break
                    # else try to pick the first string-like value as name
                    if player_name is None:
                        for k in sj.keys():
                            v = sj.get(k)
                            if isinstance(v, str) and v.strip():
                                player_name = v
                                break

            # now decide if this looks like a header/subtotal row we should skip
            skip_row = False
            if player_name is None:
                skip_row = True
            else:
                pn = str(player_name).strip()
                low = pn.lower()
                if low in ('player', 'rushed', 'rushed ', 'totals', 'team'):
                    skip_row = True
                # numeric-only names are not players
                if re.match(r'^\d+$', pn):
                    skip_row = True
            if skip_row:
                continue

            # choose mapping: per-prefix first, then global header_map
            mapping_to_use = chosen_map if chosen_map else header_map

            # populate canonical columns where NULL
            if mapping_to_use:
                cur.execute('SELECT ' + ','.join(CANONICALS) + ' FROM player_stats WHERE id=?', (pid,))
                current = cur.fetchone()
                cur_map = {col: current[i] for i, col in enumerate(CANONICALS)}
                for canon, key in mapping_to_use.items():
                    if cur_map.get(canon) is not None:
                        continue
                    val = sj.get(key)
                    ival = coerce_int(val)
                    if ival is not None:
                        updates[canon] = ival

            if not updates:
                continue
            # perform update
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
