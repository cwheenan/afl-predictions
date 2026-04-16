"""Extract odds from downloaded AFL fixture HTML and store in database."""
from bs4 import BeautifulSoup
from datetime import datetime
from afl_predictions.db import get_engine, get_session, Match, MatchOdds
import re

# Team name mapping (HTML name -> Database name)
TEAM_NAME_MAP = {
    'GWS GIANTS': 'Greater Western Sydney',
    'Adelaide Crows': 'Adelaide',
    'Sydney Swans': 'Sydney',
    'Geelong Cats': 'Geelong',
    'Gold Coast SUNS': 'Gold Coast',
    'Brisbane Lions': 'Brisbane Lions',
    'Western Bulldogs': 'Western Bulldogs',
    'West Coast Eagles': 'West Coast',
    'North Melbourne': 'North Melbourne',
    'Port Adelaide': 'Port Adelaide',
    'St Kilda': 'St Kilda',
    'Melbourne': 'Melbourne',
    'Carlton': 'Carlton',
    'Richmond': 'Richmond',
    'Essendon': 'Essendon',
    'Hawthorn': 'Hawthorn',
    'Collingwood': 'Collingwood',
    'Fremantle': 'Fremantle',
}

# Read the HTML file
with open('odds/round1.htm', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# Find all match fixtures
fixtures = soup.find_all('div', class_='fixtures__item')

engine = get_engine()
session = get_session(engine)

matches_with_odds = []

for fixture in fixtures:
    try:
        # Extract teams
        home_team_elem = fixture.find('div', class_='fixtures__match-team--home')
        away_team_elem = fixture.find('div', class_='fixtures__match-team--away')
        
        if not home_team_elem or not away_team_elem:
            continue
            
        home_team_name = home_team_elem.find('span', class_='fixtures__match-team-name')
        away_team_name = away_team_elem.find('span', class_='fixtures__match-team-name')
        
        if not home_team_name or not away_team_name:
            print("⚠ Missing team name spans")
            continue
            
        home_team = home_team_name.text.strip()
        away_team = away_team_name.text.strip()
        
        # Map to database team names
        home_team = TEAM_NAME_MAP.get(home_team, home_team)
        away_team = TEAM_NAME_MAP.get(away_team, away_team)
        
        print(f"Processing: {home_team} vs {away_team}")
        
        # Extract date
        date_header = fixture.find_previous('h2', class_='fixtures__date-header')
        date_str = date_header.text.strip() if date_header else ''
        
        # Extract time
        time_elem = fixture.find('div', class_='fixtures__status-label')
        time_str = ''
        if time_elem:
            time_div = time_elem.find('div')
            if time_div:
                time_str = time_div.text.strip()
        
        # Extract venue
        venue_elem = fixture.find('div', class_='fixtures__match-venue')
        venue = ''
        if venue_elem:
            venue_text = venue_elem.text.strip()
            # Parse venue (format: "MCG, Melbourne • Wurundjeri")
            venue = venue_text.split(',')[0].strip() if ',' in venue_text else venue_text.split('•')[0].strip()
        
        # Extract odds
        odds_div = fixture.find('div', class_='fixtures__betting-odds')
        home_odds = None
        away_odds = None
        
        if odds_div:
            odds_values = odds_div.find_all('a', class_='fixtures__betting-odds-value')
            if len(odds_values) >= 2:
                home_odds_str = odds_values[0].text.strip().replace('$', '')
                away_odds_str = odds_values[1].text.strip().replace('$', '')
                try:
                    home_odds = float(home_odds_str)
                    away_odds = float(away_odds_str)
                except (ValueError, IndexError):
                    pass
        
        if home_odds and away_odds:
            matches_with_odds.append({
                'home_team': home_team,
                'away_team': away_team,
                'date': date_str,
                'time': time_str,
                'venue': venue,
                'home_odds': home_odds,
                'away_odds': away_odds
            })
            print(f"Extracted: {home_team} (${home_odds}) vs {away_team} (${away_odds}) - {date_str}")
    
    except Exception as e:
        print(f"Error parsing fixture: {e}")
        continue

print(f"\nFound {len(matches_with_odds)} matches with odds")

# Now match these to database matches and store odds
timestamp = datetime.now()

for match_data in matches_with_odds:
    # Find matching fixture in database
    matches = session.query(Match).filter(
        Match.home_team == match_data['home_team'],
        Match.away_team == match_data['away_team']
    ).all()
    
    # Find the one from March 2026 without a score yet (upcoming match)
    db_match = None
    for m in matches:
        if m.date and '2026' in m.date and ('Mar' in m.date or '03' in m.date) and m.home_score is None:
            db_match = m
            break
    
    if db_match:
        # Check if odds already exist for this match
        existing_odds = session.query(MatchOdds).filter(
            MatchOdds.match_id == db_match.match_id,
            MatchOdds.source == 'sportsbet'
        ).first()
        
        if existing_odds:
            # Update existing odds
            existing_odds.home_win_odds = match_data['home_odds']
            existing_odds.away_win_odds = match_data['away_odds']
            existing_odds.timestamp = timestamp
            print(f"  Updated odds for {match_data['home_team']} vs {match_data['away_team']}")
        else:
            # Create new odds record
            odds = MatchOdds(
                match_id=db_match.match_id,
                source='sportsbet',
                home_win_odds=match_data['home_odds'],
                away_win_odds=match_data['away_odds'],
                timestamp=timestamp
            )
            session.add(odds)
            print(f"  Added odds for {match_data['home_team']} vs {match_data['away_team']}")
    else:
        print(f"  ⚠ No matching database entry found for {match_data['home_team']} vs {match_data['away_team']}")

session.commit()
print("\n✓ Odds stored successfully!")

# Verify
odds_count = session.query(MatchOdds).filter(MatchOdds.timestamp >= timestamp).count()
print(f"Total odds records created/updated: {odds_count}")
