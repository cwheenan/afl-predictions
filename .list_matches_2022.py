import sqlite3
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
# show schema for matches
print('matches table schema:')
cur.execute("PRAGMA table_info(matches)")
for r in cur.fetchall():
    print(' ', r)
print('\nMatches with 2022 in token:')
cur.execute("SELECT match_id, token, season, round, date, venue FROM matches WHERE token LIKE '%2022%'")
rows=cur.fetchall()
for r in rows:
    print(r)
print('\nAll matches:')
cur.execute('SELECT match_id, token, season, round, date, venue FROM matches')
for r in cur.fetchall():
    print(r)
conn.close()
