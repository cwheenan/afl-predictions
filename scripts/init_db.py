"""Create the application database (tables).

Usage:
    python scripts/init_db.py
"""
import sys
from pathlib import Path

# ensure src/ is on sys.path when running from repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from afl_predictions.db import init_db


if __name__ == '__main__':
    engine = init_db()
    print('Database initialized at', engine.url)
