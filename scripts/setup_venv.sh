#!/usr/bin/env bash
# Create and activate a virtualenv (bash-friendly), then install requirements
set -euo pipefail

# Usage: ./scripts/setup_venv.sh [python-exe]
# Example: ./scripts/setup_venv.sh python3

PY=${1:-python3}
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

echo "Using python: ${PY}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: Python executable '$PY' not found on PATH. Install Python or pass full path as first arg." >&2
  exit 2
fi

echo "Creating venv at ${VENV_DIR}..."
$PY -m venv "$VENV_DIR"

echo "Installing requirements into venv..."
# Prefer using the venv's pip directly so this works on Windows (Scripts) and Unix (bin)
PIP_CMD=""
PY_CMD=""
if [ -x "$VENV_DIR/bin/pip" ]; then
  PIP_CMD="$VENV_DIR/bin/pip"
  PY_CMD="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/pip.exe" ]; then
  PIP_CMD="$VENV_DIR/Scripts/pip.exe"
  PY_CMD="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/Script/pip.exe" ]; then
  # sometimes path differs (typo in some environments)
  PIP_CMD="$VENV_DIR/Script/pip.exe"
  PY_CMD="$VENV_DIR/Script/python.exe"
else
  # Fall back to invoking the python used to create venv with -m pip
  if command -v "$PY" >/dev/null 2>&1; then
    PY_CMD="$PY"
    PIP_CMD="$PY -m pip"
  else
    echo "ERROR: cannot find pip executable in venv and python not available." >&2
    exit 3
  fi
fi

echo "Using pip: $PIP_CMD"
"$PIP_CMD" --version || true

"$PIP_CMD" install --upgrade pip
if [ -f "$ROOT_DIR/requirements.txt" ]; then
  "$PIP_CMD" install -r "$ROOT_DIR/requirements.txt"
else
  echo "No requirements.txt found; skipping pip install" >&2
fi

echo
# Print activation instructions depending on layout
if [ -f "$VENV_DIR/bin/activate" ]; then
  ACTIVATE_SH="$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
  ACTIVATE_SH="$VENV_DIR/Scripts/activate"
else
  ACTIVATE_SH=""
fi

echo "Virtualenv ready. To activate in your shell:"
if [ -n "$ACTIVATE_SH" ]; then
  echo "  source $ACTIVATE_SH"
else
  echo "  (no activate script found; use the venv python directly:)"
  echo "  $PY -m venv $VENV_DIR && $VENV_DIR/bin/python -m pip install -r requirements.txt"
fi
echo "Run tests: pytest -q (or use '$PY_CMD -m pytest')"
echo
exit 0
