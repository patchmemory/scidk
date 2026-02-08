"""
Blueprint for authentication API routes.

Endpoints:
- POST /api/auth/login - Login with username/password
- POST /api/auth/logout - Logout and clear session
- GET /api/auth/status - Check current authentication status
"""
from flask import Blueprint, jsonify, request, current_app
from ...core.auth import get_auth_manager

bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _get_auth_manager():
    """Get AuthManager instance using settings DB path from config."""
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_auth_manager(db_path=db_path)


def _get_session_token():
    """Extract session token from request cookies or Authorization header."""
    # Try cookie first (standard session management)
    token = request.cookies.get('scidk_session')
    if token:
        return token

    # Try Authorization header (Bearer token format)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]

    return None


@bp.post('/login')
def api_auth_login():
    """Login with username and password.

    Request body:
        {
            "username": "admin",
            "password": "password123",
            "remember_me": false  // optional, default false
        }

    Returns:
        200: {"success": true, "token": "...", "username": "admin"}
        401: {"success": false, "error": "Invalid credentials"}
        400: {"success": false, "error": "Missing username or password"}
        503: {"success": false, "error": "Authentication not enabled"}
    """
    auth = _get_auth_manager()

    # Check if auth is enabled
    if not auth.is_enabled():
        return jsonify({'success': False, 'error': 'Authentication not enabled'}), 503

    # Parse request body
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember_me = bool(data.get('remember_me', False))

    # Validate input
    if not username or not password:
        return jsonify({'success': False, 'error': 'Missing username or password'}), 400

    # Verify credentials (try multi-user first)
    user = auth.verify_user_credentials(username, password)

    if not user:
        # Try legacy single-user verification
        if auth.verify_credentials(username, password):
            # Legacy auth succeeded - create basic user dict
            user = {'username': username, 'id': None, 'role': 'admin'}
        else:
            # Log failed attempt
            ip_address = request.remote_addr
            auth.log_failed_attempt(username, ip_address)
            auth.log_audit(username, 'login_failed', f'Failed login attempt', ip_address)
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    # Create session
    duration_hours = 720 if remember_me else 24  # 30 days vs 24 hours

    if user.get('id') is not None:
        # Multi-user session
        token = auth.create_user_session(user['id'], user['username'], duration_hours=duration_hours)
    else:
        # Legacy session
        token = auth.create_session(user['username'], duration_hours=duration_hours)

    if not token:
        return jsonify({'success': False, 'error': 'Failed to create session'}), 500

    # Log successful login
    ip_address = request.remote_addr
    auth.log_audit(user['username'], 'login', f'Successful login', ip_address)

    # Return success with token and user info
    response = jsonify({
        'success': True,
        'token': token,
        'username': user['username'],
        'role': user.get('role', 'admin'),
        'user_id': user.get('id'),
    })

    # Set cookie with secure flags
    # In production, add secure=True, httponly=True, samesite='Lax'
    max_age = duration_hours * 3600  # seconds
    response.set_cookie(
        'scidk_session',
        token,
        max_age=max_age,
        httponly=True,
        samesite='Lax'
    )

    return response, 200


@bp.post('/logout')
def api_auth_logout():
    """Logout and clear session.

    Returns:
        200: {"success": true}
        400: {"success": false, "error": "No active session"}
    """
    token = _get_session_token()

    if not token:
        return jsonify({'success': False, 'error': 'No active session'}), 400

    auth = _get_auth_manager()

    # Get username before deleting session for audit log
    user = auth.get_session_user(token, update_activity=False)
    username = user['username'] if user else None

    # If multi-user session doesn't exist, try legacy
    if not username:
        username = auth.verify_session(token, update_activity=False)

    auth.delete_session(token)

    # Log logout event
    if username:
        ip_address = request.remote_addr
        auth.log_audit(username, 'logout', 'User logged out', ip_address)

    # Clear cookie
    response = jsonify({'success': True})
    response.set_cookie('scidk_session', '', max_age=0)

    return response, 200


@bp.get('/status')
def api_auth_status():
    """Check current authentication status.

    Returns:
        200: {
            "authenticated": true,
            "username": "admin",
            "auth_enabled": true,
            "token_valid": true
        }
        or
        200: {
            "authenticated": false,
            "auth_enabled": true,
            "token_valid": false
        }
    """
    auth = _get_auth_manager()
    auth_enabled = auth.is_enabled()

    # If auth is disabled, everyone is authenticated
    if not auth_enabled:
        return jsonify({
            'authenticated': True,
            'username': None,
            'auth_enabled': False,
            'token_valid': False,
        }), 200

    # Check if user has valid session (try multi-user first)
    token = _get_session_token()
    user = auth.get_session_user(token) if token else None

    if not user:
        # Try legacy session verification
        username = auth.verify_session(token) if token else None
        if username:
            user = {'username': username, 'role': 'admin', 'id': None}

    if user:
        return jsonify({
            'authenticated': True,
            'username': user['username'],
            'role': user.get('role', 'admin'),
            'user_id': user.get('id'),
            'auth_enabled': True,
            'token_valid': True,
        }), 200
    else:
        return jsonify({
            'authenticated': False,
            'username': None,
            'role': None,
            'user_id': None,
            'auth_enabled': True,
            'token_valid': False,
        }), 200
