"""Backfill PlayerStats.team for matches where it's missing.

This script finds match tokens where at least one PlayerStats row has team==NULL
and calls the existing CLI parser on each token (idempotent). It prints progress
and a final summary.
"""
import subprocess
from afl_predictions.db import get_engine, get_session, Match, PlayerStats

s = get_session(get_engine())
# find tokens where any PlayerStats.team is NULL
rows = s.query(Match.token).join(PlayerStats, Match.match_id == PlayerStats.match_id).filter(PlayerStats.team == None).distinct().all()
tokens = [r[0] for r in rows]
print(f'Found {len(tokens)} tokens with PlayerStats.team == NULL')
if not tokens:
    print('Nothing to do')
    exit(0)

updated = 0
failed = 0
for i, t in enumerate(tokens, 1):
    print(f'[{i}/{len(tokens)}] Running parser for token: {t}')
    # call the CLI parser which will attempt idempotent updates
    try:
        res = subprocess.run(['python', 'scripts/parse_matches.py', '--tokens', t, '--cache-dir', 'data/raw/cache'], check=False)
        if res.returncode == 0:
            updated += 1
        else:
            failed += 1
    except Exception as e:
        print('Error calling parser for', t, e)
        failed += 1

print('Done. Updated attempts:', updated, 'failed:', failed)
