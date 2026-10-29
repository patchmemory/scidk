"""Approved human-purpose contract over real policy, ledger and HTTP adapters."""
import sqlite3

import pytest

from scidk.agent_tools.registry import ToolContext, run_tool
from scidk.agent_tools.security import DisclosureDenied, PolicyStore, REFUSAL
from scidk.services.human_policy import HumanIdentity, HumanPolicyStore
from .conftest import SCOPE
from .test_workspace import workspace, accept, post as knowledge
from .test_review_workspace import review_workspace, decision, post as review


def human_store(d):
    return HumanPolicyStore(d.db)


def remove_provider(d):
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM llm_user_settings')
        conn.execute('DELETE FROM agent_destination_approval')


def test_human_reads_without_provider_and_ai_stays_closed(workspace):
    d, client = workspace
    records = d.mapped_assertions(); accept(d, records)
    remove_provider(d)
    assert knowledge(client, 'search').json['result']['nodes']
    assert knowledge(client, 'inspect', {'id': records['pi']['claim']['entity_ref']}).status_code == 200
    ai = client.post('/api/chat/overview', json={
        'message': 'Explain Synthetic Investigator', 'send_question': True, 'scope': 'accessible'})
    assert ai.json == REFUSAL
    identity = HumanIdentity(d.alice)
    with pytest.raises(DisclosureDenied):
        with PolicyStore(d.db).resolve(identity):
            pytest.fail('Human identity entered AI policy')
    ctx = ToolContext(settings_db=d.db, identity=identity, profile='overview',
                      knowledge=d.knowledge, knowledge_enabled=True)
    assert run_tool('explain_fact', {'fact_id': records['pi']['fact_id']}, ctx) == REFUSAL


@pytest.mark.parametrize('change', ['purpose', 'ceiling', 'resource', 'evidence', 'classification'])
def test_revocation_and_classification_never_disclose(workspace, change):
    d, client = workspace
    records = d.mapped_assertions(); accept(d, records)
    ref = records['pi']['claim']['entity_ref']
    assert knowledge(client, 'inspect', {'id': ref}).status_code == 200
    store = human_store(d)
    if change == 'purpose':
        store.grant_purpose(d.alice, 'research_browse', 'medium', admin_id=d.reviewer, allow=False)
    elif change == 'ceiling':
        store.grant_purpose(d.alice, 'research_browse', 'low', admin_id=d.reviewer)
    elif change == 'classification':
        d.policy.classify(**SCOPE, risk='high', admin_id=d.reviewer)
    else:
        with sqlite3.connect(d.db) as conn:
            table = 'agent_resource_grant' if change == 'resource' else 'agent_evidence_grant'
            conn.execute(f'DELETE FROM {table} WHERE user_id=?', (d.alice,))
    assert knowledge(client, 'inspect', {'id': ref}).json == REFUSAL
    out = knowledge(client, 'search')
    assert out.json == REFUSAL or out.json['result']['nodes'] == []


def test_explicit_purposes_audit_and_no_admin_bypass(workspace):
    d, client = workspace
    store = human_store(d)
    with pytest.raises(DisclosureDenied):
        store.grant_purpose(d.alice, 'research_browse', 'medium', admin_id=d.alice)
    for purpose, risk in [('review', 'medium'), ('research_browse', 'high')]:
        with pytest.raises(DisclosureDenied):
            store.grant_purpose(d.alice, purpose, risk, admin_id=d.reviewer)
    store.grant_purpose(d.reviewer, 'research_browse', 'medium', admin_id=d.reviewer)
    records = d.mapped_assertions(); accept(d, records)
    admin = d.app.test_client()
    admin.set_cookie('scidk_session', d.auth.create_user_session(d.reviewer, 'reviewer'))
    assert knowledge(admin, 'search').json['result']['nodes'] == []
    # A grant for the other human purpose cannot substitute for browse authority.
    store.grant_purpose(d.alice, 'review_read', 'medium', admin_id=d.reviewer)
    store.grant_purpose(d.alice, 'research_browse', 'medium', admin_id=d.reviewer, allow=False)
    assert knowledge(client, 'search').json == REFUSAL
    with sqlite3.connect(d.db) as conn:
        assert conn.execute("SELECT revision,enabled FROM human_purpose_grant WHERE user_id=? AND purpose='research_browse'",
                            (d.alice,)).fetchone() == (2, 0)
        assert conn.execute("SELECT 1 FROM auth_audit_log WHERE details=?",
                            (f'human_purpose:{d.alice}:research_browse:medium:0',)).fetchone()


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://elsewhere.example'}, {'Sec-Fetch-Site': 'cross-site'},
    {'Authorization': 'Bearer invalid'}])
def test_human_origin_and_header_boundary(workspace, headers):
    _, client = workspace
    assert client.post('/api/knowledge/research/search', json={}, headers=headers).json == REFUSAL


def test_review_provider_independence_stale_and_revoked_purpose(review_workspace):
    d, client, records, _ = review_workspace
    remove_provider(d)
    aid = records['pi']['assertion_id']
    assert review(client, 'queue').json['result']['items']
    body = decision(client, aid)
    store = human_store(d)
    store.grant_purpose(d.reviewer, 'review_read', 'medium', admin_id=d.reviewer, allow=False)
    assert review(client, 'decide', body).json == REFUSAL
    store.grant_purpose(d.reviewer, 'review_read', 'medium', admin_id=d.reviewer)
    assert review(client, 'decide', body).status_code == 200
    assert review(client, 'decide', body).status_code == 409
    assert review(client, 'assistant', {'id': aid, 'message': 'Explain', 'send_question': True}).json == REFUSAL


def test_missing_human_policy_does_not_auto_initialize(workspace):
    d, client = workspace
    with sqlite3.connect(d.db) as conn:
        conn.execute('DROP TABLE human_purpose_grant')
    assert knowledge(client, 'search').json == REFUSAL
    with sqlite3.connect(d.db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='human_purpose_grant'").fetchone() is None


@pytest.mark.parametrize('state', ['locked', 'disabled', 'noauth'])
def test_session_state_changes_deny_human_reads(workspace, monkeypatch, state):
    d, client = workspace
    if state == 'locked':
        token = client.get_cookie('scidk_session').value
        assert d.auth.lock_session(token)
    elif state == 'disabled':
        with sqlite3.connect(d.db) as conn:
            conn.execute('UPDATE auth_users SET enabled=0 WHERE id=?', (d.alice,))
    else:
        monkeypatch.setattr('scidk.core.auth.AuthManager.is_enabled', lambda self: False)
    assert knowledge(client, 'search').status_code in {401, 403, 423}


def test_hidden_fields_are_not_searchable_by_human(workspace):
    d, client = workspace
    records = d.mapped_assertions(); accept(d, records)
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Person','name','hidden')")
    remove_provider(d)
    assert knowledge(client, 'search', {'q': 'Synthetic Investigator'}).json['result']['nodes'] == []
    out = knowledge(client, 'inspect', {'id': records['pi']['claim']['entity_ref']})
    assert out.status_code == 200
    assert 'name' not in out.json['result']['nodes'][0]['properties']
    assert 'RecordID:' not in str(out.json) and 'source_identifier' not in str(out.json)
