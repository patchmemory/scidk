import asyncio
import copy
import json
import sqlite3
from types import SimpleNamespace

import pytest
from flask import Flask

from scidk.agent_tools.security import BoundIdentity, DisclosureDenied, PolicyStore, REFUSAL, endpoint_identity
from scidk.agent_tools.facts import FactDisclosure
from scidk.agent_tools.registry import ToolContext, run_tool, tool_names
from scidk.curation.review import ReviewService
from scidk.core.auth import AuthManager
from scidk.pipeline.store import PipelineStore
from tests.curation.test_foundation import foundation, node, submit_node, property_body, SCOPE
from tests.curation.test_review import FakeGraph, decision, edge_proposal


@pytest.fixture
def secured(foundation, tmp_path):
    ledger, evidence, eid = foundation
    db = str(tmp_path / 'settings.sqlite')
    auth = AuthManager(db_path=db)
    admin = auth.create_user('admin', 'fixture-password', role='admin')
    alice = auth.create_user('alice', 'fixture-password', role='user')
    bob = auth.create_user('bob', 'fixture-password', role='user')
    PipelineStore(db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO pipeline_source(id,name,plugin_type) VALUES (?,?,?)", ('resource-1', 'Synthetic', 'fixture'))
    store = PolicyStore(db)
    store.initialize(admin_id=admin)
    store.classify('synthetic', 'resource-1', 'medium', admin_id=admin)
    store.grant_resource(alice, 'synthetic', 'resource-1', admin_id=admin)
    store.approve_destination('parley', 'https://parley.example/v1', 'fixture-model', 'medium', admin_id=admin)
    token = auth.create_api_token(alice, 'bound AI client')
    store.bind_token(token['id'], 'parley', admin_id=admin)
    identity = BoundIdentity(alice, 'http', token['id'])
    service, graph = ReviewService(ledger, lambda who: who == 'human'), FakeGraph()
    person = submit_node(ledger, eid)
    accepted = decision(service, person['assertion_id'])
    service.materialize([accepted['operation_id']], reviewer='human', graph=graph)
    disclosure = FactDisclosure(ledger, db, graph_target=graph.target)
    data = SimpleNamespace(ledger=ledger, evidence=evidence, eid=eid, db=db, auth=auth, admin=admin,
                           alice=alice, bob=bob, store=store, token=token, identity=identity,
                           service=service, graph=graph, person=person, disclosure=disclosure)
    yield data
    auth.close()


def read(s, fact_id=None, **kwargs):
    return s.disclosure.read_fact(fact_id or s.person['fact_id'], s.identity, **kwargs)


def test_positive_existence_has_no_unaccepted_properties(secured):
    s = secured
    out = read(s)
    assert out['status'] == 'success'
    assert out['fact']['curation_status'] == 'accepted'
    assert out['fact']['epistemic_status'] == ['inferred']
    assert 'Synthetic Person' not in json.dumps(out)
    assert 'evidence' not in out['fact'] and 'source_scope' not in out['fact']


@pytest.mark.parametrize('risk', ['high', 'low', 'medium'])
def test_risk_ceilings_and_global_high_prohibition(secured, risk):
    s = secured
    s.store.classify('synthetic', 'resource-1', risk, admin_id=s.admin)
    s.store.approve_destination('parley', 'https://parley.example/v1', 'fixture-model', 'low', admin_id=s.admin)
    out = read(s)
    assert out['status'] == ('success' if risk == 'low' else 'refused')
    with pytest.raises(DisclosureDenied):
        s.store.approve_destination('high', 'https://high.example/v1', 'm', 'high', admin_id=s.admin)


def test_missing_classification_provenance_and_legacy_fact(secured):
    s = secured
    assert read(s, 'fact:legacy-stored-only') == REFUSAL
    with sqlite3.connect(s.db) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('DELETE FROM agent_resource_classification')
    assert read(s) == REFUSAL
    assert s.disclosure.read_fact('arbitrary-secret-id', s.identity) == REFUSAL


def test_unclassified_source_does_not_inherit_medium(secured):
    s = secured
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO pipeline_source(id,name,plugin_type) VALUES ('unclassified','Fixture','fixture')")
    with s.store.resolve(s.identity) as policy:
        with pytest.raises(DisclosureDenied):
            policy.resource({'namespace': 'synthetic', 'resource_id': 'unclassified'})
        with pytest.raises(DisclosureDenied):
            policy.resource(None)


def test_cross_user_and_revoked_grants(secured):
    s = secured
    assert s.disclosure.read_fact(s.person['fact_id'], BoundIdentity(s.bob, 'http', s.token['id'])) == REFUSAL
    s.store.grant_resource(s.alice, 'synthetic', 'resource-1', admin_id=s.admin, allow=False)
    assert read(s) == REFUSAL
    # Even an administrator has no automatic source or AI disclosure grant.
    admin_token = s.auth.create_api_token(s.admin, 'admin client')
    s.store.bind_token(admin_token['id'], 'parley', admin_id=s.admin)
    assert s.disclosure.read_fact(s.person['fact_id'], BoundIdentity(s.admin, 'http', admin_token['id'])) == REFUSAL


def test_unknown_destination_unbound_identity_and_revoked_tokens(secured):
    s = secured
    for identity in (None, BoundIdentity(s.alice, 'mcp'), BoundIdentity(s.alice, 'http'),
                     BoundIdentity(s.alice, 'http', 'unknown-token')):
        assert s.disclosure.read_fact(s.person['fact_id'], identity) == REFUSAL
    unbound = s.auth.create_api_token(s.alice, 'not bound')
    assert s.disclosure.read_fact(s.person['fact_id'], BoundIdentity(s.alice, 'http', unbound['id'])) == REFUSAL
    s.auth.delete_api_token(s.token['id'])
    assert read(s) == REFUSAL


def test_disabled_user_and_unavailable_or_malformed_policy(secured, tmp_path):
    s = secured
    for path in (None, tmp_path / 'absent.sqlite', tmp_path):
        assert FactDisclosure(s.ledger, path, graph_target=s.graph.target).read_fact(s.person['fact_id'], s.identity) == REFUSAL
    s.auth.update_user(s.alice, enabled=False)
    assert read(s) == REFUSAL
    s.auth.update_user(s.alice, enabled=True)
    with sqlite3.connect(s.db) as conn:
        conn.execute('DROP TABLE agent_sharing')
    assert read(s) == REFUSAL


def test_proposed_rejected_and_superseded_stored_facts_are_not_accepted(secured):
    s = secured
    body = property_body(s.ledger, s.eid)
    aid = s.ledger.submit(body, actor='human', caller_key='property')
    fid = s.ledger.get_internal(aid)['fact_id']
    assert read(s, fid) == REFUSAL
    decision(s.service, aid, 'reject')
    assert read(s, fid) == REFUSAL
    replacement = s.ledger.submit(node(s.ledger, s.eid), actor='human', caller_key='replacement')
    decision(s.service, s.person['assertion_id'], 'supersede', superseded_by=replacement)
    assert s.person['claim']['entity_ref'] in s.graph.nodes
    assert read(s) == REFUSAL
    assert s.ledger.get_internal(s.person['assertion_id'])['curation_status'] == 'superseded'


def test_pending_acceptance_requires_applied_receipt(secured):
    s = secured
    body = property_body(s.ledger, s.eid)
    aid = s.ledger.submit(body, actor='human', caller_key='property')
    op = decision(s.service, aid)
    fid = s.ledger.get_internal(aid)['fact_id']
    assert read(s, fid) == REFUSAL
    s.service.materialize([op['operation_id']], reviewer='human', graph=s.graph)
    assert read(s, fid)['fact']['value'] == body['proposed_value']
    from scidk.agent_tools.disclosure import set_mode
    set_mode(s.db, 'Person', 'name', 'hidden')
    assert read(s, fid) == REFUSAL
    set_mode(s.db, 'Person', 'entity_ref', 'hidden')
    assert read(s) == REFUSAL


def test_relationship_requires_visible_endpoints(secured):
    s = secured
    project = submit_node(s.ledger, s.eid, 'Project')
    project_op = decision(s.service, project['assertion_id'])
    edge_id = edge_proposal(s.ledger, s.eid, s.person, project)
    edge_op = decision(s.service, edge_id)
    s.service.materialize([edge_op['operation_id'], project_op['operation_id']], reviewer='human', graph=s.graph)
    fid = s.ledger.get_internal(edge_id)['fact_id']
    assert read(s, fid)['status'] == 'success'
    from scidk.agent_tools.disclosure import set_mode
    set_mode(s.db, 'Project', 'entity_ref', 'hidden')
    assert read(s, fid) == REFUSAL


def test_evidence_citation_identifiers_and_excerpts_do_not_leak(secured):
    s = secured
    assert read(s)['status'] == 'success'
    assert read(s, include_evidence=True) == REFUSAL
    assert s.eid not in json.dumps(read(s, include_evidence=True))
    s.store.grant_evidence(s.alice, s.eid, admin_id=s.admin)
    out = read(s, include_evidence=True)
    assert out['fact']['citations'] == [{'citation': 'Synthetic fixture', 'version': '1'}]
    for hidden in ('row:1', 'source_id', 'locator', 'content_hash', 'excerpt', s.eid):
        assert hidden not in json.dumps(out)
    from scidk.agent_tools.disclosure import set_mode
    set_mode(s.db, 'EvidenceSource', 'citation', 'hidden')
    assert read(s, include_evidence=True) == REFUSAL


def test_source_access_change_applies_to_citations_too(secured):
    s = secured
    s.store.grant_evidence(s.alice, s.eid, admin_id=s.admin)
    assert read(s, include_evidence=True)['status'] == 'success'
    s.store.classify('synthetic', 'resource-1', 'high', admin_id=s.admin)
    assert read(s, include_evidence=True) == REFUSAL


@pytest.mark.parametrize('query', [
    'MATCH (n) RETURN count(n)', 'MATCH (n) RETURN n.secret AS value',
    "MATCH (n) WHERE n.secret='hidden' RETURN 1", 'MATCH (s)-[r]->(t) RETURN s,r,t',
    'CALL db.labels()', 'RETURN 1', 'SELECT COUNT(*) FROM files',
])
def test_all_arbitrary_queries_refused_before_execution(secured, monkeypatch, query):
    from scidk.agent_tools import registry
    s = secured
    def forbidden(*args, **kwargs):
        pytest.fail('Unscoped handler executed')
    monkeypatch.setitem(registry._HANDLERS, 'query_knowledge_graph', forbidden)
    ctx = ToolContext(settings_db=s.db, identity=s.identity, driver=object(), files_db='do-not-open')
    assert run_tool('query_knowledge_graph', {'cypher': query}, ctx) == REFUSAL


def test_all_existing_tools_refuse_even_for_approved_principal(secured, monkeypatch):
    from scidk.agent_tools import registry
    s = secured
    for name in tool_names():
        monkeypatch.setitem(registry._HANDLERS, name, lambda *a, **kw: pytest.fail('Legacy handler executed'))
        schema = registry._BY_NAME[name]['input_schema']
        args = {key: 'synthetic' for key in schema.get('required', [])}
        assert run_tool(name, args, ToolContext(settings_db=s.db, identity=s.identity)) == REFUSAL
    assert not any('assertion' in name or 'materializ' in name or 'review' in name for name in tool_names())


def test_arbitrary_result_filter_never_trusts_source_hints():
    from scidk.agent_tools.disclosure import SharingPolicy, filter_for_agent, check_cypher
    for result in ({'count': 7}, {'rows': [{'source_id': 'public', 'secret': 'hidden'}]}, {'error': 'private path'}):
        assert filter_for_agent(result, SharingPolicy()) == REFUSAL
    assert check_cypher('RETURN 1', SharingPolicy())


def test_policy_management_requires_named_existing_admin(secured):
    s = secured
    for admin in (s.alice, s.bob, -1, None):
        with pytest.raises(DisclosureDenied):
            s.store.classify('synthetic', 'resource-1', 'low', admin_id=admin)
    with pytest.raises(sqlite3.IntegrityError):
        s.store.classify('synthetic', 'unknown-resource', 'low', admin_id=s.admin)


def test_policy_errors_have_uniform_structure(secured):
    s = secured
    good = read(s)
    assert good['status'] == 'success'
    bad = FactDisclosure(s.ledger, s.db, graph_target='unknown-graph')
    assert bad.read_fact(s.person['fact_id'], s.identity) == REFUSAL
    assert read(s, 'unknown-legacy-fact') == REFUSAL


def test_chat_destination_matches_existing_provider_configuration(secured, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    s = secured
    provider_settings.save(s.db, 'alice', base_url='https://parley.example/v1', model='fixture-model')
    identity = BoundIdentity(s.alice, 'chat')
    assert s.disclosure.read_fact(s.person['fact_id'], identity)['status'] == 'success'
    calls = []
    monkeypatch.setattr(openai_compatible, 'chat_completion', lambda *a, **kw: calls.append(a) or {})
    assert provider_settings.disclosed_fact_turn(s.db, identity, s.disclosure, s.person['fact_id'])['status'] == 'success'
    assert len(calls) == 1 and calls[0][0] == 'https://parley.example/v1'
    assert 'Synthetic Person' not in json.dumps(calls)
    provider_settings.save(s.db, 'alice', base_url='https://unapproved.example/v1')
    assert provider_settings.disclosed_fact_turn(s.db, identity, s.disclosure, s.person['fact_id']) == REFUSAL
    assert len(calls) == 1


def test_bound_token_cannot_override_actual_provider(secured, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    s = secured
    provider_settings.save(s.db, 'alice', base_url='https://unapproved.example/v1', model='fixture-model')
    monkeypatch.setattr(openai_compatible, 'chat_completion', lambda *a, **kw: pytest.fail('Destination bypass'))
    assert provider_settings.disclosed_fact_turn(s.db, s.identity, s.disclosure, s.person['fact_id']) == REFUSAL


def test_endpoint_identity_is_exact_and_rejects_credentials():
    assert endpoint_identity('https://PARLEY.example:443/v1/') == 'https://parley.example/v1'
    for url in ('file:///tmp/x', 'https://user:pass@example.com/v1', 'https://example.com/v1?query=x', 'https://example.com/#x'):
        with pytest.raises(DisclosureDenied):
            endpoint_identity(url)


def test_missing_policy_read_does_not_create_database(tmp_path):
    path = tmp_path / 'missing.sqlite'
    store = PolicyStore(path)
    with pytest.raises(sqlite3.OperationalError):
        with store.resolve(BoundIdentity(1, 'http', 'unknown')):
            pytest.fail('Missing policy permitted')
    assert not path.exists()


def test_deleted_resource_and_unknown_visibility_deny(secured):
    s = secured
    with sqlite3.connect(s.db) as conn:
        conn.execute("DELETE FROM pipeline_source WHERE id='resource-1'")
    assert read(s) == REFUSAL


def test_malformed_property_mode_fails_closed(secured):
    s = secured
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Person','entity_ref','unknown')")
    assert read(s) == REFUSAL


def test_conflicting_accepted_support_is_withheld_even_with_receipts(secured):
    from scidk.curation.contracts import canonical, digest
    s = secured
    body = property_body(s.ledger, s.eid)
    first = s.ledger.submit(body, actor='human', caller_key='first-property')
    op = decision(s.service, first)
    s.service.materialize([op['operation_id']], reviewer='human', graph=s.graph)
    fid = s.ledger.get_internal(first)['fact_id']
    assert read(s, fid)['status'] == 'success'
    # Simulate contradictory legacy/imported acceptance; Stage 2 correctly
    # prevents this through its own review API. Disclosure must distrust it too.
    body['proposed_value'] = 'Conflicting historical fixture'
    other = s.ledger.submit(body, actor='human', caller_key='historical-conflict')
    operation = dict(assertion_id=other, decision_id='fixture-decision', revision=1, action='accept')
    h = digest('operation-body', operation)
    with sqlite3.connect(s.ledger.path) as conn:
        conn.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)',
                     ('fixture-decision', other, 1, 'accept', 'fixture-human', 'fixture', 'fixture-time', None))
        conn.execute('INSERT INTO outbox VALUES (?,?,?,?)', ('fixture-op', h, canonical(operation), 'fixture-time'))
        conn.execute('INSERT INTO receipts VALUES (?,?,?,?,?)', ('fixture-op', h, s.graph.target, 'applied', 'fixture-time'))
    assert read(s, fid) == REFUSAL


def test_other_store_cannot_authorize_outbound_content(secured, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    s = secured
    monkeypatch.setattr(openai_compatible, 'chat_completion', lambda *a, **kw: pytest.fail('Cross-store leak'))
    assert provider_settings.disclosed_fact_turn(s.db + '.other', s.identity, s.disclosure, s.person['fact_id']) == REFUSAL


def test_policy_mutations_use_existing_audit_log(secured):
    assert any(row['action'] == 'agent_disclosure_policy' for row in secured.auth.get_audit_log())


def test_destination_revocation_takes_effect_on_next_read(secured):
    s = secured
    assert read(s)['status'] == 'success'
    s.store.revoke_destination('parley', admin_id=s.admin)
    assert read(s) == REFUSAL


def test_endpoint_resource_without_access_withholds_relationship(secured):
    s = secured
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO pipeline_source(id,name,plugin_type) VALUES ('resource-2','Other fixture','fixture')")
    s.store.classify('synthetic', 'resource-2', 'low', admin_id=s.admin)
    scope = dict(SCOPE, resource_id='resource-2')
    evidence = copy.deepcopy(s.evidence)
    evidence['source_scope'] = scope
    eid = s.ledger.add_evidence(evidence)
    body = node(s.ledger, eid, 'Project')
    body['source_scope'] = scope
    body['candidate']['source_scope'] = scope
    aid = s.ledger.submit(body, actor='human', caller_key='other-resource-project')
    project = s.ledger.get_internal(aid)
    pop = decision(s.service, aid)
    edge_id = edge_proposal(s.ledger, s.eid, s.person, project)
    edge = decision(s.service, edge_id)
    s.service.materialize([edge['operation_id'], pop['operation_id']], reviewer='human', graph=s.graph)
    assert read(s, s.ledger.get_internal(edge_id)['fact_id']) == REFUSAL
    s.store.grant_resource(s.alice, 'synthetic', 'resource-2', admin_id=s.admin)
    assert read(s, s.ledger.get_internal(edge_id)['fact_id'])['status'] == 'success'


def test_slow_provider_does_not_hold_policy_lock(secured, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    s = secured
    provider_settings.save(s.db, 'alice', base_url='https://parley.example/v1', model='fixture-model')
    def transport(*args, **kwargs):
        # An administrative revocation can commit during the in-flight call.
        s.store.grant_resource(s.alice, 'synthetic', 'resource-1', admin_id=s.admin, allow=False)
        return {}
    monkeypatch.setattr(openai_compatible, 'chat_completion', transport)
    assert provider_settings.disclosed_fact_turn(s.db, s.identity, s.disclosure, s.person['fact_id'])['status'] == 'success'
    assert read(s) == REFUSAL
