import sqlite3, json
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
# totals
matches_count = cur.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
players_count = cur.execute('SELECT COUNT(*) FROM players').fetchone()[0]
ps_count = cur.execute('SELECT COUNT(*) FROM player_stats').fetchone()[0]
print('matches:', matches_count)
print('players:', players_count)
print('player_stats:', ps_count)
# duplicates (match_id,player_id)
dups = cur.execute('SELECT match_id, player_id, COUNT(*) as c FROM player_stats GROUP BY match_id, player_id HAVING c>1').fetchall()
print('duplicate (match_id,player_id) groups:', len(dups))
if dups:
    print('Sample duplicates (first 10):')
    for r in dups[:10]:
        print(r)
# matches where canonical columns (goals,kicks,disposals) are NULL for many rows
rows = cur.execute('''
SELECT m.match_id, m.token, COUNT(*) as total_rows,
 SUM(CASE WHEN team IS NULL THEN 1 ELSE 0 END) as team_nulls,
 SUM(CASE WHEN goals IS NULL AND kicks IS NULL AND disposals IS NULL THEN 1 ELSE 0 END) as all_nulls
FROM player_stats ps JOIN matches m ON ps.match_id = m.match_id
GROUP BY m.match_id ORDER BY all_nulls DESC LIMIT 20
''').fetchall()
print('\nTop matches by rows with canonical columns all NULL:')
for r in rows[:10]:
    print(r)
# sample a few player_stats rows where canonical columns are all NULL but stats_json exists
cur.execute("SELECT id, match_id, stats_json FROM player_stats WHERE (goals IS NULL AND kicks IS NULL AND disposals IS NULL) AND stats_json IS NOT NULL LIMIT 5")
for r in cur.fetchall():
    sid=r[0]
    mid=r[1]
    sj=json.loads(r[2]) if r[2] else {}
    keys=list(sj.keys())[:8]
    print('\nRow id', sid, 'match_id', mid, 'keys sample:', keys)
conn.close()
