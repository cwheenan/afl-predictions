"""Parse cached matches and add to database."""
import sys
from pathlib import Path

# Add archive scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'archive' / 'scripts'))

from parse_matches import parse_and_upsert
from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session
from afl_predictions import config


def main():
    cache_dir = str(config.DEFAULT_CACHE_DIR)
    df = load_data.list_cached_matches(cache_dir)
    
    if df.empty:
        print("No cached matches found")
        return
    
    print(f"Found {len(df)} cached matches")
    
    engine = get_engine()
    session = get_session(engine)
    
    for idx, row in df.iterrows():
        token = row['token']
        try:
            parse_and_upsert(cache_dir, token, session)
            print(f"✓ Parsed {token}")
        except Exception as e:
            print(f"✗ Failed to parse {token}: {e}")
    
    print("Done!")


if __name__ == '__main__':
    main()
