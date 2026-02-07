import sqlite3
DB = r'c:\dev\afl\data\processed\afl.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('SELECT id, match_id, team, goals, behinds, kicks, marks, disposals, tackles FROM player_stats ORDER BY id LIMIT 10')
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
