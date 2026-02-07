#!/usr/bin/env python3
"""Backfill historical betting odds for 2025 AFL season.

Uses The Odds API to fetch historical odds data for completed matches.
This provides proof of concept for incorporating odds into predictions.

Usage:
  python scripts/backfill_odds_2025.py --api-key YOUR_KEY
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from sqlalchemy import and_

from afl_predictions.db import get_engine, get_session, Match, MatchOdds


class TheOddsAPIHistorical:
    """Fetch historical odds from The Odds API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = 'https://api.the-odds-api.com'
        self.headers = {
            'User-Agent': 'AFL-Predictions/1.0'
        }
        self.team_mappings = self._build_team_mappings()
    
    def _build_team_mappings(self) -> Dict[str, str]:
        """Map API team names to our database team names."""
        # The Odds API uses full names, we need to match to our DB
        return {
            'adelaide crows': 'Adelaide',
            'adelaide': 'Adelaide',
            'brisbane lions': 'Brisbane',
            'brisbane': 'Brisbane',
            'carlton': 'Carlton',
            'carlton blues': 'Carlton',
            'collingwood': 'Collingwood',
            'collingwood magpies': 'Collingwood',
            'essendon': 'Essendon',
            'essendon bombers': 'Essendon',
            'fremantle': 'Fremantle',
            'fremantle dockers': 'Fremantle',
            'geelong': 'Geelong',
            'geelong cats': 'Geelong',
            'gold coast': 'Gold Coast',
            'gold coast suns': 'Gold Coast',
            'gws': 'GWS',
            'gws giants': 'GWS',
            'greater western sydney': 'GWS',
            'greater western sydney giants': 'GWS',
            'hawthorn': 'Hawthorn',
            'hawthorn hawks': 'Hawthorn',
            'melbourne': 'Melbourne',
            'melbourne demons': 'Melbourne',
            'north melbourne': 'North Melbourne',
            'north melbourne kangaroos': 'North Melbourne',
            'kangaroos': 'North Melbourne',
            'port adelaide': 'Port Adelaide',
            'port adelaide power': 'Port Adelaide',
            'richmond': 'Richmond',
            'richmond tigers': 'Richmond',
            'st kilda': 'St Kilda',
            'st kilda saints': 'St Kilda',
            'sydney': 'Sydney',
            'sydney swans': 'Sydney',
            'west coast': 'West Coast',
            'west coast eagles': 'West Coast',
            'western bulldogs': 'Western Bulldogs',
            'bulldogs': 'Western Bulldogs',
            'footscray': 'Western Bulldogs',
        }
    
    def normalize_team(self, team_name: str) -> str:
        """Normalize team name to database format."""
        normalized = team_name.lower()
        return self.team_mappings.get(normalized, team_name)
    
    def fetch_odds_for_date(self, date: str) -> List[Dict]:
        """Fetch odds for a specific date (YYYY-MM-DD format).
        
        The Odds API historical endpoint requires ISO 8601 date format.
        Example: 2025-03-20T12:00:00Z
        """
        # Convert date to ISO format with time (midday)
        iso_date = f"{date}T12:00:00Z"
        
        endpoint = f"{self.base_url}/v4/historical/sports/aussierules_afl/odds"
        params = {
            'apiKey': self.api_key,
            'regions': 'au',
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'decimal',
            'date': iso_date,
        }
        
        print(f"  Fetching odds for {date}...")
        
        try:
            response = requests.get(endpoint, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # Check remaining requests
            remaining = response.headers.get('x-requests-remaining', 'unknown')
            used = response.headers.get('x-requests-used', 'unknown')
            print(f"  API usage: {used} used, {remaining} remaining")
            
            if not data or 'data' not in data:
                print(f"  No odds data found for {date}")
                return []
            
            matches_odds = []
            for game in data.get('data', []):
                home_team = self.normalize_team(game.get('home_team', ''))
                away_team = self.normalize_team(game.get('away_team', ''))
                commence_time = game.get('commence_time', '')
                
                # Extract bookmaker odds
                bookmakers = game.get('bookmakers', [])
                for bookie in bookmakers:
                    bookie_name = bookie.get('key', 'unknown')
                    markets = bookie.get('markets', [])
                    
                    odds_data = {
                        'home_team': home_team,
                        'away_team': away_team,
                        'commence_time': commence_time,
                        'source': bookie_name,
                        'home_win_odds': None,
                        'away_win_odds': None,
                        'home_line_odds': None,
                        'away_line_odds': None,
                        'line_spread': None,
                        'total_points': None,
                        'over_odds': None,
                        'under_odds': None,
                    }
                    
                    for market in markets:
                        if market['key'] == 'h2h':
                            outcomes = market.get('outcomes', [])
                            for outcome in outcomes:
                                team = self.normalize_team(outcome.get('name', ''))
                                if team == home_team:
                                    odds_data['home_win_odds'] = outcome.get('price')
                                elif team == away_team:
                                    odds_data['away_win_odds'] = outcome.get('price')
                        
                        elif market['key'] == 'spreads':
                            outcomes = market.get('outcomes', [])
                            for outcome in outcomes:
                                team = self.normalize_team(outcome.get('name', ''))
                                if team == home_team:
                                    odds_data['home_line_odds'] = outcome.get('price')
                                    odds_data['line_spread'] = outcome.get('point')
                                elif team == away_team:
                                    odds_data['away_line_odds'] = outcome.get('price')
                        
                        elif market['key'] == 'totals':
                            outcomes = market.get('outcomes', [])
                            for outcome in outcomes:
                                if outcome.get('name') == 'Over':
                                    odds_data['over_odds'] = outcome.get('price')
                                    odds_data['total_points'] = outcome.get('point')
                                elif outcome.get('name') == 'Under':
                                    odds_data['under_odds'] = outcome.get('price')
                    
                    matches_odds.append(odds_data)
            
            print(f"  Found {len(matches_odds)} odds records")
            return matches_odds
        
        except requests.RequestException as e:
            print(f"  Error fetching odds: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Response: {e.response.text[:200]}")
            return []
    
    def match_odds_to_db_match(self, session, odds: Dict) -> Optional[int]:
        """Find matching database match for odds data."""
        home_team = odds['home_team']
        away_team = odds['away_team']
        
        # Try to parse the commence_time
        try:
            commence_dt = datetime.fromisoformat(odds['commence_time'].replace('Z', '+00:00'))
            target_date = commence_dt.date()
        except:
            print(f"    WARNING: Could not parse commence time: {odds['commence_time']}")
            return None
        
        # Query for all matches with these teams
        matches = session.query(Match).filter(
            and_(
                Match.home_team == home_team,
                Match.away_team == away_team
            )
        ).all()
        
        # Find best match by date
        best_match = None
        best_diff = timedelta(days=999)
        
        for match in matches:
            parsed_date = parse_date_string(match.date)
            if not parsed_date:
                continue
            
            match_date = parsed_date.date()
            diff = abs((match_date - target_date).days)
            
            if diff < best_diff:
                best_diff = diff
                best_match = match
        
        if best_match and best_diff <= 2:  # Within 2 days
            return best_match.match_id
        else:
            # No match found
            print(f"    WARNING: No match found for {home_team} vs {away_team} on {odds['commence_time']}")
            return None


def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string from database.
    
    Formats:
    - "25-Jun-2022 4:35 PM"
    - "19-Mar-2022 2:10 PM (1:10 PM)" - with extra time in parentheses
    - "Fri, 17-Apr-2015 7:50 PM" - with day of week prefix
    """
    if not date_str:
        return None
    
    # Remove extra time in parentheses if present
    date_str = date_str.split('(')[0].strip()
    
    # Try different formats
    formats = [
        '%d-%b-%Y %I:%M %p',        # 25-Jun-2022 4:35 PM
        '%a, %d-%b-%Y %I:%M %p',    # Fri, 17-Apr-2015 7:50 PM
        '%Y-%m-%d',                  # 2025-03-20
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def backfill_2025_odds(api_key: str, limit: Optional[int] = None):
    """Backfill odds for all 2025 matches."""
    engine = get_engine()
    session = get_session(engine)
    
    print("\n=== Backfilling 2025 AFL Odds ===\n")
    
    # Get all matches and filter for 2025
    all_matches = session.query(Match).all()
    
    matches = []
    for match in all_matches:
        parsed_date = parse_date_string(match.date)
        if parsed_date and parsed_date.year == 2025:
            matches.append(match)
    
    # Sort by date
    matches.sort(key=lambda m: parse_date_string(m.date))
    
    print(f"Found {len(matches)} matches in 2025")
    
    if limit:
        matches = matches[:limit]
        print(f"Limited to first {limit} matches for testing")
    
    # Group matches by date to minimize API calls
    dates_to_fetch = []
    for match in matches:
        parsed_date = parse_date_string(match.date)
        if parsed_date:
            dates_to_fetch.append(parsed_date.strftime('%Y-%m-%d'))
    
    dates_to_fetch = sorted(set(dates_to_fetch))
    print(f"Unique dates to fetch: {len(dates_to_fetch)}")
    print(f"This will use approximately {len(dates_to_fetch)} API requests")
    print()
    
    api = TheOddsAPIHistorical(api_key)
    
    total_odds_stored = 0
    matches_with_odds = 0
    
    for date_str in dates_to_fetch:
        print(f"\nProcessing {date_str}:")
        
        # Fetch odds for this date
        odds_list = api.fetch_odds_for_date(date_str)
        
        if not odds_list:
            print(f"  No odds found for {date_str}")
            continue
        
        # Match odds to database matches
        for odds in odds_list:
            match_id = api.match_odds_to_db_match(session, odds)
            
            if match_id:
                # Check if odds already exist
                existing = session.query(MatchOdds).filter(
                    and_(
                        MatchOdds.match_id == match_id,
                        MatchOdds.source == odds['source']
                    )
                ).first()
                
                if existing:
                    print(f"    Odds already exist for match {match_id} from {odds['source']}")
                    continue
                
                # Store odds in database
                match_odds = MatchOdds(
                    match_id=match_id,
                    source=odds['source'],
                    home_win_odds=odds['home_win_odds'],
                    away_win_odds=odds['away_win_odds'],
                    home_line_odds=odds['home_line_odds'],
                    away_line_odds=odds['away_line_odds'],
                    line_spread=odds['line_spread'],
                    total_points=odds['total_points'],
                    over_odds=odds['over_odds'],
                    under_odds=odds['under_odds'],
                    timestamp=datetime.now()
                )
                
                session.add(match_odds)
                total_odds_stored += 1
                matches_with_odds += 1
                
                print(f"    ✓ Stored {odds['source']} odds for match {match_id}")
                print(f"      H2H: {odds['home_win_odds']} - {odds['away_win_odds']}")
        
        # Commit after each date
        session.commit()
        
        # Rate limiting - be nice to the API
        time.sleep(1)
    
    print(f"\n=== Backfill Complete ===")
    print(f"Total odds records stored: {total_odds_stored}")
    print(f"Matches with odds: {matches_with_odds}")
    print(f"Total matches: {len(matches)}")
    
    session.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill historical odds for 2025')
    parser.add_argument('--api-key', required=True, help='The Odds API key')
    parser.add_argument('--limit', type=int, help='Limit number of matches (for testing)')
    parser.add_argument('--test-first', action='store_true', help='Test with first 10 matches only')
    
    args = parser.parse_args()
    
    limit = 10 if args.test_first else args.limit
    
    backfill_2025_odds(args.api_key, limit)


if __name__ == '__main__':
    main()
