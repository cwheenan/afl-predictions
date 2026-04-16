#!/usr/bin/env python3
"""Load 2026 AFL fixture from Squiggle API into database.

This creates Match records for upcoming games so they can receive predictions.

Usage:
  python scripts/load_2026_fixture.py
  python scripts/load_2026_fixture.py --round 0  # Opening round only
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import time
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy import and_

from afl_predictions.config import SQUIGGLE_USER_AGENT
from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.match_identity import find_matching_matches, parse_match_datetime, select_canonical_match


def normalize_team_name(team: str) -> str:
    """Normalize team names between Squiggle and our DB."""
    if not team:
        return ''
    
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


def fetch_squiggle_games(year: int, round_num: Optional[int] = None):
    """Fetch fixture from Squiggle API."""
    params = {
        'q': 'games',
        'year': year,
    }
    
    if round_num is not None:
        params['round'] = round_num
    
    headers = {
        'User-Agent': SQUIGGLE_USER_AGENT,
    }
    
    try:
        print(f"Fetching {year} fixture from Squiggle API...")
        response = requests.get('https://api.squiggle.com.au/', 
                                params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        games = data.get('games', [])
        print(f"Found {len(games)} games")
        return games
    except requests.RequestException as e:
        print(f"Error fetching Squiggle games: {e}")
        return []


def load_fixture(year: int, round_num: Optional[int] = None):
    """Load fixture from Squiggle into database."""
    
    games = fetch_squiggle_games(year, round_num)
    
    if not games:
        print("No games found!")
        return
    
    engine = get_engine()
    session = get_session(engine)
    
    added_count = 0
    skipped_count = 0
    
    print(f"\n{'='*70}")
    print(f"LOADING {year} FIXTURE")
    print(f"{'='*70}\n")
    
    for i, game in enumerate(games, 1):
        home_team = normalize_team_name(game.get('hteam', ''))
        away_team = normalize_team_name(game.get('ateam', ''))
        venue = game.get('venue', '')
        date_str = game.get('date', '')
        round_str = str(game.get('round', ''))
        
        # Parse date and extract year
        target_dt = parse_match_datetime(date_str)
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            formatted_date = date_obj.strftime('%a, %d-%b-%Y %I:%M %p')
            season = date_obj.year
        except:
            formatted_date = date_str
            season = year
        
        existing_matches = find_matching_matches(
            session,
            Match,
            home_team,
            away_team,
            target_dt=target_dt,
            season=season,
        )
        existing = select_canonical_match(existing_matches, target_dt)
        
        if existing:
            if not existing.date:
                existing.date = formatted_date
            if not existing.venue:
                existing.venue = venue
            if not existing.season:
                existing.season = season
            if existing.round in (None, ''):
                existing.round = round_str
            session.add(existing)
            print(f"[{i}/{len(games)}] Round {round_str}: {home_team} vs {away_team} - ALREADY EXISTS")
            skipped_count += 1
            continue
        
        # Create new match record (match_id is auto-generated)
        new_match = Match(
            date=formatted_date,
            season=season,
            round=round_str,
            home_team=home_team,
            away_team=away_team,
            venue=venue,
            home_score=None,  # No score yet
            away_score=None
        )
        
        session.add(new_match)
        print(f"[{i}/{len(games)}] Round {round_str}: {home_team} vs {away_team}")
        print(f"              Date: {formatted_date}")
        print(f"              Venue: {venue}")
        print(f"              ✓ ADDED")
        added_count += 1
        
        # Commit every 10 matches
        if added_count % 10 == 0:
            session.commit()
            print(f"\n  [Progress: {added_count} matches added]\n")
    
    # Final commit
    session.commit()
    
    print(f"\n{'='*70}")
    print(f"COMPLETE")
    print(f"{'='*70}")
    print(f"Total games: {len(games)}")
    print(f"Added: {added_count}")
    print(f"Skipped (already exist): {skipped_count}")
    print(f"\nNext steps:")
    print(f"  1. Collect odds: python scripts/create_odds_proxy_from_squiggle.py --year {year}")
    print(f"  2. Generate predictions: python scripts/predict_upcoming.py --year {year}")
    
    session.close()


def main():
    parser = argparse.ArgumentParser(description='Load AFL fixture from Squiggle')
    parser.add_argument('--year', type=int, default=2026, help='Season year')
    parser.add_argument('--round', type=int, help='Specific round (e.g., 0 for opening round)')
    
    args = parser.parse_args()
    
    load_fixture(args.year, args.round)


if __name__ == '__main__':
    main()
