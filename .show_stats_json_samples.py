import sqlite3, json, textwrap
DB = r'c:\\dev\\afl\\data\\processed\\afl.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
# matches of interest (from previous check)
match_ids = [1,2,3]
for mid in match_ids:
    cur.execute('SELECT token FROM matches WHERE match_id=?', (mid,))
    tok = cur.fetchone()
    tok = tok[0] if tok else '<no token>'
    print('\n' + '='*60)
    print(f'Match {mid} token: {tok}')
    cur.execute('SELECT id, stats_json FROM player_stats WHERE match_id=? LIMIT 5', (mid,))
    rows = cur.fetchall()
    if not rows:
        print('  (no player_stats rows)')
        continue
    for r in rows:
        pid = r[0]
        sj_raw = r[1]
        print('\n-- player_stats id:', pid)
        if not sj_raw:
            print('  (no stats_json)')
            continue
        try:
            sj = json.loads(sj_raw)
        except Exception as e:
            print('  (failed to parse stats_json)', e)
            print(textwrap.shorten(sj_raw, width=500))
            continue
        keys = list(sj.keys())
        print('  keys count:', len(keys))
        print('  sample keys:')
        for k in keys[:8]:
            print('   -', k)
        # print first few key->value pairs
        print('\n  sample pairs:')
        for k in keys[:8]:
            v = sj.get(k)
            print('   ', k, '=>', repr(v)[:120])
conn.close()
print('\nDone')
