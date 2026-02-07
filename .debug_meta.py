from afl_predictions.data import parse_match, load_data
import json
cache_dir='data/raw/cache'
TOKENS=[
 '091420220625.html_b28f262d',
 '030820220625.html_59d3f058',
 '151620220625.html_c86d8434',
 '050920220319.html_fea18c80',
 '031420220317.html_f23b9c2f',
 '091620220325.html_94a64e23',
 '142120220327.html_1cbb8f6d',
]
for t in TOKENS:
    meta, players = parse_match.parse_match_from_cache(cache_dir, t)
    print('\nTOKEN', t)
    print('meta:', json.dumps(meta, indent=2))
    print('players:', len(players))
    if 'teams' in meta:
        print('teams:', meta['teams'], 'scores:', meta.get('scores'))
