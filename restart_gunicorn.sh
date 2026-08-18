#!/usr/bin/env bash
set -euo pipefail

echo "🔄 Restarting gunicorn with optimized settings for qwen2.5:72b..."

# Kill existing gunicorn processes
echo "Stopping existing gunicorn processes..."
pkill -f gunicorn || true
sleep 2

# Verify all processes stopped
if pgrep -f gunicorn > /dev/null; then
    echo "⚠️  Some gunicorn processes still running, force killing..."
    pkill -9 -f gunicorn || true
    sleep 1
fi

echo "✅ Old processes stopped"

# Activate venv if present
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
fi

# Start gunicorn with settings optimized for large models
#
# --preload runs create_app() once in the master process, before workers are
# forked. Without it each of the 16 workers builds its own BackgroundScheduler
# with its own in-memory jobstore, so every scheduled job fires 16 times
# (replace_existing=True only deduplicates within one jobstore). With it, the
# scheduler is started in the master and inherited by the workers — and because
# fork() does not copy threads, only the master's timer thread actually fires.
#
# --preload requires that create_app() leave no connection open: anything live in
# the master is inherited by all 16 workers as a shared file descriptor. See
# _release_startup_connections() in scidk/app.py, the lazy `db` properties on
# InterpreterSettings and AlertManager, and get_concept_driver(), which verifies
# with a throwaway driver so the one it returns has an empty pool. Re-check that
# invariant before adding anything to app.extensions that connects in __init__.
#
# Trade-off: with the scheduler in the master, a schedule change made through the
# API lands in a worker and is persisted but not applied until restart.
# BackupScheduler.update_settings() logs a warning when that happens.
echo "Starting gunicorn with:"
echo "  - Workers: 16 (reduce to 4 if needed GPU memory)"
echo "  - Timeout: 300s (5 minutes for 72b model)"
echo "  - Bind: 127.0.0.1:5000"
echo "  - Preload: on (single scheduler in the master process)"

nohup gunicorn \
    -w 16 \
    -b 127.0.0.1:5000 \
    --timeout 300 \
    --preload \
    --access-logfile - \
    --error-logfile - \
    "scidk.app:create_app()" \
    > gunicorn.log 2>&1 &

sleep 2

# Check if started successfully
if pgrep -f gunicorn > /dev/null; then
    PID=$(pgrep -f "gunicorn.*scidk" | head -1)
    echo "✅ Gunicorn started successfully (PID: $PID)"
    echo "📋 Logs: tail -f gunicorn.log"
    echo ""
    echo "Workers running:"
    pgrep -f gunicorn | wc -l
else
    echo "❌ Failed to start gunicorn"
    echo "Check gunicorn.log for errors"
    exit 1
fi
