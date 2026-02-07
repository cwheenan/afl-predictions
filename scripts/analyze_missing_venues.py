#!/usr/bin/env python3
"""Analyze which years/matches are missing venue data."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import get_session, Match
from collections import Counter

def main():
    db = get_session()
    
    # Get matches without venues
    matches_no_venue = db.query(Match).filter(Match.venue.is_(None)).all()
    
    print(f"Total matches missing venues: {len(matches_no_venue)}\n")
    
    # Group by year
    years = Counter([m.season for m in matches_no_venue])
    
    print("Matches missing venues by year:")
    for year in sorted(years.keys()):
        print(f"  {year}: {years[year]} matches")
    
    # Sample a few tokens to inspect
    print(f"\nSample tokens to inspect:")
    for m in matches_no_venue[:5]:
        print(f"  {m.token} - {m.season} Round {m.round} - {m.home_team} vs {m.away_team}")

if __name__ == '__main__':
    main()
