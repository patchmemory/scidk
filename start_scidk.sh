#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi


# Feature flags to enable all recent behavior
export SCIDK_CHANNEL=dev
export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
export SCIDK_FEATURE_FILE_INDEX=1
export SCIDK_COMMIT_FROM_INDEX=1
export SCIDK_RCLONE_MOUNTS=1
export SCIDK_FILES_VIEWER=rocrate
# Optional: keep rclone provider visible even if rclone missing (for UI/testing)
# export SCIDK_FORCE_RCLONE=1
# Optional: set a specific SQLite DB path
#export SCIDK_DB_PATH="$HOME/.scidk/db/files.db"
export SCIDK_DB_PATH="$HOME/PycharmProjects/scidk/data/files.db"

# Bind address/port
HOST=0.0.0.0
PORT=5000

scidk-serve
# Start with gunicorn (prod-ish testing)
#exec python -m gunicorn "scidk.app:create_app()" \
#  --bind "0.0.0.0:5000" \
#  --workers 1 \
#  --threads 2 \
#  --timeout 120 \
#  --access-logfile - \
#  --error-logfile -
