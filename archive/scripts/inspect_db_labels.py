"""Inspect processed DB: count matches per season and labeled matches (have scores).
Prints counts per season and lists sample tokens missing scores.
"""
from afl_predictions.db import get_engine, get_session, Match
from sqlalchemy import func, case, or_

engine = get_engine()
session = get_session(engine)

# counts per season
rows = session.query(
    Match.season,
    func.count(Match.match_id).label('total'),
    func.sum(case(((Match.home_score != None) & (Match.away_score != None), 1), else_=0)).label('labeled')
).group_by(Match.season).order_by(Match.season).all()

print('season,total,labeled')
for r in rows:
    print(f'{r.season},{r.total},{r.labeled}')

# total missing score count and sample tokens
missing_q = session.query(Match).filter(or_(Match.home_score == None, Match.away_score == None))
missing_count = missing_q.count()
print(f'\nMatches with missing scores: {missing_count}')
print('\nSample tokens missing scores (up to 20):')
for m in missing_q.limit(20).all():
    print(m.token)

session.close()
