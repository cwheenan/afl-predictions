"""Utilities to parse cached AFLTables match tables into structured records.

This module provides two levels of API:
- parse_player_tables_from_dfs(dfs, token=None, url=None) -> (match_meta, players)
  which is pure-data (easy to unit-test) and accepts a list of pandas DataFrames
  representing the parsed HTML tables for a match page.
- parse_match_from_cache(cache_dir, token_or_url) -> same outputs but reads
  the cached CSVs using existing `load_data` helpers.

The parser is intentionally conservative: it extracts per-player rows from any
table that looks like a player stats table (contains a player/jumper column and
some numeric stat columns). It returns JSON-serialisable dicts so DB upserts
can be implemented by the caller.
"""
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
import json
import logging
import re
from bs4 import BeautifulSoup
import pandas as pd

from afl_predictions.data import abbreviations, load_data

LOG = logging.getLogger(__name__)


def _detect_name_column(df: pd.DataFrame) -> Optional[str]:
    """Return the most likely player name column in the given DataFrame.

    Common candidates: 'Player', 'Jumper' (number), or the first textual column.
    """
    cols = list(df.columns)
    # Prefer explicit matches (case-insensitive substring) for common name columns
    # Prefer 'player' or 'name' over 'jumper' because 'Jumper' often contains numeric
    # guernsey numbers rather than the textual player name.
    for c in cols:
        if isinstance(c, str) and re.search(r'player|name', c, re.IGNORECASE):
            return c
    for c in cols:
        if isinstance(c, str) and re.search(r'jumper', c, re.IGNORECASE):
            return c

    # fallback: exact candidates
    candidates = ['Player', 'Jumper', 'Name']
    for c in candidates:
        if c in cols:
            return c

    # fallback: pick the first column with string dtype or non-numeric values
    # Prefer a column where many rows look like 'Last, First' (contains a comma)
    best = None
    best_score = 0.0
    for c in cols:
        try:
            vals = df[c].dropna().astype(str).tolist()
        except Exception:
            continue
        if not vals:
            continue
        # score by proportion of rows containing a comma (common 'Last, First' pattern)
        comma_frac = sum(1 for v in vals if ',' in v) / len(vals)
        if comma_frac > best_score:
            best_score = comma_frac
            best = c
    if best is not None and best_score > 0.1:
        return best

    for c in cols:
        if df[c].dtype == object:
            return c
    # nothing obvious
    return None


def _coerce_stats(row: pd.Series) -> Dict[str, Any]:
    """Convert a pandas row to JSON-serialisable stats, coercing numerics where possible."""
    out = {}
    for k, v in row.items():
        # keep strings as-is
        if pd.isna(v):
            out[k] = None
            continue
        # try int
        try:
            if isinstance(v, str):
                vs = v.replace(',', '').strip()
                if vs == '':
                    out[k] = None
                    continue
                # convert percentages like '80%' to float 80.0 for consistency
                if vs.endswith('%'):
                    try:
                        out[k] = float(vs.replace('%', '').strip())
                    except Exception:
                        out[k] = vs
                    continue
                iv = int(float(vs))
                out[k] = iv
                continue
            if isinstance(v, (int,)):
                out[k] = int(v)
                continue
            if isinstance(v, float):
                if v.is_integer():
                    out[k] = int(v)
                else:
                    out[k] = float(v)
                continue
        except Exception:
            # leave as original
            pass
        out[k] = v
    return out


def parse_player_tables_from_dfs(dfs: List[pd.DataFrame], token: Optional[str] = None, url: Optional[str] = None, teams: Optional[list] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parse a list of DataFrames (tables) from a match page and return structured data.

    Returns (match_meta, players) where:
      - match_meta: dict with keys 'token', 'url', and optional discovered fields
      - players: list of dicts {"name":..., "team":..., "stats": {...}}

    The function is conservative and will skip tables that don't look like player
    stat tables.
    """
    match_meta: Dict[str, Any] = {'token': token, 'url': url}
    players: List[Dict[str, Any]] = []

    for ti, tbl in enumerate(dfs):
        if not isinstance(tbl, pd.DataFrame):
            continue

        # Keep original and normalized copies. We want to return stats keyed by
        # the original column names (e.g. 'GL', 'KI') while using the normalized
        # frame for detection and heuristics.
        orig_df = tbl.copy()
        try:
            norm_df = abbreviations.expand_df_columns(tbl.copy())
        except Exception:
            norm_df = orig_df.copy()

        # Attempt to detect a header row embedded in the table body where
        # pandas.read_html preserved a header as a data row (common on AFLTables).
        # We scan the first few rows for strings that look like abbreviations
        # (e.g. 'KI', 'GL', 'MK') or expanded names ('Kicks', 'Goals'). If found,
        # we'll use that row to map column positions to stat labels and then
        # augment each player's stats dict with those labels so downstream code
        # can pick canonical values.
        header_map = {}  # column_index -> header_label (string)
        try:
            max_scan = min(6, len(orig_df))
            for hr in range(max_scan):
                prow = orig_df.iloc[hr]
                str_vals = [str(x).strip() for x in prow.tolist() if pd.notna(x)]
                if not str_vals:
                    continue
                # count how many values look like known abbreviations or expanded names
                abb_count = 0
                for sv in str_vals:
                    # exact ABB match or expanded match
                    if sv in abbreviations.ABBREVIATIONS or sv in list(abbreviations.ABBREVIATIONS.values()):
                        abb_count += 1
                    # short all-caps tokens like 'KI', 'GL'
                    elif re.fullmatch(r"[A-Z]{1,4}", sv):
                        abb_count += 1
                # Heuristic: if at least 3 abbreviation-like tokens in the row,
                # treat this as a header row
                if abb_count >= 3:
                    # build header map using column positions
                    for ci, col in enumerate(orig_df.columns):
                        try:
                            val = str(orig_df.iloc[hr, ci]).strip()
                        except Exception:
                            val = ''
                        if val and val != 'nan':
                            header_map[ci] = val
                    # we won't treat the header row as a player row
                    header_row_idx = hr
                    break
            else:
                header_row_idx = None
        except Exception:
            header_map = {}
            header_row_idx = None
        name_col = _detect_name_column(norm_df)
        if name_col is None:
            # not a player table
            continue

        # Heuristic: require at least one numeric stat column besides name/jumper
        stat_cols = [c for c in norm_df.columns if c != name_col]
        if not stat_cols:
            continue

        # If there are zero numeric-ish columns, skip
        numeric_like = 0
        for c in stat_cols:
            try:
                if pd.to_numeric(norm_df[c], errors='coerce').notna().any():
                    numeric_like += 1
            except Exception:
                continue
        if numeric_like == 0:
            continue

    # Try to infer team name: sometimes present as dataframe attrs or column-less header
        team_name = None
        # If table has a column named 'Team' use it
        if 'Team' in norm_df.columns:
            # if team column is constant, prefer it
            vals = norm_df['Team'].dropna().unique()
            if len(vals) == 1:
                team_name = vals[0]

        # If there's a caption or title attribute on the DataFrame (from read_html), try that
        try:
            if hasattr(tbl, 'attrs') and isinstance(tbl.attrs, dict):
                cap = tbl.attrs.get('title') or tbl.attrs.get('caption')
                if cap and isinstance(cap, str) and cap.strip():
                    # simple heuristic: if caption contains a team name in parentheses, prefer it
                    m = re.search(r'\(([^)]+)\)', cap)
                    if m:
                        team_name = m.group(1)
        except Exception:
            pass
        # If we still don't have a team name but the caller provided team order
        # (e.g. [home, away]), use the table index to assign the team when it
        # makes sense (common pattern: first team table = home, second = away).
        try:
            if team_name is None and teams and isinstance(teams, (list, tuple)):
                if ti < len(teams):
                    team_name = teams[ti]
                elif len(teams) == 2 and ti in (0, 1):
                    team_name = teams[ti]
        except Exception:
            pass
        # Iterate rows
        # We'll iterate by integer index to access both norm_df and orig_df rows
        norm_cols = list(norm_df.columns)
        orig_cols = list(orig_df.columns)
        # map normalized name column back to original column name by position
        try:
            name_col_idx = norm_cols.index(name_col)
            orig_name_col = orig_cols[name_col_idx]
        except ValueError:
            # fallback: try to find a plausible original name
            orig_name_col = None
            for c in orig_cols:
                if str(c).lower() in ('player', 'name', 'jumper'):
                    orig_name_col = c
                    break

        for i in range(len(norm_df)):
            nrow = norm_df.iloc[i]
            orow = orig_df.iloc[i] if i < len(orig_df) else nrow

            # extract name using original-name column where possible
            name = None
            if orig_name_col and orig_name_col in orow and pd.notna(orow[orig_name_col]) and str(orow[orig_name_col]).strip() != '':
                name = orow[orig_name_col]
            else:
                # fallback to normalized name column
                if name_col in nrow and pd.notna(nrow[name_col]):
                    name = nrow[name_col]

            # skip obvious header/summary rows that pandas sometimes includes as data
            if name is None:
                continue
            name_str = str(name).strip()
            low = name_str.lower()
            if low in ('player', 'players', 'totals', 'opposition', 'team', 'teams'):
                continue
            # also skip rows that look like aggregate/label rows
            if re.match(r'^(total|totals|opp|opposition)$', low):
                continue
            # skip obvious non-player rows like 'Rushed' or similar summaries
            if low.startswith('rushed') or 'rushed' == low:
                continue
            # skip rows that are purely numeric or only punctuation (jumper-only rows)
            if re.match(r'^[\d\W]+$', name_str):
                continue

            # Build stats keyed by original column names where possible
            stats_src = {}
            for idx, nc in enumerate(norm_cols):
                oc = orig_cols[idx] if idx < len(orig_cols) else nc
                if oc == orig_name_col:
                    # skip the name column
                    continue
                # get value from original row if present, else normalized
                val = orow.get(oc) if oc in orow.index else nrow.get(nc)
                stats_src[oc] = val

            # Remove obvious index-like columns
            stats_src.pop('#', None)

            stats = _coerce_stats(pd.Series(stats_src))
            # Augment stats with header-derived abbreviations and expanded names
            # so downstream code (and existing _pick_stat heuristics) can find
            # canonical stat labels like 'GL' or 'Goals' even when the original
            # keys are positional (e.g. '...Game by Game].6').
            try:
                # copy to avoid mutating original mapping in-place
                stats_aug = dict(stats)
                for idx, oc in enumerate(orig_cols):
                    if oc == orig_name_col:
                        continue
                    if idx in header_map:
                        header_label = header_map[idx]
                        # put the raw value under the header label
                        v = stats_src.get(oc)
                        if v is not None:
                            stats_aug[header_label] = v
                        # also expand common abbreviations to expanded names
                        try:
                            expanded = abbreviations.expand_series_name(header_label)
                            if expanded and expanded != header_label:
                                stats_aug[expanded] = v
                        except Exception:
                            pass
                # canonicalize percent_played and sub flags into consistent keys
                # percent: look for expanded name 'Pct_game_played' or any key containing '%'
                percent_val = None
                sub_on_flag = False
                sub_off_flag = False
                for k, v in list(stats_aug.items()):
                    try:
                        exp = abbreviations.expand_series_name(str(k))
                    except Exception:
                        exp = str(k)
                    k_low = str(exp).lower() if exp is not None else ''
                    if 'pct' in k_low or 'percent' in k_low or '%p' in str(k).lower():
                        # coerce numeric percent if possible (coerce handled earlier)
                        percent_val = v
                    if 'subbed_on' in k_low or 'subbed' in k_low or 'sub_on' in k_low or exp == 'Subbed_on':
                        # value may contain arrow or marker
                        if isinstance(v, str) and ('\u2191' in v or '↑' in v):
                            sub_on_flag = True
                    if 'subbed_off' in k_low or 'subbed' in k_low or 'sub_off' in k_low or exp == 'Subbed_off':
                        if isinstance(v, str) and ('\u2193' in v or '↓' in v):
                            sub_off_flag = True
                if percent_val is not None:
                    stats_aug['percent_played'] = percent_val
                if sub_on_flag:
                    stats_aug['sub_on'] = True
                if sub_off_flag:
                    stats_aug['sub_off'] = True
                stats = stats_aug
            except Exception:
                pass
            players.append({
                'name': str(name) if name is not None else None,
                'team': team_name,
                'stats': stats,
            })

    return match_meta, players


def parse_match_from_cache(cache_dir: str, token_or_url: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load cached tables for a token or URL and parse them.

    Returns the same structure as parse_player_tables_from_dfs.
    """
    dfs = load_data.load_cached_match_tables(cache_dir, token_or_url)
    # try to get meta (best-effort)
    try:
        idx = load_data.list_cached_matches(cache_dir)
        # match by token or url
        meta_row = None
        if idx is not None and not idx.empty:
            meta_row = idx[(idx['token'] == token_or_url) | (idx['url'] == token_or_url)]
            if not meta_row.empty:
                row = meta_row.iloc[0].to_dict()
                token = row.get('token')
                url = row.get('url')
                # make html_path available for later HTML parsing
                html_path = row.get('html_path')
            else:
                token = None
                url = None
        else:
            token = None
            url = None
            html_path = None
    except Exception:
        token = None
        url = None

    # attempt to extract richer metadata from the cached HTML and tables
    match_meta_extra: Dict[str, Any] = {}
    try:
        # prefer parsing the HTML if we have it
        if 'html_path' in locals() and html_path:
            try:
                html = Path(html_path).read_text(encoding='utf8')
                soup = BeautifulSoup(html, 'html.parser')

                # title often contains teams and round/year
                title = soup.title.string.strip() if soup.title and soup.title.string else None
                if title:
                    match_meta_extra['title'] = title
                    # season/year from title (support 19xx and 20xx)
                    m = re.search(r"((?:19|20)\d{2})", title)
                    if m:
                        match_meta_extra['season'] = int(m.group(1))
                    # round
                    m2 = re.search(r"Round\s*(\d{1,2})", title, re.IGNORECASE)
                    if m2:
                        match_meta_extra['round'] = int(m2.group(1))

                # As a fallback, search the full page text for a 'Round' marker
                try:
                    page_text = soup.get_text(" ", strip=True)
                    m3 = re.search(r"Round[:\s]*\b(\d{1,2})\b", page_text, re.IGNORECASE)
                    if m3 and 'round' not in match_meta_extra:
                        match_meta_extra['round'] = int(m3.group(1))
                except Exception:
                    pass

                # try to find a small descriptive paragraph containing date/venue
                try:
                    for p in soup.find_all(['p', 'div']):
                        txt = (p.get_text() or '').strip()
                        if not txt or len(txt) > 200:
                            continue
                        # date like '14 June 2022' or '14/06/2022'
                        if re.search(r"\b\d{1,2}\s+\w+\s+20\d{2}\b", txt) or re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\b", txt):
                            match_meta_extra.setdefault('date_text', txt)
                        # venue heuristics: 'at MCG' or 'at Adelaide Oval'
                        if re.search(r"\bat\s+[A-Za-z ]+Oval\b|\bat\s+MCG\b|\bat\s+[A-Za-z ]+Ground\b", txt, re.IGNORECASE):
                            match_meta_extra.setdefault('venue_text', txt)
                except Exception:
                    pass
                
                # Look for venue in <b>Venue: </b><a href="...">VenueName</a> pattern
                try:
                    for b_tag in soup.find_all('b'):
                        if b_tag.string and 'Venue:' in b_tag.string:
                            # Check for adjacent <a> tag
                            next_tag = b_tag.find_next_sibling('a')
                            if next_tag and next_tag.string:
                                venue_name = next_tag.string.strip()
                                if venue_name:
                                    match_meta_extra.setdefault('venue', venue_name)
                                    break
                except Exception:
                    pass
            except Exception:
                pass

        # fallback: if we still don't have a season, try to extract it from the URL
        try:
            if 'url' in locals() and url and 'season' not in match_meta_extra:
                mu = re.search(r"/([0-9]{4})/", url)
                if mu:
                    match_meta_extra['season'] = int(mu.group(1))
        except Exception:
            pass

        # Next, try to extract teams and final scores from the parsed tables (dfs)
        try:
            for tbl_idx, tbl in enumerate(dfs):
                try:
                    ndf = abbreviations.expand_df_columns(tbl.copy())
                except Exception:
                    ndf = tbl.copy()
                
                # Strategy 1: Look for AFL Tables score format (first table with team names and quarter scores)
                # Typical format: Row 0 = headers with venue/date, Row 1 = Team1, Row 2 = Team2
                # Columns might be: [0=nav, 1=TeamName, 2=Q1, 3=Q2, 4=Q3, 5=Final, 6=nav]
                if tbl_idx == 0 and ndf.shape[0] >= 2:  # First table, at least 2 data rows
                    try:
                        # Extract venue and date from first row (header row)
                        if len(ndf) > 0:
                            header_text = str(ndf.iloc[0, 1]) if ndf.shape[1] > 1 else ""
                            if header_text:
                                # Extract venue: "Venue: M.C.G."
                                venue_match = re.search(r'Venue:\s*([^D]+?)(?:\s+Date:|$)', header_text)
                                if venue_match:
                                    match_meta_extra['venue'] = venue_match.group(1).strip()
                                
                                # Extract date: "Date: Sat, 25-Jun-2022 4:35 PM"
                                # Note: Date contains colons (time), so match up to "Attendance:"
                                date_match = re.search(r'Date:\s*(.+?)(?:\s+Attendance:|$)', header_text)
                                if date_match:
                                    match_meta_extra['date'] = date_match.group(1).strip()
                        
                        teams = []
                        scores = []
                        
                        for idx in range(min(4, len(ndf))):  # Check first 4 rows
                            row = ndf.iloc[idx]
                            
                            # Team name is usually in column 1 (column 0 is often navigation arrows)
                            team_name = str(row.iloc[1]).strip() if len(row) > 1 else ""
                            
                            # Skip header rows or nav rows
                            if not team_name or team_name in ['←', '→', 'Qrt', 'NaN', 'Field umpires'] or 'Qrt' in team_name or 'Round:' in team_name or 'Venue:' in team_name:
                                continue
                            
                            # Try to extract final score from columns (working backwards, skipping last nav column)
                            final_score = None
                            for col_idx in range(len(row) - 2, 0, -1):  # Skip last column (nav), work backwards
                                val = str(row.iloc[col_idx]).strip()
                                # AFL score format: "13.11.89" (goals.behinds.total)
                                score_match = re.search(r'(\d+)\.(\d+)\.(\d+)$', val)
                                if score_match:
                                    final_score = int(score_match.group(3))  # Extract total points
                                    break
                                # Or just a number
                                elif re.match(r'^\d{1,3}$', val):
                                    final_score = int(val)
                                    break
                            
                            if team_name and final_score is not None:
                                teams.append(team_name)
                                scores.append(final_score)
                                
                                if len(teams) == 2:  # Found both teams
                                    match_meta_extra['teams'] = teams
                                    match_meta_extra['scores'] = scores
                                    break
                        
                        if len(teams) == 2:
                            break  # Successfully extracted scores
                    except Exception:
                        pass
                
                # Strategy 2: Fallback - look for a 'T' or 'TOTAL' column (old logic)
                cols = [str(c) for c in ndf.columns]
                if any(c.strip().upper() in ('T', 'TOTAL') for c in cols):
                    try:
                        team_col = ndf.columns[0]
                        totals_col = None
                        for c in ndf.columns[::-1]:
                            if str(c).strip().upper() in ('T', 'TOTAL'):
                                totals_col = c
                                break
                        if totals_col is None:
                            totals_col = ndf.columns[-1]

                        teams = [str(x).strip() for x in ndf[team_col].dropna().tolist()]
                        totals = [int(float(x)) for x in ndf[totals_col].dropna().tolist() if str(x).strip().isdigit() or re.match(r"^\d+$", str(x).strip())]
                        if teams and totals and len(teams) == len(totals) and len(teams) >= 2:
                            match_meta_extra['teams'] = teams[:2]
                            match_meta_extra['scores'] = totals[:2]
                            break
                    except Exception:
                        continue
        except Exception:
            pass
    except Exception:
        pass

    # merge extracted extras into returned meta
    meta_out = {'token': token, 'url': url}
    meta_out.update(match_meta_extra)

    parsed_meta, players = parse_player_tables_from_dfs(dfs, token=token, url=url, teams=match_meta_extra.get('teams'))
    # merge any discovered fields
    parsed_meta.update(meta_out)
    return parsed_meta, players


__all__ = [
    'parse_player_tables_from_dfs',
    'parse_match_from_cache',
]
