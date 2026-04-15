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

from afl_predictions.db import get_engine, get_session, Match, MatchOdds


def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string from database."""
    if not date_str:
        return None
    
    # Remove extra time in parentheses if present
    date_str = date_str.split('(')[0].strip()
    
    formats = [
        '%d-%b-%Y %I:%M %p',
        '%a, %d-%b-%Y %I:%M %p',
        '%Y-%m-%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


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
        'User-Agent': 'AFL-Predictions-POC/1.0 (Educational ML project; contact via GitHub)'
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
        'User-Agent': 'AFL-Predictions-POC/1.0 (Educational ML project; contact via GitHub)'
    }
    
    try:
        response = requests.get('https://api.squiggle.com.au/', params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tips = data.get('tips', [])
        if not tips:
            return {}
        
        # Get home and away teams from first tip
        if not tips:
            return {}
        
        first_tip = tips[0]
        home_team_name = first_tip.get('hteam', '')
        away_team_name = first_tip.get('ateam', '')
        
        # Count tips for home vs away
        # tip field contains the team name that was tipped
        home_tips = sum(1 for tip in tips if tip.get('tip') == home_team_name)
        away_tips = sum(1 for tip in tips if tip.get('tip') == away_team_name)
        total = home_tips + away_tips  # Some might be empty/None
        
        if total == 0:
            return {}
        
        # Convert to probabilities
        home_prob = home_tips / total
        away_prob = away_tips / total
        
        # Apply typical bookmaker margin (~6%)
        # This makes the odds sum to implied probability > 1.0
        margin = 1.06
        
        # Convert to decimal odds with margin
        if home_prob > 0:
            home_odds = min((1.0 / home_prob) * margin, 99.0)
        else:
            home_odds = 99.0
        
        if away_prob > 0:
            away_odds = min((1.0 / away_prob) * margin, 99.0)
        else:
            away_odds = 99.0
        
        return {
            'home_win_odds': round(home_odds, 2),
            'away_win_odds': round(away_odds, 2),
            'home_tips': home_tips,
            'away_tips': away_tips,
            'total_tips': total,
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
    if rounds_range:
        start, end = map(int, rounds_range.split('-'))
        rounds = list(range(start, end + 1))
        print(f"Processing rounds {start} to {end}")
    else:
        rounds = None
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
    
    for i, game in enumerate(all_games, 1):
        game_id = game.get('id')
        home_team = normalize_team_name(game.get('hteam', ''))
        away_team = normalize_team_name(game.get('ateam', ''))
        round_num = game.get('round', '?')
        date_str = game.get('date', '')
        
        print(f"\n[{i}/{len(all_games)}] Round {round_num}: {home_team} vs {away_team}")
        
        # Match to our database
        db_matches = db_session.query(Match).filter(
            and_(
                Match.home_team == home_team,
                Match.away_team == away_team
            )
        ).all()
        
        if not db_matches:
            print(f"  ⚠ No database match found")
            matches_not_found += 1
            continue
        
        # Find best match by date
        target_date = None
        try:
            target_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        except:
            pass
        
        best_match = None
        if target_date and len(db_matches) > 1:
            for db_match in db_matches:
                parsed_date = parse_date_string(db_match.date)
                if parsed_date and abs((parsed_date.date() - target_date).days) <= 3:
                    best_match = db_match
                    break
        
        if not best_match:
            best_match = db_matches[0]
        
        matches_found += 1
        
        # Check if odds already exist
        existing = db_session.query(MatchOdds).filter(
            and_(
                MatchOdds.match_id == best_match.match_id,
                MatchOdds.source == 'squiggle_consensus'
            )
        ).first()
        
        if existing:
            print(f"  ✓ Odds already exist (match_id {best_match.match_id})")
            continue
        
        # Fetch tipster predictions
        print(f"  Fetching tips for Squiggle game {game_id}...")
        tips_data = fetch_squiggle_tips(game_id)
        
        if not tips_data:
            print(f"  ⚠ No tips found for this game")
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
        
        print(f"  ✓ Stored odds: {tips_data['home_win_odds']} - {tips_data['away_win_odds']}")
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
