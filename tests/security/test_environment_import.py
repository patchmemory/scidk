"""Host environment credentials require a named single-user administrator."""
import pytest
from flask import Flask

from scidk.core.auth import AuthManager
from scidk.web.auth_middleware import init_auth_middleware
from scidk.web.routes.api_llm import bp


@pytest.fixture
def environment_app(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=str(tmp_path / 'settings.sqlite'))
    auth = AuthManager(app.config['SCIDK_SETTINGS_DB'])
    app.register_blueprint(bp)
    init_auth_middleware(app)
    calls = []
    def environment():
        calls.append(True)
        return {'PARLEY_API_KEY': 'synthetic-host-credential', 'PARLEY_BASE_URL': 'https://provider.example/v1'}
    monkeypatch.setattr('scidk.ai.provider_settings.read_parley_env', environment)
    yield app, auth, calls
    auth.close()


@pytest.mark.parametrize('identity', ['no-auth', 'user', 'admin-token', 'admin-header-session', 'multi-user-admin', 'cross-origin', 'locked'])
def test_environment_import_negative_authorization(environment_app, identity):
    app, auth, calls = environment_app
    client = app.test_client(); headers = {}
    if identity != 'no-auth':
        role = 'user' if identity == 'user' else 'admin'
        uid = auth.create_user('principal', 'synthetic-password', role=role)
        token = auth.create_user_session(uid, 'principal')
        if identity == 'admin-token':
            headers['Authorization'] = 'Bearer ' + auth.create_api_token(uid, 'synthetic')['token']
        elif identity == 'admin-header-session':
            headers['Authorization'] = 'Bearer ' + token
        else:
            client.set_cookie('scidk_session', token)
        if identity == 'multi-user-admin':
            auth.create_user('other', 'synthetic-password', role='user')
        if identity == 'cross-origin':
            headers['Origin'] = 'https://elsewhere.example'
        if identity == 'locked':
            auth.lock_session(token)
    response = client.post('/api/llm/import-parley-env', json={}, headers=headers)
    assert response.status_code in {401, 403, 423}
    assert not calls
    assert 'synthetic-host-credential' not in response.get_data(as_text=True)


def test_environment_import_error_does_not_disclose_output(environment_app, monkeypatch):
    app, auth, _ = environment_app
    uid = auth.create_user('admin', 'synthetic-password', role='admin')
    client = app.test_client(); client.set_cookie('scidk_session', auth.create_user_session(uid, 'admin'))
    def failing_environment():
        raise ValueError('synthetic-secret-process-output')
    monkeypatch.setattr('scidk.ai.provider_settings.read_parley_env', failing_environment)
    response = client.post('/api/llm/import-parley-env', json={})
    assert response.status_code == 400
    assert 'synthetic-secret-process-output' not in response.get_data(as_text=True)
