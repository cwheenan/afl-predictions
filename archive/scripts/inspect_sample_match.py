from afl_predictions.db import get_engine, get_session, Match

s = get_session(get_engine())
m = s.query(Match).filter(Match.season==2000).first()

print('Sample Match from 2000:')
print(f'Token: {m.token}')
print(f'Season: {m.season}')
print(f'Round: {m.round}')
print(f'Teams: {m.home_team} vs {m.away_team}')
print(f'Scores: {m.home_score} - {m.away_score}')
print(f'Date: {m.date}')
print(f'Venue: {m.venue}')

print('\nAll attributes:')
attrs = [a for a in dir(m) if not a.startswith('_') and not callable(getattr(m, a))]
for attr in attrs:
    val = getattr(m, attr)
    if val is not None and val != '':
        print(f'  {attr}: {val}')
