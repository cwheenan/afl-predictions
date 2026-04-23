#!/usr/bin/env python3
"""Ingest live AFL tipping odds into the local match_odds table.

This script fetches current data from the official AFL tipping JSON endpoints,
resolves the dynamic checksum version parameter, maps squads to internal team
names, then writes one fresh `afl_tipping` odds row per matched fixture.

Usage:
  python scripts/ingest_afl_tipping_odds.py --year 2026
  python scripts/ingest_afl_tipping_odds.py --year 2026 --round 7
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import Match, MatchOdds, get_engine, get_session
from afl_predictions.match_identity import (
    find_matching_matches,
    parse_match_datetime,
    select_canonical_match,
)

CHECKSUMS_URL = 'https://tipping.afl.com.au/json/tipping/checksums.json'
JSON_BASE = 'https://tipping.afl.com.au/json/tipping'
SOURCE_NAME = 'afl_tipping'


def normalize_tipping_team_name(team_name: str) -> str:
    """Map AFL tipping squad names to internal canonical DB team names."""
    mapping = {
        'Adelaide Crows': 'Adelaide',
        'Brisbane Lions': 'Brisbane Lions',
        'Carlton': 'Carlton',
        'Collingwood': 'Collingwood',
        'Essendon': 'Essendon',
        'Fremantle': 'Fremantle',
        'Geelong Cats': 'Geelong',
        'Hawthorn': 'Hawthorn',
        'Melbourne': 'Melbourne',
        'North Melbourne': 'North Melbourne',
        'Port Adelaide': 'Port Adelaide',
        'Richmond': 'Richmond',
        'St Kilda': 'St Kilda',
        'Sydney Swans': 'Sydney',
        'West Coast Eagles': 'West Coast',
        'Western Bulldogs': 'Western Bulldogs',
        'Gold Coast SUNS': 'Gold Coast',
        'GWS GIANTS': 'Greater Western Sydney',
    }
    return mapping.get((team_name or '').strip(), (team_name or '').strip())


def fetch_checksums(timeout: int) -> Dict[str, str]:
    resp = requests.get(CHECKSUMS_URL, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError('checksums payload was not a JSON object')
    return data


def fetch_versioned_json(name: str, checksum_key: str, checksums: Dict[str, str], timeout: int):
    checksum = checksums.get(checksum_key)
    if not checksum:
        raise KeyError(f'missing checksum key: {checksum_key}')
    url = f'{JSON_BASE}/{name}.json?v={checksum}'
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json(), url


def choose_target_round(rounds: List[dict], requested_round: Optional[int]) -> Optional[int]:
    if requested_round is not None:
        return requested_round

    # Prefer earliest round that still has at least one scheduled game.
    scheduled_rounds = []
    for r in rounds:
        games = r.get('games', []) or []
        if any((g.get('status') or '').lower() != 'completed' for g in games):
            round_num = r.get('roundNumber')
            if isinstance(round_num, int):
                scheduled_rounds.append(round_num)
    if scheduled_rounds:
        return min(scheduled_rounds)

    # Fallback to max round number present.
    numeric_rounds = [r.get('roundNumber') for r in rounds if isinstance(r.get('roundNumber'), int)]
    if numeric_rounds:
        return max(numeric_rounds)
    return None


def build_squad_lookup(squads: List[dict]) -> Dict[int, str]:
    lookup: Dict[int, str] = {}
    for squad in squads:
        squad_id = squad.get('id')
        if not isinstance(squad_id, int):
            continue
        name = normalize_tipping_team_name(squad.get('name', ''))
        if name:
            lookup[squad_id] = name
    return lookup


def extract_target_games(rounds: List[dict], round_number: int) -> List[dict]:
    for r in rounds:
        if r.get('roundNumber') == round_number:
            return list(r.get('games', []) or [])
    return []


def ingest_afl_tipping_odds(
    year: int,
    round_number: Optional[int],
    include_completed: bool,
    timeout: int,
    save_raw: bool,
) -> int:
    checksums = fetch_checksums(timeout=timeout)
    rounds_payload, rounds_url = fetch_versioned_json('rounds', 'rounds', checksums, timeout=timeout)
    squads_payload, squads_url = fetch_versioned_json('squads', 'squads', checksums, timeout=timeout)

    if not isinstance(rounds_payload, list) or not isinstance(squads_payload, list):
        raise ValueError('unexpected rounds/squads payload shape')

    target_round = choose_target_round(rounds_payload, requested_round=round_number)
    if target_round is None:
        raise ValueError('could not determine target round from AFL tipping payload')

    games = extract_target_games(rounds_payload, target_round)
    if not games:
        raise ValueError(f'no games found for round {target_round}')

    squad_lookup = build_squad_lookup(squads_payload)

    engine = get_engine()
    session = get_session(engine)

    now = datetime.now()
    inserted = 0
    updated = 0
    skipped = 0
    unmatched = 0

    print(f'Checksums URL: {CHECKSUMS_URL}')
    print(f'Rounds URL:    {rounds_url}')
    print(f'Squads URL:    {squads_url}')
    print(f'Target season: {year}')
    print(f'Target round:  {target_round}')
    print(f'Games found:   {len(games)}')

    for game in games:
        game_id = game.get('id')
        home_id = game.get('homeId')
        away_id = game.get('awayId')
        home_odds_obj = game.get('homeOdds') or {}
        away_odds_obj = game.get('awayOdds') or {}
        game_status = (game.get('status') or '').lower()

        home_team = squad_lookup.get(home_id)
        away_team = squad_lookup.get(away_id)
        if not home_team or not away_team:
            print(f'- Skip game {game_id}: missing squad mapping (homeId={home_id}, awayId={away_id})')
            skipped += 1
            continue

        if not include_completed and game_status == 'completed':
            print(f'- Skip game {game_id}: completed ({home_team} vs {away_team})')
            skipped += 1
            continue

        home_odds = home_odds_obj.get('value')
        away_odds = away_odds_obj.get('value')
        if home_odds is None or away_odds is None:
            print(f'- Skip game {game_id}: missing h2h odds ({home_team} vs {away_team})')
            skipped += 1
            continue

        try:
            home_odds = float(home_odds)
            away_odds = float(away_odds)
        except (TypeError, ValueError):
            print(f'- Skip game {game_id}: non-numeric odds ({home_team} vs {away_team})')
            skipped += 1
            continue

        target_dt = parse_match_datetime(game.get('date'))
        candidates = find_matching_matches(
            session,
            Match,
            home_team,
            away_team,
            target_dt=target_dt,
            season=year,
        )
        if not candidates:
            # Fallback without season filter if season labels differ unexpectedly.
            candidates = find_matching_matches(
                session,
                Match,
                home_team,
                away_team,
                target_dt=target_dt,
                season=None,
            )

        if not candidates:
            print(f'- Unmatched game {game_id}: {home_team} vs {away_team} ({game.get("date")})')
            unmatched += 1
            continue

        match = select_canonical_match(candidates, target_dt)
        if match is None:
            print(f'- Unmatched game {game_id}: canonical match selection failed')
            unmatched += 1
            continue

        existing_count = (
            session.query(MatchOdds)
            .filter(MatchOdds.match_id == match.match_id, MatchOdds.source == SOURCE_NAME)
            .count()
        )
        if existing_count:
            (
                session.query(MatchOdds)
                .filter(MatchOdds.match_id == match.match_id, MatchOdds.source == SOURCE_NAME)
                .delete(synchronize_session=False)
            )
            updated += 1

        row = MatchOdds(
            match_id=match.match_id,
            source=SOURCE_NAME,
            home_win_odds=home_odds,
            away_win_odds=away_odds,
            timestamp=now,
        )
        session.add(row)
        inserted += 1

        print(
            f"- Stored game {game_id}: {home_team} vs {away_team} | "
            f"odds={home_odds:.2f}/{away_odds:.2f} | match_id={match.match_id}"
        )

    session.commit()
    session.close()

    if save_raw:
        out_dir = Path('data/raw/odds')
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_file = out_dir / f'afl_tipping_round_{target_round:02d}_{stamp}.json'
        with out_file.open('w', encoding='utf-8') as f:
            json.dump(
                {
                    'fetched_at': datetime.now().isoformat(),
                    'checksums_url': CHECKSUMS_URL,
                    'rounds_url': rounds_url,
                    'squads_url': squads_url,
                    'season': year,
                    'round': target_round,
                    'games': games,
                },
                f,
                indent=2,
            )
        print(f'Raw payload snapshot saved to: {out_file}')

    print('\nIngestion summary:')
    print(f'- inserted rows: {inserted}')
    print(f'- replaced rows: {updated}')
    print(f'- skipped games: {skipped}')
    print(f'- unmatched games: {unmatched}')

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description='Ingest live AFL tipping odds into match_odds')
    parser.add_argument('--year', type=int, default=datetime.now().year, help='Season year in local DB')
    parser.add_argument('--round', type=int, dest='round_number', help='Round number to ingest')
    parser.add_argument('--include-completed', action='store_true', help='Include completed games')
    parser.add_argument('--timeout', type=int, default=25, help='HTTP timeout in seconds')
    parser.add_argument('--no-save-raw', action='store_true', help='Do not save raw JSON snapshot')
    args = parser.parse_args()

    ingest_afl_tipping_odds(
        year=args.year,
        round_number=args.round_number,
        include_completed=args.include_completed,
        timeout=args.timeout,
        save_raw=not args.no_save_raw,
    )


if __name__ == '__main__':
    main()
