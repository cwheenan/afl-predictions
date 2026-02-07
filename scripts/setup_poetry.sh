#!/usr/bin/env bash
set -euo pipefail

# Helper to install dependencies with Poetry
# Usage: ./scripts/setup_poetry.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry not found on PATH. Install Poetry first:" >&2
  echo "  (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -" >&2
  exit 2
fi

cd "$ROOT_DIR"
echo "Installing dependencies via Poetry (this will create a virtual environment managed by Poetry)..."
poetry install

echo
echo "Done. Use 'poetry shell' to spawn a shell, or 'poetry run <cmd>' to run commands in the environment."
echo "Example: poetry run pytest -q"
