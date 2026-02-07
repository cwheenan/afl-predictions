import sqlite3, json
con = sqlite3.connect('data/processed/afl.db')
cur = con.cursor()
cur.execute("SELECT id, stats_json FROM player_stats LIMIT 10")
for r in cur.fetchall():
    print('ID', r[0])
    try:
        obj = json.loads(r[1])
        for k,v in list(obj.items())[:20]:
            print('  ',k,':',v)
    except Exception as e:
        print('  err', e)
con.close()
