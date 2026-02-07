import sqlite3
import re
from pathlib import Path

DB = r'c:\\dev\\afl\\data\\processed\\afl.db'
cache_dir = 'data/raw/cache'

# get cache index to map token -> html_path from the cache sqlite index directly
cache_index = 'data/raw/cache/index.db'
idx_conn = None
idx_map = {}
if Path(cache_index).exists():
    try:
        idx_conn = sqlite3.connect(cache_index)
        icur = idx_conn.cursor()
        icur.execute("SELECT token, html_path FROM cached_matches")
        for t, h in icur.fetchall():
            idx_map[t] = h
    except Exception:
        idx_map = {}
    finally:
        if idx_conn:
            idx_conn.close()

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT match_id, token FROM matches WHERE token LIKE '%2022%'")
matches = cur.fetchall()
for mid, token in matches:
    # find html path from cache index map
    html_path = idx_map.get(token)
    if not html_path:
        print('no html for', token)
        continue
    try:
        html = Path(html_path).read_text(encoding='utf8')
    except Exception as e:
        print('read error', html_path, e)
        continue

    names = []
    # Fallback: simple regex search for a table row where first TD contains 'umpire'
    # and capture the subsequent TD content
    m = re.search(r"<tr>\s*<td[^>]*>\s*([^<]*umpire[^<]*)</td>\s*<td[^>]*>(.*?)</td>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        td_html = m.group(2)
        # extract anchor texts if present
        anchors = re.findall(r"<a[^>]*>([^<]+)</a>", td_html)
        if anchors:
            for a in anchors:
                names.append(a.strip())
        else:
            # remove tags and split by comma
            txt = re.sub(r'<[^>]+>', ' ', td_html)
            parts = [p.strip() for p in re.split(r',| and | & ', txt) if p.strip()]
            for p in parts:
                p = re.sub(r"\s*\(\d+\)\s*$", '', p).strip()
                if p:
                    names.append(p)

    if not names:
        print('no umpires found for', token)
        continue

    print('match', mid, 'umpires:', names)
    # insert umpires into umpires table if missing and link
    for name in names:
        cur.execute('SELECT umpire_id FROM umpires WHERE name=?', (name,))
        row = cur.fetchone()
        if row:
            uid = row[0]
        else:
            cur.execute('INSERT INTO umpires (name) VALUES (?)', (name,))
            uid = cur.lastrowid
        # insert match_umpires if missing
        cur.execute('SELECT id FROM match_umpires WHERE match_id=? AND umpire_id=?', (mid, uid))
        if not cur.fetchone():
            cur.execute('INSERT INTO match_umpires (match_id, umpire_id) VALUES (?,?)', (mid, uid))

conn.commit()
conn.close()
