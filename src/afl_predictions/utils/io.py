"""IO utilities for reading/writing datasets and models."""

from pathlib import Path
import pandas as pd


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def write_csv(df, path: str):
    df.to_csv(path, index=False)
