"""Manually update 2026 Opening Round results."""
from afl_predictions.db import get_engine, get_session, Match
import sqlalchemy as sa

engine = get_engine()
session = get_session(engine)

# Opening Round 2026 results from AFLTables
opening_round_results = [
    {
        'date': 'Thu, 05-Mar-2026 07:30 PM',
        'home_team': 'Sydney',
        'away_team': 'Carlton',
        'home_score': 132,
        'away_score': 69,
        'venue': 'S.C.G.'
    },
    {
        'date': 'Fri, 06-Mar-2026 07:05 PM',
        'home_team': 'Gold Coast',
        'away_team': 'Geelong',
        'home_score': 125,
        'away_score': 69,
        'venue': 'Carrara'
    },
    {
        'date': 'Sat, 07-Mar-2026 04:15 PM',
        'home_team': 'Greater Western Sydney',
        'away_team': 'Hawthorn',
        'home_score': 122,
        'away_score': 95,
        'venue': 'Sydney Showground'
    },
    {
        'date': 'Sat, 07-Mar-2026 06:35 PM',
        'home_team': 'Brisbane Lions',
        'away_team': 'Western Bulldogs',
        'home_score': 106,
        'away_score': 111,
        'venue': 'Gabba'
    },
    {
        'date': 'Sun, 08-Mar-2026 07:20 PM',
        'home_team': 'St Kilda',
        'away_team': 'Collingwood',
        'home_score': 66,
        'away_score': 78,
        'venue': 'M.C.G.'
    }
]

for result in opening_round_results:
    # Find match by teams and approximate date
    from datetime import datetime
    matches = session.query(Match).filter(
        Match.home_team == result['home_team'],
        Match.away_team == result['away_team']
    ).all()
    
    # Find the one from March 2026
    match = None
    for m in matches:
        if m.date and '2026' in m.date and ('Mar' in m.date or '03' in m.date):
            match = m
            break
    
    if match:
        match.home_score = result['home_score']
        match.away_score = result['away_score']
        if not match.venue or match.venue == '':
            match.venue = result['venue']
        session.add(match)
        print(f"Updated: {result['home_team']} {result['home_score']} vs {result['away_score']} {result['away_team']}")
    else:
        # Create new match if not found
        new_match = Match(
            date=result['date'],
            home_team=result['home_team'],
            away_team=result['away_team'],
            home_score=result['home_score'],
            away_score=result['away_score'],
            venue=result['venue'],
            season=2026,
            round='1',
            round_num=1
        )
        session.add(new_match)
        print(f"Created: {result['home_team']} {result['home_score']} vs {result['away_score']} {result['away_team']}")

session.commit()
print("\nOpening Round 2026 results updated successfully!")

# Verify
matches =  [m for m in session.query(Match).all() if m.date and '2026' in m.date and m.home_score is not None]
print(f"\nTotal 2026 matches with scores: {len(matches)}")
for m in sorted(matches, key=lambda x: x.date):
    print(f"  {m.date}: {m.home_team} {m.home_score} vs {m.away_score} {m.away_team}")
