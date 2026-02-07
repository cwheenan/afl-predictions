"""Inspect processed DB: count matches and labeled matches per season and show sample missing-score tokens."""
from afl_predictions.db import get_engine, get_session, Match
from sqlalchemy import func, or_

engine = get_engine()
session = get_session(engine)

total = session.query(func.count(Match.match_id)).scalar()
labeled = session.query(func.count(Match.match_id)).filter(Match.home_score != None, Match.away_score != None).scalar()
print(f"Total matches in DB: {total}")
print(f"Matches with both scores (labeled): {labeled}")

seasons = session.query(Match.season).distinct().order_by(Match.season).all()
print('\nSeason | total | labeled')
for s in seasons:
    season = s[0]
    if season is None:
        continue
    total_s = session.query(func.count(Match.match_id)).filter(Match.season == season).scalar()
    labeled_s = session.query(func.count(Match.match_id)).filter(Match.season == season, Match.home_score != None, Match.away_score != None).scalar()
    print(f"{season} | {total_s} | {labeled_s}")

print('\nSample tokens missing scores (up to 20):')
missing = session.query(Match.token).filter(or_(Match.home_score == None, Match.away_score == None)).limit(20).all()
for m in missing:
    print('-', m[0])

# show some example of matches with scores for quick sanity
print('\nSample labeled match tokens (up to 10):')
labeled_tokens = session.query(Match.token).filter(Match.home_score != None, Match.away_score != None).limit(10).all()
for t in labeled_tokens:
    print('-', t[0])

session.close()
