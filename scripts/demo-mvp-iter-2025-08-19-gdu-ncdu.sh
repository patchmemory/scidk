#!/usr/bin/env bash
# Ensure bash is used even if invoked with 'sh script.sh'
if [ -z "${BASH_VERSION:-}" ]; then exec /usr/bin/env bash "$0" "$@"; fi
set -euo pipefail

# SciDK Demo Script: mvp-iter-2025-08-19-gdu-ncdu
# Purpose: Verify GUI Acceptance end-to-end with a minimal, repeatable flow.
# Prereqs: Python 3, project venv with requirements installed.
# Usage: ./scripts/demo-mvp-iter-2025-08-19-gdu-ncdu.sh

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
export PYTHONPATH="$ROOT"

# 0) Detect external scanner tools for transparency
NCDU_BIN=$(command -v ncdu || true)
GDU_BIN=$(command -v gdu || true)
if [[ -n "$NCDU_BIN" ]]; then
  SCAN_TOOL="ncdu"
elif [[ -n "$GDU_BIN" ]]; then
  SCAN_TOOL="gdu"
else
  SCAN_TOOL="python"
fi

echo "[INFO] Detected scan source preference: $SCAN_TOOL (ncdu -> gdu -> python fallback)"

# 1) Start the Flask app in background (if not already running)
export SCIDK_HOST=127.0.0.1
export SCIDK_PORT=5000
export SCIDK_DEBUG=1

# Try to find an existing process
APP_URL="http://${SCIDK_HOST}:${SCIDK_PORT}"
if curl -sSf "$APP_URL/api/datasets" >/dev/null 2>&1; then
  echo "[INFO] SciDK app already running at $APP_URL"
else
  echo "[INFO] Starting SciDK app at $APP_URL"
  # Use python -m to run inline; log to /tmp
  nohup python -m scidk.app >/tmp/scidk_demo_app.log 2>&1 &
  APP_PID=$!
  echo $APP_PID > /tmp/scidk_demo_app.pid
  # Wait for port
  for i in {1..50}; do
    if curl -sSf "$APP_URL/api/datasets" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  echo "[INFO] App started (pid=$(cat /tmp/scidk_demo_app.pid))"
fi

echo "[OPEN] Home UI:     ${APP_URL}/"
echo "[OPEN] Files UI:    ${APP_URL}/datasets"
echo "[OPEN] Scans API:   ${APP_URL}/api/scans"
echo "[OPEN] Dirs API:    ${APP_URL}/api/directories"
echo "[OPEN] Search API:  ${APP_URL}/api/search?q=py"

# 2) Prepare test data (small temp directory with a few files)
DEMO_DIR=$(mktemp -d /tmp/scidk_demo_XXXX)
trap 'echo "[INFO] Demo data at $DEMO_DIR"' EXIT

echo 'print("hello")' >"$DEMO_DIR/sample.py"
echo -e 'a,b\n1,2' >"$DEMO_DIR/data.csv"
echo '{"k": 1}' >"$DEMO_DIR/sample.json"

echo "[INFO] Created demo data in $DEMO_DIR"
ls -la "$DEMO_DIR"

# 3) Trigger a scan via API (non-recursive for speed)
RESP=$(curl -sS -X POST "$APP_URL/api/scan" -H 'Content-Type: application/json' \
  -d "{\"path\": \"$DEMO_DIR\", \"recursive\": false}")
echo "[INFO] Scan response: $RESP"

SCAN_ID=$(printf '%s' "$RESP" | python -c '
import sys, json
data = sys.stdin.read()
try:
    j = json.loads(data)
    print(j.get("scan_id", ""))
except Exception:
    print("")
')

if [[ -z "$SCAN_ID" ]]; then
  echo "[WARN] No scan_id parsed from response; check app logs at /tmp/scidk_demo_app.log and response above."
else
  echo "[INFO] scan_id=$SCAN_ID"
  echo "[OPEN] Filter by scan in Files UI: ${APP_URL}/datasets?scan_id=${SCAN_ID}"
fi

# 4) Verify expected fields and source badge through APIs
DIRS=$(curl -sS "$APP_URL/api/directories")
echo "[INFO] Directories registry: $DIRS"

# 5) Summarize tool preference vs. actual
if [[ "$SCAN_TOOL" == "python" ]]; then
  echo "[NOTE] Preferred tool: python (no ncdu/gdu found). Actual used source is shown in UI/API badges."
else
  echo "[NOTE] Preferred tool detected: $SCAN_TOOL. Actual used source is shown in UI/API badges."
fi

echo "---"
echo "Demo checkpoints:"
echo "1) Home shows Recent Scans and Scanned Directories with a small badge for the source (ncdu/gdu/python)."
echo "2) Files page lists a Scan form; use it to rescan if desired."
echo "3) GET /api/directories includes 'source', 'path', and 'scanned' fields."
echo "4) GET /api/scans shows 'source' per scan summary."
echo "5) Optional: Use /api/search?q=python_code to see interpreted results for sample.py."
