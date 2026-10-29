"""No-ID Overview lookup through real policy, ledger and fixed transport."""
import json
import sqlite3

import pytest

from .conftest import scenario, OTHER_SCOPE
from .test_prompt15 import ready_app
from .test_prompt12 import session
from .test_workspace import accept
from scidk.agent_tools.security import REFUSAL


@pytest.fixture
def discovery(ready_app, monkeypatch):
    d, admin = ready_app
    calls = []
    def provider(*args, **kwargs):
        calls.append((args, kwargs))
        return {'content': 'Synthetic interpretation; inspect the authorized citations.'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    return d, admin, calls


def ask(client, **extra):
    return client.post('/api/chat/overview', json=dict(message='Explain the synthetic System workflow',
        scope='system', send_question=True, **extra))


def test_no_id_system_discovery_and_citations(discovery):
    d, admin, calls = discovery
    out = ask(admin)
    assert out.status_code == 200, out.json
    sources = out.json['context']['retrieved_sources']
    assert sources[0]['id'] == 'system:synthetic-demo'
    assert sources[0]['href'].startswith('/knowledge?domain=system&id=')
    assert sources[0]['context']['context']['nodes'][0]['sources'][0]['hash']
    assert len(calls) == 1 and 'tools' not in calls[0][1]
    assert len(calls[0][0][3]) == 2
    assert 'profile' not in json.loads(calls[0][0][3][1]['content'])
    assert out.headers['Cache-Control'] == 'no-store'


def test_research_lookup_accepted_applied_released_properties_and_isolation(discovery):
    d, _, calls = discovery
    client = session(d)
    records = d.mapped_assertions()
    question = {'message': 'Find Synthetic Investigator', 'scope': 'accessible', 'send_question': True}
    assert client.post('/api/chat/overview', json=question).json['status'] == 'empty'
    accept(d, records)
    hidden = d.mapped_assertions(scope=OTHER_SCOPE, actor='fixture-importer'); accept(d, hidden)
    result = client.post('/api/chat/overview', json=question)
    assert result.status_code == 200, result.json
    encoded = json.dumps(result.json)
    assert records['pi']['claim']['entity_ref'] in encoded
    assert hidden['pi']['claim']['entity_ref'] not in encoded
    assert 'source_identifier' not in encoded
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Person','name','hidden')")
    calls.clear()
    assert client.post('/api/chat/overview', json=question).json['status'] == 'empty'
    assert not calls


@pytest.mark.parametrize('field,value', [('send_question', False), ('profile', 'review'), ('history', []), ('base_url', 'https://elsewhere.invalid')])
def test_no_id_cannot_override_consent_or_profile(discovery, field, value):
    _, admin, calls = discovery
    body = {'message': 'synthetic System', 'scope': 'system', 'send_question': True, field: value}
    assert admin.post('/api/chat/overview', json=body).json == REFUSAL
    assert not calls


def test_empty_unavailable_approval_and_bounds_make_no_provider_call(discovery, monkeypatch):
    d, admin, calls = discovery
    body = {'message': 'unfindable-topic', 'scope': 'system', 'send_question': True}
    assert admin.post('/api/chat/overview', json=body).json['status'] == 'empty'
    monkeypatch.setattr('scidk.services.overview_discovery.MAX_RESULTS', 0)
    assert ask(admin).json['status'] == 'bounded'
    monkeypatch.setattr('scidk.services.overview_discovery.MAX_RESULTS', 3)
    d.policy.revoke_destination('demo', admin_id=d.reviewer)
    assert ask(admin).json == REFUSAL
    d.app.extensions.pop('knowledge_services')
    assert ask(admin).json['status'] == 'unavailable'
    assert not calls


def test_selected_stable_context_reauthorized_and_revocation_discards_reply(discovery, monkeypatch):
    d, admin, calls = discovery
    body = {'message': 'Explain this context', 'scope': 'selection', 'send_question': True,
            'selection': {'domain': 'system', 'id': 'system:synthetic-demo'}}
    assert admin.post('/api/chat/overview', json=body).status_code == 200
    def revoke(*args, **kwargs):
        with sqlite3.connect(d.db) as conn:
            conn.execute('DELETE FROM agent_resource_grant WHERE user_id=?', (d.reviewer,))
        return {'content': 'Must never be shown'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', revoke)
    assert admin.post('/api/chat/overview', json=body).json == REFUSAL
    body['selection']['id'] = 'system:unknown'
    assert admin.post('/api/chat/overview', json=body).json == REFUSAL


@pytest.mark.parametrize('principal', ['anonymous', 'token', 'header', 'cross-origin', 'locked'])
def test_discovery_requires_same_origin_unlocked_named_cookie(discovery, principal):
    d, admin, calls = discovery
    headers = {}
    if principal == 'anonymous':
        admin = d.app.test_client()
    elif principal == 'token':
        headers['Authorization'] = 'Bearer ' + d.auth.create_api_token(d.reviewer, 'synthetic')['token']
    elif principal == 'header':
        headers['Authorization'] = 'Bearer ' + d.auth.create_user_session(d.reviewer, 'reviewer')
    elif principal == 'cross-origin':
        headers['Origin'] = 'https://elsewhere.invalid'
    else:
        token = d.auth.create_user_session(d.reviewer, 'reviewer')
        d.auth.lock_session(token); admin.set_cookie('scidk_session', token)
    out = admin.post('/api/chat/overview', json={'message': 'Synthetic System', 'scope': 'system', 'send_question': True}, headers=headers)
    assert out.status_code in {401, 403, 423}
    assert not calls


def test_discovery_deadline_refuses_before_provider(discovery, monkeypatch):
    _, admin, calls = discovery
    ticks = iter([0, 4])
    monkeypatch.setattr('scidk.services.overview_discovery.time.monotonic', lambda: next(ticks, 4))
    assert ask(admin).json['status'] == 'bounded'
    assert not calls
