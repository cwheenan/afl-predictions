"""Check for cached 1995 matches, parse missing ones, then run eval 1990-1994 -> 1995.

Usage: python scripts/run_1990_1994_1995_eval.py
"""
import subprocess
import sys
from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session, Match

engine = get_engine()
session = get_session(engine)

# Check DB for any matches in 1995
count_db = session.query(Match).filter(Match.season == 1995).count()
print('Matches in DB for 1995:', count_db)

# List cached matches and find tokens for 1995
df = load_data.list_cached_matches('data/raw/cache')
if df is None or df.empty:
    print('No cached matches found in data/raw/cache')
    sys.exit(1)

# find rows where URL or token contains 1995 or html_path contains /1995/
candidates = df[df['url'].astype(str).str.contains('/1995/') | df['token'].astype(str).str.contains('1995')]
print('Cached tokens potentially for 1995:', len(candidates))
if len(candidates) == 0:
    print('No cached 1995 tokens found. Cannot run 1990-1994->1995 eval without cached pages.')
    sys.exit(2)

# Find which tokens are missing from Matches table
cached_tokens = candidates['token'].tolist()
existing = session.query(Match.token).filter(Match.token.in_(cached_tokens)).all()
existing_tokens = set([r[0] for r in existing])
missing = [t for t in cached_tokens if t not in existing_tokens]
print('Tokens missing from DB (need parsing):', len(missing))

# Parse missing tokens using scripts/parse_matches.py
failed = []
for t in missing:
    print('Parsing token:', t)
    res = subprocess.run(['python', 'scripts/parse_matches.py', '--tokens', t, '--cache-dir', 'data/raw/cache'], check=False)
    if res.returncode != 0:
        print('Parser returned non-zero for', t)
        failed.append(t)

print('Parsing done. failed count:', len(failed))

# Re-check DB for 1995 matches
count_db_after = session.query(Match).filter(Match.season == 1995).count()
print('Matches in DB for 1995 after parse:', count_db_after)
if count_db_after == 0:
    print('No 1995 matches in DB after parsing. Aborting eval.')
    sys.exit(3)

# Run evaluation
print('Running evaluation: train 1990-1994 -> test 1995')
res = subprocess.run(['python', 'scripts/eval_time_split.py', '--train-years', '1990-1994', '--test-year', '1995', '--models-dir', 'models'], check=False)
print('Eval exit code:', res.returncode)
sys.exit(res.returncode)
