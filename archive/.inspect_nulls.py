import sqlite3, json
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
for mid in [1,2,3]:
    print('\n=== match', mid)
    cur.execute("SELECT id, team, stats_json, goals, kicks, disposals FROM player_stats WHERE match_id=? AND (goals IS NULL AND kicks IS NULL AND disposals IS NULL)", (mid,))
    rows=cur.fetchall()
    print('rows with all_nulls:', len(rows))
    for r in rows[:10]:
        sid=r[0]
        team=r[1]
        sj=r[2]
        print('\n id', sid, 'team', team)
        try:
            sjd=json.loads(sj) if sj else {}
        except Exception as e:
            print('  bad json', e)
            sjd={}
        keys=list(sjd.keys())[:12]
        print('  sample keys:', keys)
        for k in keys[:8]:
            print('   ', k, '=>', sjd.get(k))
conn.close()
