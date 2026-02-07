#!/usr/bin/env python3
"""Collect and store betting odds data for AFL matches.

This module handles fetching odds from various Australian sportsbooks and
storing them for use in prediction models.

Sources:
- TAB.com.au (government-owned, reliable)
- Sportsbet.com.au (popular bookmaker)
- Bet365 (international with AU presence)

Usage:
  python scripts/collect_odds.py --fetch-current
  python scripts/collect_odds.py --backfill-2025
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
from bs4 import BeautifulSoup

from afl_predictions.db import get_engine, get_session, Match


# Database schema for odds (will need to add this to db.py)
"""
CREATE TABLE IF NOT EXISTS match_odds (
    match_id INTEGER NOT NULL,
    source VARCHAR(50) NOT NULL,
    home_win_odds REAL,
    away_win_odds REAL,
    home_line_odds REAL,
    away_line_odds REAL,
    line_spread REAL,
    total_points REAL,
    over_odds REAL,
    under_odds REAL,
    timestamp DATETIME NOT NULL,
    PRIMARY KEY (match_id, source, timestamp),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);
"""


class OddsCollector:
    """Base class for odds collection from various sources."""
    
    def __init__(self, session):
        self.session = session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_match_odds(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """Fetch odds for a specific match. Override in subclasses."""
        raise NotImplementedError
    
    def normalize_team_name(self, team_name: str) -> str:
        """Normalize team names to match database format."""
        # Common variations
        mappings = {
            'Western Bulldogs': 'Western Bulldogs',
            'Bulldogs': 'Western Bulldogs',
            'Footscray': 'Western Bulldogs',
            'Brisbane Lions': 'Brisbane',
            'Brisbane': 'Brisbane',
            'GWS Giants': 'GWS',
            'GWS': 'GWS',
            'Greater Western Sydney': 'GWS',
            'Port Adelaide': 'Port Adelaide',
            'North Melbourne': 'North Melbourne',
            'Kangaroos': 'North Melbourne',
            'Sydney Swans': 'Sydney',
            'Sydney': 'Sydney',
            'Gold Coast Suns': 'Gold Coast',
            'Gold Coast': 'Gold Coast',
        }
        return mappings.get(team_name, team_name)
    
    def odds_to_probability(self, decimal_odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if decimal_odds <= 1.0:
            return 0.0
        return 1.0 / decimal_odds
    
    def remove_vig(self, home_odds: float, away_odds: float) -> tuple[float, float]:
        """Remove bookmaker margin (vig) to get fair probabilities."""
        home_prob = self.odds_to_probability(home_odds)
        away_prob = self.odds_to_probability(away_odds)
        
        total = home_prob + away_prob
        if total <= 0:
            return 0.5, 0.5
        
        # Normalize to sum to 1.0
        fair_home = home_prob / total
        fair_away = away_prob / total
        
        return fair_home, fair_away


class TABOddsCollector(OddsCollector):
    """Collect odds from TAB.com.au (government-owned bookmaker)."""
    
    def __init__(self, session):
        super().__init__(session)
        self.base_url = 'https://www.tab.com.au'
    
    def fetch_afl_matches(self) -> List[Dict]:
        """Fetch all upcoming AFL matches with odds."""
        # Note: This is a placeholder. Actual implementation would need to:
        # 1. Navigate to AFL section
        # 2. Parse match listings
        # 3. Extract odds data
        
        # TAB typically has JSON APIs that power their site
        # Example endpoint (would need to inspect network traffic):
        # https://api.tab.com.au/v1/sports/afl/matches
        
        print("TAB odds collection - implementation needed")
        print("Would need to:")
        print("1. Inspect TAB website's network requests")
        print("2. Find JSON API endpoints")
        print("3. Parse match and odds data")
        return []


class SportsbetOddsCollector(OddsCollector):
    """Collect odds from Sportsbet.com.au."""
    
    def __init__(self, session):
        super().__init__(session)
        self.base_url = 'https://www.sportsbet.com.au'
    
    def fetch_afl_matches(self) -> List[Dict]:
        """Fetch all upcoming AFL matches with odds."""
        # Similar to TAB - would need API endpoint discovery
        print("Sportsbet odds collection - implementation needed")
        return []


class OddsAPICollector(OddsCollector):
    """Collect odds from The Odds API (aggregator service)."""
    
    def __init__(self, session, api_key: str):
        super().__init__(session)
        self.api_key = api_key
        self.base_url = 'https://api.the-odds-api.com'
    
    def fetch_afl_matches(self) -> List[Dict]:
        """Fetch AFL odds from The Odds API."""
        # The Odds API provides odds from multiple bookmakers
        # Free tier: 500 requests/month
        # Paid tiers available
        
        endpoint = f"{self.base_url}/v4/sports/aussierules_afl/odds"
        params = {
            'apiKey': self.api_key,
            'regions': 'au',  # Australian bookmakers
            'markets': 'h2h,spreads,totals',  # Head to head, line, totals
            'oddsFormat': 'decimal',
        }
        
        try:
            response = requests.get(endpoint, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            matches = []
            for game in data:
                home_team = self.normalize_team_name(game['home_team'])
                away_team = self.normalize_team_name(game['away_team'])
                commence_time = game['commence_time']
                
                # Extract bookmaker odds
                bookmakers = game.get('bookmakers', [])
                for bookie in bookmakers:
                    bookie_name = bookie['key']
                    markets = bookie.get('markets', [])
                    
                    odds_data = {
                        'home_team': home_team,
                        'away_team': away_team,
                        'commence_time': commence_time,
                        'source': bookie_name,
                    }
                    
                    for market in markets:
                        if market['key'] == 'h2h':
                            outcomes = market['outcomes']
                            for outcome in outcomes:
                                if outcome['name'] == home_team:
                                    odds_data['home_win_odds'] = outcome['price']
                                elif outcome['name'] == away_team:
                                    odds_data['away_win_odds'] = outcome['price']
                        
                        elif market['key'] == 'spreads':
                            outcomes = market['outcomes']
                            for outcome in outcomes:
                                if outcome['name'] == home_team:
                                    odds_data['home_line_odds'] = outcome['price']
                                    odds_data['line_spread'] = outcome['point']
                                elif outcome['name'] == away_team:
                                    odds_data['away_line_odds'] = outcome['price']
                        
                        elif market['key'] == 'totals':
                            outcomes = market['outcomes']
                            for outcome in outcomes:
                                if outcome['name'] == 'Over':
                                    odds_data['over_odds'] = outcome['price']
                                    odds_data['total_points'] = outcome['point']
                                elif outcome['name'] == 'Under':
                                    odds_data['under_odds'] = outcome['price']
                    
                    matches.append(odds_data)
            
            return matches
        
        except requests.RequestException as e:
            print(f"Error fetching from Odds API: {e}")
            return []


def store_odds(session, match_id: int, odds_data: Dict):
    """Store odds data in database."""
    # This would insert into match_odds table
    # For now, just save to JSON file
    
    output_dir = Path('data/raw/odds')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f'match_{match_id}_odds.json'
    
    if output_file.exists():
        with open(output_file, 'r') as f:
            existing = json.load(f)
    else:
        existing = []
    
    existing.append({
        **odds_data,
        'timestamp': datetime.now().isoformat()
    })
    
    with open(output_file, 'w') as f:
        json.dump(existing, f, indent=2)
    
    print(f"Stored odds for match {match_id}: {odds_data.get('source', 'unknown')}")


def fetch_current_odds(session, api_key: Optional[str] = None):
    """Fetch current odds for upcoming matches."""
    print("\n=== Fetching Current AFL Odds ===\n")
    
    if api_key:
        collector = OddsAPICollector(session, api_key)
        matches = collector.fetch_afl_matches()
        
        print(f"Found {len(matches)} odds records from Odds API")
        
        for odds in matches:
            print(f"\n{odds['home_team']} vs {odds['away_team']}")
            print(f"  Source: {odds['source']}")
            if 'home_win_odds' in odds:
                print(f"  Head to Head: {odds.get('home_win_odds')} - {odds.get('away_win_odds')}")
            if 'line_spread' in odds:
                print(f"  Line: {odds.get('line_spread')} @ {odds.get('home_line_odds')}")
            if 'total_points' in odds:
                print(f"  Total: {odds.get('total_points')} (O: {odds.get('over_odds')}, U: {odds.get('under_odds')})")
    else:
        print("No API key provided. Available collectors:")
        print("  - TAB.com.au (requires implementation)")
        print("  - Sportsbet.com.au (requires implementation)")
        print("  - The Odds API (requires API key)")
        print("\nGet free API key at: https://the-odds-api.com/")


def main():
    parser = argparse.ArgumentParser(description='Collect betting odds for AFL matches')
    parser.add_argument('--fetch-current', action='store_true', help='Fetch current odds for upcoming matches')
    parser.add_argument('--api-key', type=str, help='The Odds API key')
    parser.add_argument('--source', choices=['tab', 'sportsbet', 'oddsapi'], default='oddsapi',
                       help='Odds source to use')
    
    args = parser.parse_args()
    
    engine = get_engine()
    session = get_session(engine)
    
    if args.fetch_current:
        fetch_current_odds(session, args.api_key)
    else:
        print("No action specified. Use --fetch-current to fetch odds.")
        print("Example: python scripts/collect_odds.py --fetch-current --api-key YOUR_KEY")


if __name__ == '__main__':
    main()
