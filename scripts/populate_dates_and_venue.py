import sqlite3, re
from afl_predictions.data import parse_match
from dateutil import parser as dateparser
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
cache_dir='data/raw/cache'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute("SELECT match_id, token, date, venue FROM matches WHERE token LIKE '%2022%'")
rows=cur.fetchall()
for mid, token, date, venue in rows:
    meta, players = parse_match.parse_match_from_cache(cache_dir, token)
    updated = False
    # try date_text
    dt_text = meta.get('date_text') or None
    if not dt_text and meta.get('title'):
        # attempt to extract date portion like 'Sat, 25-Jun-2022 4:35 PM' from title
        m = re.search(r"-\s*[^-]+-\s*(?:[A-Za-z]{3},\s*)?(\d{1,2}[- ]\w+[- ]20\d{2}.*?)\s*-", meta.get('title'))
        if m:
            dt_text = m.group(1)
    if dt_text and not date:
        # try parse
        try:
            dt = dateparser.parse(dt_text, fuzzy=True)
            iso = dt.isoformat()
            cur.execute('UPDATE matches SET date=?, date_iso=? WHERE match_id=?', (dt_text, iso, mid))
            updated = True
        except Exception:
            # store raw text if parse fails
            cur.execute('UPDATE matches SET date=? WHERE match_id=?', (dt_text, mid))
            updated = True
    # venue
    vtxt = meta.get('venue_text')
    if not venue and vtxt:
        # extract venue name from vtxt (look for 'at <Venue>')
        m2 = re.search(r"at\s+([A-Za-z0-9 '\-]+(?:Oval|Ground)?)", vtxt, re.IGNORECASE)
        if m2:
            cur.execute('UPDATE matches SET venue=? WHERE match_id=?', (m2.group(1).strip(), mid))
            updated = True
    if updated:
        print('updated', mid, token)
conn.commit()
conn.close()
