"""Training utilities for models.

This module provides a simple train() function that can be extended to support
multiple model types and hyperparameter tuning.
"""

from typing import Any
import joblib
from sklearn.linear_model import LogisticRegression


def train_baseline_model(X, y, save_path: str = None) -> Any:
    """Train a baseline logistic regression model and optionally persist it."""
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X, y)
    if save_path:
        joblib.dump(clf, save_path)
    return clf
