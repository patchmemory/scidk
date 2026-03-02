"""Flask decorators for authentication and authorization.

This module provides decorators for enforcing role-based access control (RBAC)
in route handlers.
"""

from functools import wraps
from flask import g, jsonify


def require_role(*allowed_roles):
    """Decorator to require specific role(s) for a route.

    Usage:
        @app.route('/admin/users')
        @require_role('admin')
        def admin_users():
            ...

        @app.route('/some-route')
        @require_role('admin', 'user')
        def some_route():
            ...

    Args:
        *allowed_roles: One or more role names (e.g., 'admin', 'user')

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # In test mode with auth disabled, allow all requests
            # This matches the behavior of auth_middleware which skips auth in test mode
            import os
            import sys
            from flask import current_app
            is_testing = (
                current_app.config.get('TESTING', False) or
                'pytest' in sys.modules or
                os.environ.get('SCIDK_E2E_TEST')
            )
            if is_testing and not os.environ.get('PYTEST_TEST_AUTH'):
                # In test mode - check if auth is actually enabled
                from ..core.auth import get_auth_manager
                db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
                auth = get_auth_manager(db_path=db_path)
                if not auth.is_enabled():
                    # Auth disabled in tests - allow the request
                    return f(*args, **kwargs)

            # Check if user is authenticated
            if not hasattr(g, 'scidk_user_role'):
                return jsonify({'error': 'Authentication required'}), 401

            # Check if user has required role
            user_role = g.scidk_user_role
            if user_role not in allowed_roles:
                return jsonify({
                    'error': 'Insufficient permissions',
                    'required_roles': list(allowed_roles),
                    'your_role': user_role
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_admin(f):
    """Decorator to require admin role for a route.

    Shortcut for @require_role('admin'), with special handling for first-time setup.
    When there are zero users, allows unauthenticated access for initial admin creation.

    Usage:
        @app.route('/admin/users')
        @require_admin
        def admin_users():
            ...

    Args:
        f: Route function

    Returns:
        Decorated function
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # In test mode with auth disabled, allow all requests
        import os
        import sys
        from flask import current_app
        is_testing = (
            current_app.config.get('TESTING', False) or
            'pytest' in sys.modules or
            os.environ.get('SCIDK_E2E_TEST')
        )
        if is_testing and not os.environ.get('PYTEST_TEST_AUTH'):
            from ..core.auth import get_auth_manager
            db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
            auth = get_auth_manager(db_path=db_path)
            if not auth.is_enabled():
                return f(*args, **kwargs)

        # Check for first-time setup (zero users) - allow unauthenticated access
        from ..core.auth import get_auth_manager
        from flask import current_app
        db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        auth = get_auth_manager(db_path=db_path)
        try:
            user_count = len(auth.list_users(include_disabled=True))
            if user_count == 0:
                # First-time setup - allow access without authentication
                return f(*args, **kwargs)
        except Exception:
            pass

        # Normal admin role check
        if not hasattr(g, 'scidk_user_role'):
            return jsonify({'error': 'Authentication required'}), 401

        user_role = g.scidk_user_role
        if user_role != 'admin':
            return jsonify({
                'error': 'Insufficient permissions',
                'required_roles': ['admin'],
                'your_role': user_role
            }), 403

        return f(*args, **kwargs)
    return decorated_function
