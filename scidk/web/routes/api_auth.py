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
    """User login
    ---
    tags:
      - Authentication
    summary: Login with username and password
    description: Authenticate user and create a session token
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - username
            - password
          properties:
            username:
              type: string
              example: admin
              description: Username
            password:
              type: string
              format: password
              example: password123
              description: Password
            remember_me:
              type: boolean
              default: false
              description: Keep session active for 30 days instead of 24 hours
    responses:
      200:
        description: Login successful
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            token:
              type: string
              description: Session token (JWT)
            username:
              type: string
              example: admin
      401:
        description: Invalid credentials
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: Invalid credentials
      400:
        description: Missing required fields
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: Missing username or password
      503:
        description: Authentication not enabled
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            error:
              type: string
              example: Authentication not enabled
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
            "token_valid": true,
            "session_locked": false
        }
        or
        200: {
            "authenticated": false,
            "auth_enabled": true,
            "token_valid": false,
            "session_locked": false
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
            'session_locked': False,
        }), 200

    # Check if user has valid session (try multi-user first)
    token = _get_session_token()
    user = auth.get_session_user(token) if token else None

    if not user:
        # Try legacy session verification
        username = auth.verify_session(token) if token else None
        if username:
            user = {'username': username, 'role': 'admin', 'id': None}

    # Check if session is locked
    session_locked = auth.is_session_locked(token) if token else False

    if user:
        return jsonify({
            'authenticated': True,
            'username': user['username'],
            'role': user.get('role', 'admin'),
            'user_id': user.get('id'),
            'auth_enabled': True,
            'token_valid': True,
            'session_locked': session_locked,
        }), 200
    else:
        return jsonify({
            'authenticated': False,
            'username': None,
            'role': None,
            'user_id': None,
            'auth_enabled': True,
            'token_valid': False,
            'session_locked': False,
        }), 200


@bp.post('/lock')
def api_auth_lock():
    """Lock current session (auto-lock feature).

    Returns:
        200: {"success": true, "locked_at": timestamp}
        400: {"success": false, "error": "No active session"}
        503: {"success": false, "error": "Authentication not enabled"}
    """
    auth = _get_auth_manager()

    # Check if auth is enabled
    if not auth.is_enabled():
        return jsonify({'success': False, 'error': 'Authentication not enabled'}), 503

    token = _get_session_token()

    if not token:
        return jsonify({'success': False, 'error': 'No active session'}), 400

    # Lock the session
    success = auth.lock_session(token)

    if success:
        # Get lock info
        lock_info = auth.get_session_lock_info(token)

        # Log lock event
        if lock_info:
            ip_address = request.remote_addr
            auth.log_audit(lock_info['username'], 'session_locked', 'Session locked', ip_address)

        return jsonify({
            'success': True,
            'locked_at': lock_info['locked_at'] if lock_info else None,
        }), 200
    else:
        return jsonify({'success': False, 'error': 'Failed to lock session'}), 500


@bp.post('/unlock')
def api_auth_unlock():
    """Unlock a locked session with password verification.

    Request body:
        {
            "password": "password123"
        }

    Returns:
        200: {"success": true}
        400: {"success": false, "error": "Missing password"}
        401: {"success": false, "error": "Invalid password"}
        400: {"success": false, "error": "No active session"}
        503: {"success": false, "error": "Authentication not enabled"}
    """
    auth = _get_auth_manager()

    # Check if auth is enabled
    if not auth.is_enabled():
        return jsonify({'success': False, 'error': 'Authentication not enabled'}), 503

    token = _get_session_token()

    if not token:
        return jsonify({'success': False, 'error': 'No active session'}), 400

    # Parse request body
    data = request.get_json() or {}
    password = data.get('password', '')

    if not password:
        return jsonify({'success': False, 'error': 'Missing password'}), 400

    # Attempt unlock
    success = auth.unlock_session(token, password)

    if success:
        # Get session info for audit log
        lock_info = auth.get_session_lock_info(token)

        if lock_info:
            ip_address = request.remote_addr
            auth.log_audit(lock_info['username'], 'session_unlocked', 'Session unlocked successfully', ip_address)

        return jsonify({'success': True}), 200
    else:
        # Log failed unlock attempt
        lock_info = auth.get_session_lock_info(token)
        if lock_info:
            ip_address = request.remote_addr
            auth.log_failed_attempt(lock_info['username'], ip_address)
            auth.log_audit(lock_info['username'], 'unlock_failed', 'Failed unlock attempt', ip_address)

        return jsonify({'success': False, 'error': 'Invalid password'}), 401
