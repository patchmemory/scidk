"""
Tests for per-user API token (Bearer) authentication.

Covers:
- AuthManager token CRUD and verification (table creation, generate, list,
  revoke, bcrypt verify, last_used_at update, disabled-user handling).
- Token management endpoints (admin-only).
- Bearer API token auth flowing through the middleware + decorators.
"""
import os
import re
import tempfile
import time

import pytest

from scidk.core.auth import AuthManager, get_auth_manager
from scidk.app import create_app


HEX64 = re.compile(r'^[0-9a-f]{64}$')


class TestApiTokenManager:
    """Unit tests for AuthManager API token methods."""

    @pytest.fixture
    def auth(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        auth_manager = AuthManager(db_path=db_path)
        yield auth_manager
        auth_manager.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_api_tokens_table_exists(self, auth):
        cur = auth.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_tokens'"
        )
        assert cur.fetchone() is not None

    def test_create_api_token_returns_id_and_plaintext(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        result = auth.create_api_token(user_id, 'MATLAB script')
        assert result is not None
        assert 'id' in result and 'token' in result
        # secrets.token_hex(32) -> 64 hex chars
        assert HEX64.match(result['token'])

    def test_create_api_token_unknown_user(self, auth):
        assert auth.create_api_token(99999, 'nope') is None

    def test_list_api_tokens_hides_secrets(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        created = auth.create_api_token(user_id, 'script A')

        tokens = auth.list_api_tokens()
        assert len(tokens) == 1
        t = tokens[0]
        assert t['id'] == created['id']
        assert t['user_id'] == user_id
        assert t['label'] == 'script A'
        assert 'token' not in t
        assert 'token_hash' not in t

    def test_verify_api_token_valid(self, auth):
        user_id = auth.create_user('alice', 'pw', role='admin')
        created = auth.create_api_token(user_id, 'script')

        user = auth.verify_api_token(created['token'])
        assert user is not None
        assert user['id'] == user_id
        assert user['username'] == 'alice'
        assert user['role'] == 'admin'

    def test_verify_api_token_invalid(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        auth.create_api_token(user_id, 'script')
        assert auth.verify_api_token('not-a-real-token') is None
        assert auth.verify_api_token('') is None
        assert auth.verify_api_token(None) is None

    def test_verify_api_token_updates_last_used(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        created = auth.create_api_token(user_id, 'script')

        assert auth.list_api_tokens()[0]['last_used_at'] is None
        time.sleep(1)  # CURRENT_TIMESTAMP has 1s resolution
        auth.verify_api_token(created['token'])
        assert auth.list_api_tokens()[0]['last_used_at'] is not None

    def test_verify_api_token_disabled_user(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        created = auth.create_api_token(user_id, 'script')
        auth.update_user(user_id, enabled=False)
        assert auth.verify_api_token(created['token']) is None

    def test_delete_api_token(self, auth):
        user_id = auth.create_user('alice', 'pw', role='user')
        created = auth.create_api_token(user_id, 'script')

        assert auth.delete_api_token(created['id']) is True
        assert auth.list_api_tokens() == []
        # Deleting again / unknown id returns False
        assert auth.delete_api_token(created['id']) is False
        assert auth.delete_api_token('no-such-id') is False

        # A revoked token no longer authenticates
        assert auth.verify_api_token(created['token']) is None


class TestApiTokenEndpoints:
    """Endpoint + Bearer auth tests with authentication enforced."""

    @pytest.fixture
    def app(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            test_db_path = f.name
        os.environ['PYTEST_TEST_AUTH'] = '1'
        app = create_app()
        app.config['TESTING'] = True
        app.config['SCIDK_SETTINGS_DB'] = test_db_path
        yield app
        os.environ.pop('PYTEST_TEST_AUTH', None)
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)

    @pytest.fixture
    def auth(self, app):
        return get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def _admin(self, auth):
        uid = auth.create_user('admin', 'password123', role='admin')
        session = auth.create_user_session(uid, 'admin')
        return uid, session

    def _user(self, auth):
        uid = auth.create_user('bob', 'password123', role='user')
        session = auth.create_user_session(uid, 'bob')
        return uid, session

    def test_create_token_requires_admin(self, client, auth):
        user_id, user_session = self._user(auth)
        resp = client.post(
            '/api/settings/tokens',
            json={'user_id': user_id, 'label': 'x'},
            headers={'Authorization': f'Bearer {user_session}'},
        )
        assert resp.status_code == 403

    def test_create_token_unauthenticated(self, client, auth):
        # Auth is enabled (an admin exists) but no credentials provided.
        self._admin(auth)
        resp = client.post('/api/settings/tokens', json={'user_id': 1, 'label': 'x'})
        assert resp.status_code == 401

    def test_create_list_revoke_flow(self, client, auth):
        admin_id, admin_session = self._admin(auth)
        hdr = {'Authorization': f'Bearer {admin_session}'}

        # Create
        resp = client.post(
            '/api/settings/tokens',
            json={'user_id': admin_id, 'label': 'pipeline token'},
            headers=hdr,
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert HEX64.match(body['token'])
        token_id = body['id']
        plaintext = body['token']

        # List (metadata only)
        resp = client.get('/api/settings/tokens', headers=hdr)
        assert resp.status_code == 200
        tokens = resp.get_json()['tokens']
        assert any(t['id'] == token_id for t in tokens)
        assert all('token' not in t and 'token_hash' not in t for t in tokens)

        # Revoke
        resp = client.delete(f'/api/settings/tokens/{token_id}', headers=hdr)
        assert resp.status_code == 200

        # Revoke again -> 404
        resp = client.delete(f'/api/settings/tokens/{token_id}', headers=hdr)
        assert resp.status_code == 404

        # Revoked token no longer authenticates
        resp = client.get('/api/users', headers={'Authorization': f'Bearer {plaintext}'})
        assert resp.status_code == 401

    def test_create_token_validation(self, client, auth):
        admin_id, admin_session = self._admin(auth)
        hdr = {'Authorization': f'Bearer {admin_session}'}

        assert client.post('/api/settings/tokens', json={'label': 'x'}, headers=hdr).status_code == 400
        assert client.post('/api/settings/tokens', json={'user_id': admin_id}, headers=hdr).status_code == 400
        assert client.post('/api/settings/tokens', json={'user_id': 99999, 'label': 'x'}, headers=hdr).status_code == 404

    def test_api_token_authenticates_as_admin(self, client, auth):
        admin_id, admin_session = self._admin(auth)
        created = auth.create_api_token(admin_id, 'admin token')

        # Use the API token (not a session) as Bearer on an admin-only route.
        resp = client.get('/api/users', headers={'Authorization': f'Bearer {created["token"]}'})
        assert resp.status_code == 200

    def test_api_token_carries_user_role(self, client, auth):
        user_id, _ = self._user(auth)
        # Need auth enabled with at least one admin so enforcement is on
        self._admin(auth)
        created = auth.create_api_token(user_id, 'user token')

        # A 'user'-role token is blocked from an admin-only route.
        resp = client.get('/api/users', headers={'Authorization': f'Bearer {created["token"]}'})
        assert resp.status_code == 403

    def test_invalid_bearer_token_rejected(self, client, auth):
        self._admin(auth)  # auth enabled
        resp = client.get('/api/users', headers={'Authorization': 'Bearer totally-bogus'})
        assert resp.status_code == 401
