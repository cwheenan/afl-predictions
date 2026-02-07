"""CLI to build a manifest CSV from the DB pages table.

Usage:
    python scripts/make_manifest.py --out data/processed/manifest.csv
"""
import argparse
from afl_predictions import config
from afl_predictions.data.manifest import make_manifest


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--db-url', default=None, help='Optional DB URL override')
    p.add_argument('--out', default='data/processed/manifest.csv', help='Output CSV path')
    return p.parse_args()


def main():
    args = parse_args()
    df = make_manifest(db_url=args.db_url, out_path=args.out)
    if df.empty:
        print('No pages found in DB; manifest is empty.')
        return
    counts = df['page_type'].value_counts()
    print('Manifest written to', args.out)
    print('Counts by page_type:')
    print(counts.to_string())


if __name__ == '__main__':
    main()
