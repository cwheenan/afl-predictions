"""Safe, small crawler to discover AFLTables links starting from seed pages.

Usage:
    python scripts/crawl_afltables.py seeds.txt --cache-dir data/raw/cache --master-list data/raw/all_urls.txt --dry-run

Behavior:
 - For each seed URL, the crawler will ensure the page is cached (using fetch_and_cache_match)
   unless --dry-run is set in which case it will only read existing cache entries.
 - It will then parse the cached HTML and extract links under the afltables domain.
 - Discovered links are appended to the master list file (if not already present).
 - The crawler is intentionally conservative: respects robots via fetch_and_cache_match,
   sleeps according to config.DEFAULT_RATE_LIMIT when making network calls, and supports
   a --limit to cap the number of pages discovered in a run.
"""
import argparse
from pathlib import Path
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from afl_predictions import config
from afl_predictions.data import load_data


AFLTABLES_NETLOC = 'afltables.com'


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('seeds_file', help='Text file with seed URLs (one per line)')
    p.add_argument('--cache-dir', default=str(config.DEFAULT_CACHE_DIR), help='Cache directory')
    p.add_argument('--master-list', default='data/raw/all_urls.txt', help='Path to master URL list to append discovered links')
    p.add_argument('--dry-run', action='store_true', help='Do not perform network fetches; only parse existing cache entries')
    p.add_argument('--limit', type=int, default=None, help='Stop after discovering this many new links')
    return p.parse_args()


def extract_afltables_links(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        # make absolute
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc.endswith(AFLTABLES_NETLOC):
            # keep only relevant paths (games, umpires, players, teams, stats)
            if re.search(r'/afl/stats/(games|umpires|players|teams|stats)/', parsed.path):
                links.add(full)
    return sorted(links)


def load_master_list(path):
    p = Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding='utf8').splitlines() if l.strip()]


def append_to_master_list(path, urls):
    p = Path(path)
    existing = set(load_master_list(path))
    new = [u for u in urls if u not in existing]
    if not new:
        return 0
    with p.open('a', encoding='utf8') as f:
        for u in new:
            f.write(u + '\n')
    return len(new)


def main():
    args = parse_args()
    seeds_path = Path(args.seeds_file)
    if not seeds_path.exists():
        raise SystemExit(f'Seeds file not found: {seeds_path}')

    seeds = [l.strip() for l in seeds_path.read_text(encoding='utf8').splitlines() if l.strip()]
    discovered = []

    for seed in seeds:
        try:
            # ensure cached (unless dry-run)
            entry = load_data.get_cache_entry_by_url(args.cache_dir, seed)
            if entry is None and not args.dry_run:
                # fetch and cache seed page
                load_data.fetch_and_cache_match(seed, args.cache_dir)
                entry = load_data.get_cache_entry_by_url(args.cache_dir, seed)

            if entry is None:
                print('No cached content for seed (skipping):', seed)
                continue

            # read raw HTML
            html_path = Path(entry['html_path'])
            if not html_path.exists():
                print('HTML file missing for seed (skipping):', seed)
                continue
            html = html_path.read_text(encoding='utf8')
            links = extract_afltables_links(html, seed)
            for l in links:
                if l not in discovered:
                    discovered.append(l)
            if args.limit and len(discovered) >= args.limit:
                break
        except Exception as e:
            print('Error processing seed', seed, e)

    # append discovered links to master list
    added = append_to_master_list(args.master_list, discovered)
    print(f'Discovered {len(discovered)} links, appended {added} new links to {args.master_list}')


if __name__ == '__main__':
    main()
