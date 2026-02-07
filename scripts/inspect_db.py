import sqlite3

conn = sqlite3.connect('data/processed/afl.db')
cur = conn.cursor()
print('index_list:', cur.execute("PRAGMA index_list('player_stats')").fetchall())
print('table_info:', cur.execute("PRAGMA table_info('player_stats')").fetchall())
print('create_sql:', cur.execute("SELECT sql FROM sqlite_master WHERE tbl_name='player_stats' AND type='table'").fetchall())
conn.close()
