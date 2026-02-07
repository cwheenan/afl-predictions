"""Helpers to build dataset artifacts (train/test splits, persisted datasets).

This file should provide functions used by the training pipeline to assemble
feature tables and labels ready for model training.
"""

import pandas as pd
from typing import Tuple


def train_test_split_season(df: pd.DataFrame, test_size: int = 10) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Simple split by taking the last `test_size` matches as test set.

    This is a placeholder; replace with time-aware splitting as needed.
    """
    if test_size <= 0:
        return df, pd.DataFrame(columns=df.columns)
    return df[:-test_size].reset_index(drop=True), df[-test_size:].reset_index(drop=True)
