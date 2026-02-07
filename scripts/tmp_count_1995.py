from afl_predictions.db import get_engine, get_session, Match
s = get_session(get_engine())
print('Matches in DB season 1995:', s.query(Match).filter(Match.season==1995).count())
