#!/usr/bin/env bash
# Dev helper to always run the project CLI using the virtual environment interpreter when available.
# Usage examples:
#   bash scripts/dev.sh ready-queue
#   bash scripts/dev.sh start <task-id>
#   bash scripts/dev.sh complete <task-id>
#
# Note: If .venv is missing, this falls back to python3 on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
CLI="$REPO_ROOT/dev_cli.py"

if [[ -x "$VENV_PY" ]]; then
  exec "$VENV_PY" "$CLI" "$@"
else
  echo "⚠️  .venv not found or not executable; falling back to python3 on PATH" >&2
  exec python3 "$CLI" "$@"
fi
