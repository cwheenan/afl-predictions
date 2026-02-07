import sqlite3
import json
from pprint import pprint

DB = r'c:\dev\afl\data\processed\afl.db'
CAN = ['goals','behinds','kicks','handballs','disposals','marks','tackles','hitouts','frees_for','frees_against']

conn = sqlite3.connect(DB)
cur = conn.cursor()
cols_check = ' AND '.join([f"{c} IS NULL" for c in CAN])
sql = f"SELECT id, match_id, team, stats_json FROM player_stats WHERE {cols_check} ORDER BY match_id, id"
cur.execute(sql)
rows = cur.fetchall()
print(f'Found {len(rows)} player_stats rows with all canonical columns NULL')

for i, (pid, mid, team, sj) in enumerate(rows[:50], 1):
    try:
        stats = json.loads(sj) if sj else {}
    except Exception:
        stats = {}
    # show only first 6 keys for brevity
    sample = {k: stats[k] for k in list(stats.keys())[:6]}
    print(f"\n{i}. id={pid} match_id={mid} team={team}")
    pprint(sample)

conn.close()
