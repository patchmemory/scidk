"""Readiness and explicit shared usage over real policy and fake HTTP provider."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scidk.ai import provider_settings
from scidk.ai.shared_provider import grant, resolve
from scidk.agent_tools.security import REFUSAL
from scidk.knowledge.projection import Projection, ContextService, git_revision, content_hash
from scidk.web.routes.ui import bp
from scidk.web.routes.api_llm import bp as llm_bp
from .conftest import ROOT, SCOPE
from .test_prompt12 import session


@pytest.fixture
def ready_app(scenario):
    d = scenario
    d.app.register_blueprint(bp); d.app.register_blueprint(llm_bp)
    d.app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_CHAT_READINESS_ENABLED=True,
        SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_REVIEW_WORKSPACE_ENABLED=True, SCIDK_REVIEW_CHAT_ENABLED=True)
    for name in ('get_system_context', 'explain_fact'):
        d.caps.grant_tool(d.reviewer, 'overview', name, admin_id=d.reviewer)
    d.policy.grant_resource(d.reviewer, **SCOPE, admin_id=d.reviewer)
    node = {'id': 'system:synthetic-demo', 'type': 'documentation', 'name': 'Synthetic System chat demonstration',
        'source_scope': SCOPE, 'visibility': 'restricted', 'git_revision': git_revision(ROOT),
        'applicability': 'knowledge-context/1', 'sources': [{'path': 'tests/fixtures/knowledge_curation/intake.csv',
        'hash': content_hash(d.intake_bytes), 'source_scope': SCOPE}]}
    projection = Projection([node], [], {'domain': 'system', 'synthetic': True})
    d.knowledge.system = ContextService(projection, d.db, enabled=True)
    for uid in (d.reviewer, d.alice):
        d.policy.grant_evidence(uid, ContextService.grant_id(node), admin_id=d.reviewer)
    client = session(d, 'reviewer')
    return d, client


def system_context():
    return {'tool': 'get_system_context', 'arguments': {'entry_id': 'system:synthetic-demo', 'depth': 0}}


@pytest.fixture
def fake_provider():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.headers.get('Authorization'), body))
            data = json.dumps({'model': 'synthetic-model', 'choices': [{'message': {'content':
                'Synthetic System context: consult system:synthetic-demo. No research facts are asserted.'},
                'finish_reason': 'stop'}]}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}/v1', calls
    server.shutdown(); thread.join(timeout=5); server.server_close()


def test_readiness_is_boolean_only_no_model_or_hidden_records(ready_app, monkeypatch):
    d, client = ready_app
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', lambda *a, **k: pytest.fail('Readiness must not contact a provider'))
    result = client.post('/admin/chat-readiness', json={'context': system_context()})
    assert result.status_code == 200, result.json
    assert result.json['ready'] is True
    assert all(type(item['ok']) is bool for item in result.json['checks'])
    assert result.json['transport']['connectivity_verified'] is False
    encoded = result.get_data(as_text=True)
    assert 'synthetic-demo' not in encoded and 'provider.example' not in encoded and 'intake-demo-a' not in encoded
    d.app.config['SCIDK_OVERVIEW_CHAT_ENABLED'] = False
    checks = client.post('/admin/chat-readiness', json={'context': system_context()}).json['checks']
    assert next(c for c in checks if c['check'] == 'chat_flag')['ok'] is False
    assert next(c for c in checks if c['check'] == 'context_authorized')['ok'] is True
    d.policy.revoke_destination('demo', admin_id=d.reviewer)
    checks = client.post('/admin/chat-readiness', json={}).json['checks']
    assert next(c for c in checks if c['check'] == 'provider_configuration')['ok'] is True
    assert next(c for c in checks if c['check'] == 'approved_provider')['ok'] is False


def test_readiness_denies_nonadmin_noauth_tokens_crossorigin_and_unknown_args(ready_app):
    d, client = ready_app
    alice = session(d)
    assert alice.post('/admin/chat-readiness', json={}).status_code == 403
    assert d.app.test_client().get('/admin/chat-readiness').status_code in {302, 401, 403}
    for header in ('Bearer ' + d.tokens['alice']['token'], 'Bearer ' + d.auth.create_user_session(d.reviewer, 'reviewer')):
        assert client.post('/admin/chat-readiness', json={}, headers={'Authorization': header}).status_code == 403
    assert client.post('/admin/chat-readiness', json={}, headers={'Origin': 'https://elsewhere.example'}).status_code == 403
    assert client.post('/admin/chat-readiness', json={'user_id': d.alice}).status_code == 400
    d.app.config['SCIDK_CHAT_READINESS_ENABLED'] = False
    assert client.get('/admin/chat-readiness').status_code == 404


def test_system_chat_real_transport_shared_key_stays_server_side(ready_app, fake_provider):
    d, admin = ready_app
    endpoint, calls = fake_provider
    d.policy.approve_destination('fake-http', endpoint, 'synthetic-model', 'medium', admin_id=d.reviewer)
    provider_settings.save(d.db, 'reviewer', base_url=endpoint, model='synthetic-model', api_key='synthetic-shared-only')
    alice = session(d)
    provider_settings.save(d.db, 'alice', base_url=endpoint, model='synthetic-model')
    grant(d.db, d.alice, d.reviewer, admin_id=d.reviewer)
    assert provider_settings.stored_endpoint(d.db, 'alice')['api_key'] is None
    assert provider_settings.public_settings(d.db, 'alice')['has_key'] is False
    response = alice.post('/api/chat/overview', json={'message': 'Describe this synthetic context.', 'context': system_context(), 'send_question': True})
    assert response.status_code == 200, response.json
    assert len(calls) == 1 and calls[0][0] == 'Bearer synthetic-shared-only'
    assert 'Synthetic System chat' in json.dumps(calls[0][1]) and 'tools' not in calls[0][1]
    assert 'synthetic-shared-only' not in response.get_data(as_text=True)
    assert 'synthetic-shared-only' not in alice.get('/api/llm/settings').get_data(as_text=True)
    # Changing an endpoint/model never carries the owner's secret to the new one.
    provider_settings.save(d.db, 'alice', base_url='https://elsewhere.example/v1')
    assert resolve(d.db, 'alice')['api_key'] is None
    grant(d.db, d.alice, d.reviewer, admin_id=d.reviewer, allow=False)
    assert resolve(d.db, 'alice')['api_key'] is None
    with pytest.raises(Exception):
        grant(d.db, d.bob, d.reviewer, admin_id=d.alice)


def test_shared_usage_revocation_during_turn_refuses_reply(ready_app, monkeypatch):
    d, _ = ready_app
    alice = session(d)
    provider_settings.save(d.db, 'reviewer', base_url='https://provider.example/v1', model='synthetic-model', api_key='synthetic-granted-key')
    grant(d.db, d.alice, d.reviewer, admin_id=d.reviewer)
    def revoking(*a, **k):
        grant(d.db, d.alice, d.reviewer, admin_id=d.reviewer, allow=False)
        return {'content': 'Must not return after shared usage revocation'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', revoking)
    assert alice.post('/api/chat/overview', json={'message': 'Explain', 'context': system_context(), 'send_question': True}).json == REFUSAL


@pytest.mark.parametrize('change', ['owner-disabled', 'owner-demoted', 'recipient-disabled', 'owner-model'])
def test_shared_usage_rechecks_account_and_exact_owner_model(ready_app, change):
    d, _ = ready_app
    session(d)
    provider_settings.save(d.db, 'reviewer', base_url='https://provider.example/v1', model='synthetic-model', api_key='synthetic-owner-only')
    grant(d.db, d.alice, d.reviewer, admin_id=d.reviewer)
    assert resolve(d.db, 'alice')['api_key'] == 'synthetic-owner-only'
    if change == 'owner-disabled':
        d.auth.update_user(d.reviewer, enabled=False)
    elif change == 'owner-demoted':
        d.auth.update_user(d.reviewer, role='user')
    elif change == 'recipient-disabled':
        d.auth.update_user(d.alice, enabled=False)
    else:
        provider_settings.save(d.db, 'reviewer', model='another-model')
    assert resolve(d.db, 'alice')['api_key'] is None
