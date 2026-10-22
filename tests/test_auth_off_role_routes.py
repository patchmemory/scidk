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


# ── Fail closed: an unreadable settings DB is not "auth off" ────────────────

class _UnreadableDB:
    """Opens fine, fails every read: a locked or damaged settings DB."""
    def __init__(self, real):
        self._real = real

    def execute(self, sql, *args, **kwargs):
        if sql.lstrip().upper().startswith('SELECT'):
            import sqlite3
            raise sqlite3.OperationalError('database is locked')
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_is_enabled_is_true_when_auth_state_is_unreadable(tmp_path):
    from scidk.core.auth import AuthManager
    auth = AuthManager(db_path=str(tmp_path / 'settings.db'))
    assert auth.is_enabled() is False          # readable, no users: off
    auth.db = _UnreadableDB(auth.db)
    assert auth.is_enabled() is True           # unreadable: treated as on


def test_gated_routes_refuse_when_auth_state_is_unreadable(prod_like_client, monkeypatch):
    _, client = prod_like_client
    from scidk.core import auth as auth_mod
    real = auth_mod.AuthManager.__init__

    def init(self, *a, **kw):
        real(self, *a, **kw)
        self.db = _UnreadableDB(self.db)
    monkeypatch.setattr(auth_mod.AuthManager, '__init__', init)
    assert client.get('/api/drives').status_code == 401
    assert client.get('/api/users').status_code == 401


def test_gated_route_never_runs_on_a_corrupt_settings_file(prod_like_client):
    app, client = prod_like_client
    with open(app.config['SCIDK_SETTINGS_DB'], 'wb') as f:
        f.write(b'not a sqlite database' * 100)
    resp = client.get('/api/drives')
    assert resp.status_code != 200
    assert 'drives' not in (resp.get_json(silent=True) or {})
