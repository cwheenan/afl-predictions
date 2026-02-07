"""Find matches in processed DB with missing season and re-run parser/upsert on their tokens.
Writes tokens to data/raw/cache/manifest_missing_season_tokens.csv and invokes parse_matches.py indirectly.
"""
from afl_predictions.db import get_engine, get_session, Match
from pathlib import Path
import pandas as pd

engine = get_engine()
session = get_session(engine)

rows = session.query(Match).filter(Match.season == None).all()
print(f'Found {len(rows)} matches with season=NULL')
tokens = [r.token for r in rows if r.token]
Path('data/raw/cache').mkdir(parents=True, exist_ok=True)
pd.DataFrame({'token': tokens}).to_csv('data/raw/cache/manifest_missing_season_tokens.csv', index=False)
print(f'wrote {len(tokens)} tokens to data/raw/cache/manifest_missing_season_tokens.csv')
session.close()
