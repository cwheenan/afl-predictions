from afl_predictions.db import get_engine, get_session, Match, PlayerStats, MatchLineup
s = get_session(get_engine())
m = s.query(Match).filter(Match.season == 1990).first()
print('MATCH:', m.match_id, m.token, m.home_team, 'vs', m.away_team)
mls = s.query(MatchLineup).filter(MatchLineup.match_id == m.match_id).all()
print('MatchLineup rows:', len(mls))
for ml in mls[:20]:
    print('ML:', ml.id, ml.player_id, ml.is_named, ml.is_starting, ml.position_role, ml.expected_probability)

# show unique teams present in PlayerStats
rows = s.query(PlayerStats).filter(PlayerStats.match_id == m.match_id).all()
teams = set(r.team for r in rows)
print('PlayerStats teams unique:', teams)
