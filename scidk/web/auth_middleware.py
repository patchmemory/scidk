"""Authentication middleware for SciDK.

This module provides a before_request handler that enforces authentication
when it's enabled. Public routes (login page, auth API) are always accessible.
"""

from flask import request, redirect, url_for, current_app
from ..core.auth import get_auth_manager


# Routes that should always be accessible without authentication
PUBLIC_ROUTES = {
    '/login',
    '/api/auth/login',
    '/api/auth/status',
    '/api/settings/security/auth',  # Allow disabling/checking auth config
    '/static',  # Prefix for static files
}


def is_public_route(path: str) -> bool:
    """Check if a route is public (doesn't require authentication).

    Args:
        path: Request path

    Returns:
        bool: True if route is public, False otherwise
    """
    # Exact matches
    if path in PUBLIC_ROUTES:
        return True

    # Prefix matches (e.g., /static/*)
    for public_prefix in PUBLIC_ROUTES:
        if path.startswith(public_prefix + '/'):
            return True

    return False


def check_auth():
    """Check authentication before each request.

    This function runs before every request. If authentication is enabled
    and the user is not authenticated, they are redirected to the login page
    (unless accessing a public route).

    Returns:
        None if authentication passes, redirect Response if not authenticated
    """
    # Skip auth check in testing mode (unless specifically testing auth)
    if current_app.config.get('TESTING', False):
        # Only enforce auth in tests that explicitly enable it
        import os
        if not os.environ.get('PYTEST_TEST_AUTH'):
            return None

    # Skip auth check for public routes
    if is_public_route(request.path):
        return None

    # Get auth manager
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    auth = get_auth_manager(db_path=db_path)

    # If auth is not enabled, allow all requests
    if not auth.is_enabled():
        return None

    # Get session token from cookie or header
    token = request.cookies.get('scidk_session')
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

    # Verify session
    username = auth.verify_session(token) if token else None

    if username:
        # Authentication successful - store username in Flask g for access in routes
        from flask import g
        g.scidk_user = username
        return None
    else:
        # Not authenticated - redirect to login page with original URL
        if request.path.startswith('/api/'):
            # API requests should return 401 instead of redirecting
            from flask import jsonify
            return jsonify({'error': 'Authentication required'}), 401
        else:
            # UI requests redirect to login
            return redirect(url_for('ui.login', redirect=request.path))


def init_auth_middleware(app):
    """Initialize authentication middleware for the Flask app.

    Args:
        app: Flask application instance
    """
    app.before_request(check_auth)
