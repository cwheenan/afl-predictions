#!/usr/bin/env python3
"""Run weekly AFL update workflow.

Pipeline steps:
1) Ingest live AFL tipping odds into match_odds.
2) Optionally retrain the model on completed seasons.
3) Generate upcoming match predictions.

Usage:
  python scripts/run_weekly_update.py --year 2026
  python scripts/run_weekly_update.py --year 2026 --round 7 --retrain
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List


def run_step(cmd: List[str], label: str) -> None:
    print(f"\n[{label}] {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Step failed ({label}) with exit code {result.returncode}")


def build_train_years(start_year: int, end_year: int) -> List[str]:
    if start_year > end_year:
        raise ValueError('train start year cannot be greater than end year')
    return [str(y) for y in range(start_year, end_year + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description='Run weekly AFL odds + prediction workflow')
    parser.add_argument('--year', type=int, default=datetime.now().year, help='Season year to process')
    parser.add_argument('--round', type=int, dest='round_number', help='Round number override')
    parser.add_argument('--model', default='models/rf_with_odds_final.joblib', help='Model path for prediction step')
    parser.add_argument('--odds-weight', type=float, help='Optional odds blend weight for predictions')
    parser.add_argument('--skip-odds-ingest', action='store_true', help='Skip AFL tipping odds ingest')
    parser.add_argument('--retrain', action='store_true', help='Retrain model before prediction')
    parser.add_argument('--train-start-year', type=int, default=2021, help='First season to include when retraining')
    parser.add_argument('--no-save-raw-odds', action='store_true', help='Disable raw AFL tipping payload snapshots')
    args = parser.parse_args()

    py_exe = sys.executable
    script_dir = Path(__file__).resolve().parent

    print('=== Weekly AFL Update ===')
    print(f'Season year: {args.year}')
    print(f'Round: {args.round_number if args.round_number is not None else "auto"}')
    print(f'Model: {args.model}')

    if not args.skip_odds_ingest:
        odds_cmd = [
            py_exe,
            str(script_dir / 'ingest_afl_tipping_odds.py'),
            '--year',
            str(args.year),
        ]
        if args.round_number is not None:
            odds_cmd += ['--round', str(args.round_number)]
        if args.no_save_raw_odds:
            odds_cmd.append('--no-save-raw')
        run_step(odds_cmd, 'ingest-odds')
    else:
        print('\n[ingest-odds] skipped by flag')

    if args.retrain:
        train_years = build_train_years(args.train_start_year, args.year)
        retrain_cmd = [
            py_exe,
            str(script_dir / 'retrain_current_season.py'),
            '--train-years',
            *train_years,
            '--model-out',
            args.model,
        ]
        run_step(retrain_cmd, 'retrain')
    else:
        print('\n[retrain] skipped (use --retrain to enable)')

    predict_cmd = [
        py_exe,
        str(script_dir / 'predict_upcoming.py'),
        '--year',
        str(args.year),
        '--model',
        args.model,
    ]
    if args.round_number is not None:
        predict_cmd += ['--round', str(args.round_number)]
    if args.odds_weight is not None:
        predict_cmd += ['--odds-weight', str(args.odds_weight)]

    run_step(predict_cmd, 'predict')
    print('\nWeekly update completed successfully.')


if __name__ == '__main__':
    main()
