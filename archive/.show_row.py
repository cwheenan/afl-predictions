import sqlite3, json
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
rowid=31
cur.execute('SELECT id, team, stats_json, goals, behinds, kicks, handballs, disposals, marks, tackles, hitouts FROM player_stats WHERE id=?', (rowid,))
r=cur.fetchone()
print('id', r[0], 'team', r[1])
print('goals', r[3], 'kicks', r[5], 'disposals', r[7])
print('stats_json keys sample:')
sj=json.loads(r[2]) if r[2] else {}
for k in list(sj.keys())[:12]:
    print(' -', k, '=>', sj[k])
conn.close()
