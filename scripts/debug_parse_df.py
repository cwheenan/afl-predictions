import pandas as pd
from afl_predictions.data.parse_match import parse_player_tables_from_dfs, _detect_name_column
from afl_predictions.data import abbreviations

df = pd.DataFrame([
    {'Jumper': 1, 'Player': 'A Player', 'GL': '2', 'KI': '12'},
    {'Jumper': 2, 'Player': 'B Player', 'GL': '0', 'KI': '8'},
])

print('orig cols:', list(df.columns))
try:
    norm = abbreviations.expand_df_columns(df.copy())
    print('norm cols:', list(norm.columns))
except Exception as e:
    print('expand cols failed', e)

print('detect name col:', _detect_name_column(norm))

meta, players = parse_player_tables_from_dfs([df], token='sampletoken')
print('meta', meta)
print('players', players)
