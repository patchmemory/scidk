"""
Blueprint for audit log API routes (admin-only).

Endpoints:
- GET /api/audit-log - Get audit log entries
"""
from flask import Blueprint, jsonify, request, current_app
from ...core.auth import get_auth_manager
from ..decorators import require_admin

bp = Blueprint('audit', __name__, url_prefix='/api/audit-log')


def _get_auth_manager():
    """Get AuthManager instance using settings DB path from config."""
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_auth_manager(db_path=db_path)


@bp.get('')
@require_admin
def api_audit_log():
    """Get audit log entries (admin only).

    Query params:
        since: Unix timestamp - only return entries after this time (optional)
        username: Filter by username (optional)
        limit: Maximum number of entries (default: 100, max: 1000)

    Returns:
        200: {"entries": [...]}
    """
    auth = _get_auth_manager()

    # Parse query params
    since = request.args.get('since')
    username = request.args.get('username')
    limit = request.args.get('limit', '100')

    # Convert since to float if provided
    since_timestamp = None
    if since:
        try:
            since_timestamp = float(since)
        except ValueError:
            return jsonify({'error': 'Invalid since timestamp'}), 400

    # Validate and cap limit
    try:
        limit = int(limit)
        limit = min(limit, 1000)  # Cap at 1000
        limit = max(limit, 1)     # Minimum 1
    except ValueError:
        limit = 100

    # Get audit log
    entries = auth.get_audit_log(
        since_timestamp=since_timestamp,
        username=username,
        limit=limit
    )

    return jsonify({'entries': entries}), 200
