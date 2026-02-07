from afl_predictions.db import get_engine, get_session, PlayerStats
s = get_session(get_engine())
ps = s.query(PlayerStats).filter(PlayerStats.match_id==332).all()
print('Found', len(ps), 'playerstats for match 332')
for p in ps[:10]:
    print(p.id, p.team, p.goals, p.behinds, (p.stats_json[:80] if p.stats_json else None))
