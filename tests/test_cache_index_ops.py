import sys
from pathlib import Path
import json
import tempfile
import pytest
import pandas as pd

# Ensure the local `src` package is on sys.path for tests run from workspace root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from afl_predictions.data import load_data


def test_index_add_and_lookup(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # create a fake meta entry
    meta = {
        'token': 'testtoken',
        'url': 'https://afltables.com/afl/stats/games/2025/091920250905.html',
        'fetched_at': 1700000000,
        'html_path': str(cache_dir / 'html' / 'testtoken.html'),
        'tables': [str(cache_dir / 'tables' / 'testtoken_tbl0.csv')],
    }

    # index should be created and entry added without error
    load_data.add_cache_entry(cache_dir, meta)

    # list_cached_matches should return a DataFrame with one row
    df = load_data.list_cached_matches(cache_dir)
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 1
    assert df.iloc[0]['token'] == 'testtoken'

    # is_url_cached should be True for this URL
    assert load_data.is_url_cached(cache_dir, meta['url']) is True

    # get_cache_entry_by_url should return the stored metadata
    entry = load_data.get_cache_entry_by_url(cache_dir, meta['url'])
    assert entry is not None
    assert entry['token'] == 'testtoken'
    assert entry['url'] == meta['url']
