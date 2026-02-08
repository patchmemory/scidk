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

    Shortcut for @require_role('admin').

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
    return require_role('admin')(f)
