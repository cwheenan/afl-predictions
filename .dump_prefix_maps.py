import sqlite3, json, re
DB=r'c:\\dev\\afl\\data\\processed\\afl.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
mid=1
cur.execute('SELECT stats_json FROM player_stats WHERE match_id=? ORDER BY id', (mid,))
rows=cur.fetchall()
rows_stats=[]
for r in rows:
    try:
        sj=json.loads(r[0]) if r[0] else {}
    except Exception:
        sj={}
    rows_stats.append(sj)
# find prefixes
prefixes=set()
for sj in rows_stats:
    for k in sj.keys():
        if not isinstance(k, str):
            continue
        if 'Match Statistics' in k:
            p = k.split('Match Statistics')[0].strip()
            p = re.sub(r"\[.*$", "", p).strip()
            p = re.sub(r"[\.|\-]+$", "", p).strip()
            if p:
                prefixes.add(p)
print('prefixes:', prefixes)
# build candidate per prefix
for p in prefixes:
    scoped_rows=[]
    for sj in rows_stats:
        small={k:v for k,v in sj.items() if isinstance(k,str) and k.startswith(p)}
        if small:
            scoped_rows.append(small)
    print('\nprefix', p, 'scoped_rows', len(scoped_rows))
    # pick candidate
    candidate=None
    best_score=-1
    for sj in scoped_rows:
        values=list(sj.values())
        non_num=0; short_str=0; abb_hits=0
        for v in values:
            if isinstance(v,str):
                vs=v.strip()
                if len(vs)<=8: short_str+=1
                if re.match(r'^[A-Za-z%\\u2191\\u2193]+$', vs) and len(vs)<=4: abb_hits+=1
                non_num+=1
            else:
                try:
                    float(v)
                except Exception:
                    non_num+=1
        score=abb_hits*10+short_str*3+non_num
        if score>best_score:
            best_score=score; candidate=sj
    print(' best_score', best_score)
    if not candidate:
        continue
    for k,v in candidate.items():
        print('  ', k, '=>', v)
conn.close()
