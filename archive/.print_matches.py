import sqlite3
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute('SELECT match_id, token, season, round, round_num, date, venue, home_team, away_team, home_score, away_score FROM matches')
for r in cur.fetchall():
    print(r)
conn.close()
