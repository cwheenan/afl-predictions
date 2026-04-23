#!/usr/bin/env python3
"""Create odds proxy data from Squiggle API tipster predictions.

Squiggle aggregates professional AFL tipsters. Their consensus strongly 
correlates with betting markets and provides a free historical odds proxy.

Usage:
  python scripts/create_odds_proxy_from_squiggle.py --year 2025
  python scripts/create_odds_proxy_from_squiggle.py --year 2024 --rounds 1-10
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import json
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from sqlalchemy import and_

from afl_predictions.config import SQUIGGLE_USER_AGENT
from afl_predictions.db import get_engine, get_session, Match, MatchOdds
from afl_predictions.match_identity import canonical_round_for_group, detect_current_round, find_matching_matches, parse_match_datetime, select_canonical_match

def normalize_team_name(team: str) -> str:
    """Normalize team names between Squiggle and our DB."""
    mappings = {
        'adelaide': 'Adelaide',
        'brisbane lions': 'Brisbane Lions',
        'brisbane': 'Brisbane Lions',
        'lions': 'Brisbane Lions',
        'carlton': 'Carlton',
        'collingwood': 'Collingwood',
        'essendon': 'Essendon',
        'fremantle': 'Fremantle',
        'geelong': 'Geelong',
        'geelong cats': 'Geelong',
        'gold coast': 'Gold Coast',
        'gold coast suns': 'Gold Coast',
        'gws': 'Greater Western Sydney',
        'gws giants': 'Greater Western Sydney',
        'greater western sydney': 'Greater Western Sydney',
        'giants': 'Greater Western Sydney',
        'hawthorn': 'Hawthorn',
        'melbourne': 'Melbourne',
        'north melbourne': 'North Melbourne',
        'kangaroos': 'North Melbourne',
        'port adelaide': 'Port Adelaide',
        'richmond': 'Richmond',
        'st kilda': 'St Kilda',
        'sydney': 'Sydney',
        'sydney swans': 'Sydney',
        'west coast': 'West Coast',
        'west coast eagles': 'West Coast',
        'western bulldogs': 'Western Bulldogs',
        'bulldogs': 'Western Bulldogs',
    }
    return mappings.get(team.lower().strip(), team)


def fetch_squiggle_games(year: int, round_num: Optional[int] = None) -> List[Dict]:
    """Fetch game data from Squiggle API."""
    params = {
        'q': 'games',
        'year': year,
    }
    
    if round_num:
        params['round'] = round_num
    
    headers = {
        'User-Agent': SQUIGGLE_USER_AGENT,
    }
    
    try:
        response = requests.get('https://api.squiggle.com.au/', params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get('games', [])
    except requests.RequestException as e:
        print(f"Error fetching Squiggle games: {e}")
        return []


def fetch_squiggle_tips(game_id: int) -> Dict:
    """Fetch tipster predictions for a game."""
    params = {
        'q': 'tips',
        'game': game_id,
    }
    
    headers = {
        'User-Agent': SQUIGGLE_USER_AGENT,
    }
    
    try:
        response = requests.get('https://api.squiggle.com.au/', params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tips = data.get('tips', [])
        if not tips:
            return {}

        # Guard against error payloads (e.g. bad_UA) being mistaken for real tip rows.
        valid_tips = [
            tip for tip in tips
            if not tip.get('error') and tip.get('hteam') and tip.get('ateam')
        ]
        if not valid_tips:
            return {}

        first_tip = valid_tips[0]
        home_team_name = first_tip.get('hteam', '')
        away_team_name = first_tip.get('ateam', '')

        # Prefer averaged per-tip home confidence when present.
        # Squiggle hconfidence is percentage chance (0-100) for home team.
        hconf_vals = []
        for tip in valid_tips:
            hconfidence = tip.get('hconfidence')
            try:
                if hconfidence is not None:
                    hconf_vals.append(float(hconfidence) / 100.0)
            except (TypeError, ValueError):
                continue

        if hconf_vals:
            home_prob = sum(hconf_vals) / len(hconf_vals)
            away_prob = 1.0 - home_prob
            home_tips = sum(1 for tip in valid_tips if tip.get('tip') == home_team_name)
            away_tips = sum(1 for tip in valid_tips if tip.get('tip') == away_team_name)
            total = len(valid_tips)
        else:
            # Fallback to tip counts with Laplace smoothing to avoid 0%/100% artefacts.
            home_tips = sum(1 for tip in valid_tips if tip.get('tip') == home_team_name)
            away_tips = sum(1 for tip in valid_tips if tip.get('tip') == away_team_name)
            total = home_tips + away_tips
            if total == 0:
                return {}
            alpha = 1.0
            home_prob = (home_tips + alpha) / (total + 2.0 * alpha)
            away_prob = 1.0 - home_prob

        # Clamp to keep this as a calibrated consensus prior, not pseudo-"$1.01 vs $99" odds.
        home_prob = min(max(home_prob, 0.05), 0.95)
        away_prob = min(max(away_prob, 0.05), 0.95)

        # Store in odds columns for compatibility with existing feature pipeline.
        # No bookmaker margin is applied because this is tip consensus, not sportsbook prices.
        home_odds = 1.0 / home_prob
        away_odds = 1.0 / away_prob
        
        return {
            'home_win_odds': round(home_odds, 2),
            'away_win_odds': round(away_odds, 2),
            'home_tips': home_tips,
            'away_tips': away_tips,
            'total_tips': len(valid_tips),
            'confidence': 'high' if total >= 10 else ('medium' if total >= 5 else 'low'),
        }
    
    except requests.RequestException as e:
        print(f"  Error fetching tips for game {game_id}: {e}")
        return {}


def create_odds_proxy_for_year(year: int, rounds_range: Optional[str] = None, test_limit: Optional[int] = None):
    """Create odds proxy data for all games in a year."""
    engine = get_engine()
    db_session = get_session(engine)
    
    print(f"\n=== Creating Odds Proxy from Squiggle Tips ({year}) ===\n")
    print("Squiggle aggregates professional AFL tipsters")
    print("Tipster consensus correlates strongly with betting markets\n")
    
    # Determine which rounds to process
    current_year = datetime.now().year
    if rounds_range:
        start, end = map(int, rounds_range.split('-'))
        rounds = list(range(start, end + 1))
        print(f"Processing rounds {start} to {end}")
    else:
        rounds = None
        if year == current_year:
            season_matches = db_session.query(Match).filter(Match.season == year).all()
            current_round = detect_current_round(season_matches)
            if current_round is not None:
                rounds = list(range(0, current_round + 1))
                print(f"Processing rounds 0 to {current_round} for current season")
            else:
                print(f"Processing all rounds in {year}")
        else:
            print(f"Processing all rounds in {year}")
    
    # Fetch all games for the year
    print(f"\nFetching games from Squiggle...")
    all_games = fetch_squiggle_games(year)
    
    if rounds:
        # Filter by round
        all_games = [g for g in all_games if int(g.get('round', 0)) in rounds]
    
    if test_limit:
        all_games = all_games[:test_limit]
        print(f"Limited to first {test_limit} games for testing")
    
    print(f"Found {len(all_games)} games to process\n")
    
    total_stored = 0
    matches_found = 0
    matches_not_found = 0
    issues: List[Dict[str, object]] = []

    def issue_phase(round_value) -> str:
        current_year = datetime.now().year
        if year == current_year:
            season_matches = db_session.query(Match).filter(Match.season == year).all()
            current_round_detected = detect_current_round(season_matches)
            try:
                if current_round_detected is not None and int(round_value) <= int(current_round_detected):
                    return 'previous_matches'
            except Exception:
                pass
            return 'upcoming_matches'
        return 'historical_matches'

    def add_issue(reason: str, message: str, game: Dict, home_team: str, away_team: str):
        issues.append(
            {
                'phase': issue_phase(game.get('round')),
                'reason': reason,
                'game_id': game.get('id'),
                'round': game.get('round'),
                'date': game.get('date'),
                'home_team': home_team,
                'away_team': away_team,
                'message': message,
            }
        )
    
    for i, game in enumerate(all_games, 1):
        game_id = game.get('id')
        home_team = normalize_team_name(game.get('hteam', ''))
        away_team = normalize_team_name(game.get('ateam', ''))
        round_num = game.get('round', '?')
        date_str = game.get('date', '')
        
        print(f"\n[{i}/{len(all_games)}] Round {round_num}: {home_team} vs {away_team}")
        
        target_dt = parse_match_datetime(date_str)
        db_matches = find_matching_matches(
            db_session,
            Match,
            home_team,
            away_team,
            target_dt=target_dt,
            season=year,
        )
        
        if not db_matches:
            msg = '  WARNING No database match found'
            print(msg)
            add_issue('db_match_not_found', msg.strip(), game, home_team, away_team)
            matches_not_found += 1
            continue

        best_match = select_canonical_match(db_matches, target_dt)
        canonical_round = canonical_round_for_group(db_matches, target_dt)
        if canonical_round and str(best_match.round) != canonical_round:
            best_match.round = canonical_round
            db_session.add(best_match)

        if len(db_matches) > 1 and canonical_round and str(round_num) != canonical_round:
            print(f"  Note: Squiggle round {round_num} mapped to canonical round {canonical_round}")
        
        matches_found += 1
        
        # Check if odds already exist
        existing = db_session.query(MatchOdds).filter(
            and_(
                MatchOdds.match_id == best_match.match_id,
                MatchOdds.source == 'squiggle_consensus'
            )
        ).first()
        
        if existing:
            print(f"  OK Odds already exist (match_id {best_match.match_id})")
            continue
        
        # Fetch tipster predictions
        print(f"  Fetching tips for Squiggle game {game_id}...")
        tips_data = fetch_squiggle_tips(game_id)
        
        if not tips_data:
            msg = '  WARNING No tips found for this game'
            print(msg)
            add_issue('no_tips_for_game', msg.strip(), game, home_team, away_team)
            continue
        
        # Store in database
        match_odds = MatchOdds(
            match_id=best_match.match_id,
            source='squiggle_consensus',
            home_win_odds=tips_data['home_win_odds'],
            away_win_odds=tips_data['away_win_odds'],
            timestamp=datetime.now()
        )
        
        db_session.add(match_odds)
        total_stored += 1
        
        print(f"  OK Stored odds: {tips_data['home_win_odds']} - {tips_data['away_win_odds']}")
        print(f"    Based on {tips_data['total_tips']} tipsters ({tips_data['home_tips']}-{tips_data['away_tips']})")
        print(f"    Confidence: {tips_data['confidence']}")
        
        # Commit every 10 matches
        if total_stored % 10 == 0:
            db_session.commit()
            print(f"\n  [Progress: {total_stored} odds stored]")
        
        # Rate limit - be nice to Squiggle
        time.sleep(0.5)
    
    # Final commit
    db_session.commit()
    
    print(f"\n=== Complete ===")
    print(f"Games processed: {len(all_games)}")
    print(f"Matches found in DB: {matches_found}")
    print(f"Matches not found: {matches_not_found}")
    print(f"Odds records stored: {total_stored}")

    reports_dir = Path('data/processed/ingestion_reports')
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = reports_dir / f'squiggle_proxy_issues_{year}_{stamp}.json'

    by_reason: Dict[str, int] = {}
    by_phase: Dict[str, int] = {}
    for issue in issues:
        reason = str(issue.get('reason'))
        phase = str(issue.get('phase'))
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_phase[phase] = by_phase.get(phase, 0) + 1

    with report_path.open('w', encoding='utf-8') as fh:
        json.dump(
            {
                'generated_at': datetime.now().isoformat(),
                'script': 'create_odds_proxy_from_squiggle.py',
                'season': year,
                'summary': {
                    'total_issues': len(issues),
                    'by_phase': by_phase,
                    'by_reason': by_reason,
                },
                'issues': issues,
            },
            fh,
            indent=2,
        )
    print(f'Issue report saved to: {report_path}')
    
    db_session.close()


def main():
    parser = argparse.ArgumentParser(description='Create odds proxy from Squiggle tipster consensus')
    parser.add_argument('--year', type=int, default=2025, help='Year to process')
    parser.add_argument('--rounds', type=str, help='Round range (e.g., "1-10")')
    parser.add_argument('--test', type=int, help='Limit to first N games for testing')
    
    args = parser.parse_args()
    
    create_odds_proxy_for_year(args.year, args.rounds, args.test)


if __name__ == '__main__':
    main()
