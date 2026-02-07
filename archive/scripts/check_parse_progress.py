#!/usr/bin/env python3
"""Check progress of re-parsing operation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import get_session, Match

def main():
    """Check parsing progress."""
    db = get_session()
    
    total = db.query(Match).filter(Match.token.isnot(None)).count()
    with_scores = db.query(Match).filter(Match.home_score.isnot(None)).count()
    with_dates = db.query(Match).filter(Match.date.isnot(None)).count()
    with_venues = db.query(Match).filter(Match.venue.isnot(None)).count()
    
    print(f"Total matches: {total}")
    print(f"With scores: {with_scores} ({100*with_scores/total:.1f}%)")
    print(f"With dates: {with_dates} ({100*with_dates/total:.1f}%)")
    print(f"With venues: {with_venues} ({100*with_venues/total:.1f}%)")
    print(f"Remaining: {total - with_scores}")

if __name__ == '__main__':
    main()
