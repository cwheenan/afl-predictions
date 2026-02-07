#!/usr/bin/env python3
"""Debug date extraction from a specific match."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pandas as pd
from afl_predictions.data import load_data

token = '091420220625.html_b28f262d'
cache_dir = 'data/raw/cache'

# Load cached tables
dfs = load_data.load_cached_match_tables(cache_dir, token)
print(f"Found {len(dfs)} tables")

# Focus on first table
if dfs:
    print("\n=== First DataFrame ===")
    df = dfs[0]
    print(f"Shape: {df.shape}")
    print(f"\nFirst 3 rows:\n{df.head(3)}")
    
    if len(df) > 0:
        print(f"\n=== Row 0 (headers) ===")
        for i, val in enumerate(df.iloc[0]):
            print(f"  Col {i}: {repr(val)}")
            
        # Check column 1 specifically
        if df.shape[1] > 1:
            header_text = str(df.iloc[0, 1])
            print(f"\nHeader text from col 1: {repr(header_text)}")
            
            import re
            venue_match = re.search(r'Venue:\s*([^:]+?)(?:\s+Date:|$)', header_text)
            print(f"Venue match: {venue_match.group(1) if venue_match else None}")
            
            date_match = re.search(r'Date:\s*([^:]+?)(?:\s+Attendance:|$)', header_text)
            print(f"Date match: {date_match.group(1) if date_match else None}")
