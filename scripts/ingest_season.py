"""Ingest AFLTables season match pages for specified rounds and parse into DB.

Behavior:
- Fetch season page (e.g. https://afltables.com/afl/seas/2015.html)
- Extract match links grouped by round and select only requested rounds
- Fetch and cache those match pages (polite; respects robots.txt and rate limits)
- Parse cached matches into processed DB using existing `scripts/parse_matches.py` logic

Usage example (from repo root):
  python scripts/ingest_season.py --year 2015 --rounds 3-5 --max-pages 500

This script will NOT fetch the target prediction round (e.g., round 6) unless
explicitly included in the rounds argument.
"""
import argparse
import json
import re
from urllib.parse import urljoin
from pathlib import Path
import requests

from afl_predictions import config
from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session


def write_issue_report(report_name: str, payload: dict) -> Path:
    reports_dir = Path('data/processed/ingestion_reports')
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = payload.get('generated_at', '').replace(':', '').replace('-', '').replace('T', '_')[:15]
    if not stamp:
        stamp = 'unknown'
    out_file = reports_dir / f'{report_name}_{stamp}.json'
    with out_file.open('w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2)
    return out_file


def parse_rounds_arg(s: str):
    # Accept formats like '3-5' or '3,4,5' or '3'
    if '-' in s:
        a, b = s.split('-', 1)
        return list(range(int(a), int(b) + 1))
    if ',' in s:
        return [int(x) for x in s.split(',')]
    return [int(s)]


def fetch_season_page(year: int):
    season_url = f"https://afltables.com/afl/seas/{year}.html"
    ua = config.DEFAULT_USER_AGENT
    resp = requests.get(season_url, headers={'User-Agent': ua}, timeout=config.DEFAULT_HTTP_TIMEOUT)
    resp.raise_for_status()
    return season_url, resp.text


def extract_match_links_by_round(html: str, base_url: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    rounds = {}
    # find all candidate game links and try to infer the nearest 'Round' label
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/afl/stats/games/' not in href and '/stats/games/' not in href:
            continue
        full = urljoin(base_url, href)
        # try to find nearest previous text that mentions Round X
        prev_text = a.find_previous(string=re.compile(r'Round\s*\d{1,2}', re.IGNORECASE))
        rn = None
        if prev_text:
            m = re.search(r'Round\s*(\d{1,2})', str(prev_text), re.IGNORECASE)
            if m:
                rn = int(m.group(1))
        # fallback: see if the anchor text contains a round mention
        if rn is None:
            at = a.get_text(' ', strip=True)
            m2 = re.search(r'Round\s*(\d{1,2})', at, re.IGNORECASE)
            if m2:
                rn = int(m2.group(1))

        rounds.setdefault(rn, []).append(full)
    return rounds


def run(year: int, rounds, cache_dir: str, rate: float, max_pages: int):
    season_url, html = fetch_season_page(year)
    by_round = extract_match_links_by_round(html, season_url)
    # collect URLs for requested rounds
    urls = []
    for r in rounds:
        lst = by_round.get(r) or []
        # dedupe
        for u in lst:
            if u not in urls:
                urls.append(u)
            if len(urls) >= max_pages:
                break
        if len(urls) >= max_pages:
            break

    print(f'Found {len(urls)} match URLs for year={year} rounds={rounds}')
    if not urls:
        print('No URLs found for requested rounds; aborting')
        return urls

    return urls


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--rounds', type=str, default='1-23')
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR))
    p.add_argument('--rate', type=float, default=1.0)
    p.add_argument('--max-pages', type=int, default=500)
    p.add_argument('--dry-run', action='store_true', help='Do not fetch pages; just enumerate URLs and optionally write manifest')
    p.add_argument('--manifest', default=None, help='Path to write manifest CSV of URLs (token empty until cached)')
    p.add_argument('--resume', action='store_true', help='When not dry-run, skip fetching tokens already in cache')
    args = p.parse_args()

    rounds = parse_rounds_arg(args.rounds)
    urls = run(args.year, rounds, args.cache_dir, args.rate, args.max_pages)
    issues = []

    def add_issue(reason: str, message: str, url: str | None = None):
        issues.append(
            {
                'phase': 'season_ingestion',
                'reason': reason,
                'url': url,
                'message': message,
            }
        )

    if args.manifest:
        import csv
        with open(args.manifest, 'w', newline='', encoding='utf8') as fh:
            w = csv.writer(fh)
            w.writerow(['url'])
            for u in urls:
                w.writerow([u])
        print('Wrote manifest to', args.manifest)

    if args.dry_run:
        print('Dry run complete; no pages fetched')
        report = {
            'generated_at': datetime_now_iso(),
            'script': 'ingest_season.py',
            'season': args.year,
            'rounds': rounds,
            'summary': {
                'total_issues': len(issues),
                'by_reason': summarize_reasons(issues),
            },
            'issues': issues,
        }
        report_path = write_issue_report('ingest_season_issues', report)
        print(f'Issue report saved to: {report_path}')
        return

    # Not dry-run: fetch, cache, and parse
    load_data.init_cache_index(args.cache_dir)
    # If resume: remove URLs that are already cached
    if args.resume:
        df = load_data.list_cached_matches(args.cache_dir)
        cached_urls = set(df['url'].tolist()) if not df.empty else set()
        to_fetch = [u for u in urls if u not in cached_urls]
    else:
        to_fetch = urls

    print(f'Fetching {len(to_fetch)} pages (rate={args.rate}s)')
    if not to_fetch:
        add_issue('no_pages_to_fetch', 'No pages remained to fetch after resume filter')
    load_data.fetch_many(to_fetch, args.cache_dir, rate_limit_sec=args.rate)

    # parse and upsert these tokens
    df = load_data.list_cached_matches(args.cache_dir)
    selected_tokens = []
    missing_cached_urls = []
    for u in urls:
        row = df[df['url'] == u]
        if not row.empty:
            selected_tokens.append(row.iloc[0]['token'])
        else:
            missing_cached_urls.append(u)

    for u in missing_cached_urls:
        add_issue('missing_cached_token_after_fetch', 'URL missing from cache index after fetch', u)

    if not selected_tokens:
        print('No cached tokens found after fetching — aborting')
        report = {
            'generated_at': datetime_now_iso(),
            'script': 'ingest_season.py',
            'season': args.year,
            'rounds': rounds,
            'summary': {
                'total_issues': len(issues),
                'by_reason': summarize_reasons(issues),
            },
            'issues': issues,
        }
        report_path = write_issue_report('ingest_season_issues', report)
        print(f'Issue report saved to: {report_path}')
        return

    # parse and upsert these tokens
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from parse_matches import parse_and_upsert
    
    engine = get_engine()
    session = get_session(engine)
    for t in selected_tokens:
        try:
            parse_and_upsert(args.cache_dir, t, session)
        except Exception as e:
            print('Failed to parse token', t, e)
            add_issue('parse_and_upsert_failed', f'Failed to parse token {t}: {e}')

    report = {
        'generated_at': datetime_now_iso(),
        'script': 'ingest_season.py',
        'season': args.year,
        'rounds': rounds,
        'summary': {
            'total_issues': len(issues),
            'by_reason': summarize_reasons(issues),
        },
        'issues': issues,
    }
    report_path = write_issue_report('ingest_season_issues', report)
    print(f'Issue report saved to: {report_path}')


def summarize_reasons(issues: list[dict]) -> dict:
    counts = {}
    for i in issues:
        reason = str(i.get('reason'))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


if __name__ == '__main__':
    main()
