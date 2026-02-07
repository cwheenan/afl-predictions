# Archived Scripts

This folder contains development and debugging scripts that were used during initial data collection and model development but are no longer needed for regular operation.

## What's Archived

### Debug Scripts (debug_*, tmp_*)
One-off scripts used to diagnose parsing issues, inspect database state, and verify data quality during development.

### Season-Specific Fixes
Scripts that fixed specific data issues in historical seasons (particularly 1995 and 2015). These fixes have been applied to the database.

### Historical Operations
- **Backfills**: Scripts that populated missing data (teams, scores, statistics). Already completed.
- **Migrations**: Database schema updates. Already applied.
- **Parsing helpers**: Early development tools for HTML parsing and token extraction.

### Superseded Training Scripts
- `train_ensemble.py` - Replaced by `train_ensemble_with_odds.py`
- `train_models.py` - Individual model training (superseded by ensemble)
- `stack_with_oof*.py` - Old stacking approach (superseded by odds-as-member method)
- `tune_hyperparameters.py`, `xgb_*search.py` - Hyperparameter tuning (optimal params now hard-coded)

### Inspection & Analysis
Various scripts used during development to:
- Inspect cached data
- Verify database integrity
- Analyze feature distributions
- Debug specific matches

## Restoration

If you need any of these scripts:
```bash
# Copy back to scripts/
cp archive/scripts/SCRIPT_NAME.py scripts/

# Or restore entire category
git log --all --full-history -- "archive/scripts/*" 
```

Most of these won't be needed again, but they're preserved in case you want to:
- Re-run historical data fixes
- Rebuild the database from scratch
- Debug specific parsing issues
- Review development history

## Current Production Scripts

See the main `scripts/` folder for the 22 active production scripts used for:
- Data collection
- Model training
- Predictions
- Weekly updates
