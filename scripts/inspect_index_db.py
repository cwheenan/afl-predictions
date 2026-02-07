import sqlite3
p='data/raw/cache/index.db'
conn=sqlite3.connect(p)
cur=conn.cursor()
rows=cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('tables:', rows)
for t in [r[0] for r in rows]:
    try:
        print('\n==',t,'==')
        for r in cur.execute(f"PRAGMA table_info('{t}')").fetchall():
            print(r)
        print('sample rows:')
        for r in cur.execute(f"SELECT * FROM {t} LIMIT 5").fetchall():
            print(r)
    except Exception as e:
        print('error', e)
conn.close()
