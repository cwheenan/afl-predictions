import sys
from pathlib import Path
import pytest
import pandas as pd

# Ensure the local `src` package is on sys.path for tests run from workspace root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from afl_predictions.data import load_data


def test_fetch_match_tables_smoke():
    # smoke test for function existence; doesn't call network
    assert hasattr(load_data, 'fetch_match_tables')


def test_load_local_dataset_concatenates_csvs(tmp_path):
    # create two small CSVs
    df1 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df2 = pd.DataFrame({"a": [3], "b": ["z"]})

    p1 = tmp_path / "part1.csv"
    p2 = tmp_path / "part2.csv"
    df1.to_csv(p1, index=False)
    df2.to_csv(p2, index=False)

    # load by directory
    out = load_data.load_local_dataset(str(tmp_path))
    assert isinstance(out, pd.DataFrame)
    # should have 3 rows total and columns a,b
    assert out.shape[0] == 3
    assert list(out.columns) == ["a", "b"]

    # load by explicit list
    out2 = load_data.load_local_dataset([str(p1), str(p2)])
    assert out2.shape[0] == 3
