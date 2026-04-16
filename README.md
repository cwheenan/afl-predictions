# AFL Predictions

Predicting AFL match outcomes using historical stats and betting odds. Currently sitting at 79.1% accuracy on 2025 season data.

## What's in here

- `src/afl_predictions/` - Core package (data loading, features, models)
- `data/` - Raw HTML cache, processed database
- `models/` - Trained models and evaluation results
- `scripts/` - Data collection, training, and prediction scripts
- `notes/` - Documentation and deployment guides

## Data Collection

All match data comes from AFLTables.com. To avoid hammering their servers, I cache everything locally:

- `scripts/fetch_afltables.py` downloads match pages and saves the HTML + parsed tables to `data/raw/cache/`
- There's a 2-second delay between requests (configurable with `--rate`)
- Once cached, we just read from disk instead of fetching again

The whole dataset (1990-2025) is already cached, so you shouldn't need to fetch much unless you're adding new seasons.

## Quick Setup

Using venv:

```bash
./scripts/setup_venv.sh python3
source .venv/bin/activate
./scripts/run_tests.sh
```

Or on Windows with PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Environment variables:

```powershell
Copy-Item .env.example .env
# Edit .env with your values (especially User-Agent contact details)
```

The code now loads `.env` automatically via `src/afl_predictions/config.py`.

## Model Performance

**Current: 79.1% accuracy** (117/148 correct on 2025 season)

The model is an ensemble that combines:
- Random Forest trained on 44 features (stats + odds + ladder/context): 77.0% accuracy on 2025 holdout
- Squiggle tipster consensus odds proxy: ~80% accuracy

Final prediction: RF probability (60%) + Odds probability (40%)

This beats the stats-only baseline (~69%) by around 10 percentage points.

## Current Workflow Notes

- Match identity is based on `home_team + away_team + date proximity`, not round label alone.
- For current season odds sync, we only pull through the detected current round (not future rounds).
- Prediction outputs are organized by round under `predictions/<year>/round_<NN>/`.
- Historical and misc prediction JSON files are stored under `predictions/<year>/misc/`.

## Making Predictions

For upcoming rounds in 2026:

```bash
# Collect odds from Squiggle
python scripts/create_odds_proxy_from_squiggle.py --year 2026

# Generate predictions
python scripts/predict_upcoming.py --year 2026

# Or force a specific round
python scripts/predict_upcoming.py --year 2026 --round 6
```

Predictions are written to paths like:

- `predictions/2026/round_06/predictions_2026_YYYYMMDD_HHMMSS.json`

If you use The Odds API collector, set `THE_ODDS_API_KEY` in `.env` or pass `--api-key`:

```bash
python scripts/collect_odds.py --fetch-current
```

See [notes/2026_deployment_guide.md](notes/2026_deployment_guide.md) for the full weekly workflow.

## Training

If you want to retrain on updated data:

```bash
# Train full ensemble with odds
python scripts/train_ensemble_with_odds.py

# Evaluate different approaches
python scripts/evaluate_odds_impact.py
```

Useful maintenance scripts:

- `python scripts/cleanup_duplicate_matches.py --season 2026 --apply`
- `python scripts/organize_prediction_files.py --year 2026 --apply`

Models are saved to `models/` as `.joblib` files (not in git due to size).



