"""Review UI adapters exercise real policy, ledger and human decision services."""
import copy
import json
import sqlite3

import pytest

from scidk.agent_tools.security import REFUSAL
from scidk.agent_tools.profiles import PROFILES
from scidk.web.routes.ui import bp
from .conftest import SCOPE, OTHER_SCOPE
from .test_prompt12 import session, overview_body


def post(client, operation, body=None, **kwargs):
    return client.post('/api/review/' + operation, json=body or {}, **kwargs)


@pytest.fixture
def review_workspace(scenario):
    d = scenario
    from scidk.services.human_policy import HumanPolicyStore
    human = HumanPolicyStore(d.db)
    human.initialize(admin_id=d.reviewer)
    for uid in (d.alice, d.reviewer):
        human.grant_purpose(uid, 'review_read', 'medium', admin_id=d.reviewer)
    d.app.register_blueprint(bp)
    d.app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_REVIEW_WORKSPACE_ENABLED=True,
                        SCIDK_REVIEW_CHAT_ENABLED=True)
    records = d.mapped_assertions()
    hidden = d.mapped_assertions(scope=OTHER_SCOPE, actor='fixture-importer')
    # Reviewer ability to decide never substitutes for disclosure permission.
    for profile, names in PROFILES.items():
        for name in names:
            d.caps.grant_tool(d.reviewer, profile, name, admin_id=d.reviewer)
    d.policy.grant_resource(d.reviewer, **SCOPE, admin_id=d.reviewer)
    for item in records.values():
        for ref in [item['assertion_id'], *item['claim']['evidence_refs']]:
            d.policy.grant_evidence(d.reviewer, ref, admin_id=d.reviewer)
    client = session(d, 'reviewer')
    return d, client, records, hidden


def decision(client, aid, action='accept', **extra):
    preview = post(client, 'preview', {'id': aid})
    assert preview.status_code == 200, preview.json
    checked = preview.json['result']
    return {'id': aid, 'action': action, 'expected_revision': checked['expected_revision'],
            'preview_digest': checked['preview_digest'], 'rationale': 'Examined synthetic evidence',
            'confirm': True, **extra}


def test_queue_filters_hidden_records_and_context(review_workspace):
    d, client, records, hidden = review_workspace
    result = post(client, 'queue').json['result']
    assert len(result['items']) == len(records)
    serialized = json.dumps(result)
    assert all(item['assertion_id'] not in serialized for item in hidden.values())
    assert 'count' not in result and result['next_offset'] is None
    assert post(client, 'queue', {'domain': 'ontology'}).json['result']['items'] == []
    assert post(client, 'queue', {'source': OTHER_SCOPE['resource_id']}).json['result']['items'] == []
    for kind in ('node', 'property', 'relationship'):
        items = post(client, 'queue', {'kind': kind}).json['result']['items']
        assert items and all(a['claim']['target_kind'] == kind for a in items)
    aid = records['pi']['assertion_id']
    assert len(post(client, 'queue', {'context_id': aid}).json['result']['items']) == 1
    ref = records['pi']['claim']['entity_ref']
    assert post(client, 'queue', {'context_id': ref}).json['result']['items']
    assert post(client, 'queue', {'offset': 20}).json['result']['items'] == []
    assert post(client, 'queue', {'assigned_reviewer': 'reviewer'}).json == REFUSAL


def test_detail_citations_history_and_restrictions(review_workspace):
    d, client, records, hidden = review_workspace
    aid = records['pi']['assertion_id']
    out = post(client, 'inspect', {'id': aid})
    assert out.headers['Cache-Control'] == 'no-store'
    item = out.json['result']
    assert item['curation_status'] == 'proposed' and item['claim']['epistemic_status'] == 'inferred'
    assert item['evidence'][0]['accessed_at'] and item['evidence'][0]['version']
    assert 'identity_claims' not in json.dumps(item) and 'RecordID:' not in json.dumps(item)
    assert post(client, 'inspect', {'id': aid, 'history': True}).json == REFUSAL
    for ref in (hidden['pi']['assertion_id'], 'unknown'):
        assert post(client, 'inspect', {'id': ref}).json == REFUSAL
        assert post(client, 'preview', {'id': ref}).json == REFUSAL
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_evidence_grant WHERE user_id=? AND evidence_id=?',
                     (d.reviewer, records['pi']['claim']['evidence_refs'][0]))
    assert post(client, 'inspect', {'id': aid}).json == REFUSAL
    assert post(client, 'queue').json['result']['items'] == []


def test_human_decisions_revision_replay_and_no_materialization(review_workspace):
    d, client, records, _ = review_workspace
    aid = records['pi']['assertion_id']
    body = decision(client, aid)
    unconfirmed = dict(body, confirm=False)
    assert post(client, 'decide', unconfirmed).json == REFUSAL
    response = post(client, 'decide', body)
    assert response.status_code == 200, response.json
    assert response.json['result']['materialization_status'] == 'pending'
    assert post(client, 'decide', body).status_code == 409
    item = post(client, 'inspect', {'id': aid}).json['result']
    assert item['curation_status'] == 'accepted' and item['claim']['epistemic_status'] == 'inferred'
    assert len(post(client, 'queue', {'status': 'accepted'}).json['result']['items']) == 1
    rejected = records['pi.name']['assertion_id']
    assert post(client, 'decide', decision(client, rejected, 'reject')).status_code == 200
    assert post(client, 'inspect', {'id': rejected}).json['result']['curation_status'] == 'rejected'
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0] == 0
        rows = conn.execute('SELECT reviewer_id,rationale FROM decisions').fetchall()
        assert len(rows) == 2 and all(r == str(d.reviewer) and text for r, text in rows)
    with sqlite3.connect(d.db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_audit_log WHERE action='curation_review'").fetchone()[0] == 2


def test_nonreviewer_direct_calls_revocation_tokens_and_flags(review_workspace):
    d, client, records, _ = review_workspace
    aid = records['pi']['assertion_id']; alice = session(d)
    body = decision(client, aid)
    assert post(alice, 'inspect', {'id': aid}).status_code == 200
    for operation, data in [('preview', {'id': aid}), ('decide', body)]:
        assert post(alice, operation, data).json == REFUSAL
    for header in ('Bearer ' + d.tokens['alice']['token'], 'Bearer ' + d.auth.create_user_session(d.reviewer, 'reviewer')):
        assert post(client, 'queue', headers={'Authorization': header}).json == REFUSAL
    assert post(client, 'decide', body, headers={'Origin': 'https://elsewhere.example'}).json == REFUSAL
    with sqlite3.connect(d.db) as conn:
        conn.execute("UPDATE interpreter_settings SET value='[]' WHERE key='curation.human_reviewer_user_ids'")
    assert post(client, 'decide', body).json == REFUSAL
    d.app.config['SCIDK_REVIEW_WORKSPACE_ENABLED'] = False
    assert post(client, 'queue').json == REFUSAL
    d.app.config['SCIDK_REVIEW_WORKSPACE_ENABLED'] = True
    d.app.config['SCIDK_CURATION_ENABLED'] = False
    assert post(client, 'preview', {'id': aid}).json == REFUSAL


def test_queue_pagination_and_history_are_independently_authorized(review_workspace):
    d, client, records, _ = review_workspace
    claim = records['pi.name']['claim']
    for index in range(23):
        aid = d.ledger.submit(claim, actor='fixture-importer', caller_key='pagination-' + str(index))
        d.policy.grant_evidence(d.reviewer, aid, admin_id=d.reviewer)
    first = post(client, 'queue').json['result']
    second = post(client, 'queue', {'offset': first['next_offset']}).json['result']
    assert len(first['items']) == 20 and second['items'] and second['next_offset'] is None
    assert not ({a['assertion_id'] for a in first['items']} & {a['assertion_id'] for a in second['items']})
    aid = records['pi']['assertion_id']
    assert post(client, 'decide', decision(client, aid, 'reject')).status_code == 200
    assert post(client, 'inspect', {'id': aid, 'history': True}).json == REFUSAL
    from scidk.agent_tools.assertions import AssertionAccess
    with sqlite3.connect(d.ledger.path) as conn:
        row = conn.execute('SELECT action,revision,rationale,created_at FROM decisions WHERE assertion_id=?', (aid,)).fetchone()
    history = [dict(zip(('action', 'revision', 'rationale', 'created_at'), row))]
    d.policy.grant_evidence(d.reviewer, AssertionAccess.history_grant_id(aid, history), admin_id=d.reviewer)
    assert post(client, 'inspect', {'id': aid, 'history': True}).json['result']['decision_history'] == history


def test_supersession_and_conflicts_are_explicit(review_workspace):
    d, client, records, _ = review_workspace
    aid = records['pi.name']['assertion_id']
    assert post(client, 'decide', decision(client, aid)).status_code == 200
    claim = copy.deepcopy(records['pi.name']['claim']); claim['proposed_value'] = 'Synthetic alternate name'
    replacement = d.ledger.submit(claim, actor='fixture-importer', caller_key='replacement-name')
    d.policy.grant_evidence(d.reviewer, replacement, admin_id=d.reviewer)
    conflict = post(client, 'preview', {'id': replacement}).json['result']
    assert aid in conflict['conflict_ids']
    assert post(client, 'decide', decision(client, replacement)).status_code == 409
    assert post(client, 'decide', decision(client, aid, 'supersede', superseded_by=replacement)).status_code == 200
    assert post(client, 'decide', decision(client, replacement)).status_code == 200
    assert post(client, 'inspect', {'id': aid}).json['result']['curation_status'] == 'superseded'


def test_review_assistant_isolation_consent_and_provider_revocation(review_workspace, monkeypatch):
    d, client, records, _ = review_workspace
    aid = records['pi']['assertion_id']; calls = []
    def provider(*args, **kwargs):
        calls.append(args)
        return {'content': 'Inferred proposal. Verify the supplied citation before deciding.'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    body = {'id': aid, 'message': 'Explain the uncertainty.', 'send_question': True}
    assert post(client, 'assistant', dict(body, send_question=False)).json == REFUSAL
    assert not calls
    assert post(client, 'assistant', dict(body, profile='overview')).json == REFUSAL
    out = post(client, 'assistant', body)
    assert out.status_code == 200, out.json
    assert len(calls) == 1 and 'proposed' in calls[0][3][1]['content']
    assert client.post('/api/chat/overview?profile=review', json=overview_body(records['pi']['fact_id'])).json == REFUSAL
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion',
                        lambda *a, **k: {'content': 'I accepted it', 'tool_calls': [{'name': 'accept'}]})
    assert post(client, 'assistant', body).json == REFUSAL
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM decisions').fetchone()[0] == 0
    def revoking(*args, **kwargs):
        d.policy.grant_resource(d.reviewer, **SCOPE, admin_id=d.reviewer, allow=False)
        return {'content': 'Stale response must not appear'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', revoking)
    assert post(client, 'assistant', body).json == REFUSAL


def test_proposals_require_explicit_permission_and_replay_idempotently(review_workspace):
    d, client, records, _ = review_workspace
    alice = session(d)
    claim = copy.deepcopy(records['pi.name']['claim']); claim['proposed_value'] = 'Synthetic revised name'
    body = {'assertion': claim, 'caller_key': 'human-proposal-1', 'confirm': True}
    assert post(alice, 'propose', dict(body, confirm=False)).json == REFUSAL
    first = post(alice, 'propose', body)
    assert first.status_code == 200, first.json
    assert post(alice, 'propose', body).json == first.json
    assert d.ledger.get_internal(first.json['result']['assertion_id'])['claim']['epistemic_status'] == 'inferred'
    assert post(client, 'propose', body).json == REFUSAL  # no reviewer proposal scope
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM decisions').fetchone()[0] == 0


def test_queue_and_decision_fail_closed_after_classification_or_destination_change(review_workspace):
    d, client, records, _ = review_workspace
    aid = records['pi']['assertion_id']
    body = decision(client, aid)
    assert post(d.app.test_client(), 'queue').status_code in {401, 403}
    d.policy.classify(**SCOPE, risk='high', admin_id=d.reviewer)
    assert post(client, 'queue').json['result']['items'] == []
    assert post(client, 'decide', body).json == REFUSAL
    d.policy.classify(**SCOPE, risk='medium', admin_id=d.reviewer)
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_destination_approval')
    assert post(client, 'queue').status_code == 200
    assert post(client, 'decide', body).status_code == 200


def test_hidden_conflict_identifiers_are_never_disclosed(review_workspace):
    d, client, records, _ = review_workspace
    claim = copy.deepcopy(records['pi.name']['claim'])
    claim['source_scope'] = OTHER_SCOPE
    claim['evidence_refs'] = [d.evidence(source_id='private-conflict', scope=OTHER_SCOPE)[0]]
    claim['proposed_value'] = 'Private alternate value'
    hidden_id = d.ledger.submit(claim, actor='fixture-importer', caller_key='private-conflict')
    assert d.review(hidden_id).status_code == 200
    result = post(client, 'preview', {'id': records['pi.name']['assertion_id']})
    assert result.json == REFUSAL
    assert hidden_id not in result.get_data(as_text=True)


def test_assistant_compares_only_authorized_same_fact_assertions(review_workspace, monkeypatch):
    d, client, records, _ = review_workspace
    claim = copy.deepcopy(records['pi.name']['claim'])
    claim['proposed_value'] = 'Permitted alternative'
    visible_id = d.ledger.submit(claim, actor='fixture-importer', caller_key='comparison-visible')
    d.policy.grant_evidence(d.reviewer, visible_id, admin_id=d.reviewer)
    claim['source_scope'] = OTHER_SCOPE
    claim['evidence_refs'] = [d.evidence(source_id='comparison-private', scope=OTHER_SCOPE)[0]]
    claim['proposed_value'] = 'Private comparison value'
    hidden_id = d.ledger.submit(claim, actor='fixture-importer', caller_key='comparison-private')
    payloads = []
    def provider(*args, **kwargs):
        payloads.append(args[3][1]['content'])
        return {'content': 'These permitted proposals disagree; examine their citations.'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    response = post(client, 'assistant', {'id': records['pi.name']['assertion_id'],
                    'message': 'Compare this claim with alternatives.', 'send_question': True})
    assert response.status_code == 200, response.json
    assert visible_id in payloads[0] and 'Permitted alternative' in payloads[0]
    assert hidden_id not in payloads[0] and 'Private comparison value' not in payloads[0]
    assert hidden_id not in response.get_data(as_text=True)


@pytest.mark.parametrize('operation,body', [('queue', {'offset': True}), ('inspect', {'id': '42', 'cypher': 'MATCH (n) RETURN n'}),
    ('materialize', {}), ('decide', {'reviewer': 'spoof', 'confirm': True}), ('queue', {'domain': 'unknown'})])
def test_invalid_requests_and_no_write_escape(review_workspace, operation, body):
    _, client, _, _ = review_workspace
    assert post(client, operation, body).json == REFUSAL
