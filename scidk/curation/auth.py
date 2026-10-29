"""Existing SciDK session + explicit human review grant. No API-token fallback."""
import json

from flask import current_app, request
from scidk.core.auth import get_auth_manager
from scidk.core.settings import InterpreterSettings
from .review import AuthorizationError


class AuthenticationError(AuthorizationError):
    pass


GRANT_KEY = 'curation.human_reviewer_user_ids'


def request_reviewer():
    auth = get_auth_manager(db_path=current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db'))
    try:
        if not auth.is_enabled():
            raise AuthenticationError('Authentication must be enabled for curation review')
        if request.headers.get('Authorization'):
            raise AuthorizationError('API credentials cannot perform human review')
        token = request.cookies.get('scidk_session')
        user = auth.get_session_user(token) if token else None
        if not user or not user.get('id'):
            raise AuthenticationError('Named user session required')
        if auth.is_session_locked(token):
            raise AuthorizationError('Session is locked')
        if user['role'] != 'admin' or not granted_user(user['id']):
            raise AuthorizationError('Explicit human reviewer grant required')
        # SameSite cookies are supplemented by rejecting cross-origin browser POSTs.
        if request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            raise AuthorizationError('Cross-site review rejected')
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            raise AuthorizationError('Cross-origin review rejected')
        return str(user['id'])
    finally:
        auth.close()


def granted_user(reviewer):
    path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    auth = get_auth_manager(db_path=path)
    try:
        if not auth.is_enabled():
            return False
        user = auth.get_user(int(reviewer))
        if not user or not user['enabled'] or user['role'] != 'admin':
            return False
        settings = InterpreterSettings(path)
        try:
            row = settings.db.execute('SELECT value FROM interpreter_settings WHERE key=?', (GRANT_KEY,)).fetchone()
            grants = json.loads(row[0]) if row else []
        finally:
            settings.close()
        return isinstance(grants, list) and any(type(item) is int and item == user['id'] for item in grants)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    finally:
        auth.close()
