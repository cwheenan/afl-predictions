#!/usr/bin/env python3
"""Add match_odds table to database.

Usage:
  python scripts/migrate_add_odds_table.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import get_engine, Base, MatchOdds

def main():
    engine = get_engine()
    
    print("Adding match_odds table to database...")
    
    # Create only the MatchOdds table
    MatchOdds.__table__.create(engine, checkfirst=True)
    
    print("✓ match_odds table created successfully")
    print("\nTable structure:")
    print("  - id (primary key)")
    print("  - match_id (foreign key to matches)")
    print("  - source (bookmaker name)")
    print("  - home_win_odds, away_win_odds (H2H odds)")
    print("  - home_line_odds, away_line_odds, line_spread (line betting)")
    print("  - total_points, over_odds, under_odds (totals)")
    print("  - timestamp (when odds were collected)")
    
    print("\nReady to collect odds data!")
    print("Next step: python scripts/collect_odds.py --fetch-current --api-key YOUR_KEY")

if __name__ == '__main__':
    main()
