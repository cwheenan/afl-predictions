from bs4 import BeautifulSoup
from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session, Match

cache_dir = 'data/raw/cache'
df = load_data.list_cached_matches(cache_dir)
engine = get_engine()
session = get_session(engine)
updated = 0

for _, idx in df.iterrows():
    t = idx.get('token')
    if not t:
        continue
    m = session.query(Match).filter_by(token=t).first()
    if not m:
        continue
    if m.home_score is not None and m.away_score is not None:
        continue
    html_path = idx.get('html_path')
    if not html_path:
        continue
    try:
        with open(html_path, 'r', encoding='utf8') as fh:
            html = fh.read()
    except Exception:
        continue

    soup = BeautifulSoup(html, 'html.parser')
    candidate = None
    for tbl in soup.find_all('table'):
        try:
            links = tbl.find_all('a')
            bolds = tbl.find_all('b')
            if len(links) >= 2 and len(bolds) >= 2:
                candidate = tbl
                break
        except Exception:
            continue

    if candidate is None:
        continue

    rows = candidate.find_all('tr')
    team_scores = []
    for r in rows:
        a = r.find('a')
        if not a:
            continue
        team_name = a.get_text().strip()
        btags = r.find_all('b')
        if btags:
            val = None
            for b in reversed(btags):
                txt = b.get_text().strip()
                if txt.isdigit():
                    val = int(txt)
                    break
            if val is not None:
                team_scores.append((team_name, val))

    if len(team_scores) >= 2:
        def key(s):
            return s.lower().split()[0]

        scmap = {key(n): pts for n, pts in team_scores}
        home_key = key(m.home_team) if m.home_team else None
        away_key = key(m.away_team) if m.away_team else None
        h = scmap.get(home_key)
        a = scmap.get(away_key)
        if h is None or a is None:
            h, a = team_scores[0][1], team_scores[1][1]
        try:
            m.home_score = int(h)
            m.away_score = int(a)
            session.add(m)
            session.commit()
            updated += 1
            print('updated scores', t, m.home_team, m.home_score, m.away_team, m.away_score)
        except Exception as e:
            print('failed set', t, e)

print('done', updated)
