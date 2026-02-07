import sqlite3
from pathlib import Path

DB = Path('data/processed/afl.db')
if not DB.exists():
    print('Database not found at', DB)
    raise SystemExit(1)

con = sqlite3.connect(str(DB))
cur = con.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
rows = cur.fetchall()
for name, sql in rows:
    print('\nTABLE:', name)
    print(sql)
    try:
        cur.execute(f"PRAGMA table_info('{name}')")
        cols = cur.fetchall()
        print('\nColumns:')
        for c in cols:
            # cid, name, type, notnull, dflt_value, pk
            print(f"  - {c[1]} ({c[2]}) notnull={c[3]} pk={c[5]} default={c[4]}")
    except Exception as e:
        print('  (could not read columns)', e)

# indexes
print('\nIndexes:')
cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name")
for name, tbl, sql in cur.fetchall():
    print(f" - {name} ON {tbl}: {sql}")

con.close()
