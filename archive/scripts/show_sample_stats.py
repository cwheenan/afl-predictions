import sqlite3
con = sqlite3.connect('data/processed/afl.db')
cur = con.cursor()
cur.execute('''
SELECT ps.id, p.name, m.token, ps.goals, ps.kicks, ps.disposals, ps.marks, ps.tackles
FROM player_stats ps
JOIN players p ON ps.player_id = p.player_id
JOIN matches m ON ps.match_id = m.match_id
LIMIT 10
''')
for row in cur.fetchall():
    print(row)
con.close()
