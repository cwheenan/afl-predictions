from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match

s = get_session(get_engine())
rows = s.query(Match).filter(Match.season==1995).limit(10).all()
print('Found', len(rows), 'matches for 1995 (showing up to 10)')
for m in rows:
    try:
        fv = features_for_match(s, m.match_id)
        print('match_id', m.match_id, 'token', m.token, '-> features:', None if not fv else list(fv.items())[:6])
    except Exception as e:
        print('match_id', m.match_id, 'token', m.token, '-> ERROR', e)
