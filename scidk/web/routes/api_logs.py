"""Blueprint for Logs API routes (admin-only).

Provides REST endpoints for:
- Listing log entries with filtering
- Exporting logs as a file
"""
from flask import Blueprint, jsonify, request, send_file
from pathlib import Path
from ..decorators import require_admin
import re
from datetime import datetime

bp = Blueprint('logs_viewer', __name__, url_prefix='/api/logs')


@bp.get('/viewer')
@require_admin
def api_logs_viewer():
    """Get recent log entries with filtering.

    Query params:
        level: Filter by log level (INFO, WARNING, ERROR)
        source: Filter by logger name (e.g., 'scidk.core.scanner')
        search: Text search in log messages
        since: Unix timestamp - only return entries after this time
        limit: Max entries to return (default: 100, max: 1000)

    Returns:
        {
            "entries": [
                {
                    "timestamp": "2026-02-09 14:07:32",
                    "level": "INFO",
                    "source": "scidk.core.scanner",
                    "message": "Scan started: /demo_data/"
                },
                ...
            ]
        }
    """
    log_dir = Path('logs')
    log_file = log_dir / 'scidk.log'

    if not log_file.exists():
        return jsonify({'entries': []})

    # Parse query params
    level_filter = request.args.get('level', '').upper()
    source_filter = request.args.get('source', '').lower()
    search_query = request.args.get('search', '').lower()
    since = request.args.get('since')
    limit = min(int(request.args.get('limit', '100')), 1000)

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromtimestamp(float(since))
        except ValueError:
            pass

    # Read log file (last N lines for performance)
    entries = []
    line_pattern = re.compile(
        r'\[(?P<timestamp>[\d\-\s:]+)\] \[(?P<level>\w+)\] \[(?P<source>[\w\.]+)\] (?P<message>.*)'
    )

    # Read file in reverse for recent entries
    with log_file.open('r') as f:
        # For production, consider using a more efficient tail implementation
        lines = f.readlines()
        lines.reverse()  # Newest first

        for line in lines:
            if len(entries) >= limit:
                break

            match = line_pattern.match(line.strip())
            if not match:
                continue

            entry = match.groupdict()

            # Apply filters
            if level_filter and entry['level'] != level_filter:
                continue

            if source_filter and source_filter not in entry['source'].lower():
                continue

            if search_query and search_query not in entry['message'].lower():
                continue

            if since_dt:
                try:
                    entry_dt = datetime.strptime(entry['timestamp'], '%Y-%m-%d %H:%M:%S')
                    if entry_dt < since_dt:
                        continue
                except ValueError:
                    pass

            entries.append(entry)

    return jsonify({'entries': entries})


@bp.get('/export')
@require_admin
def api_logs_export():
    """Export logs as text file.

    Returns:
        Log file download
    """
    log_dir = Path('logs')
    log_file = log_dir / 'scidk.log'

    if not log_file.exists():
        return jsonify({'error': 'No log file found'}), 404

    return send_file(
        str(log_file.absolute()),
        as_attachment=True,
        download_name=f'scidk_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )
