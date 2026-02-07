from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match
import pandas as pd

s = get_session(get_engine())
rows = s.query(Match).filter(Match.home_score != None, Match.away_score != None).all()
print('Total matches with scores:', len(rows))
data = []
for m in rows:
    try:
        fv = features_for_match(s, m.match_id)
    except Exception:
        continue
    if not fv:
        continue
    row = dict(fv)
    row['match_id'] = m.match_id
    row['token'] = m.token
    row['season'] = int(m.season) if m.season is not None else None
    row['label'] = 1 if (m.home_score is not None and m.away_score is not None and m.home_score > m.away_score) else 0
    data.append(row)

if not data:
    print('No data')
else:
    df = pd.DataFrame(data)
    df = df.dropna(subset=['season'])
    df['season'] = df['season'].astype(int)
    print('Seasons present and counts:')
    print(df['season'].value_counts().sort_index())
    print('Columns:', list(df.columns)[:20])
