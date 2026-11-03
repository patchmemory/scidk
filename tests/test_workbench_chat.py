"""Shared Chat workbench endpoint: POST /api/chat/workbench.

Only the outgoing provider HTTP call (requests.post inside the one governed client) is stubbed; nothing leaves the
machine. Every unavailable case must also prove the stub was never reached.
"""
import json
import sqlite3
from pathlib import Path

import pytest
import requests

from scidk.agent_tools import security
from scidk.agent_tools.capabilities import CapabilityStore
from scidk.agent_tools.security import PolicyStore
from scidk.ai import openai_compatible, provider_settings
from scidk.app import create_app
from scidk.core.auth import get_auth_manager
from scidk.pipeline.store import PipelineStore
from scidk.services import workbench_chat

URL = 'https://parley.example/v1'
MODEL = 'fixture-model'
KEY = 'fixture-secret-key-9876'
PROMPT = 'synthetic prompt about metadata'
ANSWER = 'synthetic answer text'
ROOT = Path(__file__).resolve().parents[1]


class Transport:
    """Stub for requests.post inside scidk.ai.openai_compatible."""

    def __init__(self):
        self.calls, self.content, self.error, self.extra = [], ANSWER, None, {}

    def __call__(self, url, headers=None, data=None, timeout=None, allow_redirects=None, **kw):
        self.calls.append({'url': url, 'headers': dict(headers or {}), 'body': json.loads(data)})
        if self.error:
            raise self.error
        message = {'role': 'assistant', 'content': self.content, **self.extra.get('message', {})}
        payload = {'choices': [{'message': message, 'finish_reason': self.extra.get('finish', 'stop')}],
                   'usage': {'prompt_tokens': 3, 'completion_tokens': 4}, 'model': MODEL}
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        response.headers['x-parley-v1-request-id'] = 'req-123'
        return response


@pytest.fixture
def transport(monkeypatch):
    stub = Transport()
    monkeypatch.setattr(openai_compatible.requests, 'post', stub)
    monkeypatch.setattr(openai_compatible.requests, 'get', lambda *a, **k: pytest.fail('unexpected GET'))
    workbench_chat.reset_rate_limits()
    yield stub
    workbench_chat.reset_rate_limits()


@pytest.fixture
def build(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    monkeypatch.setattr(security, 'FULL_ACCESS', False)

    def make(*, flags=True, provider=True, approve=True, capabilities=True, approved_model=MODEL):
        app = create_app()
        db = str(tmp_path / 'settings.db')
        app.config.update(TESTING=True, SCIDK_SETTINGS_DB=db, SCIDK_GUI_V3_ENABLED=flags,
                          SCIDK_OVERVIEW_CHAT_ENABLED=flags)
        auth = get_auth_manager(db_path=db)
        admin = auth.create_user('admin', 'password123', role='admin')
        alice = auth.create_user('alice', 'password123', role='user')
        PipelineStore(db)
        store = PolicyStore(db)
        store.initialize(admin_id=admin)
        if capabilities:
            CapabilityStore(db).initialize(admin_id=admin)
        if approve:
            store.approve_destination('parley', URL, approved_model, 'medium', admin_id=admin)
        if provider:
            provider_settings.save(db, 'alice', preset='custom', base_url=URL, model=MODEL, api_key=KEY)
        client = app.test_client()
        client.set_cookie('scidk_session', auth.create_user_session(alice, 'alice'))
        return app, client, db

    return make


def send(client, message=PROMPT, **overrides):
    body = {'message': message, 'send_question': True}
    body.update(overrides)
    return client.post('/api/chat/workbench', json=body)


def audit_rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT username, action, details FROM auth_audit_log WHERE action='workbench_chat' "
                            'ORDER BY id').fetchall()


# ── Gates: nothing is sent unless every condition holds ──────────────────────

def test_ready_turn_sends_exactly_the_typed_message_and_returns_the_answer(build, transport):
    app, client, db = build()
    response = send(client)
    data = response.get_json()
    assert response.status_code == 200 and data['status'] == 'success' and data['reply'] == ANSWER
    assert response.headers['Cache-Control'] == 'no-store'
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call['url'] == URL + '/chat/completions' and call['body']['model'] == MODEL
    assert [m['role'] for m in call['body']['messages']] == ['system', 'user']
    assert call['body']['messages'][1]['content'] == PROMPT
    assert 'tools' not in call['body'] and 'tool_choice' not in call['body']
    # The key is used server-side only and never returned to the browser.
    assert call['headers']['Authorization'] == 'Bearer ' + KEY
    assert KEY not in response.get_data(as_text=True)


def test_unauthenticated_requests_are_rejected_without_transport(build, transport):
    app, client, db = build()
    anonymous = app.test_client()
    assert send(anonymous).status_code in {401, 403}
    cross = send(client, headers={'Origin': 'https://elsewhere.invalid'}) if False else client.post(
        '/api/chat/workbench', json={'message': PROMPT, 'send_question': True},
        headers={'Origin': 'https://elsewhere.invalid'})
    assert cross.status_code in {401, 403}
    # A bearer token (not a named browser session) is not accepted either.
    auth = get_auth_manager(db_path=db)
    token = auth.create_api_token(2, 'synthetic')['token']
    bearer = app.test_client().post('/api/chat/workbench', json={'message': PROMPT, 'send_question': True},
                                    headers={'Authorization': 'Bearer ' + token})
    assert bearer.status_code in {401, 403}
    assert transport.calls == []


def test_full_access_is_refused_before_any_transport(build, transport, monkeypatch):
    app, client, db = build()
    monkeypatch.setattr(security, 'FULL_ACCESS', True)
    response = send(client)
    assert response.status_code == 503 and response.get_json()['reason'] == 'full_access'
    assert transport.calls == []
    assert workbench_chat.state(app, None) == {'ready': False, 'reason': 'full_access',
                                               'message': workbench_chat.MESSAGES['full_access']}


def test_full_access_refusal_precedes_credential_policy_and_transport(build, transport, monkeypatch):
    app, client, db = build()
    monkeypatch.setattr(security, 'FULL_ACCESS', True)

    def forbidden(*args, **kwargs):
        pytest.fail('read credentials or policy before refusing full_access')
    monkeypatch.setattr(workbench_chat, 'governed_credentials', forbidden)
    monkeypatch.setattr(workbench_chat.PolicyStore, 'resolve', forbidden)
    monkeypatch.setattr(workbench_chat.openai_compatible, 'chat_completion', forbidden)
    response = send(client)
    assert response.status_code == 503 and response.get_json()['reason'] == 'full_access'
    assert workbench_chat.evaluate(app, None) == ('full_access', None, None)
    assert transport.calls == [] and audit_rows(db) == []


@pytest.mark.parametrize('options,reason', [
    ({'flags': False}, 'disabled'),
    ({'provider': False}, 'provider'),
    ({'approve': False}, 'approval'),
    ({'approved_model': 'another-model'}, 'approval'),
    ({'capabilities': False}, 'grants'),
])
def test_missing_readiness_fails_closed_with_a_coarse_reason(build, transport, options, reason):
    app, client, db = build(**options)
    response = send(client)
    data = response.get_json()
    assert response.status_code == 503 and data['status'] == 'unavailable' and data['reason'] == reason
    assert data['error'] == workbench_chat.MESSAGES[reason]
    text = response.get_data(as_text=True)
    assert KEY not in text and URL not in text and MODEL not in text
    assert transport.calls == []
    assert audit_rows(db) == []


def test_write_capable_tool_grant_blocks_the_workbench(build, transport, monkeypatch):
    app, client, db = build()
    monkeypatch.setattr(workbench_chat, 'permitted_tools', lambda policy, profile: {'submit_assertion'})
    assert send(client).get_json()['reason'] == 'grants'
    assert transport.calls == []


@pytest.mark.parametrize('body', [
    {'message': PROMPT},                                              # no explicit send intent
    {'message': PROMPT, 'send_question': 'true'},
    {'message': PROMPT, 'send_question': True, 'history': []},        # no replayed history
    {'message': PROMPT, 'send_question': True, 'context': {'tool': 'get_system_context', 'arguments': {}}},
    {'message': PROMPT, 'send_question': True, 'tools': ['query_knowledge_graph']},
    {'message': PROMPT, 'send_question': True, 'cypher': 'MATCH (n) DETACH DELETE n'},
    {'message': 5, 'send_question': True},
    {'message': '   ', 'send_question': True},
    {'message': 'x' * (workbench_chat.MAX_MESSAGE_CHARS + 1), 'send_question': True},
    ['not', 'an', 'object'],
])
def test_only_a_bounded_message_with_explicit_send_is_accepted(build, transport, body):
    app, client, db = build()
    response = client.post('/api/chat/workbench', json=body)
    assert response.status_code == 400 and response.get_json()['reason'] == 'invalid'
    assert transport.calls == []
    assert client.post('/api/chat/workbench', data='message=x', content_type='text/plain').status_code == 400
    assert transport.calls == []


# ── Honest provider outcomes; no tools, no writes ────────────────────────────

def test_requested_tool_calls_are_never_executed(build, transport):
    app, client, db = build()
    transport.extra = {'message': {'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
        'name': 'query_knowledge_graph', 'arguments': json.dumps({'cypher': 'MATCH (n) DETACH DELETE n'})}}]}}
    response = send(client)
    assert response.get_json()['reply'] == ANSWER and 'tool' not in json.dumps(response.get_json())
    assert len(transport.calls) == 1                     # no second round, no tool result sent back


def test_workbench_service_has_no_tool_graph_or_file_reach():
    source = (ROOT / 'scidk/services/workbench_chat.py').read_text()
    for name in ('run_tool', 'available_tool_definitions', 'graph_turn', 'context_turn', 'neo4j', 'get_driver',
                 'open(', 'subprocess', 'os.system', 'localStorage'):
        assert name not in source, name
    route = (ROOT / 'scidk/web/routes/api_chat.py').read_text().split("def api_chat_workbench")[1]
    for name in ('run_tool', 'driver', 'neo4j', 'ledger', 'pipeline'):
        assert name not in route, name


@pytest.mark.parametrize('failure,reason,outcome', [
    (requests.ConnectionError('boom with synthetic detail'), 'unreachable', 'unreachable'),
    (RuntimeError('unexpected'), 'provider_error', 'error'),
])
def test_provider_failure_is_reported_without_internal_detail(build, transport, failure, reason, outcome):
    app, client, db = build()
    transport.error = failure
    response = send(client)
    assert response.status_code == 503 and response.get_json()['reason'] == reason
    assert 'synthetic detail' not in response.get_data(as_text=True)
    assert audit_rows(db)[-1][2].endswith('outcome=' + outcome)


def test_refusal_and_empty_answers_are_not_shown_as_answers(build, transport):
    app, client, db = build()
    transport.content = None
    transport.extra = {'message': {'refusal': 'synthetic refusal detail'}}
    refused = send(client)
    assert refused.get_json()['status'] == 'refused' and 'synthetic refusal detail' not in refused.get_data(as_text=True)
    transport.extra = {}
    assert send(client).get_json()['reason'] == 'provider_error'


# ── Audit and rate limit ─────────────────────────────────────────────────────

def test_audit_rows_are_content_free_and_name_user_preset_and_request(build, transport):
    app, client, db = build()
    data = send(client).get_json()
    rows = audit_rows(db)
    assert [r[0] for r in rows] == ['alice', 'alice'] and [r[1] for r in rows] == ['workbench_chat'] * 2
    assert rows[0][2] == 'request_id=%s preset=custom outcome=attempt' % data['request_id']
    assert rows[1][2] == ('request_id=%s provider_request_id=req-123 preset=custom outcome=success' % data['request_id'])
    everything = json.dumps(rows)
    for secret in (PROMPT, ANSWER, KEY, URL, MODEL):
        assert secret not in everything


def test_turn_is_not_sent_when_the_audit_record_cannot_be_written(build, transport, monkeypatch):
    app, client, db = build()

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError('read only')
    monkeypatch.setattr(workbench_chat, '_audit', broken)
    assert send(client).get_json()['reason'] == 'audit'
    assert transport.calls == []


def test_per_user_rate_limit(build, transport):
    app, client, db = build()
    for _ in range(workbench_chat.RATE_LIMIT):
        assert send(client).status_code == 200
    limited = send(client)
    assert limited.status_code == 429 and limited.get_json()['reason'] == 'rate_limited'
    assert len(transport.calls) == workbench_chat.RATE_LIMIT


# ── Page state (inset dialog and full page) ──────────────────────────────────

@pytest.mark.parametrize('path', ['/review?view=guidance', '/review/guidance', '/overview', '/review'])
def test_ready_state_is_server_derived_and_loads_the_ask_script_only_then(build, transport, path, monkeypatch):
    app, client, db = build()
    page = client.get(path).get_data(as_text=True)
    assert 'data-provider-state="configured"' in page and 'data-send-url="/api/chat/workbench"' in page
    assert 'src="/static/js/workbench_chat.js"' in page
    for secret in (KEY, URL, MODEL, 'api_key'):
        assert secret not in page
    assert 'fetch(' not in page.split('<script')[1]            # the inline script has no network code
    monkeypatch.setattr(security, 'FULL_ACCESS', True)
    blocked = client.get(path).get_data(as_text=True)
    assert 'data-provider-state="not-configured"' in blocked and 'src="/static/js/workbench_chat.js"' not in blocked
    assert 'unrestricted full-access mode' in blocked
    assert transport.calls == []                                # rendering never contacts the provider


def test_prefill_is_rendered_into_the_draft_and_never_sent(build, transport):
    app, client, db = build()
    page = client.get('/review?view=guidance&prefill=synthetic+draft').get_data(as_text=True)
    assert 'synthetic draft</textarea>' in page
    assert transport.calls == [] and audit_rows(db) == []


def test_browser_script_posts_once_per_click_and_keeps_nothing():
    script = (ROOT / 'scidk/ui/static/js/workbench_chat.js').read_text()
    assert script.count('fetch(') == 1 and "'cw:ask'" in script
    for forbidden in ('localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', 'innerHTML', 'sendBeacon',
                      'WebSocket', 'EventSource', 'setInterval', 'setTimeout'):
        assert forbidden not in script, forbidden
    template = (ROOT / 'scidk/ui/templates/gui/_chat_workbench.html').read_text()
    assert template.count('/api/chat/workbench') >= 1 and 'localStorage' not in template
    assert 'sessionStorage' not in template and 'fetch(' not in template.split('<script>')[1].split('</script>')[0]


def test_live_read_only_profile_allows_the_workbench_post_only():
    from flask import Flask
    from scidk.live_development import read_only_request
    app = Flask(__name__)
    with app.test_request_context('/api/chat/workbench', method='POST'):
        assert read_only_request() is None
    with app.test_request_context('/api/chat/workbench/other', method='POST'):
        assert read_only_request()[1] == 403
