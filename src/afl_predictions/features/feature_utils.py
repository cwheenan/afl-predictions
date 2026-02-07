"""Utility helpers for feature engineering (rolling stats, date handling)."""

import pandas as pd


def compute_rolling_win_rate(results_series: pd.Series, window: int = 5) -> pd.Series:
    """Compute rolling win rate from a boolean Series where True indicates a win."""
    return results_series.rolling(window, min_periods=1).mean()
