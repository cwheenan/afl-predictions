import sqlite3, json, os

db = r'c:\dev\afl\data\processed\afl.db'
if not os.path.exists(db):
    print('DB not found', db)
    raise SystemExit(1)
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute('SELECT id, team, stats_json FROM player_stats LIMIT 10')
rows = cur.fetchall()
for r in rows:
    print('ID', r[0], 'TEAM', r[1])
    try:
        sj = json.loads(r[2]) if r[2] else {}
    except Exception as e:
        print('  (failed to parse stats_json)', e)
        sj = {}
    keys = list(sj.keys())[:12]
    print('  keys sample:', keys)
    for k in keys:
        print('   ', repr(k), '->', sj[k])
    print('-' * 40)
conn.close()
