"""
Blueprint for API token management routes (admin-only).

API tokens let non-browser clients (Python scripts, MATLAB, etc.) authenticate
with an ``Authorization: Bearer <token>`` header instead of a browser session.
Each token is tied to a user and carries that user's existing role.

Endpoints:
- POST   /api/settings/tokens        - Generate a new token (plaintext returned once)
- GET    /api/settings/tokens        - List all tokens (metadata only)
- DELETE /api/settings/tokens/<id>   - Revoke a token by id
"""
import json
from flask import Blueprint, jsonify, request, current_app, g
from ...core.auth import get_auth_manager
from ..decorators import require_admin

bp = Blueprint('tokens', __name__, url_prefix='/api/settings/tokens')


def _get_auth_manager():
    """Get AuthManager instance using settings DB path from config."""
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_auth_manager(db_path=db_path)


@bp.post('')
@require_admin
def api_tokens_create():
    """Generate a new API token for a user (admin only).

    Request body:
        {
            "user_id": 123,
            "label": "Anderson MATLAB script"
        }

    Returns:
        201: {
            "id": "<uuid>",
            "token": "<plaintext>",
            "message": "Store this token now - it will not be shown again."
        }
        400: {"error": "Missing user_id or label"}
        404: {"error": "User not found"}
    """
    auth = _get_auth_manager()
    data = request.get_json(silent=True) or {}

    user_id = data.get('user_id')
    label = (data.get('label') or '').strip()

    if user_id is None or not label:
        return jsonify({'error': 'Missing user_id or label'}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id must be an integer'}), 400

    if auth.get_user(user_id) is None:
        return jsonify({'error': 'User not found'}), 404

    result = auth.create_api_token(user_id, label)
    if not result:
        return jsonify({'error': 'Failed to create token'}), 500

    # Audit the issuance (never log the plaintext token itself)
    created_by = g.scidk_user if hasattr(g, 'scidk_user') else 'system'
    details = json.dumps({'token_id': result['id'], 'user_id': user_id, 'label': label})
    auth.log_audit(created_by, 'api_token_created', details, request.remote_addr)

    return jsonify({
        'id': result['id'],
        'token': result['token'],
        'message': 'Store this token now - it will not be shown again.',
    }), 201


@bp.get('')
@require_admin
def api_tokens_list():
    """List all API tokens (admin only).

    Never returns token hashes or plaintext.

    Returns:
        200: {"tokens": [{"id", "user_id", "label", "created_at", "last_used_at"}]}
    """
    auth = _get_auth_manager()
    return jsonify({'tokens': auth.list_api_tokens()}), 200


@bp.delete('/<token_id>')
@require_admin
def api_tokens_delete(token_id):
    """Revoke (delete) an API token by id (admin only).

    Returns:
        200: {"success": true}
        404: {"error": "Token not found"}
    """
    auth = _get_auth_manager()
    deleted = auth.delete_api_token(token_id)

    if not deleted:
        return jsonify({'error': 'Token not found'}), 404

    created_by = g.scidk_user if hasattr(g, 'scidk_user') else 'system'
    auth.log_audit(created_by, 'api_token_revoked', json.dumps({'token_id': token_id}), request.remote_addr)

    return jsonify({'success': True}), 200
