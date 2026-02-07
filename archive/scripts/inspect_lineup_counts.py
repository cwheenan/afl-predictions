import sqlite3
DB='data/processed/afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute('SELECT COUNT(*) FROM player_stats')
total=cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM player_stats WHERE percent_played IS NOT NULL')
with_pct=cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM player_stats WHERE named IS NOT NULL')
with_named=cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM player_stats WHERE sub_on=1')
son=cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM player_stats WHERE sub_off=1')
s_off=cur.fetchone()[0]
print('player_stats total:', total)
print('with percent_played:', with_pct)
print('with named:', with_named)
print('with sub_on:', son)
print('with sub_off:', s_off)
conn.close()
