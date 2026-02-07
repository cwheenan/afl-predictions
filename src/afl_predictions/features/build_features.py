"""Feature engineering functions for AFL match data.

Start with a small set of candidate features and expand iteratively.
"""

import pandas as pd


def build_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of features for modeling.

    Example engineered features (placeholders):
    - home_advantage (1 if home team, else 0)
    - score_diff_last (difference in scores from previous match)
    - recent_form_home / recent_form_away (rolling win rate)

    This is intentionally small to be extended later.
    """
    features = pd.DataFrame()
    # ... implement feature logic
    return features
