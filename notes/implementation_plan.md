# Implementation Plan: Closing the Performance Gap
*Date: February 2, 2026*

## Goal
Improve model accuracy from 68.8% to target 76%+ (matching human performance)

## Phase 1: Quick Wins (Calculable from Existing Data)
**Estimated Impact**: +2-3 percentage points
**Timeline**: 1-2 days

### 1.1 Days Rest / Fixture Congestion
**Implementation**:
```python
def calculate_days_rest(session, team_name, match_date, match_id):
    """Calculate days since team's previous match"""
    # Find previous match for this team before this date
    # Return days difference
    pass

# Features to add:
- home_days_rest
- away_days_rest  
- diff_days_rest
- home_short_break (< 6 days)
- away_short_break (< 6 days)
```

**Expected Impact**: HIGH - Short breaks known to reduce performance

### 1.2 Travel Distance
**Implementation**:
```python
# Create venue location mapping
VENUE_LOCATIONS = {
    'M.C.G.': {'city': 'Melbourne', 'state': 'VIC', 'lat': -37.82, 'lon': 144.98},
    'Marvel Stadium': {'city': 'Melbourne', 'state': 'VIC', ...},
    'Optus Stadium': {'city': 'Perth', 'state': 'WA', ...},
    # ... etc
}

TEAM_HOME_CITIES = {
    'West Coast': 'Perth',
    'Fremantle': 'Perth',
    'Adelaide': 'Adelaide',
    # ... etc
}

def calculate_travel_distance(team, venue):
    """Calculate km traveled for team to venue"""
    pass

# Features to add:
- home_travel_km
- away_travel_km
- home_interstate (boolean)
- away_interstate (boolean)
```

**Expected Impact**: HIGH - Perth teams traveling east are fatigued

### 1.3 Current Season Form (Ladder Position)
**Implementation**:
```python
def calculate_ladder_position(session, team, before_match_id, season):
    """Calculate team's ladder position at time of match"""
    # Get all matches this season before this match_id
    # Calculate wins, losses, percentage
    # Rank teams
    pass

# Features to add:
- home_ladder_pos (1-18)
- away_ladder_pos (1-18)
- home_in_eight (boolean - finals contention)
- away_in_eight (boolean)
- diff_ladder_pos
```

**Expected Impact**: MEDIUM - Pressure and motivation factors

### 1.4 Game Importance Context
**Implementation**:
```python
# Features to add:
- rounds_remaining (pressure increases late season)
- home_can_make_finals (mathematically alive)
- away_can_make_finals
- derby_game (both teams same city)
- rivalry_game (historical rivals)
```

**Expected Impact**: MEDIUM - Dead rubbers vs crucial games

---

## Phase 2: Betting Odds Integration
**Estimated Impact**: +3-5 percentage points
**Timeline**: 2-3 days
**Challenge**: Legal/ethical scraping

### 2.1 Historical Odds Collection
**Sources to Investigate**:
- TAB.com.au (historical odds)
- Odds comparison sites (oddsportal.com, etc.)
- Betting exchange data (Betfair)

**Implementation**:
```python
# Database schema addition
class MatchOdds:
    match_id: int
    home_odds: float  # e.g., 1.85
    away_odds: float  # e.g., 2.10
    line: float  # e.g., -12.5 points
    total: float  # e.g., 165.5 total points
    source: str
    timestamp: datetime
```

**Features to add**:
- implied_home_prob (from odds)
- implied_away_prob
- favorite_indicator
- line_spread
- odds_movement (if multiple timestamps available)

**Expected Impact**: VERY HIGH - Odds incorporate injuries, weather, expert analysis

### 2.2 Alternative: Squiggle Predictions as Proxy
If betting odds unavailable, use community predictions:
```python
# Squiggle API: api.squiggle.com.au
# Provides aggregated expert predictions
# Free and documented
```

---

## Phase 3: Team Selection Data
**Estimated Impact**: +2-4 percentage points
**Timeline**: 3-5 days
**Challenge**: Requires AFL.com.au scraping

### 3.1 Player Availability
**Implementation**:
```python
# Track key player absences
class PlayerAvailability:
    match_id: int
    team: str
    missing_players: List[str]
    missing_fantasy_value: float  # Sum of missing players' avg fantasy
    key_forward_out: bool
    key_defender_out: bool
    ruckman_out: bool
```

**Features to add**:
- home_team_strength (% of best 22 available)
- away_team_strength
- home_missing_stars (count of high-impact players)
- away_missing_stars

**Expected Impact**: VERY HIGH - Key injuries dramatically affect outcomes

### 3.2 Player Performance Tracking
**Implementation**:
```python
# Aggregate player-level stats
def calculate_team_quality(session, team, match_id):
    """Sum recent fantasy scores of available players"""
    # Get players who played for team in recent matches
    # Weight by recency and performance
    pass
```

**Expected Impact**: HIGH - Better measure of actual team strength

---

## Phase 4: Weather Data
**Estimated Impact**: +1-2 percentage points
**Timeline**: 2-3 days

### 4.1 Historical Weather
**Source**: Bureau of Meteorology (BOM)
- Historical rainfall data
- Temperature
- Wind speed

**Implementation**:
```python
class MatchWeather:
    match_id: int
    rainfall_mm: float
    temperature_c: float
    wind_kmh: float
    conditions: str  # 'fine', 'rain', 'wet'

# Features to add:
- wet_weather (boolean)
- extreme_temp (< 10°C or > 30°C)
- high_wind (> 30 km/h)
```

**Expected Impact**: MEDIUM - Rain favors defensive teams, affects scoring

---

## Phase 5: Advanced Features
**Estimated Impact**: +1-2 percentage points
**Timeline**: Ongoing

### 5.1 Momentum Indicators
```python
# Recent winning/losing streaks
- home_win_streak (0, 1, 2, 3+)
- away_win_streak
- home_big_win_last (won by 50+ last game)
```

### 5.2 Matchup History
```python
# Specific team vs team patterns
- h2h_recent_dominance (one team won last 4+ meetings)
- avg_margin_in_h2h_last_5
```

### 5.3 Coaching Stability
```python
# Coach changes and experience
- home_coach_tenure (games coached this team)
- away_coach_tenure
- new_coach_indicator (first 10 games)
```

---

## Implementation Priority Order

**Week 1: Foundation (Existing Data)**
1. ✅ Days rest calculation
2. ✅ Travel distance/interstate flags
3. ✅ Ladder position tracking
4. ✅ Game context (rounds remaining, finals alive)

**Week 2: External Data Collection**
5. 🔍 Squiggle API integration (easy)
6. 🔍 Betting odds scraping (if feasible)
7. 🔍 Weather data (BOM historical)

**Week 3: Player-Level Data**
8. 🔍 AFL.com.au team list scraping
9. 🔍 Player injury tracking
10. 🔍 Player performance aggregation

**Week 4: Testing and Refinement**
11. ✅ Re-run walk-forward validation
12. ✅ Feature importance analysis
13. ✅ Model retraining with new features

---

## Success Metrics

**Baseline**: 68.8% (130/189 correct)
**Target**: 76.0% (143/189 correct) - matching human performance
**Stretch**: 78.0% (147/189 correct) - exceeding human performance

**Incremental Targets**:
- Phase 1 complete: 71% (134/189) [+4 predictions]
- Phase 2 complete: 74% (140/189) [+10 predictions]
- Phase 3 complete: 76% (143/189) [+13 predictions]

---

## Risk Assessment

**High Risk**:
- Betting odds scraping may violate ToS
- AFL.com.au may block aggressive scraping
- Team selection data may not be available historically

**Mitigation**:
- Use Squiggle API as alternative to betting odds
- Implement polite scraping with delays and user agents
- Start with 2025 data, expand backwards if possible

**Medium Risk**:
- New features may not improve model (like previous attempt)
- Overfitting on 2025 data
- Data collection takes longer than expected

**Mitigation**:
- Test each feature group separately
- Maintain train/test separation rigorously
- Parallel implementation of multiple feature sources

---

*Last Updated: February 2, 2026*
