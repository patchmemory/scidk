import copy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from flask import Flask

from scidk.agent_tools.registry import (ToolContext, run_tool, available_tool_definitions,
                                       openai_functions, TOOL_DEFINITIONS)
from scidk.agent_tools.security import REFUSAL, BoundIdentity, DisclosureDenied
from scidk.agent_tools.capabilities import CapabilityStore
from scidk.agent_tools.knowledge import KnowledgeServices, NAMES
from scidk.agent_tools.assertions import AssertionAccess
from scidk.knowledge.projection import system_projection, ContextService
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.external import mondo_fixture
from scidk.knowledge.system_manifest import ENTRIES
from tests.curation.test_foundation import foundation, SCOPE, catalog, property_body, node, submit_node
from tests.security.test_disclosure import secured
from tests.curation.test_review import decision, edge_proposal

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def integrated(secured):
    s = secured
    cap = CapabilityStore(s.db)
    cap.initialize(admin_id=s.admin)
    for profile in ('overview', 'review'):
        from scidk.agent_tools.profiles import PROFILES
        for name in PROFILES[profile]:
            cap.grant_tool(s.alice, profile, name, admin_id=s.admin)
    cap.grant_proposal(s.alice, **SCOPE, admin_id=s.admin)
    graph = system_projection(ROOT, {e['id']: SCOPE for e in ENTRIES})
    ontology = ontology_projection([], catalog(), revision='test',
        bindings={k: SCOPE for k in ('catalog', 'sqlite:Person', 'sqlite:Project')})
    for g in (graph, ontology):
        for n in g.snapshot()['nodes']:
            s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
    s.store.grant_evidence(s.alice, s.eid, admin_id=s.admin)
    s.store.grant_evidence(s.alice, s.person['assertion_id'], admin_id=s.admin)
    services = KnowledgeServices(system=ContextService(graph, s.db, enabled=True),
        ontologies={'canonical': ContextService(ontology, s.db, enabled=True),
                    'MONDO': ContextService(mondo_fixture().projection('MONDO', source_scope=SCOPE, revision='test'), s.db, enabled=True)},
        assertions=AssertionAccess(s.ledger, s.disclosure), system_root=ROOT)
    ctx = ToolContext(settings_db=s.db, identity=s.identity, profile='review',
                      knowledge=services, knowledge_enabled=True, proposal_enabled=True)
    return SimpleNamespace(s=s, cap=cap, services=services, ctx=ctx)


def call(i, name, args=None):
    return run_tool(name, args or {}, i.ctx)


def grant_assertion(i, aid):
    i.s.store.grant_evidence(i.s.alice, aid, admin_id=i.s.admin)


def make_app(i):
    from scidk.web.routes import api_agent, api_chat
    from scidk.web.auth_middleware import init_auth_middleware
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=i.s.db, SCIDK_ASSISTANT_PROFILE='review',
                      SCIDK_KNOWLEDGE_CONTEXT_ENABLED=True, SCIDK_CURATION_ENABLED=True)
    app.extensions['knowledge_services'] = i.services
    app.register_blueprint(api_agent.bp)
    app.register_blueprint(api_chat.bp)
    init_auth_middleware(app)
    return app


def test_shared_discovery_and_profiles(integrated):
    i = integrated
    assert {d['name'] for d in available_tool_definitions(i.ctx)} == NAMES
    i.ctx.profile = 'overview'
    assert {d['name'] for d in available_tool_definitions(i.ctx)} == {'get_system_context', 'get_ontology_context', 'explain_fact'}
    assert call(i, 'get_assertion', {'assertion_id': i.s.person['assertion_id']}) == REFUSAL
    assert call(i, 'submit_assertion', {'assertion': node(i.s.ledger, i.s.eid), 'caller_key': 'key'}) == REFUSAL
    assert all(not any(word in n for word in ('accept', 'reject', 'review', 'materializ', 'supersede')) for n in NAMES)
    with pytest.raises(DisclosureDenied):
        i.cap.grant_tool(i.s.alice, 'overview', 'submit_assertion', admin_id=i.s.admin)
    with pytest.raises(DisclosureDenied):
        i.cap.grant_tool(i.s.alice, 'review', 'materialize', admin_id=i.s.admin)


@pytest.mark.parametrize('denial', ['disabled', 'identity', 'destination', 'capability', 'profile', 'backend', 'policy'])
def test_discovery_and_execution_fail_closed(integrated, denial):
    i = integrated
    if denial == 'disabled':
        i.ctx.knowledge_enabled = False
    elif denial == 'identity':
        i.ctx.identity = BoundIdentity(i.s.bob, 'http', i.s.token['id'])
    elif denial == 'destination':
        i.s.store.revoke_destination('parley', admin_id=i.s.admin)
    elif denial == 'capability':
        for name in NAMES:
            i.cap.grant_tool(i.s.alice, 'review', name, admin_id=i.s.admin, allow=False)
    elif denial == 'profile':
        i.ctx.profile = 'admin'
    elif denial == 'backend':
        i.ctx.knowledge = None
    else:
        with sqlite3.connect(i.s.db) as conn:
            conn.execute('DROP TABLE agent_tool_schema')
    assert available_tool_definitions(i.ctx) == []
    assert call(i, 'get_system_context', {'entry_id': 'workflow:csv-import'}) == REFUSAL


def test_bounded_contexts_and_external_selection(integrated):
    i = integrated
    system = call(i, 'get_system_context', {'entry_id': 'workflow:csv-import'})
    assert system['status'] == 'success'
    assert not system['context']['warnings']
    assert 'schema:mapping' in {n['id'] for n in system['context']['nodes']}
    ontology = call(i, 'get_ontology_context', {'entry_id': 'label:Person'})
    assert ontology['status'] == 'success'
    rel = next(n for n in ontology['context']['nodes'] if n['id'].startswith('relationship:'))
    assert rel['definition']['target_label'] == 'Project'
    mondo = call(i, 'get_ontology_context', {'entry_id': 'external:MONDO', 'catalog': 'MONDO'})
    assert mondo['status'] == 'success' and 'MONDO:0004992' in json.dumps(mondo)


def test_stale_warnings_are_scoped(integrated, monkeypatch):
    i = integrated
    monkeypatch.setattr(i.services.system.projection, 'freshness', lambda *a, **kw: [
        {'id': 'workflow:csv-import', 'reason': 'source_changed_or_missing'},
        {'id': 'hidden:secret', 'reason': 'source_changed_or_missing'}])
    out = call(i, 'get_system_context', {'entry_id': 'workflow:csv-import'})
    assert out['context']['warnings'] == [{'id': 'workflow:csv-import', 'reason': 'source_changed_or_missing'}]


def test_conflicts_are_explicit_but_authorized(integrated, tmp_path):
    i = integrated
    path = tmp_path / 'person.yaml'
    path.write_text('id: person\nname: Person\nproperties:\n  name:\n    type: integer\n')
    graph = ontology_projection([path], catalog(), revision='test',
        bindings={k: SCOPE for k in ('catalog', str(path), 'sqlite:Person', 'sqlite:Project')})
    for n in graph.snapshot()['nodes']:
        i.s.store.grant_evidence(i.s.alice, ContextService.grant_id(n), admin_id=i.s.admin)
    i.services.ontologies['canonical'] = ContextService(graph, i.s.db, enabled=True)
    out = call(i, 'get_ontology_context', {'entry_id': 'ontology:catalog'})
    assert out['status'] == 'success' and out['context']['metadata']['blockers']
    assert not any(n['id'].startswith('label:') for n in out['context']['nodes'])
    i.s.store.grant_resource(i.s.alice, **SCOPE, admin_id=i.s.admin, allow=False)
    assert call(i, 'get_ontology_context', {'entry_id': 'ontology:catalog'}) == REFUSAL


def test_accepted_explanation_and_assertion_rationale(integrated):
    i = integrated
    out = call(i, 'explain_fact', {'fact_id': i.s.person['fact_id']})
    assert out['status'] == 'success' and out['fact']['curation_status'] == 'accepted'
    assert out['fact']['citations'] == [{'citation': 'Synthetic fixture', 'version': '1'}]
    assertion = call(i, 'get_assertion', {'assertion_id': i.s.person['assertion_id']})['assertion']
    assert assertion['curation_status'] == 'accepted' and assertion['rationale']
    assert 'identity_claims' not in json.dumps(assertion)
    assert 'Synthetic Person' not in json.dumps(assertion)
    assert 'decision_history' not in assertion
    assert assertion['evidence'][0]['evidence_id'] == i.s.eid


def test_explicit_history_grant(integrated):
    i = integrated
    args = {'assertion_id': i.s.person['assertion_id'], 'include_history': True}
    assert call(i, 'get_assertion', args) == REFUSAL
    with sqlite3.connect(i.s.ledger.path) as conn:
        rows = conn.execute('SELECT action,revision,rationale,created_at FROM decisions WHERE assertion_id=? ORDER BY revision DESC',
                            (i.s.person['assertion_id'],)).fetchall()
    history = [dict(action=d[0], revision=d[1], rationale=d[2], created_at=d[3]) for d in rows]
    gid = AssertionAccess.history_grant_id(i.s.person['assertion_id'], history)
    i.s.store.grant_evidence(i.s.alice, gid, admin_id=i.s.admin)
    out = call(i, 'get_assertion', args)
    assert out['assertion']['decision_history'] == history
    assert 'reviewer_id' not in json.dumps(out)


@pytest.mark.parametrize('denial', ['evidence', 'assertion', 'resource', 'classification', 'property', 'decision_property', 'high', 'unknown'])
def test_restricted_assertion_refusals_are_generic(integrated, denial):
    i, s = integrated, integrated.s
    aid = s.person['assertion_id']
    if denial == 'evidence':
        s.store.grant_evidence(s.alice, s.eid, admin_id=s.admin, allow=False)
    elif denial == 'assertion':
        s.store.grant_evidence(s.alice, aid, admin_id=s.admin, allow=False)
    elif denial == 'resource':
        s.store.grant_resource(s.alice, **SCOPE, admin_id=s.admin, allow=False)
    elif denial == 'classification':
        with sqlite3.connect(s.db) as conn:
            conn.execute('PRAGMA foreign_keys=OFF')
            conn.execute('DELETE FROM agent_resource_classification')
    elif denial == 'property':
        with sqlite3.connect(s.db) as conn:
            conn.execute("INSERT INTO agent_sharing VALUES ('Assertion','rationale','hidden',NULL,NULL)")
    elif denial == 'decision_property':
        with sqlite3.connect(s.db) as conn:
            conn.execute("INSERT INTO agent_sharing VALUES ('Decision','rationale','hidden',NULL,NULL)")
    elif denial == 'high':
        s.store.classify(**SCOPE, risk='high', admin_id=s.admin)
    else:
        aid = 'assertion:unknown'
    assert call(i, 'get_assertion', {'assertion_id': aid}) == REFUSAL
    assert call(i, 'get_assertion', {'assertion_id': 'unknown-or-legacy'}) == REFUSAL


def test_superseded_proposed_legacy_and_conflicting_support(integrated):
    i, s = integrated, integrated.s
    prop = property_body(s.ledger, s.eid)
    aid = s.ledger.submit(prop, actor='human', caller_key='property')
    grant_assertion(i, aid)
    fact = s.ledger.get_internal(aid)['fact_id']
    assert call(i, 'explain_fact', {'fact_id': fact})['fact']['assertion_statuses'] == ['proposed']
    accepted = decision(s.service, aid)
    s.service.materialize([accepted['operation_id']], reviewer='human', graph=s.graph)
    assert call(i, 'explain_fact', {'fact_id': fact})['fact']['curation_status'] == 'accepted'
    replacement_body = dict(prop, proposed_value='Different name')
    replacement = s.ledger.submit(replacement_body, actor='human', caller_key='replacement')
    grant_assertion(i, replacement)
    # Normal review prevents conflicting acceptance. Inject a malformed legacy
    # support state to verify disclosure still fails closed independently.
    with sqlite3.connect(s.ledger.path) as conn:
        conn.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)',
                     ('injected-conflict', replacement, 1, 'accept', 'human',
                      'Synthetic conflicting historical support', '2026-10-29', None))
    conflict = call(i, 'explain_fact', {'fact_id': fact})
    assert conflict['fact']['curation_status'] == 'not_currently_supported'
    # Supersede support without trusting the value still present in FakeGraph.
    third = s.ledger.submit(dict(prop, proposed_value='Third candidate'), actor='human', caller_key='third')
    grant_assertion(i, third)
    for target in (aid, replacement):
        decision(s.service, target, action='supersede', superseded_by=third)
    out = call(i, 'explain_fact', {'fact_id': fact})
    assert out['fact']['assertion_statuses'] == ['proposed', 'superseded']
    assert out['fact']['curation_status'] != 'accepted'
    assert call(i, 'explain_fact', {'fact_id': 'legacy:neo4j-only'}) == REFUSAL


def test_authenticated_idempotent_proposals_never_review(integrated):
    i, s = integrated, integrated.s
    body = node(s.ledger, s.eid, record='row:agent')
    args = {'assertion': body, 'caller_key': 'agent-key'}
    first = call(i, 'submit_assertion', args)
    assert first['status'] == 'success' and first['validation'] == 'valid'
    assert call(i, 'submit_assertion', args) == first
    internal = s.ledger.get_internal(first['assertion_id'])
    assert internal['proposed_by'] == 'agent-user:' + str(s.alice)
    assert internal['curation_status'] == 'proposed'
    with sqlite3.connect(s.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions WHERE assertion_id=?', (first['assertion_id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM outbox WHERE json_extract(body,\'$.assertion_id\')=?', (first['assertion_id'],)).fetchone()[0] == 0
    assert call(i, 'submit_assertion', dict(args, assertion=dict(body, method='changed'))) == REFUSAL
    i.cap.grant_proposal(s.alice, **SCOPE, admin_id=s.admin, allow=False)
    assert call(i, 'submit_assertion', args) == REFUSAL


@pytest.mark.parametrize('change', [
    {'ontology_version': 'wrong'}, {'evidence_refs': ['hidden']}, {'proposed_by': 'admin'},
    {'domain': 'fourth'}, {'target_kind': 'review'}, {'source_scope': {'namespace': 'synthetic', 'resource_id': 'unknown'}},
])
def test_proposal_validation_and_missing_provenance(integrated, change):
    i = integrated
    body = dict(node(i.s.ledger, i.s.eid), **change)
    assert call(i, 'submit_assertion', {'assertion': body, 'caller_key': 'invalid'}) == REFUSAL


@pytest.mark.parametrize('args', [[], False, {'entry_id': 'x', 'depth': True}, {'entry_id': 'x', 'depth': 7},
                                  {'entry_id': 'x', 'limit': 129}, {'entry_id': 'x', 'profile': 'review'}, {},
                                  {'entry_id': 42}, {'entry_id': 'x', 'identity': {'user_id': 1}}])
def test_strict_tool_arguments(integrated, args):
    out = run_tool('get_system_context', args, integrated.ctx)
    assert out == {'status': 'error', 'error': 'Invalid tool arguments.'}


def test_http_chat_and_trusted_host_mcp_parity(integrated):
    from scidk.mcp_server import ScidkMcpServer
    i = integrated
    client = make_app(i).test_client()
    headers = {'Authorization': 'Bearer ' + i.s.token['token']}
    args = {'entry_id': 'workflow:csv-import'}
    http = client.post('/api/agent/tools/get_system_context', headers=headers, json=args).json
    chat = client.post('/api/chat/tools/get_system_context', headers=headers, json=args).json
    mcp = ScidkMcpServer(tool_context=i.ctx)
    assert http['status'] == 'success' and chat == http == mcp.dispatch('get_system_context', args)
    names = lambda defs: {d['name'] for d in defs}
    tools = client.get('/api/agent/tools', headers=headers).json['tools']
    funcs = client.get('/api/agent/functions.json', headers=headers).json
    chat_funcs = client.get('/api/chat/functions.json', headers=headers).json
    assert names(tools) == {d['function']['name'] for d in funcs} == {d['function']['name'] for d in chat_funcs}
    assert names(tools) == names(mcp.tool_definitions()) == NAMES
    spec = client.get('/api/agent/openapi.json', headers=headers).json
    assert {d['post']['operationId'] for d in spec['paths'].values()} == NAMES
    assert client.post('/api/agent/tools/get_system_context', headers=headers, json=[]).json['status'] == 'error'


def test_unbound_mcp_no_proposals_or_discovery(integrated, monkeypatch):
    from scidk.mcp_server import ScidkMcpServer
    i = integrated
    monkeypatch.setenv('SCIDK_SETTINGS_DB', i.s.db)
    server = ScidkMcpServer()
    assert server.tool_definitions() == []
    for name in NAMES:
        assert server.dispatch(name, {}) == REFUSAL
    assert available_tool_definitions() == [] and openai_functions() == []


def test_cookie_chat_uses_existing_user_destination(integrated):
    from scidk.ai import provider_settings
    i = integrated
    provider_settings.save(i.s.db, 'alice', base_url='https://parley.example/v1', model='fixture-model')
    client = make_app(i).test_client()
    session = i.s.auth.create_user_session(i.s.alice, 'alice')
    client.set_cookie('scidk_session', session)
    assert client.post('/api/chat/tools/explain_fact', json={'fact_id': i.s.person['fact_id']}).json['status'] == 'success'
    provider_settings.save(i.s.db, 'alice', base_url='https://unapproved.example/v1', model='fixture-model')
    assert client.post('/api/chat/tools/explain_fact', json={'fact_id': i.s.person['fact_id']}).json == REFUSAL


def test_provider_uses_actual_approved_destination_only(integrated, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    i = integrated
    provider_settings.save(i.s.db, 'alice', base_url='https://parley.example/v1', model='fixture-model')
    sends = []
    monkeypatch.setattr(openai_compatible, 'chat_completion', lambda *a, **kw: sends.append((a, kw)))
    out = provider_settings.disclosed_tool_turn(i.ctx, 'explain_fact', {'fact_id': i.s.person['fact_id']})
    assert out == {'status': 'success', 'finish_reason': 'sent'} and len(sends) == 1
    assert sends[0][0][0] == 'https://parley.example/v1'
    assert 'Synthetic Person' not in sends[0][0][3][0]['content']
    provider_settings.save(i.s.db, 'alice', base_url='https://wrong.example/v1', model='fixture-model')
    assert provider_settings.disclosed_tool_turn(i.ctx, 'explain_fact', {'fact_id': i.s.person['fact_id']}) == REFUSAL
    assert len(sends) == 1


def test_legacy_queries_stay_suspended_and_no_agent_review(integrated):
    i = integrated
    assert call(i, 'query_knowledge_graph', {'cypher': 'MATCH (n) RETURN count(n)'}) == REFUSAL
    assert call(i, 'scan_summary') == REFUSAL
    assert not {'review', 'accept', 'reject', 'supersede', 'materialize'} & {d['name'] for d in TOOL_DEFINITIONS}


def test_relationship_endpoints_require_independent_source_access(integrated):
    i, s = integrated, integrated.s
    other_scope = dict(SCOPE, resource_id='other-resource')
    evidence = dict(s.evidence, source_scope=other_scope, source_id='other-export')
    eid = s.ledger.add_evidence(evidence)
    body = node(s.ledger, eid, label='Project', record='row:other')
    body['source_scope'] = other_scope
    body['candidate']['source_scope'] = other_scope
    aid = s.ledger.submit(body, actor='human', caller_key='other-project')
    project = s.ledger.get_internal(aid)['claim']['entity_ref']
    relationship = node(s.ledger, s.eid)
    relationship.pop('candidate')
    relationship.update(target_kind='relationship', subject_ref=s.person['claim']['entity_ref'],
                        predicate='PI_OF', object_ref=project, qualifiers={})
    rid = s.ledger.submit(relationship, actor='human', caller_key='cross-resource-edge')
    grant_assertion(i, rid)
    assert call(i, 'get_assertion', {'assertion_id': rid}) == REFUSAL
    assert call(i, 'submit_assertion', {'assertion': relationship, 'caller_key': 'edge'}) == REFUSAL
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO pipeline_source(id,name,plugin_type) VALUES ('other-resource','Synthetic other','fixture')")
    s.store.classify(**other_scope, risk='medium', admin_id=s.admin)
    s.store.grant_resource(s.alice, **other_scope, admin_id=s.admin)
    s.store.grant_evidence(s.alice, eid, admin_id=s.admin)
    assert call(i, 'get_assertion', {'assertion_id': rid})['status'] == 'success'
    assert call(i, 'submit_assertion', {'assertion': relationship, 'caller_key': 'edge'})['status'] == 'success'
    s.store.classify(**other_scope, risk='high', admin_id=s.admin)
    assert call(i, 'get_assertion', {'assertion_id': rid}) == REFUSAL


def test_profile_selector_cannot_grant_privileges(integrated):
    i = integrated
    client = make_app(i).test_client()
    headers = {'Authorization': 'Bearer ' + i.s.token['token']}
    args = {'assertion_id': i.s.person['assertion_id']}
    assert client.post('/api/agent/tools/get_assertion?profile=overview', headers=headers, json=args).json == REFUSAL
    assert client.post('/api/agent/tools/get_assertion?profile=review', headers=headers, json=args).json['status'] == 'success'
    i.cap.grant_tool(i.s.alice, 'review', 'get_assertion', admin_id=i.s.admin, allow=False)
    assert client.post('/api/agent/tools/get_assertion?profile=review', headers=headers, json=args).json == REFUSAL
    assert client.get('/api/agent/tools?profile=admin', headers=headers).json['tools'] == []


def test_no_proposal_discovery_without_usable_scoped_grant(integrated):
    i = integrated
    i.cap.grant_proposal(i.s.alice, **SCOPE, admin_id=i.s.admin, allow=False)
    assert 'submit_assertion' not in {d['name'] for d in available_tool_definitions(i.ctx)}
    with pytest.raises(DisclosureDenied):
        i.cap.grant_tool(i.s.bob, 'review', 'get_assertion', admin_id=i.s.bob)


def test_property_and_sanitization_cannot_be_bypassed(integrated):
    i, s = integrated, integrated.s
    body = property_body(s.ledger, s.eid)
    aid = s.ledger.submit(body, actor='human', caller_key='property-to-hide')
    grant_assertion(i, aid)
    assert call(i, 'get_assertion', {'assertion_id': aid})['status'] == 'success'
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO agent_sharing VALUES ('Person','name','hidden',NULL,NULL)")
    assert call(i, 'get_assertion', {'assertion_id': aid}) == REFUSAL
    assert call(i, 'submit_assertion', {'assertion': body, 'caller_key': 'hidden'}) == REFUSAL


def test_provider_rechecks_revocation_before_transport(integrated, monkeypatch):
    from scidk.ai import provider_settings, openai_compatible
    from scidk.agent_tools import registry
    i = integrated
    provider_settings.save(i.s.db, 'alice', base_url='https://parley.example/v1', model='fixture-model')
    real_run = registry.run_tool
    def revoke_after_read(*a, **kw):
        out = real_run(*a, **kw)
        if out.get('status') == 'success':
            i.s.store.grant_resource(i.s.alice, **SCOPE, admin_id=i.s.admin, allow=False)
        return out
    monkeypatch.setattr(registry, 'run_tool', revoke_after_read)
    monkeypatch.setattr(openai_compatible, 'chat_completion', lambda *a, **kw: pytest.fail('Unauthorized network send'))
    assert provider_settings.disclosed_tool_turn(i.ctx, 'explain_fact', {'fact_id': i.s.person['fact_id']}) == REFUSAL


def test_proposal_flag_independent_of_read_tools(integrated):
    i = integrated
    i.ctx.proposal_enabled = False
    assert 'submit_assertion' not in {d['name'] for d in available_tool_definitions(i.ctx)}
    assert call(i, 'submit_assertion', {'assertion': node(i.s.ledger, i.s.eid), 'caller_key': 'off'}) == REFUSAL
    assert call(i, 'explain_fact', {'fact_id': i.s.person['fact_id']})['status'] == 'success'


def test_configuration_and_argument_overrides_do_not_authorize(integrated):
    i = integrated
    app = make_app(i)
    app.config['SCIDK_KNOWLEDGE_CONTEXT_ENABLED'] = False
    client = app.test_client()
    headers = {'Authorization': 'Bearer ' + i.s.token['token'], 'X-User': 'admin', 'X-Endpoint': 'parley'}
    assert client.get('/api/agent/tools', headers=headers).json['tools'] == []
    assert client.post('/api/agent/tools/explain_fact', headers=headers,
                       json={'fact_id': i.s.person['fact_id']}).json == REFUSAL


def test_hidden_proposal_reference_refuses_before_write(integrated):
    i, s = integrated, integrated.s
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO agent_sharing VALUES ('Person','assertion_id','hidden',NULL,NULL)")
    with sqlite3.connect(s.ledger.path) as conn:
        before = conn.execute('SELECT count(*) FROM assertions').fetchone()[0]
    assert call(i, 'submit_assertion', {'assertion': node(s.ledger, s.eid, record='row:hidden-ref'),
                                       'caller_key': 'hidden-output'}) == REFUSAL
    with sqlite3.connect(s.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM assertions').fetchone()[0] == before


def test_canonical_sanitization_refuses_assertion_values(integrated):
    from scidk.curation.ontology import Ontology
    i, s = integrated, integrated.s
    definitions = catalog()
    definitions[0]['properties'][0]['sanitize'] = 'hash'
    s.ledger.ontology = Ontology([], definitions)
    candidate = node(s.ledger, s.eid, record='row:private')
    aid = s.ledger.submit(candidate, actor='human', caller_key='private-node')
    reference = s.ledger.get_internal(aid)['claim']['entity_ref']
    body = dict(candidate)
    body.pop('candidate')
    body.update(target_kind='property', target_ref=reference, property_key='name', proposed_value='Private name')
    pid = s.ledger.submit(body, actor='human', caller_key='private-property')
    grant_assertion(i, pid)
    assert call(i, 'get_assertion', {'assertion_id': pid}) == REFUSAL
    assert call(i, 'submit_assertion', {'assertion': body, 'caller_key': 'sanitized'}) == REFUSAL
