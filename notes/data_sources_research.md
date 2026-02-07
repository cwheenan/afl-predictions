# AFL Data Sources Research
*Research Date: February 2, 2026*

## Current Performance Gap
- **Current Model**: 68.8% accuracy (130/189 correct in 2025)
- **Human Performance**: 76.7% accuracy (145/189 correct)
- **Gap**: 15 predictions (7.9 percentage points)

## Objective
Identify publicly available data sources that could close the performance gap between ML models and human prediction accuracy.

---

## 1. OFFICIAL AFL DATA SOURCES

### AFL Tables (afltables.com)
**Current Status**: ✅ Already integrated
- Match results, scores, venues, dates
- Player statistics (goals, kicks, marks, etc.)
- Historical data back to 1897

**Missing from Current Implementation**:
- Player names and identifiers (we have stats but not linked to specific players)
- Team lineups per match (who actually played)
- Umpire information
- Attendance figures
- Game notes/commentary

**Potential Value**: HIGH - Already proven reliable source

### AFL.com.au Official Site
**Status**: 🔍 To investigate
- Official team lists (usually released Thursday before games)
- Injury lists and player availability
- Match previews and statistics
- Live scores and match center data
- Player profiles and career stats
- Brownlow votes and awards

**API Availability**: Likely has internal APIs (used by mobile apps)
**Access Method**: Web scraping or reverse engineering mobile app APIs
**Potential Value**: VERY HIGH - Real-time team selection data

### AFL Fantasy API
**Status**: 🔍 To investigate
- Player prices (reflects expected performance)
- Injury/suspension status
- Player roles/positions
- Ownership percentages (crowd wisdom)
- Live scoring data

**Potential Value**: HIGH - Fantasy prices incorporate injury news and form

---

## 2. SPORTS DATA PROVIDERS

### Squiggle API (squiggle.com.au)
**Status**: 🔍 To investigate
- Aggregates predictions from multiple tipsters
- Historical tipping accuracy by source
- ELO ratings for teams
- Game predictions with confidence levels
- Free API available

**Access**: Public API documented at api.squiggle.com.au
**Potential Value**: HIGH - Can use as ensemble feature or benchmark

### FiveThirtyEight Style ELO Systems
**Status**: 🔍 To research if available
- Team strength ratings
- Probability models
- Historical performance tracking

**Potential Value**: MEDIUM - Could use as features

### Betting Odds
**Status**: 🔍 To investigate
- TAB / Sportsbet / Bet365 odds
- Line betting (margin predictions)
- Over/under totals
- Opening vs closing odds (reflects injury news)

**Access Method**: Web scraping from betting sites
**Legal Considerations**: Check terms of service
**Potential Value**: VERY HIGH - Odds incorporate all public information including injuries, weather, motivation

---

## 3. FIXTURE AND CONTEXT DATA

### Days Between Games (Rest Days)
**Status**: ⚠️ Calculable from existing data
- Can derive from match dates we already have
- 5-day breaks vs 6-day vs 7+ day breaks
- Back-to-back away games

**Implementation**: Add date parsing and calculation
**Potential Value**: MEDIUM-HIGH - Known to affect performance

### Travel Distance
**Status**: 📊 Requires venue location data
- Distance between team's home city and venue
- Interstate vs intrastate games
- Perth teams traveling east coast (significant impact)

**Data Needed**: Stadium locations (lat/long)
**Implementation**: Geocoding venues, calculate distances
**Potential Value**: HIGH - Travel fatigue is documented factor

### Ladder Position
**Status**: ⚠️ Calculable from existing data
- Current season standing when match played
- Top 8 positioning pressure
- Mathematical finals elimination

**Implementation**: Calculate rolling ladder from results
**Potential Value**: MEDIUM - Affects motivation and pressure

### Weather Data
**Status**: 🔍 External API needed
- Temperature, rainfall, wind
- Historical weather at venue/date

**Potential Sources**:
- Bureau of Meteorology (BOM) historical data
- OpenWeatherMap API (limited historical)
- Weather Underground

**Potential Value**: MEDIUM - Rain affects scoring, wind affects accuracy

---

## 4. INJURY AND TEAM SELECTION DATA

### Official Team Lists
**Status**: 🔍 AFL.com.au or club websites
- Named teams (Thu before game)
- Late changes (90 min before bounce)
- Emergencies and substitutes
- Player positions

**Timing Challenge**: Need week-ahead data for predictions
**Potential Value**: VERY HIGH - Key injuries swing games

### Injury Lists
**Status**: 🔍 AFL.com.au injury tracker
- Test status, 1-2 weeks, season, indefinite
- Body part affected
- Injury history

**Potential Value**: VERY HIGH - Missing stars = different team strength

### Player Impact Metrics
**Status**: 📊 Calculate from stats
- Average Fantasy points
- Goals per game
- Champion Data rankings (if accessible)
- Brownlow votes as quality indicator

**Implementation**: Aggregate from AFL Tables player stats
**Potential Value**: HIGH - Weight team strength by player quality

---

## 5. SOCIAL MEDIA AND NEWS SOURCES

### AFL News Aggregators
**Status**: 🔍 To investigate
- AFL.com.au news section
- Club websites
- Fox Sports / ESPN
- The Age / Herald Sun sports sections

**Content**: 
- Team news, selection speculation
- Coach comments on preparation
- Player quotes and confidence

**Extraction**: Web scraping, NLP sentiment analysis?
**Potential Value**: LOW-MEDIUM - Hard to quantify, noisy

---

## 6. HISTORICAL PATTERNS FROM EXISTING DATA

### Rivalry Games
**Status**: ⚠️ Can identify from existing data
- Traditional rivalries (Carlton v Collingwood, etc.)
- Derby games (local derbies)
- Historical performance in rivalries

**Implementation**: Tag certain matchups as rivalry games
**Potential Value**: MEDIUM - May perform differently

### Finals Experience
**Status**: ⚠️ Can calculate from historical data
- Players' finals games played
- Recent finals appearance
- Premiership experience

**Implementation**: Track team finals history
**Potential Value**: MEDIUM - Experience matters in pressure games

### Coaching Records
**Status**: 🔍 Requires coach data collection
- Coach name per season
- Win/loss record
- First year vs experienced

**Potential Value**: MEDIUM - Coaching quality varies significantly

---

## 7. ADVANCED STATISTICS

### Champion Data (Stats Provider)
**Status**: 🔍 Commercial - likely too expensive
- Player ratings
- Expected score models
- Advanced metrics (contested possessions, etc.)

**Access**: Subscription/commercial licensing
**Potential Value**: HIGH but cost-prohibitive

### AFL Tables Player Pages
**Status**: ⚠️ Available but not yet scraped
- Individual player career stats
- Game-by-game performance
- Player ages, heights, weights

**Implementation**: Extend scraping to player pages
**Potential Value**: HIGH - Build player-level models

---

## PRIORITY RANKING

### Immediate High-Value Targets (Likely Biggest Impact):
1. **Betting Odds** - Incorporate all public info including injuries
2. **Days Rest / Fixture Congestion** - Calculable from existing data
3. **Travel Distance** - Requires venue geocoding
4. **Ladder Position** - Calculable from existing data
5. **Team Selection Data** - From AFL.com.au (requires scraping)

### Medium-Term Targets:
6. **Squiggle API** - Easy to integrate, crowd wisdom
7. **Player-level statistics** - From AFL Tables
8. **Weather data** - Historical weather APIs
9. **Rivalry/context indicators** - From existing data

### Lower Priority:
10. Social media sentiment
11. News article analysis
12. Commercial data providers

---

## NEXT STEPS

1. **Immediate Win**: Add calculable features from existing data
   - Days rest between games
   - Ladder position when playing
   - Travel indicator (interstate yes/no)

2. **High-Value Scraping**: 
   - Betting odds (if legally/ethically acceptable)
   - Team selections from AFL.com.au

3. **API Integration**:
   - Squiggle API for benchmarking
   - Weather API for historical conditions

4. **Data Infrastructure**:
   - Extend database schema for new features
   - Build scrapers for ongoing data collection
   - Create feature engineering pipeline

---

## LEGAL AND ETHICAL CONSIDERATIONS

- **Betting Data**: Check terms of service for scraping
- **AFL.com.au**: Respect robots.txt, rate limiting
- **Commercial APIs**: Review pricing and licensing
- **Personal Data**: Avoid collecting player personal information
- **Terms Compliance**: Ensure all scraping complies with site ToS

---

*Last Updated: February 2, 2026*
