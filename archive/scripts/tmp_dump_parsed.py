from afl_predictions.data import parse_match
meta, players = parse_match.parse_match_from_cache('data/raw/cache', '031619900331.html_4a47977e')
print('META:', meta.get('teams'))
for i,p in enumerate(players[:30]):
    print(i, p.get('name'), 'team=', p.get('team'))
