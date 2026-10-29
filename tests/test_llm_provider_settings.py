"""The one OpenAI-compatible provider setting, per user (Task 1).

Runs against a small fake Parley (an http.server thread) that checks the
Bearer key, serves /models and /chat/completions, sets Parley's cost and
request-id headers, and refuses with content_filter for one model.
"""
import json
import os
import sqlite3
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scidk.ai import provider_settings
from scidk.ai.openai_compatible import OpenAICompatibleProvider, ProviderError, chat_completion, list_models
from scidk.app import create_app

GOOD_KEY = 'sk-parley-v1-good-secret-1234'


class _FakeParley(BaseHTTPRequestHandler):
    seen_auth = []

    def log_message(self, *a):
        pass

    def _send(self, code, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        auth = self.headers.get('Authorization', '')
        type(self).seen_auth.append(auth)
        if auth != f'Bearer {GOOD_KEY}':
            self._send(401, {'error': {'message': 'invalid api key'}})
            return False
        return True

    def do_GET(self):
        if self.path != '/v1/models':
            type(self).seen_auth.append(self.headers.get('Authorization', ''))
            self._send(404, {'error': {'message': 'not found'}})
        elif self._authorized():
            self._send(200, {'data': [{'id': 'claude-sonnet-5-5'}, {'id': 'filtered-model'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path != '/v1/chat/completions' or not self._authorized():
            return
        if body['model'] == 'filtered-model':
            msg, finish = {'role': 'assistant', 'content': None, 'refusal': 'Blocked by policy'}, 'content_filter'
        else:
            msg, finish = {'role': 'assistant', 'content': 'ok', 'thinking': 'secret reasoning'}, 'stop'
        self._send(200, {'model': body['model'], 'choices': [{'message': msg, 'finish_reason': finish}],
                         'usage': {'prompt_tokens': 5, 'completion_tokens': 1}},
                   {'x-parley-v1-cost': '0.0004', 'x-parley-v1-request-id': 'req-123'})


@pytest.fixture(scope='module')
def parley():
    server = HTTPServer(('127.0.0.1', 0), _FakeParley)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}/v1'
    server.shutdown()


# ── Client ─────────────────────────────────────────────────────────────────

def test_client_lists_models_and_reports_cost(parley):
    assert list_models(parley, GOOD_KEY) == ['claude-sonnet-5-5', 'filtered-model']
    turn = chat_completion(parley, GOOD_KEY, 'claude-sonnet-5-5', [{'role': 'user', 'content': 'hi'}])
    assert turn['content'] == 'ok' and turn['cost'] == '0.0004' and turn['request_id'] == 'req-123'
    assert 'thinking' not in turn['raw_message']


def test_client_bad_key_is_a_clear_error(parley):
    with pytest.raises(ProviderError, match='401.*check the API key'):
        list_models(parley, 'sk-wrong')


def test_refusal_is_shown_not_raised(parley):
    p = OpenAICompatibleProvider(parley, GOOD_KEY, 'filtered-model')
    assert 'Blocked by policy' in p.complete('hi')
    assert p.last_turn['finish_reason'] == 'content_filter'


# ── Storage ────────────────────────────────────────────────────────────────

def test_key_is_encrypted_at_rest_and_never_returned(tmp_path, monkeypatch):
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    db = str(tmp_path / 'settings.db')
    out = provider_settings.save(db, 'alice', preset='parley', base_url='https://parley.api.mit.edu/v1',
                                 model='claude-sonnet-5-5', api_key=GOOD_KEY)
    assert GOOD_KEY not in json.dumps(out) and out['key_hint'] == 'sk-…1234' and out['has_key']
    raw = sqlite3.connect(db).execute('SELECT api_key_enc FROM llm_user_settings').fetchone()[0]
    assert GOOD_KEY not in raw
    key_file = tmp_path / '.scidk_secret.key'
    assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    assert provider_settings.credentials(db, 'alice')['api_key'] == GOOD_KEY
    # a blank key on save keeps the stored one; clear_key removes it
    assert provider_settings.save(db, 'alice', model='other')['has_key']
    assert not provider_settings.save(db, 'alice', clear_key=True)['has_key']


def test_bad_base_url_is_refused(tmp_path):
    with pytest.raises(ValueError):
        provider_settings.save(str(tmp_path / 's.db'), 'alice', base_url='file:///etc/passwd')


# ── Routes, two users ──────────────────────────────────────────────────────

@pytest.fixture
def two_users(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    from scidk.core.auth import get_auth_manager
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])

    def h(name):
        uid = auth.create_user(name, 'password123', role='user')
        return {'Authorization': f'Bearer {auth.create_user_session(uid, name)}'}
    return app, app.test_client(), {'alice': h('alice'), 'bob': h('bob')}


def test_each_user_has_their_own_setting(two_users, parley):
    _, c, u = two_users
    r = c.put('/api/llm/settings', headers=u['alice'], json={
        'preset': 'parley', 'base_url': parley, 'model': 'claude-sonnet-5-5', 'api_key': GOOD_KEY})
    assert r.status_code == 200 and GOOD_KEY not in r.get_data(as_text=True)
    assert c.get('/api/llm/settings', headers=u['bob']).get_json()['configured'] is False
    mine = c.get('/api/llm/settings', headers=u['alice']).get_json()
    assert mine['model'] == 'claude-sonnet-5-5' and mine['key_hint'] == 'sk-…1234'
    assert c.get('/api/llm/settings').status_code == 401


def test_test_connection_and_models(two_users, parley):
    _, c, u = two_users
    c.put('/api/llm/settings', headers=u['alice'], json={'base_url': parley, 'model': 'claude-sonnet-5-5',
                                                         'api_key': GOOD_KEY})
    ok = c.post('/api/llm/test', headers=u['alice'], json={}).get_json()
    assert ok['ok'] and ok['models'] == 2 and ok['cost'] == '0.0004'
    assert c.get('/api/llm/models', headers=u['alice']).get_json()['models'][0] == 'claude-sonnet-5-5'
    bad = c.post('/api/llm/test', headers=u['bob'], json={'base_url': parley, 'api_key': 'sk-nope'}).get_json()
    assert not bad['ok'] and '401' in bad['error']


def test_stored_key_is_not_sent_to_another_url(two_users, parley):
    _, c, u = two_users
    c.put('/api/llm/settings', headers=u['alice'], json={'base_url': parley, 'model': 'm', 'api_key': GOOD_KEY})
    _FakeParley.seen_auth.clear()
    c.get('/api/llm/models', headers=u['alice'], query_string={'base_url': parley + '/other'})
    assert _FakeParley.seen_auth and all(GOOD_KEY not in a for a in _FakeParley.seen_auth)


def test_import_from_parley_env_refused_on_shared_install(two_users):
    _, c, u = two_users
    r = c.post('/api/llm/import-parley-env', headers=u['alice'], json={})
    assert r.status_code == 403


def test_import_from_parley_env_on_single_user_install(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    fake = bin_dir / 'parley'
    fake.write_text("#!/bin/sh\necho \"export PARLEY_API_KEY='sk-parley-v1-fromenv-9999'\"\n"
                    "echo \"export PARLEY_BASE_URL='https://parley.example/v1'\"\n")
    fake.chmod(0o755)
    monkeypatch.setenv('PATH', f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    from scidk.core.auth import get_auth_manager
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('admin', 'synthetic-password', role='admin')
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'admin'))
    out = client.post('/api/llm/import-parley-env', json={'model': 'claude-sonnet-5-5'})
    body = out.get_json()
    assert out.status_code == 200, body
    assert body['base_url'] == 'https://parley.example/v1' and body['key_hint'] == 'sk-…9999'
    assert 'fromenv' not in out.get_data(as_text=True)


# ── The chat routes use the user's provider ────────────────────────────────

def test_for_request_prefers_the_users_setting(two_users, parley):
    app, c, u = two_users
    c.put('/api/llm/settings', headers=u['alice'], json={'base_url': parley, 'model': 'claude-sonnet-5-5',
                                                         'api_key': GOOD_KEY})
    from flask import g
    from scidk.ai.provider_factory import LLMProviderFactory
    with app.test_request_context('/api/chat/graphrag', method='POST', json={'message': 'hi'}):
        g.scidk_user = 'alice'
        p = LLMProviderFactory.for_request({'chat_llm_provider': 'ollama'})
        assert isinstance(p, OpenAICompatibleProvider) and p.complete('hi') == 'ok'
    # An explicit provider in the request takes the legacy path (here: no OpenAI key configured).
    monkeypatch_env = {k: os.environ.pop(k) for k in ('SCIDK_CHAT_OPENAI_API_KEY', 'OPENAI_API_KEY') if k in os.environ}
    try:
        with app.test_request_context('/api/chat/graphrag', method='POST', json={'message': 'hi', 'provider': 'openai'}):
            g.scidk_user = 'alice'
            with pytest.raises(ValueError, match='OpenAI API key required'):
                LLMProviderFactory.for_request({'chat_llm_provider': 'openai'})
    finally:
        os.environ.update(monkeypatch_env)


def test_models_can_be_listed_before_a_model_is_chosen(two_users, parley):
    """The browser saves URL + key, then loads models to pick one: no model yet."""
    _, c, u = two_users
    c.put('/api/llm/settings', headers=u['alice'], json={'preset': 'custom', 'base_url': parley, 'api_key': GOOD_KEY})
    r = c.get('/api/llm/models', headers=u['alice'], query_string={'base_url': parley})
    assert r.status_code == 200, r.get_json()
    assert 'claude-sonnet-5-5' in r.get_json()['models']
