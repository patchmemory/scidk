#!/usr/bin/env sh
set -euo pipefail
# Bootstrap a local dev environment with Python 3.12 venv and repo-local Playwright browsers
# Usage: scripts/bootstrap-dev.sh

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_ROOT"

# Ensure Python 3.12 is available
if ! command -v python3.12 >/dev/null 2>&1; then
  echo "python3.12 not found on PATH. Please install Python 3.12 and retry." >&2
  exit 1
fi

# Create venv if missing
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
. .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .[dev]

# Create repo-local cache dirs
mkdir -p dev/test-runs/tmp dev/test-runs/pytest-tmp dev/test-runs/artifacts dev/test-runs/downloads dev/test-runs/pw-browsers

# Install Playwright browsers locally (chromium is sufficient for our suite)
PLAYWRIGHT_BROWSERS_PATH="$REPO_ROOT/dev/test-runs/pw-browsers" \
TMPDIR="$REPO_ROOT/dev/test-runs/tmp" \
.venv/bin/python -m playwright install chromium

echo "\nBootstrap complete. Try: make e2e"
