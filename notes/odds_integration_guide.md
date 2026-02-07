# Betting Odds Integration Guide

## Overview
Betting odds are the single most valuable feature for AFL prediction as they incorporate:
- Injury news and team selection
- Weather forecasts
- Expert analysis
- Public sentiment
- All other available information

## Data Sources

### 1. The Odds API (Recommended for Development)
**URL**: https://the-odds-api.com/
**Cost**: Free tier (500 requests/month), Paid from $49/month
**Coverage**: Multiple Australian bookmakers (TAB, Sportsbet, Bet365, etc.)
**Format**: Clean JSON API
**Historical**: Not available on free tier

**Advantages**:
- Aggregates multiple bookmakers
- Clean, documented API
- Easy to integrate
- Normalized team names

**Setup**:
```bash
# 1. Register at https://the-odds-api.com/
# 2. Get API key from dashboard
# 3. Test endpoint:
curl "https://api.the-odds-api.com/v4/sports/aussierules_afl/odds?apiKey=YOUR_KEY&regions=au&markets=h2h"
```

### 2. Direct Bookmaker Sites (For Production)
**TAB.com.au**:
- Government-owned, reliable
- Has JSON APIs (need to discover endpoints)
- Method: Inspect network traffic in browser dev tools

**Sportsbet.com.au**:
- Popular Australian bookmaker
- Mobile app likely uses JSON API
- Method: Reverse engineer app or inspect site

**Bet365**:
- International bookmaker with AU presence
- Has odds for all matches

## Feature Engineering from Odds

### Basic Features (Direct from Odds)
```python
# From head-to-head (H2H) odds
home_odds = 1.85  # Example: home team at $1.85
away_odds = 2.10  # Example: away team at $2.10

# Convert to implied probability
home_prob_raw = 1 / home_odds  # = 0.541
away_prob_raw = 1 / away_odds  # = 0.476
total = home_prob_raw + away_prob_raw  # = 1.017 (>1 due to bookmaker margin)

# Remove bookmaker margin (vig)
home_prob_fair = home_prob_raw / total  # = 0.532
away_prob_fair = away_prob_raw / total  # = 0.468

# Features:
- odds_home_prob: fair probability of home win
- odds_away_prob: fair probability of away win
- odds_favorite: 1 if home favored, 0 if away favored
- odds_favorite_prob: probability of favorite winning
- odds_underdog_prob: probability of underdog winning
```

### Line Betting Features
```python
# Line betting (handicap)
line_spread = -12.5  # Home team giving 12.5 points
home_line_odds = 1.90
away_line_odds = 1.90

# Features:
- odds_line_spread: the handicap (negative = home favored)
- odds_line_home_prob: probability home covers line
- odds_line_away_prob: probability away covers line
- odds_expected_margin: implied margin from line
```

### Total Points Features
```python
# Over/Under total points
total_points = 165.5
over_odds = 1.90
under_odds = 1.90

# Features:
- odds_total_points: expected total score
- odds_over_prob: probability of high scoring
- odds_under_prob: probability of low scoring
```

### Derived Features
```python
# Strength of favorite
favorite_strength = odds_favorite_prob - 0.5  # Distance from 50/50

# Uncertainty
uncertainty = 1 - abs(home_prob_fair - away_prob_fair)  # Close to 0.5 = uncertain

# Odds movement (if have multiple timestamps)
odds_drift_home = current_odds - opening_odds  # Positive = drifting
odds_steam_home = opening_odds - current_odds  # Positive = steaming (money coming in)
```

## Integration into Models

### Approach 1: Direct Features (Simple)
Add odds-derived probabilities as features alongside existing stats:
```python
features = {
    # Existing features
    'diff_goals': 2.3,
    'diff_kicks': 15.2,
    # ... other stats
    
    # New odds features
    'odds_home_prob': 0.532,
    'odds_away_prob': 0.468,
    'odds_favorite': 1,
    'odds_line_spread': -12.5,
    'odds_total_points': 165.5,
}
```

**Advantages**:
- Easy to implement
- Model learns how to weight odds vs stats
- Can capture non-linear relationships

### Approach 2: Ensemble with Odds (Hybrid)
Use odds probability as a separate model in ensemble:
```python
# Get predictions from each model
rf_pred = 0.62  # Random forest prediction
lr_pred = 0.58  # Logistic regression prediction
odds_pred = 0.53  # Fair probability from odds

# Ensemble
final_pred = 0.3 * rf_pred + 0.3 * lr_pred + 0.4 * odds_pred
```

**Advantages**:
- Odds get significant weight (they should!)
- Still benefit from stat-based models
- Easy to adjust weights

### Approach 3: Odds as Target Calibration
Use odds to calibrate model outputs:
```python
# Model gives 70% confidence but odds say 55%
# Adjust toward odds (odds likely more accurate)

calibrated = 0.7 * model_pred + 0.3 * odds_pred
```

## Expected Impact

Based on literature and betting markets:
- Odds alone: ~72-75% accuracy (professional tipsters)
- Stats alone: ~68-69% accuracy (our current models)
- Odds + Stats ensemble: ~74-77% accuracy (combining both approaches)

**Target with odds integration**: 74-76% accuracy (140-143/189 correct in 2025)

## Implementation Checklist

### Phase 1: Infrastructure
- [ ] Add match_odds table to database
- [ ] Create OddsCollector classes for each source
- [ ] Test data collection for current round
- [ ] Store odds in database

### Phase 2: Historical Data
- [ ] Backfill 2025 season odds (if available)
- [ ] Handle missing odds (some matches may not have historical data)
- [ ] Validate odds data quality

### Phase 3: Feature Engineering
- [ ] Add odds_home_prob, odds_away_prob features
- [ ] Add line_spread, total_points features
- [ ] Test feature extraction on sample matches

### Phase 4: Model Integration
- [ ] Retrain models with odds features
- [ ] Test ensemble with odds as separate model
- [ ] Compare accuracies: stats-only vs odds-only vs hybrid

### Phase 5: Production
- [ ] Automate odds collection before each round
- [ ] Handle late odds updates (closer to game time)
- [ ] Monitor odds vs actual results for calibration

## Handling Missing Historical Odds

For historical validation (2025 walk-forward), we may not have odds data. Options:

1. **Use Squiggle predictions as proxy**:
   - Squiggle aggregates expert tipsters
   - Available historically
   - Similar concept to odds probabilities

2. **Impute from margin-based models**:
   - Train separate model to predict odds from stats
   - Use predicted odds when actual odds missing
   - Less accurate but better than nothing

3. **Train on 2026 forward only**:
   - Accept can't validate historically
   - Start collecting odds from now
   - Validate as season progresses

## Legal and Ethical Notes

✅ **Legal in Australia**: Gambling and odds collection is legal
✅ **Public Information**: Odds are publicly displayed
✅ **Terms of Service**: Check each bookmaker's ToS for scraping
✅ **Rate Limiting**: Respect site limits, use delays
✅ **Purpose**: For prediction, not for gambling systems (check local laws)

## Next Steps

1. **Get The Odds API key** (free tier for testing)
2. **Test current round collection**: `python scripts/collect_odds.py --fetch-current --api-key YOUR_KEY`
3. **Add database table** for odds storage
4. **Integrate as features** in next model training
5. **Measure improvement** with walk-forward validation (when odds available)

## Resources

- The Odds API: https://the-odds-api.com/
- Australian Bookmakers: TAB, Sportsbet, Bet365, Ladbrokes, Neds
- Squiggle (alternative): https://squiggle.com.au/
- Odds formats: https://www.oddsportal.com/bet-calculator/

---

*Last Updated: February 2, 2026*
