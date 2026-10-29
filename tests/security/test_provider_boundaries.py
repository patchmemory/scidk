"""Personal providers and approved global credential/configuration boundaries."""
from types import SimpleNamespace

import pytest
from flask import Flask
from cryptography.fernet import Fernet

from scidk.core.auth import AuthManager
from scidk.core.api_endpoint_registry import APIEndpointRegistry
from scidk.web.auth_middleware import init_auth_middleware
from scidk.web.routes import api_llm, api_settings


@pytest.fixture
def credential_app(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=str(tmp_path / 'settings.sqlite'))
    auth = AuthManager(app.config['SCIDK_SETTINGS_DB'])
    admin = auth.create_user('admin', 'synthetic-password', role='admin')
    user = auth.create_user('ordinary', 'synthetic-password', role='user')
    registry = APIEndpointRegistry(app.config['SCIDK_SETTINGS_DB'], Fernet.generate_key().decode())
    eid = registry.create_endpoint({'name': 'Synthetic endpoint', 'url': 'https://original.invalid/data',
        'auth_method': 'bearer', 'auth_value': 'synthetic-server-key', 'field_mappings': {}})['id']
    app.extensions['scidk'] = {'api_endpoint_registry': registry}
    app.register_blueprint(api_llm.bp); app.register_blueprint(api_settings.bp)
    init_auth_middleware(app)
    yield app, auth, admin, user, registry, eid
    auth.close()


def client_as(app, auth, uid, name):
    client = app.test_client(); client.set_cookie('scidk_session', auth.create_user_session(uid, name))
    return client


@pytest.mark.parametrize('principal', ['ordinary', 'anonymous', 'token', 'header-session', 'cross-origin'])
def test_global_credential_and_backup_routes_require_named_admin(credential_app, principal, monkeypatch):
    app, auth, admin, user, registry, eid = credential_app
    client = client_as(app, auth, user if principal == 'ordinary' else admin,
                       'ordinary' if principal == 'ordinary' else 'admin')
    headers = {}
    if principal == 'anonymous':
        client = app.test_client()
    if principal == 'token':
        headers['Authorization'] = 'Bearer ' + auth.create_api_token(admin, 'synthetic')['token']
    if principal == 'header-session':
        headers['Authorization'] = 'Bearer ' + auth.create_user_session(admin, 'admin')
    if principal == 'cross-origin':
        headers['Origin'] = 'https://elsewhere.invalid'
    monkeypatch.setattr(api_settings.requests, 'get', lambda *a, **k: pytest.fail('Unauthorized credential transport'))
    operations = [('GET', '/api/settings/api-endpoints', None),
        ('POST', '/api/settings/api-endpoints', {}),
        ('GET', '/api/settings/api-endpoints/' + eid, None),
        ('PUT', '/api/settings/api-endpoints/' + eid, {}),
        ('DELETE', '/api/settings/api-endpoints/' + eid, None),
        ('GET', '/api/settings/backups/example', None),
        ('DELETE', '/api/settings/backups/example', None),
        ('PATCH', '/api/settings/api-endpoints/' + eid, {'url': 'https://receiver.invalid/data'}),
        ('POST', '/api/settings/api-endpoints/' + eid + '/test', {}),
        ('GET', '/api/settings/export', None), ('POST', '/api/settings/import', {}),
        ('GET', '/api/settings/backups', None), ('POST', '/api/settings/backups', {}),
        ('POST', '/api/settings/backups/example/restore', {}), ('GET', '/api/backups/example.zip', None)]
    for method, path, body in operations:
        response = client.open(path, method=method, json=body, headers=headers)
        assert response.status_code in {401, 403}, (method, path, response.status_code)
        assert 'synthetic-server-key' not in response.get_data(as_text=True)
    assert registry.get_endpoint(eid)['url'] == 'https://original.invalid/data'


def test_personal_settings_remain_isolated_and_errors_hide_secrets(credential_app, monkeypatch):
    app, auth, admin, user, _, _ = credential_app
    ordinary = client_as(app, auth, user, 'ordinary'); owner = client_as(app, auth, admin, 'admin')
    assert owner.put('/api/llm/settings', json={'base_url': 'https://provider.invalid/v1',
        'model': 'synthetic', 'api_key': 'synthetic-owner-key'}).status_code == 200
    assert ordinary.get('/api/llm/settings').json['has_key'] is False
    assert ordinary.put('/api/llm/settings', json={'username': 'admin', 'api_key': 'replacement'}).status_code == 400
    assert ordinary.put('/api/llm/settings', json={'base_url': 'https://personal.invalid/v1', 'model': 'synthetic'}).status_code == 200
    def failure(*a, **k):
        raise RuntimeError('synthetic-owner-key secret backend output')
    monkeypatch.setattr('scidk.ai.openai_compatible.list_models', failure)
    for response in (owner.get('/api/llm/models'), owner.post('/api/llm/test', json={})):
        assert 'synthetic-owner-key' not in response.get_data(as_text=True)
        assert 'backend output' not in response.get_data(as_text=True)
        assert response.headers['Cache-Control'] == 'no-store'
    assert ordinary.post('/api/llm/import-parley-env', json={}).status_code == 403
    assert ordinary.put('/api/llm/settings', json={'base_url': 'https://key@provider.invalid/v1'}).status_code == 400


def test_named_admin_registry_test_refuses_redirects(credential_app, monkeypatch):
    app, auth, admin, _, _, eid = credential_app
    client = client_as(app, auth, admin, 'admin')
    assert client.get('/api/settings/api-endpoints').status_code == 200
    calls = []
    def redirect(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=302)
    monkeypatch.setattr(api_settings.requests, 'get', redirect)
    response = client.post('/api/settings/api-endpoints/' + eid + '/test', json={})
    assert response.status_code == 502 and calls[0]['allow_redirects'] is False
    assert 'synthetic-server-key' not in response.get_data(as_text=True)


def test_noauth_cannot_use_provider_or_global_credentials(tmp_path):
    app = Flask(__name__); app.config.update(TESTING=True, SCIDK_SETTINGS_DB=str(tmp_path / 'settings.sqlite'))
    auth = AuthManager(app.config['SCIDK_SETTINGS_DB'])
    app.register_blueprint(api_llm.bp); app.register_blueprint(api_settings.bp); init_auth_middleware(app)
    for method, path in [('GET', '/api/llm/settings'), ('PUT', '/api/llm/settings'), ('GET', '/api/llm/models'),
                         ('POST', '/api/llm/test'), ('GET', '/api/settings/export'), ('GET', '/api/settings/api-endpoints')]:
        assert app.test_client().open(path, method=method, json={}).status_code == 403
    auth.close()


def test_trusted_first_admin_bootstrap_and_transition(tmp_path):
    from scidk.web.routes.api_auth import bp as auth_bp
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=str(tmp_path / 'bootstrap.sqlite'))
    app.register_blueprint(api_settings.bp); app.register_blueprint(auth_bp)
    client = app.test_client()
    body = {'enabled': True, 'username': 'first-admin', 'password': 'synthetic-password'}
    token = 'synthetic-one-time-bootstrap-token-32-plus'
    path = '/api/settings/security/auth'
    # No configured administrator confers no rights, even from loopback.
    assert client.post(path, json=body).status_code == 403
    app.config['SCIDK_AUTH_BOOTSTRAP_TOKEN'] = token
    headers = {'X-SciDK-Bootstrap': token}
    assert client.post(path, json=body, headers={**headers, 'Origin': 'https://elsewhere.invalid'}).status_code == 403
    assert client.post(path, json=body, headers=headers, environ_base={'REMOTE_ADDR': '192.0.2.1'}).status_code == 403
    assert client.get('/api/settings/api-endpoints').status_code == 403
    assert client.post(path, json=body, headers=headers).status_code == 200
    # Bootstrap token is not a session and is unusable after first-user creation.
    assert client.post(path, json=body, headers=headers).status_code == 403
    assert client.get('/api/settings/export').status_code == 403
    response = client.post('/api/auth/login', json={'username': 'first-admin', 'password': 'synthetic-password'})
    assert response.status_code == 200 and response.json['role'] == 'admin'
    assert client.get('/api/settings/api-endpoints').status_code == 200
    auth = AuthManager(app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('ordinary', 'synthetic-password', role='user')
    ordinary = client_as(app, auth, uid, 'ordinary')
    assert ordinary.post(path, json={'enabled': False}).status_code == 403
    assert ordinary.get('/api/settings/export').status_code == 403
    assert client.post(path, json={'enabled': True, 'username': 'first-admin', 'password': 'synthetic-new-password'}).status_code == 200
    auth.close()
