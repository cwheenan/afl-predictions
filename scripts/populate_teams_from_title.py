import sqlite3, re
from afl_predictions.data import parse_match
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
cache_dir='data/raw/cache'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute("SELECT match_id, token, home_team, away_team FROM matches WHERE token LIKE '%2022%'")
rows=cur.fetchall()
for mid, token, home, away in rows:
    if home and away:
        print('skip', mid, token)
        continue
    meta, players = parse_match.parse_match_from_cache(cache_dir, token)
    title = meta.get('title')
    if not title:
        print('no title for', token)
        continue
    m = re.search(r"-\s*([^\-]+?)\s+v\s+([^\-]+?)\s+-", title)
    if not m:
        print('no teams in title for', token, title)
        continue
    h = m.group(1).strip()
    a = m.group(2).strip()
    print('update', mid, token, '=>', h, 'v', a)
    cur.execute('UPDATE matches SET home_team=?, away_team=? WHERE match_id=?', (h, a, mid))
conn.commit()
conn.close()
