import json
from afl_predictions.data import parse_match

token = '011219950331.html_4ffff252'
meta, players = parse_match.parse_match_from_cache('data/raw/cache', token)
print(json.dumps({k: meta.get(k) for k in ['token','title','teams','scores','date_text','venue_text']}, indent=2))
print('players sample (first 3):', players[:3])
