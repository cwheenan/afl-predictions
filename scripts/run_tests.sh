#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

PYTEST_CMD=""
if [ -x "$VENV_DIR/bin/pytest" ]; then
  PYTEST_CMD="$VENV_DIR/bin/pytest"
elif [ -x "$VENV_DIR/Scripts/pytest.exe" ]; then
  PYTEST_CMD="$VENV_DIR/Scripts/pytest.exe"
elif [ -x "$VENV_DIR/bin/python" ]; then
  PYTEST_CMD="$VENV_DIR/bin/python -m pytest"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PYTEST_CMD="$VENV_DIR/Scripts/python.exe -m pytest"
else
  echo "Virtualenv not found or missing pytest. Run ./scripts/setup_venv.sh first." >&2
  exit 2
fi

echo "Running tests with: $PYTEST_CMD"
eval "$PYTEST_CMD -q '$ROOT_DIR/tests'"
