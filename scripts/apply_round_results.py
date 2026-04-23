"""Apply AFLTables parsed results to fixture rows in the DB.

Matches parsed rows (which have scores but wrong round/date) to fixture rows
(which have correct dates/rounds but no scores) using team pairing, then
transfers scores and deletes the duplicate parsed rows.

Usage:
  python scripts/apply_round_results.py --season 2026 --fixture-round 5 --parsed-round 6
  python scripts/apply_round_results.py --season 2026 --fixture-round 6 --parsed-round 7
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from afl_predictions.db import get_engine, get_session, Match, PlayerStats, MatchOdds


def write_issue_report(season: int, fixture_round: int, parsed_round: int, issues: list[dict]) -> Path:
    reports_dir = Path('data/processed/ingestion_reports')
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_file = reports_dir / f'apply_round_results_issues_{season}_f{fixture_round:02d}_p{parsed_round:02d}_{stamp}.json'
    with out_file.open('w', encoding='utf-8') as fh:
        json.dump(
            {
                'generated_at': datetime.now().isoformat(),
                'script': 'apply_round_results.py',
                'season': season,
                'fixture_round': fixture_round,
                'parsed_round': parsed_round,
                'summary': {
                    'total_issues': len(issues),
                    'by_reason': summarize_reasons(issues),
                },
                'issues': issues,
            },
            fh,
            indent=2,
        )
    return out_file


def summarize_reasons(issues: list[dict]) -> dict:
    counts = {}
    for i in issues:
        reason = str(i.get('reason'))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def apply_results(season: int, fixture_round: int, parsed_round: int, dry_run: bool = False):
    engine = get_engine()
    session = get_session(engine)

    fixture_rows = session.query(Match).filter(
        Match.season == season,
        Match.round == str(fixture_round),
        Match.home_score == None,
    ).all()

    parsed_rows = session.query(Match).filter(
        Match.season == season,
        Match.round == str(parsed_round),
        Match.home_score != None,
        Match.token != None,
    ).all()

    issues = []

    if not fixture_rows:
        print(f'No unscored fixture rows found for season={season} round={fixture_round}')
        issues.append(
            {
                'phase': 'apply_round_results',
                'reason': 'no_fixture_rows',
                'message': f'No unscored fixture rows for season={season} round={fixture_round}',
            }
        )
        report = write_issue_report(season, fixture_round, parsed_round, issues)
        print(f'Issue report saved to: {report}')
        return
    if not parsed_rows:
        print(f'No scored parsed rows found for season={season} round={parsed_round}')
        issues.append(
            {
                'phase': 'apply_round_results',
                'reason': 'no_parsed_rows',
                'message': f'No scored parsed rows for season={season} round={parsed_round}',
            }
        )
        report = write_issue_report(season, fixture_round, parsed_round, issues)
        print(f'Issue report saved to: {report}')
        return

    # Build lookup: (home_team, away_team) -> parsed row
    parsed_lookup = {(r.home_team, r.away_team): r for r in parsed_rows}

    matched = 0
    unmatched = []

    for fixture in fixture_rows:
        key = (fixture.home_team, fixture.away_team)
        parsed = parsed_lookup.get(key)
        if parsed is None:
            unmatched.append(key)
            continue

        print(f'  {fixture.home_team} vs {fixture.away_team}: '
              f'{parsed.home_score}-{parsed.away_score}')

        if not dry_run:
            fixture.home_score = parsed.home_score
            fixture.away_score = parsed.away_score
            if not fixture.venue and parsed.venue:
                fixture.venue = parsed.venue

            # Migrate player_stats from parsed row to fixture row
            for ps in session.query(PlayerStats).filter(PlayerStats.match_id == parsed.match_id).all():
                ps.match_id = fixture.match_id

            # Migrate odds from parsed row to fixture row
            for odds in session.query(MatchOdds).filter(MatchOdds.match_id == parsed.match_id).all():
                odds.match_id = fixture.match_id

            session.flush()
            session.delete(parsed)

        matched += 1

    if not dry_run:
        session.commit()

    print(f'\nMatched and updated: {matched}')
    if unmatched:
        print(f'Unmatched fixture rows: {unmatched}')
        for home_team, away_team in unmatched:
            issues.append(
                {
                    'phase': 'apply_round_results',
                    'reason': 'fixture_row_unmatched',
                    'home_team': home_team,
                    'away_team': away_team,
                    'message': f'Unmatched fixture row: {home_team} vs {away_team}',
                }
            )
    if dry_run:
        print('(dry run - no changes applied)')

    report = write_issue_report(season, fixture_round, parsed_round, issues)
    print(f'Issue report saved to: {report}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--fixture-round', type=int, required=True,
                        help='Round number in our fixture DB (e.g. 5)')
    parser.add_argument('--parsed-round', type=int, required=True,
                        help='Round number stored by AFLTables parse (fixture-round + 1)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f'Applying season={args.season} AFLTables-round={args.parsed_round} '
          f'-> fixture-round={args.fixture_round}')
    apply_results(args.season, args.fixture_round, args.parsed_round, args.dry_run)


if __name__ == '__main__':
    main()
