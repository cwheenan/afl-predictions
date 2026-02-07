# Quick Reference: Key Data Sources
*For immediate implementation*

## Calculable Immediately (No External Data Needed)

### Days Rest
```python
# From Match table date field
# Calculate days between consecutive games for each team
# Implementation: Parse dates, sort by team and date, calculate diff
```

### Interstate Travel
```python
# Venue to team-home mapping
VENUES = {
    # VIC venues (10 teams: Carlton, Collingwood, Essendon, Geelong, Hawthorn, 
    #             Melbourne, North Melbourne, Richmond, St Kilda, Western Bulldogs)
    'M.C.G.': 'VIC',
    'Marvel Stadium': 'VIC',
    'Kardinia Park': 'VIC',
    
    # WA venues (2 teams: West Coast, Fremantle)
    'Subiaco': 'WA',
    'Optus Stadium': 'WA',
    'Perth Stadium': 'WA',
    
    # SA venues (2 teams: Adelaide, Port Adelaide)
    'Adelaide Oval': 'SA',
    'Football Park': 'SA',
    
    # NSW venues (1 team: Sydney)
    'S.C.G.': 'NSW',
    'Sydney Showground': 'NSW',
    'ANZ Stadium': 'NSW',
    'Stadium Australia': 'NSW',
    
    # QLD venues (3 teams: Brisbane, Gold Coast, Brisbane Bears historically)
    'Gabba': 'QLD',
    'Carrara': 'QLD',
    'Metricon Stadium': 'QLD',
    
    # TAS venues (no home team but games played there)
    'York Park': 'TAS',
    'Bellerive Oval': 'TAS',
    'UTAS Stadium': 'TAS',
    
    # NT venues (no home team but games played there)
    'Marrara Oval': 'NT',
    'TIO Stadium': 'NT',
    
    # Canberra (no home team but GWS plays games there)
    'Manuka Oval': 'ACT',
}

TEAM_HOME_STATES = {
    # VIC teams
    'Carlton': 'VIC', 'Collingwood': 'VIC', 'Essendon': 'VIC',
    'Geelong': 'VIC', 'Hawthorn': 'VIC', 'Melbourne': 'VIC',
    'North Melbourne': 'VIC', 'Richmond': 'VIC', 'St Kilda': 'VIC',
    'Western Bulldogs': 'VIC', 'Footscray': 'VIC',  # Historical name
    
    # Interstate teams
    'West Coast': 'WA', 'Fremantle': 'WA',
    'Adelaide': 'SA', 'Port Adelaide': 'SA',
    'Sydney': 'NSW', 'GWS': 'NSW', 'Greater Western Sydney': 'NSW',
    'Brisbane': 'QLD', 'Brisbane Lions': 'QLD', 'Brisbane Bears': 'QLD',
    'Gold Coast': 'QLD',
    
    # Historical teams
    'Fitzroy': 'VIC',
    'University': 'VIC',
}

# Feature: home_interstate = (team_home_state != venue_state)
```

### Ladder Position
```python
# Calculate from Match table results
def build_ladder(season_matches):
    """
    For each match, calculate ladder up to that point
    Points: 4 for win, 0 for loss, 2 for draw
    Percentage: (points for / points against) * 100
    """
    # Return: {match_id: {team: position}}
    pass
```

---

## High-Value External APIs (Free/Easy)

### 1. Squiggle API
**URL**: https://api.squiggle.com.au/
**Documentation**: https://api.squiggle.com.au/

**Endpoints**:
```bash
# Get all games for a year
GET https://api.squiggle.com.au/?q=games;year=2025

# Get tips for games
GET https://api.squiggle.com.au/?q=tips;year=2025

# Get sources (tipsters)
GET https://api.squiggle.com.au/?q=sources

# Get standings (ladder)
GET https://api.squiggle.com.au/?q=standings;year=2025
```

**Features Available**:
- Game results and scores
- Multiple tipster predictions (can ensemble)
- Tipster accuracy history
- ELO-style team ratings
- Margin predictions

**Value**: Can use as:
1. Feature (avg predicted margin from tipsters)
2. Ensemble member (treat as another model)
3. Benchmark (compare our accuracy to Squiggle sources)

**Rate Limits**: Generous, documented on site
**Cost**: FREE

---

### 2. Weather Data

#### Option A: Bureau of Meteorology (BOM)
**URL**: http://www.bom.gov.au/climate/data/
**Access**: Web interface for historical data
**Coverage**: All Australian cities
**Cost**: FREE

**Manual Process**:
1. Identify weather station near each venue
2. Download daily observations for match dates
3. Extract rainfall, temperature, wind

**Automation**: Would require scraping or finding unofficial API

#### Option B: Visual Crossing Weather API
**URL**: https://www.visualcrossing.com/
**Access**: REST API
**Historical Data**: Available back many years
**Cost**: FREE tier (1000 records/day)

```bash
# Example: Get weather for MCG on specific date
GET https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/-37.82,144.98/2025-03-20?key=YOUR_KEY

# Returns: temp, precip, wind, conditions
```

---

## Medium-Value Sources (Require Scraping)

### 3. AFL.com.au Match Centers
**Example URL**: https://www.afl.com.au/matches/2025/round-1/match-1
**Content**:
- Team lineups (when announced)
- Match stats
- Player stats
- Injury lists

**Scraping Strategy**:
```python
# 1. Build match URLs from token/date
# 2. Parse team list HTML tables
# 3. Extract injury status from text
# 4. Store in database
```

**Challenges**:
- Site structure may change
- Need to map team names consistently
- Historical lineups may not be complete

---

### 4. Betting Odds (Historical)

#### Option A: Odds Portal
**URL**: https://www.oddsportal.com/aussie-rules/australia/afl/
**Content**: Historical odds from multiple bookmakers
**Access**: Web scraping
**Challenge**: Terms of service, potential blocking

#### Option B: Australian TAB
**URL**: https://www.tab.com.au/
**Content**: Current and recent odds
**Challenge**: Historical data limited

#### Option C: Betfair Exchange
**URL**: https://www.betfair.com.au/
**Content**: Market odds (reflects true probabilities better)
**API**: Available but requires account
**Challenge**: Historical API access may require pro account

**Feature Engineering from Odds**:
```python
# Convert odds to implied probability
home_prob = 1 / home_odds
away_prob = 1 / away_odds

# Normalize (bookmaker margin)
total = home_prob + away_prob
home_prob_fair = home_prob / total
away_prob_fair = away_prob / total

# Use as features or training weights
```

---

## Database Schema Extensions

### New Tables Needed

```sql
-- Days rest and travel
CREATE TABLE match_context (
    match_id INTEGER PRIMARY KEY,
    home_days_rest INTEGER,
    away_days_rest INTEGER,
    home_interstate BOOLEAN,
    away_interstate BOOLEAN,
    home_travel_km FLOAT,
    away_travel_km FLOAT,
    rounds_remaining INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Ladder positions
CREATE TABLE match_ladder_positions (
    match_id INTEGER,
    team VARCHAR(100),
    ladder_position INTEGER,
    wins INTEGER,
    losses INTEGER,
    draws INTEGER,
    percentage FLOAT,
    in_top_eight BOOLEAN,
    can_make_finals BOOLEAN,
    PRIMARY KEY (match_id, team),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Weather
CREATE TABLE match_weather (
    match_id INTEGER PRIMARY KEY,
    temperature_c FLOAT,
    rainfall_mm FLOAT,
    wind_kmh FLOAT,
    conditions VARCHAR(50),  -- 'fine', 'rain', 'overcast'
    data_source VARCHAR(100),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Betting odds
CREATE TABLE match_odds (
    match_id INTEGER,
    bookmaker VARCHAR(100),
    home_odds FLOAT,
    away_odds FLOAT,
    line_spread FLOAT,  -- e.g., -12.5
    line_odds_home FLOAT,
    line_odds_away FLOAT,
    total_points FLOAT,
    timestamp DATETIME,
    PRIMARY KEY (match_id, bookmaker, timestamp),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- External predictions (Squiggle)
CREATE TABLE external_predictions (
    match_id INTEGER,
    source VARCHAR(100),
    home_predicted_score FLOAT,
    away_predicted_score FLOAT,
    predicted_margin FLOAT,
    confidence FLOAT,
    timestamp DATETIME,
    PRIMARY KEY (match_id, source),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);
```

---

## Next Actions

1. **Immediate** (Today):
   - ✅ Create venue state mapping
   - ✅ Implement days rest calculator
   - ✅ Implement interstate indicator
   - ✅ Test on small sample

2. **Tomorrow**:
   - ✅ Implement ladder position calculator
   - ✅ Add database tables
   - ✅ Test Squiggle API integration

3. **This Week**:
   - 🔍 Integrate weather data source
   - 🔍 Research betting odds options
   - 🔍 Plan AFL.com.au scraping

4. **Next Week**:
   - 🔍 Re-train models with new features
   - 🔍 Run walk-forward validation
   - 🔍 Measure improvement

---

*Last Updated: February 2, 2026*
