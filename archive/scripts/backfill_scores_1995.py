from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.data import parse_match

engine = get_engine()
s = get_session(engine)
rows = s.query(Match).filter(Match.season==1995).all()
print('Found', len(rows), '1995 matches to inspect')
updated = 0
for m in rows:
    try:
        meta, players = parse_match.parse_match_from_cache('data/raw/cache', m.token)
        scores = meta.get('scores') or meta.get('score')
        if not scores:
            # try to parse final score from title
            title = meta.get('title') or ''
            import re
            mm = re.search(r"(\d+\.\d+\s*\(\d+\))\s*to\s*(\d+\.\d+\s*\(\d+\))", title)
            if mm:
                # leave for now
                scores = None
        if scores and len(scores) >= 2:
            try:
                hs = int(scores[0])
                as_ = int(scores[1])
            except Exception:
                # sometimes scores are like '12.10 (82)'
                try:
                    import re
                    def extract_total(s):
                        mmm = re.search(r"\((\d+)\)", str(s))
                        if mmm:
                            return int(mmm.group(1))
                        return int(str(s).split()[0])
                    hs = extract_total(scores[0])
                    as_ = extract_total(scores[1])
                except Exception:
                    hs = None
                    as_ = None
            if hs is not None and as_ is not None and (m.home_score != hs or m.away_score != as_):
                m.home_score = hs
                m.away_score = as_
                s.add(m)
                s.commit()
                updated += 1
                print('Updated scores for', m.token, '->', hs, as_)
    except Exception as e:
        s.rollback()
        print('Failed to parse meta for', m.token, 'error', e)

print('Done. updated_count=', updated)
