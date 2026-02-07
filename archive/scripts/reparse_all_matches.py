#!/usr/bin/env python3
"""Re-parse all cached matches to populate missing scores/dates/venues."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions import config
from afl_predictions.db import get_session, Match

# Import parse_and_upsert from parse_matches
sys.path.insert(0, str(Path(__file__).parent))
from parse_matches import parse_and_upsert

def main():
    """Re-parse all matches in the database."""
    db = get_session()
    cache_dir = str(config.DEFAULT_CACHE_DIR)
    
    # Get matches that still need venues populated
    matches = db.query(Match).filter(
        Match.token.isnot(None),
        Match.venue.is_(None)
    ).all()
    
    total_matches = db.query(Match).filter(Match.token.isnot(None)).count()
    completed = total_matches - len(matches)
    
    print(f"Total matches: {total_matches}")
    print(f"Already processed: {completed}")
    print(f"Remaining: {len(matches)}")
    print(f"Cache directory: {cache_dir}")
    print("Re-parsing to populate dates and venues...")
    print()
    
    success_count = 0
    error_count = 0
    
    for i, match in enumerate(matches, 1):
        try:
            updated = parse_and_upsert(cache_dir, match.token, db)
            if updated:
                success_count += 1
            
            if i % 100 == 0:
                print(f"Progress: {i}/{len(matches)} ({success_count} updated, {error_count} errors)")
        except Exception as e:
            error_count += 1
            if error_count <= 10:  # Only print first 10 errors
                print(f"Error parsing {match.token}: {e}")
    
    print(f"\nComplete! Processed {len(matches)} matches")
    print(f"  - Updated: {success_count}")
    print(f"  - Errors: {error_count}")
    print(f"  - Unchanged: {len(matches) - success_count - error_count}")

if __name__ == '__main__':
    main()
