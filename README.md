# AFL Predictions 2026

Starter project for predicting AFL match outcomes for the 2026 season.

Structure:
- `src/afl_predictions/` : core package with modules for data, features, models and utils
- `data/` : raw/processed data directories
- `models/` : saved trained models
- `scripts/` : helper scripts for training and weekly updates

Next steps:
1. Implement robust parsers for AFLTables pages and local CSV ingestion.
2. Build feature engineering functions (percent game time, rest days, travel, recent form).
3. Implement training pipeline with cross-validation and weekly retraining.

Polite data ingestion and caching
--------------------------------
We should avoid overloading afltables.com. The project includes a small caching
workflow:

- Use `scripts/fetch_afltables.py` to fetch a list of match URLs and cache raw HTML
	and parsed tables under `data/raw/cache/`.
- The fetcher checks `robots.txt` when possible, sets a clear `User-Agent`, and
	sleeps between requests (default 2s). You can increase the delay with `--rate`.
- Once cached, use `src/afl_predictions/data/load_data.py::load_cached_match_tables`
	to load parsed CSVs without hitting the remote site.

This keeps a local copy so the repository doesn't repeatedly query the remote site.

Bash (WSL / Git Bash / Linux) quickstart
--------------------------------------
If you prefer working in bash (WSL, Git Bash, or a Linux shell), here's a quick setup
using the standard venv module. From the repository root:

```bash
# create a venv using the system python (use 'python3' if needed)
./scripts/setup_venv.sh python3

# activate the venv in your shell
source .venv/bin/activate

# run tests
./scripts/run_tests.sh
```

Notes:
- On Windows, run these commands inside WSL, Git Bash, or another bash-compatible shell.
- If you don't have `python3` available, pass a full path to the Python executable to
	`./scripts/setup_venv.sh` (for example `/c/Users/you/AppData/Local/Programs/Python/Python311/python.exe`).

Poetry quickstart
-----------------
If you prefer Poetry for deterministic dependency management and an isolated environment, you can use it instead.

1. Install Poetry (one-time):

```bash
# install via the official installer
(curl -sSL https://install.python-poetry.org | python3 -)
```

2. Install project dependencies and create the Poetry-managed environment:

```bash
./scripts/setup_poetry.sh
```

3. Run tests inside Poetry's environment:

```bash
poetry run pytest -q
# or start an interactive shell with
poetry shell
```

Notes:
- Poetry will create and manage a virtual environment for the project. Use `poetry run` or `poetry shell` to execute commands inside it.
- If you later want to export a requirements.txt from Poetry:

```bash
poetry export -f requirements.txt --output requirements.txt --without-hashes
```



