from afl_predictions.data import load_data, parse_match
from afl_predictions.db import get_engine, get_session, Match
import re

cache_dir = 'data/raw/cache'
df = load_data.list_cached_matches(cache_dir)
df2015 = df[df['url'].str.contains('/2015/')]
tokens = df2015['token'].tolist()
engine = get_engine()
session = get_session(engine)
updated = 0
for t in tokens:
    m = session.query(Match).filter_by(token=t).first()
    if not m:
        continue
    if m.home_team and m.away_team:
        continue
    meta, _ = parse_match.parse_match_from_cache(cache_dir, t)
    title = meta.get('title') or ''
    mm = re.search(r"-\s*([^-]+?)\s+v\s+([^-]+?)\s+-", title)
    if mm:
        m.home_team = m.home_team or mm.group(1).strip()
        m.away_team = m.away_team or mm.group(2).strip()
        session.add(m)
        session.commit()
        updated += 1
        print('updated', t, m.home_team, m.away_team)
print('done', updated)
