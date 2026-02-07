import json
from afl_predictions.db import get_engine, get_session, Match, PlayerStats

s = get_session(get_engine())
rows = s.query(Match).filter(Match.season==1995).all()
print('Found', len(rows), '1995 matches')
updated = 0
for m in rows:
    if m.home_score is not None and m.away_score is not None:
        continue
    ps_rows = s.query(PlayerStats).filter(PlayerStats.match_id==m.match_id).order_by(PlayerStats.id).all()
    if not ps_rows:
        continue
    mid = len(ps_rows) // 2
    home_goals = home_behinds = away_goals = away_behinds = 0
    for i, ps in enumerate(ps_rows):
        # determine team
        team = ps.team
        if not team:
            team = m.home_team if i < mid else m.away_team
        # get goals
        goals = ps.goals
        behinds = ps.behinds
        if goals is None or behinds is None:
            # try parse stats_json
            try:
                sj = json.loads(ps.stats_json) if ps.stats_json else {}
            except Exception:
                sj = {}
            if goals is None:
                # find first key that looks like goals
                for k, v in sj.items():
                    kn = str(k).lower()
                    if 'goal' in kn or kn.strip() in ('gl', 'g'):
                        try:
                            g = v
                            if isinstance(g, str):
                                g = g.replace(',', '').strip()
                                if g == '' or g.lower() == 'nan':
                                    continue
                            g = int(float(g))
                            goals = g
                            break
                        except Exception:
                            continue
            if behinds is None:
                for k, v in sj.items():
                    kn = str(k).lower()
                    if 'behind' in kn or kn.strip() in ('bh', 'b'):
                        try:
                            b = v
                            if isinstance(b, str):
                                b = b.replace(',', '').strip()
                                if b == '' or b.lower() == 'nan':
                                    continue
                            b = int(float(b))
                            behinds = b
                            break
                        except Exception:
                            continue
        # default 0
        goals = int(goals) if goals is not None else 0
        behinds = int(behinds) if behinds is not None else 0
        if team == m.home_team:
            home_goals += goals
            home_behinds += behinds
        else:
            away_goals += goals
            away_behinds += behinds
    # if we found any non-zero totals, update match
    if (home_goals + home_behinds + away_goals + away_behinds) > 0:
        try:
            # compute final scores as goals*6 + behinds
            m.home_score = home_goals * 6 + home_behinds
            m.away_score = away_goals * 6 + away_behinds
            s.add(m)
            s.commit()
            updated += 1
            print('Updated match', m.token, 'scores ->', m.home_score, m.away_score)
        except Exception as e:
            s.rollback()
            print('Failed to update match', m.token, 'error', e)

print('Done. updated count=', updated)
