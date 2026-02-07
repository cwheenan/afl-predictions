from afl_predictions.db import get_engine, get_session, Match

s = get_session(get_engine())
rows = s.query(Match).filter(Match.season==1995).limit(10).all()
print('Found', len(rows), 'sample matches')
for m in rows:
    print(m.match_id, m.token, 'home_score=', m.home_score, 'away_score=', m.away_score, 'home_team=', m.home_team, 'away_team=', m.away_team)
