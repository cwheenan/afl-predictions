"""Generate a manifest CSV from the DB `pages` table.

The manifest helps inspect what has been cached and prioritized for parsing.
"""
from pathlib import Path
import json
import pandas as pd
from typing import Optional

from afl_predictions import config
from afl_predictions.db import get_engine


def make_manifest(db_url: Optional[str] = None, out_path: Optional[str] = None) -> pd.DataFrame:
    """Read the `pages` table from the database and emit a manifest CSV.

    Returns the DataFrame written.
    """
    engine = get_engine(db_url)
    sql = "SELECT token, url, page_type, fetched_at, html_path, tables_json FROM pages"
    df = pd.read_sql_query(sql, con=engine)

    if df.empty:
        # ensure processed dir exists for consistency
        outp = Path(out_path or 'data/processed/manifest.csv')
        outp.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=['token', 'url', 'page_type', 'fetched_at', 'html_path', 'tables_count']).to_csv(outp, index=False)
        return pd.DataFrame()

    # compute tables_count from tables_json
    def _count_tables(x):
        try:
            arr = json.loads(x) if x else []
            return len(arr)
        except Exception:
            return 0

    df['tables_count'] = df['tables_json'].apply(_count_tables)
    # convert fetched_at (seconds) to ISO UTC
    df['fetched_at_iso'] = pd.to_datetime(df['fetched_at'], unit='s', utc=True).dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    outp = Path(out_path or 'data/processed/manifest.csv')
    outp.parent.mkdir(parents=True, exist_ok=True)
    df_out = df[['token', 'url', 'page_type', 'fetched_at_iso', 'html_path', 'tables_count']]
    df_out.to_csv(outp, index=False)
    return df_out


if __name__ == '__main__':
    make_manifest()
