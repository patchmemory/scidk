"""With auth off (no users), role-gated routes run instead of returning 401.

Regression for FILES_PAGE_REVIEW X1: require_role / require_admin used to skip
the check only under pytest/TESTING, so a no-auth deployment got 401 on Add
Drive, Attribute, Collect and the rest while every test passed. Here the test
bypass is disabled (PYTEST_TEST_AUTH, TESTING off) to look like production.
"""
import pytest

from scidk.app import create_app


@pytest.fixture
def prod_like_client(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    app = create_app()
    app.config['TESTING'] = False
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    return app, app.test_client()


def test_require_role_runs_when_auth_off(prod_like_client):
    _, client = prod_like_client
    resp = client.get('/api/drives')
    assert resp.status_code == 200, resp.get_json()


def test_require_admin_runs_when_auth_off(prod_like_client):
    _, client = prod_like_client
    resp = client.get('/api/users')
    assert resp.status_code == 200, resp.get_json()


def test_auth_on_still_rejects_unauthenticated(prod_like_client):
    app, client = prod_like_client
    from scidk.core.auth import get_auth_manager
    get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB']).create_user(
        'someone', 'password123', role='user')
    assert client.get('/api/drives').status_code == 401
    assert client.get('/api/users').status_code == 401
