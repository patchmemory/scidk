"""Tests for audit attribution of the authenticated user (Cycle 2, Task D / J10).

The attribute set by the auth layer is ``g.scidk_user``
(``auth_middleware.check_auth`` and ``decorators._authenticate_bearer_token``).
``g.scidk_username`` is set nowhere, so every read of it returned None.
"""
import pytest
from flask import g

from scidk.web.routes.api_scripts import _get_current_user


# ── _get_current_user reads g.scidk_user, falls back to 'system' ─────────────

def test_returns_authenticated_username(app):
    with app.test_request_context('/api/scripts/scripts'):
        g.scidk_user = 'alice'
        assert _get_current_user() == 'alice'


def test_falls_back_to_system_when_g_is_empty(app):
    """The three auth-bypass paths reach endpoints with nothing on g."""
    with app.test_request_context('/api/scripts/scripts'):
        assert _get_current_user() == 'system'


def test_falls_back_to_system_when_username_is_blank(app):
    with app.test_request_context('/api/scripts/scripts'):
        g.scidk_user = ''
        assert _get_current_user() == 'system'


def test_does_not_read_the_nonexistent_username_attribute(app):
    """A g.scidk_username value must not be picked up — nothing ever sets it."""
    with app.test_request_context('/api/scripts/scripts'):
        g.scidk_username = 'ghost'
        assert _get_current_user() == 'system'


# ── The username reaches the execution audit record ──────────────────────────

class _StubExecution:
    def to_dict(self):
        return {'status': 'ok'}


class _StubManager:
    def __init__(self):
        self.execute_kwargs = None

    def execute_script(self, **kwargs):
        self.execute_kwargs = kwargs
        return _StubExecution()


@pytest.fixture()
def stub_manager(app, monkeypatch):
    """Replace the ScriptsManager so no script file or Neo4j call is needed."""
    from scidk.web.routes import api_scripts

    manager = _StubManager()
    monkeypatch.setattr(api_scripts, '_get_scripts_manager', lambda: manager)
    monkeypatch.setattr(
        api_scripts, '_get_neo4j_driver_and_database', lambda: (None, None)
    )
    return manager


def test_executed_by_records_the_authenticated_user(app, stub_manager):
    @app.before_request
    def _fake_auth():
        # Mirrors what auth_middleware.check_auth does on a valid session.
        g.scidk_user = 'alice'
        g.scidk_user_role = 'admin'

    resp = app.test_client().post('/api/scripts/scripts/some-id/run', json={})

    assert resp.status_code == 200
    assert stub_manager.execute_kwargs['executed_by'] == 'alice'


def test_executed_by_falls_back_to_system_without_auth(app, stub_manager):
    """No AttributeError and no behaviour change on the test-bypass path."""
    resp = app.test_client().post('/api/scripts/scripts/some-id/run', json={})

    assert resp.status_code == 200
    assert stub_manager.execute_kwargs['executed_by'] == 'system'
