"""Abbreviation mapping and helpers for AFLTables scraped columns.

This module centralises the common abbreviations used on afltables pages so
parsers can expand them to readable column names before downstream processing.

Usage:
    from afl_predictions.data.abbreviations import ABBREVIATIONS, expand_df_columns
    df = expand_df_columns(df)
"""
from typing import Dict
import re
import pandas as pd

# Common abbreviations observed on AFLTables pages (partial list provided by user).
ABBREVIATIONS: Dict[str, str] = {
    '#': 'Jumper',
    'GM': 'Games',
    'KI': 'Kicks',
    'MK': 'Marks',
    'HB': 'Handballs',
    'DI': 'Disposals',
    'DA': 'Disposal_avg',
    'GL': 'Goals',
    'BH': 'Behinds',
    'HO': 'Hit_outs',
    'TK': 'Tackles',
    'RB': 'Rebound_50s',
    'IF': 'Inside_50s',
    'CL': 'Clearances',
    'CG': 'Clangers',
    'FF': 'Free_kicks_for',
    'FA': 'Free_kicks_against',
    'BR': 'Brownlow_votes',
    'CP': 'Contested_possessions',
    'UP': 'Uncontested_possessions',
    '\u2193': 'Subbed_off',  # ↓
    'CM': 'Contested_marks',
    'MI': 'Marks_inside_50',
    '1%': 'One_percenters',
    'BO': 'Bounces',
    'GA': 'Goal_assist',
    '%P': 'Pct_game_played',
    'SU': 'Sub_on_off',
    '\u2191': 'Subbed_on',   # ↑
}


def _normalize_col_name(col: str) -> str:
    """Normalize a column name for matching: strip whitespace and HTML leftovers."""
    if not isinstance(col, str):
        return col
    # Remove HTML entities like <br> and whitespace
    c = re.sub(r'<[^>]+>', '', col)
    c = c.strip()
    # Collapse multiple spaces
    c = re.sub(r'\s+', ' ', c)
    return c


def expand_df_columns(df: pd.DataFrame, inplace: bool = False) -> pd.DataFrame:
    """Return a DataFrame with columns renamed according to the ABBREVIATIONS map.

    The function attempts exact matches first, then case-insensitive matches where
    whitespace and basic HTML tags have been removed. Columns without a mapping
    are left unchanged.
    """
    if not inplace:
        df = df.copy()

    new_cols = []
    for col in df.columns:
        norm = _normalize_col_name(col)
        # exact match
        if norm in ABBREVIATIONS:
            new_cols.append(ABBREVIATIONS[norm])
            continue
        # case-insensitive match
        found = False
        for k, v in ABBREVIATIONS.items():
            if k.lower() == norm.lower():
                new_cols.append(v)
                found = True
                break
        if found:
            continue

        # try to match when column contains the abbreviation (e.g. 'KI (kicks)')
        matched = None
        for k, v in ABBREVIATIONS.items():
            if re.search(r'\b' + re.escape(k) + r'\b', norm, flags=re.IGNORECASE):
                matched = v
                break
        if matched:
            new_cols.append(matched)
            continue

        # Fallback: keep original
        new_cols.append(col)

    df.columns = new_cols
    return df


def expand_series_name(name: str) -> str:
    """Expand a single column name string using the abbreviations map.

    Returns the expanded name or the original if no match.
    """
    norm = _normalize_col_name(name)
    if norm in ABBREVIATIONS:
        return ABBREVIATIONS[norm]
    for k, v in ABBREVIATIONS.items():
        if k.lower() == norm.lower():
            return v
    for k, v in ABBREVIATIONS.items():
        if re.search(r'\b' + re.escape(k) + r'\b', norm, flags=re.IGNORECASE):
            return v
    return name
