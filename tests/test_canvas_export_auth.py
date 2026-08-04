"""Auth on the canvas export routes (Cycle 2, Task E).

/export/cypher, /export/python, and /export/rocrate were open while /commit
next to them was admin-gated. They only serialize a client-supplied snapshot,
so they stay open to any authenticated role rather than to admins only — but an
unauthenticated caller now gets a 401.

Setup mirrors TestRBACDecorator in test_auth_multiuser.py: PYTEST_TEST_AUTH
makes the decorators enforce instead of taking the test-mode bypass, and
creating a user is what flips AuthManager.is_enabled() on.
"""
import os
import tempfile
from pathlib import Path

import pytest

from scidk.app import create_app


EXPORT_ROUTES = [
    '/api/canvas/export/cypher',
    '/api/canvas/export/python',
    '/api/canvas/export/rocrate',
]

SNAPSHOT = {
    'snapshot': {
        'nodes': [
            {'id': 'n1', 'label': 'Sample', 'name': 'S1', 'provisional': True},
        ],
        'edges': [],
    },
    'layer_name': 'test_layer',
}


@pytest.fixture
def auth_app():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        test_db_path = f.name

    os.environ['PYTEST_TEST_AUTH'] = '1'

    application = create_app()
    application.config['TESTING'] = True
    application.config['SCIDK_SETTINGS_DB'] = test_db_path

    yield application

    os.environ.pop('PYTEST_TEST_AUTH', None)
    Path(test_db_path).unlink(missing_ok=True)


@pytest.fixture
def auth(auth_app):
    from scidk.core.auth import get_auth_manager
    return get_auth_manager(db_path=auth_app.config['SCIDK_SETTINGS_DB'])


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


@pytest.mark.parametrize('route', EXPORT_ROUTES)
def test_export_requires_authentication(client, route):
    resp = client.post(route, json=SNAPSHOT)

    assert resp.status_code == 401


@pytest.mark.parametrize('route', EXPORT_ROUTES)
def test_export_allowed_for_regular_user(client, auth, route):
    """Export is read-like, so a non-admin user is not locked out."""
    user_id = auth.create_user('exporter', 'password123', role='user')
    token = auth.create_user_session(user_id, 'exporter')

    resp = client.post(
        route, json=SNAPSHOT, headers={'Authorization': f'Bearer {token}'}
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_data(as_text=True).strip() != ''


@pytest.mark.parametrize('route', EXPORT_ROUTES)
def test_export_allowed_for_admin(client, auth, route):
    user_id = auth.create_user('boss', 'password123', role='admin')
    token = auth.create_user_session(user_id, 'boss')

    resp = client.post(
        route, json=SNAPSHOT, headers={'Authorization': f'Bearer {token}'}
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_commit_still_admin_only(client, auth):
    """The stricter gate on /commit is unchanged."""
    user_id = auth.create_user('exporter', 'password123', role='user')
    token = auth.create_user_session(user_id, 'exporter')

    resp = client.post(
        '/api/canvas/commit?preview=1',
        json=SNAPSHOT,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert resp.status_code == 403
