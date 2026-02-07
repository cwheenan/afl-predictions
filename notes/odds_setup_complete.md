# Betting Odds Integration - Setup Complete

## What's Been Implemented

### 1. Database Schema ✅
- Added `MatchOdds` table to database
- Stores: H2H odds, line betting, totals, timestamps
- Foreign key to matches table
- Supports multiple bookmaker sources

### 2. Data Collection Framework ✅
**File**: `scripts/collect_odds.py`

**Features**:
- `OddsCollector` base class for different bookmakers
- `OddsAPICollector` - Integrates with The Odds API (multiple bookmakers aggregated)
- `TABOddsCollector` - Placeholder for TAB.com.au (needs implementation)
- `SportsbetOddsCollector` - Placeholder for Sportsbet (needs implementation)
- Odds normalization and probability conversion
- Bookmaker margin (vig) removal

### 3. Documentation ✅
**File**: `notes/odds_integration_guide.md`

**Covers**:
- Data sources comparison
- Feature engineering from odds
- Three integration approaches (features, ensemble, calibration)
- Expected impact analysis
- Implementation checklist
- Legal and ethical considerations

## Next Steps to Use Odds

### Option 1: The Odds API (Quick Start - Recommended)
**Best for**: Immediate testing and development

1. **Get API Key**:
   - Visit https://the-odds-api.com/
   - Sign up for free account
   - Get API key from dashboard
   - Free tier: 500 requests/month

2. **Test Current Odds**:
   ```bash
   python scripts/collect_odds.py --fetch-current --api-key YOUR_KEY_HERE
   ```

3. **Features**:
   - Aggregates TAB, Sportsbet, Bet365, and others
   - Clean JSON API
   - ~$49/month for 10,000 requests if you need more

### Option 2: Direct Bookmaker Scraping (Production Ready)
**Best for**: Long-term, cost-effective solution

**TAB.com.au** (Government bookmaker - most reliable):
1. Open https://www.tab.com.au/sports/betting/Australian%20Rules in browser
2. Open Developer Tools (F12) → Network tab
3. Navigate AFL section, watch for API calls
4. Find JSON endpoints (usually api.tab.com.au)
5. Implement in `collect_odds.py` TABOddsCollector

**Sportsbet.com.au** (Popular bookmaker):
1. Similar process to TAB
2. Look for JSON API endpoints
3. Implement in SportsbetOddsCollector

**Benefits**:
- Free (no API costs)
- Direct from source
- Can collect historical data

**Considerations**:
- Check Terms of Service
- Implement rate limiting (1-2 second delays)
- Handle site structure changes
- Respect robots.txt

### Option 3: Hybrid Approach
**Best for**: Reliability + cost management

- Use The Odds API for current round predictions (24 matches × 3 bookmakers = 72 requests)
- Manually collect and store for historical backfilling
- Switch to direct scraping once patterns established

## How Odds Will Improve Models

### Current Performance
- **Stats-only models**: 68.8% (130/189 correct)
- **Human performance**: 76.7% (145/189 correct)
- **Gap**: 15 predictions

### Expected With Odds
Based on betting market efficiency and research:
- **Odds alone**: 72-75% accuracy
- **Stats + Odds hybrid**: 74-77% accuracy
- **Target**: 74-76% (140-143/189 correct)
- **Improvement**: +9-13 predictions

### Why Odds Are Powerful
Bookmakers incorporate:
✅ Injury news (key players out)
✅ Team selection (announced 1-2 days before)
✅ Weather forecasts
✅ Recent form and momentum
✅ Travel and fixture congestion
✅ Public betting patterns
✅ Expert analysis
✅ All other publicly available information

Essentially, odds are the "wisdom of the crowd + expert analysis" distilled into a number.

## Integration Approaches

### Approach 1: Odds as Features (Simple)
Add to existing model:
```python
features = {
    # Existing 16 features
    'diff_goals': 2.3,
    'diff_kicks': 15.2,
    # ...
    
    # New odds features  
    'odds_home_prob': 0.62,  # Fair probability from odds
    'odds_line_spread': -9.5,  # Line handicap
    'odds_total_points': 172.5,  # Expected total
}
```
**Expected**: +3-5% improvement

### Approach 2: Odds as Ensemble Member (Recommended)
```python
# Predictions
rf_pred = 0.68  # Random Forest
lr_pred = 0.65  # Logistic Regression  
odds_pred = 0.62  # From betting odds

# Weighted ensemble (odds get highest weight)
final = 0.25 * rf_pred + 0.25 * lr_pred + 0.50 * odds_pred
```
**Expected**: +5-7% improvement

### Approach 3: Odds Calibration
Use odds to calibrate model confidence:
```python
# Model says 80% but odds say 60%
# Odds are probably more accurate
calibrated = 0.6 * model_pred + 0.4 * odds_pred
```
**Expected**: +4-6% improvement

## Timeline

### This Week (Immediate):
1. ✅ Database table added
2. ✅ Collection framework built
3. ✅ Documentation complete
4. ⏳ Get The Odds API key
5. ⏳ Test current round collection
6. ⏳ Verify odds data quality

### Next Week (Integration):
1. ⏳ Add odds features to feature engineering
2. ⏳ Retrain models with odds
3. ⏳ Test ensemble with odds
4. ⏳ Measure accuracy improvement

### Week 3 (Production):
1. ⏳ Automate odds collection
2. ⏳ Set up pre-match odds fetching
3. ⏳ Monitor and log accuracy
4. ⏳ Refine ensemble weights

## Current Status

✅ **Infrastructure**: Database and collection framework ready
✅ **Documentation**: Complete guide available
⏳ **Data Collection**: Waiting for API key or bookmaker endpoints
⏳ **Model Integration**: Ready to implement once data available
⏳ **Testing**: Ready to validate on current rounds

## Quick Start Commands

```bash
# 1. Add match_odds table (already done)
python scripts/migrate_add_odds_table.py

# 2. Test odds collection (need API key)
python scripts/collect_odds.py --fetch-current --api-key YOUR_KEY

# 3. Later: Integrate into predictions
python scripts/train_ensemble.py --with-odds --save

# 4. Make predictions with odds
python scripts/predict_match.py --token <match> --use-odds
```

## Expected Results

**Before Odds** (Current):
- Random Forest: 68.3%
- Logistic Regression: 67.7%
- Top 2 Ensemble: 68.8%

**After Odds** (Projected):
- With odds features: 71-73%
- Odds ensemble member: 74-76%
- **Target**: 76% (matches human performance)

This would add **10-14 correct predictions** to reach 140-144/189.

## Resources

- **The Odds API**: https://the-odds-api.com/
- **TAB**: https://www.tab.com.au/sports/betting/Australian%20Rules
- **Sportsbet**: https://www.sportsbet.com.au/betting/australian-rules
- **Squiggle** (backup option): https://squiggle.com.au/
- **Implementation Guide**: `notes/odds_integration_guide.md`

---

*Setup completed: February 2, 2026*
*Ready for data collection and integration*
