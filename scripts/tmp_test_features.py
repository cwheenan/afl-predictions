from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match

engine = get_engine()
session = get_session(engine)

m = session.query(Match).filter(Match.home_score != None, Match.away_score != None).first()
if not m:
    print('no matches with scores')
else:
    print('match.match_id:', m.match_id)
    try:
        fv = features_for_match(session, m.match_id)
        print('features len', len(fv))
        for k, v in list(fv.items())[:20]:
            print(k, v)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('error calling features_for_match:', e)
