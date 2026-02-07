#!/usr/bin/env python3
"""Batch re-parse to populate missing dates and venues efficiently."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions import config
from afl_predictions.db import get_session, Match
from afl_predictions.data import parse_match

def main():
    """Batch update dates and venues."""
    db = get_session()
    cache_dir = str(config.DEFAULT_CACHE_DIR)
    
    # Get matches that still need venues
    matches = db.query(Match).filter(
        Match.token.isnot(None),
        Match.venue.is_(None)
    ).all()
    
    print(f"Updating {len(matches)} matches...")
    
    updated_count = 0
    error_count = 0
    
    for i, match in enumerate(matches, 1):
        try:
            # Parse metadata
            meta, _ = parse_match.parse_match_from_cache(cache_dir, match.token)
            
            # Update fields if available
            changed = False
            if meta.get('venue') and not match.venue:
                match.venue = meta['venue']
                changed = True
            if meta.get('date') and not match.date:
                match.date = meta['date']
                changed = True
                
            if changed:
                updated_count += 1
                db.add(match)
            
            # Batch commit every 500 matches
            if i % 500 == 0:
                db.commit()
                print(f"Progress: {i}/{len(matches)} ({updated_count} updated, {error_count} errors)")
                
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"Error: {match.token}: {e}")
    
    # Final commit
    db.commit()
    
    print(f"\nComplete!")
    print(f"  Updated: {updated_count}")
    print(f"  Errors: {error_count}")

if __name__ == '__main__':
    main()
