import sys
from pathlib import Path
import pandas as pd

# Ensure src/ is on sys.path for test imports when running from workspace root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from afl_predictions.data.parse_match import parse_player_tables_from_dfs


def test_parse_basic_player_table():
    # create a simple player-stats-like DataFrame
    df = pd.DataFrame(
        [
            {'Jumper': 1, 'Player': 'A Player', 'GL': '2', 'KI': '12'},
            {'Jumper': 2, 'Player': 'B Player', 'GL': '0', 'KI': '8'},
        ]
    )

    meta, players = parse_player_tables_from_dfs([df], token='sampletoken')
    assert isinstance(meta, dict)
    assert meta.get('token') == 'sampletoken'
    assert isinstance(players, list)
    assert len(players) == 2
    # check first player's parsed stats
    p0 = players[0]
    assert p0['name'] == 'A Player'
    assert p0['stats']['GL'] == 2
    assert p0['stats']['KI'] == 12
