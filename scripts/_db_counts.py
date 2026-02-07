from afl_predictions.db import get_engine, get_session, Match, Player, PlayerStats

eng = get_engine()
s = get_session(eng)
print('matches:', s.query(Match).count())
print('players:', s.query(Player).count())
print('player_stats:', s.query(PlayerStats).count())
