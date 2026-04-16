#!/usr/bin/env python3
"""Move prediction JSON files into round-based subdirectories.

Target layout:
  predictions/<year>/round_<NN>/predictions_*.json
  predictions/<year>/misc/<file>.json for files without round metadata
"""
import argparse
import json
import re
from pathlib import Path


def infer_year_and_round(file_path: Path) -> tuple[int | None, int | None]:
    try:
        data = json.loads(file_path.read_text(encoding='utf-8'))
        year = data.get('year')
        round_num = data.get('round')
        if isinstance(year, int) and round_num is not None:
            return year, int(round_num)
        if isinstance(year, int):
            return year, None
    except Exception:
        pass

    match = re.search(r'predictions_(\d{4})', file_path.name)
    year = int(match.group(1)) if match else None
    round_match = re.search(r'_r(\d+)', file_path.stem, re.IGNORECASE)
    round_num = int(round_match.group(1)) if round_match else None
    return year, round_num


def destination_for(file_path: Path) -> Path:
    year, round_num = infer_year_and_round(file_path)
    year_label = str(year) if year is not None else 'unknown_year'
    round_label = f'round_{round_num:02d}' if round_num is not None else 'misc'
    return Path('predictions') / year_label / round_label / file_path.name


def main():
    parser = argparse.ArgumentParser(description='Organize prediction JSON files into round-based folders')
    parser.add_argument('--dry-run', action='store_true', help='Show planned moves without changing files')
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    candidates = []
    for pattern in ['predictions_*.json', 'predictions/**/*.json']:
        candidates.extend(repo_root.glob(pattern))

    seen = set()
    files = []
    for file_path in candidates:
        resolved = file_path.resolve()
        if resolved in seen or not file_path.is_file():
            continue
        seen.add(resolved)
        files.append(file_path)

    moved = 0
    for file_path in sorted(files):
        relative = file_path.relative_to(repo_root)
        destination = repo_root / destination_for(relative)
        if file_path.resolve() == destination.resolve() if destination.exists() else False:
            continue
        if relative.parts[:2] == ('predictions', destination.relative_to(repo_root).parts[1]) and relative.parent == destination.relative_to(repo_root).parent:
            continue

        print(f'{relative} -> {destination.relative_to(repo_root)}')
        moved += 1
        if not args.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            file_path.replace(destination)

    print(f'files_moved: {moved}')


if __name__ == '__main__':
    main()