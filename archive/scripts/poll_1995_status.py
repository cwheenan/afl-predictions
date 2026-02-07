from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.data import load_data
import csv, os, datetime

MANIFEST = os.path.join('data', 'raw', 'cache', 'manifest_1995.csv')
CACHE_DIR = os.path.join('data', 'raw', 'cache')


def read_manifest_count(manifest_path):
    if not os.path.exists(manifest_path):
        return 0
    with open(manifest_path, newline='', encoding='utf8') as fh:
        reader = csv.reader(fh)
        rows = list(reader)
        # header + rows
        return max(0, len(rows) - 1)


def cached_tokens_for_manifest(manifest_path, cache_dir):
    if not os.path.exists(manifest_path):
        return 0
    with open(manifest_path, newline='', encoding='utf8') as fh:
        reader = csv.reader(fh)
        urls = [r[0] for r in list(reader)[1:] if r]
    df = load_data.list_cached_matches(cache_dir)
    if df.empty:
        return 0
    cached_urls = set(df['url'].tolist())
    return sum(1 for u in urls if u in cached_urls)


if __name__ == '__main__':
    ts = datetime.datetime.utcnow().isoformat() + 'Z'
    total_manifest = read_manifest_count(MANIFEST)
    cached = cached_tokens_for_manifest(MANIFEST, CACHE_DIR)

    engine = get_engine()
    session = get_session(engine)
    try:
        db_count = session.query(Match).filter(Match.season == 1995).count()
    except Exception:
        db_count = -1

    print(f"[{ts}] manifest_total={total_manifest} cached_manifest={cached} db_matches_1995={db_count}")
