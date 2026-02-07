"""Global configuration for the afl_predictions package.

Keep default values here so they can be changed in one place if sites or
environments change.
"""
from pathlib import Path

# Base URL for AFLTables pages (useful if the site moves or we mirror elsewhere)
AFLTABLES_BASE_URL = "https://afltables.com/afl/stats/games/"

# Default cache directory used by data ingestion functions (relative to repo root)
DEFAULT_CACHE_DIR = Path("data/raw/cache")

# Default User-Agent to use when politely fetching pages
DEFAULT_USER_AGENT = "afl-predictions-bot/0.1 (+https://example.com/)"

# Respect robots.txt when True. Set False to ignore robots checks (not recommended).
RESPECT_ROBOTS = True

# Default rate limit between requests (seconds)
DEFAULT_RATE_LIMIT = 2.0

# Default timeout for HTTP requests (seconds)
DEFAULT_HTTP_TIMEOUT = 10

# Database URL for SQLAlchemy. Default is a local sqlite file in data/processed.
# You can override with an environment variable or by editing this value.
DB_URL = f"sqlite:///data/processed/afl.db"
