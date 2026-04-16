"""Quick script to check 2026 matches."""
from afl_predictions.db import get_engine, get_session, Match
import re

engine = get_engine()
session = get_session(engine)

matches = [m for m in session.query(Match).all() if m.date and re.search(r'2026', m.date)]
print(f'Found {len(matches)} matches in 2026')

matches_sorted = sorted(matches, key=lambda m: m.date if m.date else '')
for m in matches_sorted[:20]:
    home_score = m.home_score if m.home_score is not None else 'TBD'
    away_score = m.away_score if m.away_score is not None else 'TBD'
    print(f'{m.date}: {m.home_team} {home_score} vs {away_score} {m.away_team}')
