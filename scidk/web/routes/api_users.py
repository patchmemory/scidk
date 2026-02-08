"""
Blueprint for user management API routes (admin-only).

Endpoints:
- GET /api/users - List all users
- GET /api/users/<user_id> - Get user by ID
- POST /api/users - Create new user
- PUT /api/users/<user_id> - Update user
- DELETE /api/users/<user_id> - Delete user
- POST /api/users/<user_id>/sessions/delete - Delete all user sessions (force logout)
"""
import json
from flask import Blueprint, jsonify, request, current_app, g
from ...core.auth import get_auth_manager
from ..decorators import require_admin

bp = Blueprint('users', __name__, url_prefix='/api/users')


def _get_auth_manager():
    """Get AuthManager instance using settings DB path from config."""
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_auth_manager(db_path=db_path)


@bp.get('')
@require_admin
def api_users_list():
    """List all users (admin only).

    Query params:
        include_disabled: Include disabled users (default: false)

    Returns:
        200: {"users": [...]}
    """
    auth = _get_auth_manager()
    include_disabled = request.args.get('include_disabled', 'false').lower() == 'true'

    users = auth.list_users(include_disabled=include_disabled)

    return jsonify({'users': users}), 200


@bp.get('/<int:user_id>')
@require_admin
def api_users_get(user_id):
    """Get user by ID (admin only).

    Returns:
        200: {"user": {...}}
        404: {"error": "User not found"}
    """
    auth = _get_auth_manager()
    user = auth.get_user(user_id)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'user': user}), 200


@bp.post('')
@require_admin
def api_users_create():
    """Create new user (admin only).

    Request body:
        {
            "username": "newuser",
            "password": "password123",
            "role": "user"  // "admin" or "user"
        }

    Returns:
        201: {"success": true, "user_id": 123}
        400: {"error": "Missing required fields"}
        409: {"error": "Username already exists"}
    """
    auth = _get_auth_manager()
    data = request.get_json() or {}

    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user').strip()

    # Validate input
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400

    if role not in ('admin', 'user'):
        return jsonify({'error': 'Invalid role (must be "admin" or "user")'}), 400

    # Check if username already exists
    existing = auth.get_user_by_username(username)
    if existing:
        return jsonify({'error': 'Username already exists'}), 409

    # Create user
    created_by = g.scidk_user if hasattr(g, 'scidk_user') else 'system'
    user_id = auth.create_user(username, password, role, created_by=created_by)

    if not user_id:
        return jsonify({'error': 'Failed to create user'}), 500

    # Log audit event
    ip_address = request.remote_addr
    details = json.dumps({'user_id': user_id, 'username': username, 'role': role})
    auth.log_audit(created_by, 'user_created', details, ip_address)

    return jsonify({'success': True, 'user_id': user_id}), 201


@bp.put('/<int:user_id>')
@require_admin
def api_users_update(user_id):
    """Update user (admin only).

    Request body (all fields optional):
        {
            "username": "newusername",
            "password": "newpassword",
            "role": "admin",
            "enabled": true
        }

    Returns:
        200: {"success": true}
        404: {"error": "User not found"}
        400: {"error": "..."}
        403: {"error": "Cannot modify last admin"}
    """
    auth = _get_auth_manager()
    data = request.get_json() or {}

    # Check if user exists
    user = auth.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Safety check: prevent disabling or demoting the last admin
    if user['role'] == 'admin':
        admin_count = auth.count_admin_users()
        if admin_count <= 1:
            new_role = data.get('role')
            new_enabled = data.get('enabled')
            if (new_role and new_role != 'admin') or (new_enabled is False):
                return jsonify({'error': 'Cannot disable or demote the last admin user'}), 403

    # Extract update fields
    username = data.get('username', '').strip() if 'username' in data else None
    password = data.get('password') if 'password' in data else None
    role = data.get('role') if 'role' in data else None
    enabled = data.get('enabled') if 'enabled' in data else None

    # Validate role if provided
    if role is not None and role not in ('admin', 'user'):
        return jsonify({'error': 'Invalid role (must be "admin" or "user")'}), 400

    # Check username uniqueness if changing username
    if username and username != user['username']:
        existing = auth.get_user_by_username(username)
        if existing:
            return jsonify({'error': 'Username already exists'}), 409

    # Update user
    success = auth.update_user(user_id, username=username, password=password, role=role, enabled=enabled)

    if not success:
        return jsonify({'error': 'Failed to update user'}), 500

    # Log audit event
    updated_by = g.scidk_user if hasattr(g, 'scidk_user') else 'system'
    ip_address = request.remote_addr
    changes = {}
    if username: changes['username'] = username
    if password: changes['password'] = '***'
    if role: changes['role'] = role
    if enabled is not None: changes['enabled'] = enabled
    details = json.dumps({'user_id': user_id, 'changes': changes})
    auth.log_audit(updated_by, 'user_updated', details, ip_address)

    return jsonify({'success': True}), 200


@bp.delete('/<int:user_id>')
@require_admin
def api_users_delete(user_id):
    """Delete user (admin only).

    Returns:
        200: {"success": true}
        404: {"error": "User not found"}
        403: {"error": "Cannot delete last admin"}
        400: {"error": "Cannot delete yourself"}
    """
    auth = _get_auth_manager()

    # Check if user exists
    user = auth.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Prevent self-deletion
    current_username = g.scidk_user if hasattr(g, 'scidk_user') else None
    if user['username'] == current_username:
        return jsonify({'error': 'Cannot delete yourself'}), 400

    # Delete user (safety check for last admin is inside delete_user)
    success = auth.delete_user(user_id)

    if not success:
        return jsonify({'error': 'Cannot delete last admin user'}), 403

    # Log audit event
    deleted_by = current_username or 'system'
    ip_address = request.remote_addr
    details = json.dumps({'user_id': user_id, 'username': user['username']})
    auth.log_audit(deleted_by, 'user_deleted', details, ip_address)

    return jsonify({'success': True}), 200


@bp.post('/<int:user_id>/sessions/delete')
@require_admin
def api_users_delete_sessions(user_id):
    """Delete all sessions for a user (force logout, admin only).

    Returns:
        200: {"success": true}
        404: {"error": "User not found"}
    """
    auth = _get_auth_manager()

    # Check if user exists
    user = auth.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Delete sessions
    success = auth.delete_user_sessions(user_id)

    if not success:
        return jsonify({'error': 'Failed to delete sessions'}), 500

    # Log audit event
    action_by = g.scidk_user if hasattr(g, 'scidk_user') else 'system'
    ip_address = request.remote_addr
    details = json.dumps({'user_id': user_id, 'username': user['username']})
    auth.log_audit(action_by, 'user_sessions_deleted', details, ip_address)

    return jsonify({'success': True}), 200
