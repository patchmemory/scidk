"""Strict named-session boundary for credential and readiness adapters."""
from flask import current_app, g, request
from ..core.auth import get_auth_manager


def named_session(*, admin=False, allow_header=False):
    auth = get_auth_manager(db_path=current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db'))
    try:
        header = request.headers.get('Authorization', '')
        if header and (not allow_header or not header.startswith('Bearer ')):
            raise PermissionError()
        token = header[7:] if header else request.cookies.get('scidk_session')
        user = auth.get_session_user(token) if token and auth.is_enabled() else None
        if (not user or not user.get('id') or auth.is_session_locked(token)
                or (admin and user.get('role') != 'admin')
                or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none')
                or (request.headers.get('Origin') and request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/'))):
            raise PermissionError()
        g.scidk_user = user['username']; g.scidk_user_id = user['id']; g.scidk_user_role = user['role']
        return user
    finally:
        auth.close()
