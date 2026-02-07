"""Test the parser on a sample match to see what's extracted."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.data import parse_match
import json
import sys

# Test on a sample token
token = sys.argv[1] if len(sys.argv) > 1 else '091420220625.html_b28f262d'
cache_dir = 'data/raw/cache'

print(f'Testing parser on token: {token}\n')

try:
    meta, players = parse_match.parse_match_from_cache(cache_dir, token)
    
    print('Extracted metadata:')
    print(json.dumps(meta, indent=2, default=str))
    
    print(f'\nNumber of player records: {len(players)}')
    
    print('\nKey fields:')
    print(f'  Season: {meta.get("season")}')
    print(f'  Round: {meta.get("round")}')
    print(f'  Teams: {meta.get("teams")}')
    print(f'  Scores: {meta.get("scores")}')
    print(f'  Date: {meta.get("date_text")}')
    print(f'  Venue: {meta.get("venue_text")}')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
