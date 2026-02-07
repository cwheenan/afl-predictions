"""Prediction helpers: load model and produce predictions for upcoming matches."""

import joblib
import pandas as pd
from typing import Any


def load_model(path: str) -> Any:
    return joblib.load(path)


def predict(model: Any, X: pd.DataFrame) -> pd.Series:
    return model.predict_proba(X)[:, 1]
