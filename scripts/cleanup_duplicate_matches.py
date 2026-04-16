#!/usr/bin/env python3
"""Consolidate duplicate match rows into a single canonical record.

This script identifies logical duplicate matches using team pairing plus match
date, migrates dependent rows to the canonical match, and deletes the redundant
match rows.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import get_engine, get_session, Match, MatchLineup, MatchOdds, MatchUmpire, PlayerStats
from afl_predictions.match_identity import same_match_key, select_canonical_match


def merge_match_group(session, group, dry_run: bool = False) -> dict[str, int]:
    canonical = select_canonical_match(group)
    duplicates = [match for match in group if match.match_id != canonical.match_id]

    migrated_odds = 0
    migrated_player_stats = 0
    migrated_lineups = 0
    migrated_umpires = 0
    deleted_matches = 0

    existing_odds_sources = {
        row.source for row in session.query(MatchOdds).filter(MatchOdds.match_id == canonical.match_id).all()
    }
    existing_player_stats = {
        (row.player_id, row.team) for row in session.query(PlayerStats).filter(PlayerStats.match_id == canonical.match_id).all()
    }
    existing_lineups = {
        row.player_id for row in session.query(MatchLineup).filter(MatchLineup.match_id == canonical.match_id).all()
    }
    existing_umpires = {
        row.umpire_id for row in session.query(MatchUmpire).filter(MatchUmpire.match_id == canonical.match_id).all()
    }

    for duplicate in duplicates:
        for odds in session.query(MatchOdds).filter(MatchOdds.match_id == duplicate.match_id).all():
            if odds.source in existing_odds_sources:
                if not dry_run:
                    session.delete(odds)
            else:
                if not dry_run:
                    odds.match_id = canonical.match_id
                    session.add(odds)
                existing_odds_sources.add(odds.source)
                migrated_odds += 1

        for player_stats in session.query(PlayerStats).filter(PlayerStats.match_id == duplicate.match_id).all():
            key = (player_stats.player_id, player_stats.team)
            if key in existing_player_stats:
                if not dry_run:
                    session.delete(player_stats)
            else:
                if not dry_run:
                    player_stats.match_id = canonical.match_id
                    session.add(player_stats)
                existing_player_stats.add(key)
                migrated_player_stats += 1

        for lineup in session.query(MatchLineup).filter(MatchLineup.match_id == duplicate.match_id).all():
            if lineup.player_id in existing_lineups:
                if not dry_run:
                    session.delete(lineup)
            else:
                if not dry_run:
                    lineup.match_id = canonical.match_id
                    session.add(lineup)
                existing_lineups.add(lineup.player_id)
                migrated_lineups += 1

        for umpire in session.query(MatchUmpire).filter(MatchUmpire.match_id == duplicate.match_id).all():
            if umpire.umpire_id in existing_umpires:
                if not dry_run:
                    session.delete(umpire)
            else:
                if not dry_run:
                    umpire.match_id = canonical.match_id
                    session.add(umpire)
                existing_umpires.add(umpire.umpire_id)
                migrated_umpires += 1

        if not dry_run:
            session.delete(duplicate)
        deleted_matches += 1

    return {
        'deleted_matches': deleted_matches,
        'migrated_odds': migrated_odds,
        'migrated_player_stats': migrated_player_stats,
        'migrated_lineups': migrated_lineups,
        'migrated_umpires': migrated_umpires,
        'canonical_match_id': canonical.match_id,
    }


def main():
    parser = argparse.ArgumentParser(description='Consolidate duplicate match rows')
    parser.add_argument('--year', type=int, default=2026, help='Season year to clean up')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without modifying the database')
    args = parser.parse_args()

    engine = get_engine()
    session = get_session(engine)

    matches = [
        match for match in session.query(Match).filter(Match.season == args.year).all()
        if match.date and match.home_team and match.away_team
    ]
    groups = defaultdict(list)
    for match in matches:
        groups[same_match_key(match)].append(match)

    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    print(f'Found {len(duplicate_groups)} duplicate groups in {args.year}')

    totals = defaultdict(int)
    for group in duplicate_groups:
        summary = merge_match_group(session, group, dry_run=args.dry_run)
        for key, value in summary.items():
            if key != 'canonical_match_id':
                totals[key] += value

    if args.dry_run:
        session.rollback()
        print('Dry run complete; no database changes applied')
    else:
        session.commit()
        print('Cleanup committed')

    for key in ['deleted_matches', 'migrated_odds', 'migrated_player_stats', 'migrated_lineups', 'migrated_umpires']:
        print(f'{key}: {totals[key]}')

    session.close()


if __name__ == '__main__':
    main()