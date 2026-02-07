from afl_predictions.db import get_engine, get_session, Match, PlayerStats

s = get_session(get_engine())
m = s.query(Match).filter(Match.season == 1990).first()
print('MATCH:', m.match_id, m.token, m.home_team, 'vs', m.away_team)
rows = s.query(PlayerStats).filter(PlayerStats.match_id == m.match_id).limit(12).all()
for r in rows:
    sj = r.stats_json
    sj_short = (sj[:200] + '...') if sj and len(sj) > 200 else sj
    print('PS:', r.id, r.player_id, r.team, 'goals=', r.goals, 'behinds=', r.behinds, 'kicks=', r.kicks, 'disposals=', r.disposals, 'percent_played=', r.percent_played, 'named=', r.named, 'stats_json=', sj_short)
