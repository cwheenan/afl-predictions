"""Data ingestion utilities for AFL predictions.

This module contains small helper functions to fetch and parse AFLTables match pages
and to assemble local CSVs into a season-level DataFrame.

Note: these are starter implementations and should be extended with caching,
retries, and robust parsing for production use.
"""

from typing import List, Union
import hashlib
import json
import time
import sqlite3
import requests
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import random
import csv

from afl_predictions import config


def fetch_match_tables(url: str, timeout: int = 10) -> List[pd.DataFrame]:
    """Fetch an AFLTables match page and return tables parsed by pandas.read_html.

    Returns a list of DataFrames parsed from the page.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    return tables


def load_csvs_to_df(paths: List[str]) -> pd.DataFrame:
    """Load multiple season CSVs and concatenate into a single DataFrame.

    Placeholder: expects CSVs to have compatible schema (one row per match).
    """
    dfs = [pd.read_csv(p) for p in paths]
    return pd.concat(dfs, ignore_index=True)


def load_local_dataset(path: Union[str, Path, List[str]]) -> pd.DataFrame:
    """Load CSV files from a directory, a single CSV path, or a list of CSV paths.

    - If `path` is a directory path (str or Path), all `*.csv` files in that directory
      will be read in lexicographic order and concatenated.
    - If `path` is a single CSV file path, it will be read and returned as a DataFrame.
    - If `path` is a list of file paths, those will be read and concatenated.

    Raises FileNotFoundError if no CSVs are found.
    """
    # Normalize input to list of paths
    if isinstance(path, (list, tuple)):
        paths = [str(p) for p in path]
    else:
        p = Path(path)
        if p.is_dir():
            paths = sorted([str(x) for x in p.glob("*.csv")])
        elif p.is_file():
            paths = [str(p)]
        else:
            raise FileNotFoundError(f"Path does not exist: {path}")

    if not paths:
        raise FileNotFoundError(f"No CSV files found at: {path}")

    return load_csvs_to_df(paths)


def _safe_filename_from_url(url: str) -> str:
    """Create a short filename token from URL using last path segment + hash."""
    parsed = urlparse(url)
    name = Path(parsed.path).name or parsed.netloc
    # keep only safe chars
    token = hashlib.md5(url.encode("utf8")).hexdigest()[:8]
    return f"{name}_{token}"


def _robots_allows(url: str, user_agent: str = None) -> bool:
    """Check robots.txt for the site; if it cannot be fetched, return True (fail-open).

    We do this to be considerate of the remote site. If robots.txt denies access,
    the caller should respect that decision and skip fetching.
    """
    # honour global config flag to optionally ignore robots.txt
    if not config.RESPECT_ROBOTS:
        return True

    parsed = urlparse(url)
    netloc = parsed.netloc
    robots_url = urljoin(f"{parsed.scheme}://{netloc}", '/robots.txt')
    ua = user_agent or config.DEFAULT_USER_AGENT
    # cache RobotFileParser per host to avoid repeated network calls
    if not hasattr(_robots_allows, '_rp_cache'):
        _robots_allows._rp_cache = {}
    rp_cache = _robots_allows._rp_cache
    try:
        if netloc not in rp_cache:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            rp_cache[netloc] = rp
        else:
            rp = rp_cache[netloc]
        return rp.can_fetch(ua, url)
    except Exception:
        # If robots.txt can't be read, be conservative but don't block — caller may
        # still want to proceed. We'll allow and rely on rate limiting.
        return True


def fetch_and_cache_match(url: str, cache_dir: Union[str, Path], *,
                          user_agent: str = None,
                          timeout: int = None,
                          sleep_sec: float = None,
                          force: bool = False) -> List[pd.DataFrame]:
    """Fetch an AFLTables match page politely and cache raw HTML + parsed tables.

    Behavior and storage layout (under `cache_dir`):
      cache_dir/
        html/
          <token>.html           # raw HTML
        tables/
          <token>_tbl0.csv       # parsed tables as CSVs
        metadata/
          <token>.json           # metadata (url, fetched_at)

    - `force=True` will refetch even if cached files exist.
    - The function sleeps `sleep_sec` after a successful request to avoid hammering.
    - If robots.txt disallows the URL, raises PermissionError.
    """
    cdir = Path(cache_dir)
    html_dir = cdir / 'html'
    tables_dir = cdir / 'tables'
    meta_dir = cdir / 'metadata'
    html_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    if not _robots_allows(url, user_agent=user_agent):
        raise PermissionError(f"robots.txt disallows fetching {url}")

    token = _safe_filename_from_url(url)
    html_path = html_dir / f"{token}.html"
    meta_path = meta_dir / f"{token}.json"

    # If cached and not forced, try to load cached CSV tables
    existing_tables = sorted(tables_dir.glob(f"{token}_tbl*.csv"))
    if existing_tables and not force:
        return [pd.read_csv(p) for p in existing_tables]

    ua = user_agent or config.DEFAULT_USER_AGENT
    to = timeout or config.DEFAULT_HTTP_TIMEOUT
    headers = {"User-Agent": ua}
    resp = requests.get(url, timeout=to, headers=headers)
    resp.raise_for_status()

    # save raw HTML
    html_path.write_text(resp.text, encoding='utf8')

    # parse tables using pandas (some pages may have zero tables)
    try:
        tables = pd.read_html(resp.text)
    except ValueError:
        # no tables found on the page — that's OK for some non-match pages
        tables = []

    # persist each table to CSV
    for i, tbl in enumerate(tables):
        out_path = tables_dir / f"{token}_tbl{i}.csv"
        tbl.to_csv(out_path, index=False)

    # record metadata including file paths for index
    table_files = []
    for i in range(len(tables)):
        table_files.append(str(tables_dir / f"{token}_tbl{i}.csv"))

    meta = {
        "url": url,
        "fetched_at": int(time.time()),
        "token": token,
        "html_path": str(html_path),
        "tables": table_files,
    }
    meta_path.write_text(json.dumps(meta), encoding='utf8')


    # add to sqlite index for quick lookup
    try:
        add_cache_entry(cdir, meta)
    except Exception as e:
        # don't fail the fetch if index update fails; log for user
        print('Warning: failed to update cache index:', e)

    # be polite and sleep to avoid rapid-fire requests
    sec = sleep_sec if sleep_sec is not None else config.DEFAULT_RATE_LIMIT
    time.sleep(sec)

    return tables


def load_cached_match_tables(cache_dir: Union[str, Path], url_or_token: str) -> List[pd.DataFrame]:
    """Load cached parsed tables from the cache for a given url or token.

    `url_or_token` may be the original URL used to fetch, or the token returned by
    `_safe_filename_from_url`. The function will try both.
    """
    cdir = Path(cache_dir)
    tables_dir = cdir / 'tables'
    token = url_or_token
    # if looks like a URL, convert to token
    if url_or_token.startswith('http'):
        token = _safe_filename_from_url(url_or_token)

    files = sorted(tables_dir.glob(f"{token}_tbl*.csv"))
    if not files:
        raise FileNotFoundError(f"No cached tables found for {url_or_token}")
    return [pd.read_csv(p) for p in files]


def _index_db_path(cache_dir: Union[str, Path]) -> Path:
    return Path(cache_dir) / 'index.db'


def init_cache_index(cache_dir: Union[str, Path]):
    """Create the sqlite index file and table if it does not exist."""
    dbp = _index_db_path(cache_dir)
    conn = sqlite3.connect(str(dbp))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cached_matches (
            token TEXT PRIMARY KEY,
            url TEXT,
            fetched_at INTEGER,
            html_path TEXT,
            tables_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_cache_entry(cache_dir: Union[str, Path], meta: dict):
    """Insert or replace a cache metadata record into the sqlite index."""
    dbp = _index_db_path(cache_dir)
    init_cache_index(cache_dir)
    conn = sqlite3.connect(str(dbp))
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO cached_matches (token, url, fetched_at, html_path, tables_json) VALUES (?, ?, ?, ?, ?)",
        (
            meta.get('token'),
            meta.get('url'),
            int(meta.get('fetched_at', 0)),
            meta.get('html_path'),
            json.dumps(meta.get('tables', [])),
        ),
    )
    conn.commit()
    conn.close()


def list_cached_matches(cache_dir: Union[str, Path]) -> pd.DataFrame:
    """Return a DataFrame listing cached matches from the sqlite index.

    Columns: token, url, fetched_at, html_path, tables (list)
    """
    dbp = _index_db_path(cache_dir)
    if not Path(dbp).exists():
        return pd.DataFrame(columns=["token", "url", "fetched_at", "html_path", "tables"])
    conn = sqlite3.connect(str(dbp))
    df = pd.read_sql_query("SELECT token, url, fetched_at, html_path, tables_json FROM cached_matches", conn)
    conn.close()
    # convert tables_json to list
    df['tables'] = df['tables_json'].apply(lambda x: json.loads(x) if x else [])
    df = df.drop(columns=['tables_json'])
    return df


def get_cache_entry_by_url(cache_dir: Union[str, Path], url: str) -> dict:
    """Return the metadata dict for a cached entry matching the URL, or None if not found."""
    df = list_cached_matches(cache_dir)
    if df.empty:
        return None
    matches = df[df['url'] == url]
    if matches.empty:
        return None
    row = matches.iloc[0].to_dict()
    return {
        'token': row.get('token'),
        'url': row.get('url'),
        'fetched_at': int(row.get('fetched_at', 0)),
        'html_path': row.get('html_path'),
        'tables': row.get('tables', []),
    }


def is_url_cached(cache_dir: Union[str, Path], url: str) -> bool:
    """Return True if the given URL is present in the sqlite cache index."""
    return get_cache_entry_by_url(cache_dir, url) is not None


def fetch_many(urls: List[str], cache_dir: Union[str, Path], *, rate_limit_sec: float = 2.0,
               manifest_path: str = None, retries: int = 3, jitter: float = 0.5,
               skip_cached: bool = True, **kwargs) -> None:
    """Fetch many match pages, caching each.

    Improvements:
    - optional manifest CSV writer with per-URL status
    - retries with exponential backoff and optional jitter
    - skip URLs already present in cache when `skip_cached=True`
    - respects `rate_limit_sec` between successful requests
    """
    cdir = Path(cache_dir)
    init_cache_index(cdir)

    # prepare manifest writer if requested
    manifest_fh = None
    manifest_writer = None
    if manifest_path:
        mf = Path(manifest_path)
        mf.parent.mkdir(parents=True, exist_ok=True)
        manifest_fh = open(mf, 'a', newline='', encoding='utf8')
        manifest_writer = csv.writer(manifest_fh)
        # write header if file was empty
        if mf.stat().st_size == 0:
            manifest_writer.writerow(['url', 'status', 'token', 'error', 'fetched_at', 'elapsed'])

    try:
        for url in urls:
            # skip if already cached
            if skip_cached and is_url_cached(cdir, url):
                if manifest_writer:
                    manifest_writer.writerow([url, 'skipped', '', '', int(time.time()), 0])
                continue

            attempt = 0
            start_ts = time.time()
            last_err = None
            token = ''
            while attempt <= retries:
                attempt += 1
                try:
                    # exponential backoff on retry
                    backoff = (2 ** (attempt - 1))
                    # call fetch_and_cache_match which respects robots and will sleep after success
                    tables = fetch_and_cache_match(url, cdir, sleep_sec=rate_limit_sec, **kwargs)
                    # success — look up token
                    meta = get_cache_entry_by_url(cdir, url) or {}
                    token = meta.get('token') or _safe_filename_from_url(url)
                    elapsed = time.time() - start_ts
                    if manifest_writer:
                        manifest_writer.writerow([url, 'fetched', token, '', int(time.time()), round(elapsed, 2)])
                    break
                except PermissionError:
                    # disallowed by robots — record and break
                    last_err = 'robots'
                    if manifest_writer:
                        manifest_writer.writerow([url, 'disallowed', '', 'robots', int(time.time()), 0])
                    break
                except Exception as e:
                    last_err = str(e)
                    # if we've exhausted retries, record failure
                    if attempt > retries:
                        elapsed = time.time() - start_ts
                        if manifest_writer:
                            manifest_writer.writerow([url, 'failed', token, last_err, int(time.time()), round(elapsed, 2)])
                        print('Failed to fetch', url, last_err)
                        break
                    # sleep with jitter before next retry
                    sleep_time = backoff + random.uniform(0, jitter)
                    time.sleep(sleep_time)
            # end attempts
    finally:
        if manifest_fh:
            manifest_fh.close()
