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
echo "Starting gunicorn with:"
echo "  - Workers: 16 (reduce to 4 if needed GPU memory)"
echo "  - Timeout: 300s (5 minutes for 72b model)"
echo "  - Bind: 127.0.0.1:5000"

nohup gunicorn \
    -w 16 \
    -b 127.0.0.1:5000 \
    --timeout 300 \
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
