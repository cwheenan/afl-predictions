"""Global configuration for the afl_predictions package.

Keep default values here so they can be changed in one place if sites or
environments change.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load local .env file when present.
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

# Base URL for AFLTables pages (useful if the site moves or we mirror elsewhere)
AFLTABLES_BASE_URL = "https://afltables.com/afl/stats/games/"

# Default cache directory used by data ingestion functions (relative to repo root)
DEFAULT_CACHE_DIR = Path("data/raw/cache")

# Default User-Agent to use when politely fetching pages
DEFAULT_USER_AGENT = os.getenv("APP_USER_AGENT", "afl-predictions-bot/0.1 (+https://example.com/)")

# Specific User-Agent for Squiggle requests (falls back to app User-Agent)
SQUIGGLE_USER_AGENT = os.getenv("SQUIGGLE_USER_AGENT", DEFAULT_USER_AGENT)

# Respect robots.txt when True. Set False to ignore robots checks (not recommended).
RESPECT_ROBOTS = True

# Default rate limit between requests (seconds)
DEFAULT_RATE_LIMIT = 2.0

# Default timeout for HTTP requests (seconds)
DEFAULT_HTTP_TIMEOUT = 10

# Database URL for SQLAlchemy. Default is a local sqlite file in data/processed.
# You can override with an environment variable or by editing this value.
DB_URL = os.getenv("DB_URL", "sqlite:///data/processed/afl.db")

# Optional external API keys.
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
