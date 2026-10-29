"""Cross-component acceptance tests. No production graph, provider or browser."""
import copy
import json
import sqlite3

import pytest

from scidk.agent_tools.registry import ToolContext, run_tool, available_tool_definitions
from scidk.agent_tools.security import REFUSAL
from scidk.curation.contracts import ConflictError
from scidk.knowledge.projection import ContextService, system_projection, content_hash
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.external import mondo_fixture, propose_alignment
from scidk.knowledge.system_manifest import ENTRIES
from scidk.mcp_server import ScidkMcpServer
from tests.curation.test_review import FakeGraph
from .conftest import ROOT, FIXTURES, SCOPE, OTHER_SCOPE


def accept(d, assertions, keys=None):
    operations = []
    for key in (keys or assertions):
        result = d.review(assertions[key])
        assert result.status_code == 200, result.json
        operations.append(result.json['operation_id'])
    return operations


def explain(d, assertion, **kwargs):
    return d.tool('explain_fact', {'fact_id': assertion['fact_id']}, **kwargs)


def test_mapping_human_review_and_agent_explanation(scenario):
    d = scenario
    assertions = d.mapped_assertions()
    assert set(assertions) == {'pi', 'pi.name', 'project', 'project.project_id',
                               'project.short_description', 'project.record_source', 'PI_OF'}
    project, person, edge = (assertions[k] for k in ('project', 'pi', 'PI_OF'))
    assert project['claim']['candidate']['identity_claims']['project_id'] == 'CAC-DEMO-001'
    assert person['claim']['candidate']['source_identifier'] == {'record_id': 'WO-DEMO-001', 'role': 'pi'}
    assert 'email' not in person['claim']['candidate']['identity_claims']
    assert not d.graph.nodes and not d.graph.edges
    assert explain(d, person, profile='overview') == REFUSAL
    pending = d.tool('get_assertion', {'assertion_id': person['assertion_id']})
    assert pending['assertion']['curation_status'] == 'proposed'
    first = accept(d, assertions, ['project', 'pi'])
    d.apply(first)
    ref = person['claim']['entity_ref']
    assert 'name' not in d.graph.nodes[ref]
    assert explain(d, person, profile='overview')['fact']['curation_status'] == 'accepted'
    assert explain(d, assertions['pi.name'], profile='overview') == REFUSAL
    # Preserve unrelated existing graph provenance through property application.
    d.graph.nodes[ref]['created_at'] = 'synthetic-original'
    d.graph.nodes[ref]['legacy_provenance'] = 'synthetic-preserved'
    rest = accept(d, assertions, ['pi.name', 'project.project_id', 'project.short_description', 'PI_OF'])
    rejected = d.review(assertions['project.record_source'], action='reject')
    assert rejected.status_code == 200
    d.apply(list(reversed(rest)))
    assert d.graph.nodes[ref]['name'] == 'Dr Synthetic Investigator'
    assert d.graph.nodes[ref]['created_at'] == 'synthetic-original'
    assert d.graph.nodes[ref]['legacy_provenance'] == 'synthetic-preserved'
    assert 'record_source' not in d.graph.nodes[project['claim']['entity_ref']]
    out = explain(d, edge, profile='overview')
    assert out['status'] == 'success' and out['fact']['curation_status'] == 'accepted'
    assert out['fact']['citations'][0]['version'] == d.mapping_revision
    d.history_grant(edge['assertion_id'])
    history = d.tool('get_assertion', {'assertion_id': edge['assertion_id'], 'include_history': True})
    assert history['assertion']['decision_history'][0]['action'] == 'accept'
    # Source and mapping replay converge on the same assertion, entity and fact IDs.
    replay = d.mapped_assertions()
    assert {k: v['assertion_id'] for k, v in replay.items()} == {k: v['assertion_id'] for k, v in assertions.items()}
    before = copy.deepcopy((d.graph.nodes, d.graph.edges, d.graph.markers))
    d.apply(first + rest)
    assert (d.graph.nodes, d.graph.edges, d.graph.markers) == before
    second_row = d.mapped_assertions(row=1)
    assert second_row['pi']['claim']['entity_ref'] != ref
    assert second_row['project']['claim']['entity_ref'] == project['claim']['entity_ref']
    assert second_row['PI_OF']['fact_id'] != edge['fact_id']


def test_overview_never_releases_pending_or_rejected_even_with_review_grants(scenario):
    d = scenario
    assertions = d.mapped_assertions()
    person = assertions['pi']
    # The same user has broad Review metadata grants. Changing the selected
    # profile must still enforce Overview's current accepted-support boundary.
    assert explain(d, person, profile='overview') == REFUSAL
    assert explain(d, person)['fact']['assertion_statuses'] == ['proposed']
    assert d.review(person, action='reject').status_code == 200
    assert explain(d, person, profile='overview') == REFUSAL
    assert explain(d, person)['fact']['assertion_statuses'] == ['rejected']
    assert d.tool('get_assertion', {'assertion_id': person['assertion_id']}, profile='overview') == REFUSAL


def test_transaction_endpoints_crash_and_target_binding(scenario):
    d = scenario
    assertions = d.mapped_assertions()
    edge_operation = accept(d, assertions, ['PI_OF'])
    with pytest.raises(ConflictError, match='dependency'):
        d.apply(edge_operation)
    assert not d.graph.nodes and not d.graph.edges
    operations = accept(d, assertions, ['project', 'pi', 'pi.name']) + edge_operation
    d.graph.fail = True
    with pytest.raises(RuntimeError, match='Injected'):
        d.apply(list(reversed(operations)))
    assert not d.graph.nodes and not d.graph.edges and not d.graph.markers
    d.graph.fail = False
    def crash():
        raise RuntimeError('Synthetic interruption after graph commit')
    with pytest.raises(RuntimeError, match='Synthetic interruption'):
        d.apply(list(reversed(operations)), after_graph_commit=crash)
    assert len(d.graph.edges) == 1
    before = copy.deepcopy((d.graph.nodes, d.graph.edges, d.graph.markers))
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
        assert conn.execute('SELECT graph_target FROM graph_binding').fetchone() == (d.graph.target,)
    alien = FakeGraph()
    alien.target = 'explicit-other-disposable-target'
    with d.app.app_context(), pytest.raises(ConflictError, match='target'):
        d.service.materialize(operations, reviewer=str(d.reviewer), graph=alien)
    d.apply(operations)
    assert (d.graph.nodes, d.graph.edges, d.graph.markers) == before
    assert explain(d, assertions['PI_OF'], profile='overview')['fact']['curation_status'] == 'accepted'
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == len(operations)


def test_independent_evidence_conflicts_supersession_and_retained_graph(scenario):
    d = scenario
    assertions = d.mapped_assertions()
    d.apply(accept(d, assertions, ['project', 'pi', 'pi.name', 'PI_OF']))
    original = assertions['pi.name']
    primary_eid = original['claim']['evidence_refs'][0]
    with sqlite3.connect(d.ledger.path) as conn:
        primary_evidence = json.loads(conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (primary_eid,)).fetchone()[0])
    check_bytes = (FIXTURES / 'corroboration.json').read_bytes()
    evidence = dict(primary_evidence, source_id='synthetic-personnel-check', source_type='synthetic_check',
        citation=json.loads(check_bytes)['citation'], version='synthetic-check/1',
        content_hash=content_hash(check_bytes), derivation_root='independent-synthetic-personnel-check')
    eid = d.ledger.add_evidence(evidence)
    d.policy.grant_evidence(d.alice, eid, admin_id=d.reviewer)
    common = dict(original['claim'])
    corroboration = d.submit(dict(common, evidence_refs=[eid]), 'independent-name-support')
    d.apply(accept(d, {'corroboration': corroboration}))
    out = explain(d, original, profile='overview')
    assert len(out['fact']['citations']) == 2
    assert primary_evidence['derivation_root'] != evidence['derivation_root']
    correction = d.submit(dict(common, proposed_value='Dr Synthetic Corrected Investigator'), 'corrected-name')
    blocked = d.review(correction)
    assert blocked.status_code == 409
    assert d.graph.nodes[assertions['pi']['claim']['entity_ref']]['name'] == common['proposed_value']
    assert d.review(original, action='supersede', superseded_by=correction['assertion_id']).status_code == 200
    assert explain(d, original, profile='overview')['fact']['curation_status'] == 'accepted'
    assert d.review(corroboration, action='supersede', superseded_by=correction['assertion_id']).status_code == 200
    # Old graph bytes survive, but neither superseded support nor a pending
    # correction can be returned as currently accepted in Overview.
    assert d.graph.nodes[assertions['pi']['claim']['entity_ref']]['name'] == common['proposed_value']
    assert explain(d, original, profile='overview') == REFUSAL
    uncertain = explain(d, original)
    assert uncertain['fact']['assertion_statuses'] == ['proposed', 'superseded']
    d.apply(accept(d, {'correction': correction}))
    assert explain(d, correction, profile='overview')['fact']['value'] == 'Dr Synthetic Corrected Investigator'
    d.history_grant(original['assertion_id'])
    history = d.tool('get_assertion', {'assertion_id': original['assertion_id'], 'include_history': True})
    assert [r['action'] for r in history['assertion']['decision_history']] == ['supersede', 'accept']
    with sqlite3.connect(d.ledger.path) as conn:
        stored = json.loads(conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (primary_eid,)).fetchone()[0])
        assert stored == primary_evidence


def test_two_principals_and_transport_parity_without_query_bypasses(scenario, monkeypatch):
    d = scenario
    assertions = d.mapped_assertions()
    d.apply(accept(d, assertions, ['project', 'pi', 'pi.name', 'PI_OF']))
    other = d.mapped_assertions(scope=OTHER_SCOPE, actor='fixture-importer')
    assert other['pi']['claim']['entity_ref'] != assertions['pi']['claim']['entity_ref']
    assert other['project']['claim']['entity_ref'] != assertions['project']['claim']['entity_ref']
    d.apply(accept(d, other, ['project', 'pi', 'PI_OF']))
    for assertion in other.values():
        for eid in assertion['claim']['evidence_refs']:
            d.policy.grant_evidence(d.bob, eid, admin_id=d.reviewer)
    assert explain(d, other['PI_OF'], profile='overview', principal='bob')['status'] == 'success'
    for principal, expected in [('alice', 'success'), ('bob', 'refused')]:
        headers = {'Authorization': 'Bearer ' + d.tokens[principal]['token']}
        client = d.app.test_client()
        args = {'fact_id': assertions['PI_OF']['fact_id']}
        http = client.post('/api/agent/tools/explain_fact?profile=overview', headers=headers, json=args).json
        chat = client.post('/api/chat/tools/explain_fact?profile=overview', headers=headers, json=args).json
        ctx = ToolContext(settings_db=d.db, identity=d.identities[principal], profile='overview',
                          knowledge=d.knowledge, knowledge_enabled=True)
        host = ScidkMcpServer(tool_context=ctx)
        assert http == chat == host.dispatch('explain_fact', args)
        assert http['status'] == expected
        for query in ('RETURN 1', 'MATCH (n) RETURN count(n)',
                      'MATCH (n) WHERE n.name="Dr Synthetic Investigator" RETURN 1'):
            out = client.post('/api/agent/tools/query_knowledge_graph', headers=headers, json={'cypher': query})
            assert out.json == REFUSAL
        assert client.post('/api/agent/tools/scan_summary', headers=headers, json={}).json == REFUSAL
    denied = explain(d, assertions['PI_OF'], profile='overview', principal='bob')
    assert denied == d.tool('explain_fact', {'fact_id': 'fact:unknown'}, principal='bob') == REFUSAL
    assert d.tool('get_assertion', {'assertion_id': assertions['pi']['assertion_id']}, principal='bob') == REFUSAL
    # Missing provenance is not repaired from graph presence.
    d.graph.nodes['legacy-no-ledger'] = {'name': 'Synthetic legacy value'}
    assert d.tool('explain_fact', {'fact_id': 'legacy-no-ledger'}, profile='overview') == REFUSAL
    assert d.tool('submit_assertion', {'assertion': dict(assertions['PI_OF']['claim']), 'caller_key': 'bob'}, principal='bob') == REFUSAL
    with sqlite3.connect(d.ledger.path) as conn:
        decisions_before = conn.execute('SELECT count(*) FROM decisions').fetchone()[0]
    headers = {'Authorization': 'Bearer ' + d.tokens['alice']['token']}
    assert d.app.test_client().post('/api/curation/assertions/' + assertions['pi']['assertion_id'] + '/review',
                                  headers=headers, json={'action': 'accept'}).status_code == 403
    ordinary_human = d.app.test_client()
    ordinary_human.set_cookie('scidk_session', d.auth.create_user_session(d.alice, 'alice'))
    assert ordinary_human.post('/api/curation/assertions/' + assertions['pi']['assertion_id'] + '/preview').status_code == 403
    for name in ('accept_assertion', 'review_assertion', 'reject_assertion', 'supersede_assertion', 'materialize'):
        assert d.tool(name, {})['status'] != 'success'
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions').fetchone()[0] == decisions_before
    monkeypatch.setenv('SCIDK_SETTINGS_DB', d.db)
    stdio = ScidkMcpServer()
    assert stdio.tool_definitions() == [] and stdio.dispatch('explain_fact', args) == REFUSAL


def test_disclosure_revocation_across_the_integrated_support_path(scenario):
    d = scenario
    assertions = d.mapped_assertions()
    d.apply(accept(d, assertions, ['project', 'pi', 'pi.name', 'PI_OF']))
    assert explain(d, assertions['PI_OF'], profile='overview')['status'] == 'success'
    eid = assertions['pi']['claim']['evidence_refs'][0]
    d.policy.grant_evidence(d.alice, eid, admin_id=d.reviewer, allow=False)
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    d.policy.grant_evidence(d.alice, eid, admin_id=d.reviewer)
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing VALUES ('Person','name','hidden',NULL,NULL)")
    assert explain(d, assertions['pi.name'], profile='overview') == REFUSAL
    assert d.tool('get_assertion', {'assertion_id': assertions['pi.name']['assertion_id']}) == REFUSAL
    with sqlite3.connect(d.db) as conn:
        conn.execute("DELETE FROM agent_sharing WHERE label='Person'")
        conn.execute("INSERT INTO agent_sharing VALUES ('PI_OF','object_ref','hidden',NULL,NULL)")
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_sharing')
    d.policy.approve_destination('demo', 'https://provider.example/v1', 'synthetic-model', 'low', admin_id=d.reviewer)
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    d.policy.approve_destination('demo', 'https://provider.example/v1', 'synthetic-model', 'medium', admin_id=d.reviewer)
    d.policy.classify(**SCOPE, risk='high', admin_id=d.reviewer)
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    assert d.tool('get_system_context', {'entry_id': 'workflow:csv-import'}) == REFUSAL
    d.policy.classify(**SCOPE, risk='medium', admin_id=d.reviewer)
    d.policy.grant_resource(d.alice, **SCOPE, admin_id=d.reviewer, allow=False)
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL
    d.policy.grant_resource(d.alice, **SCOPE, admin_id=d.reviewer)
    assert explain(d, assertions['PI_OF'], profile='overview')['status'] == 'success'
    with sqlite3.connect(d.db) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('DELETE FROM agent_resource_classification WHERE resource_id=?', (SCOPE['resource_id'],))
    assert explain(d, assertions['PI_OF'], profile='overview') == REFUSAL


def test_three_domains_stale_context_blockers_and_proposed_mondo(scenario, tmp_path, monkeypatch):
    d = scenario
    assertions = d.mapped_assertions()
    d.apply(accept(d, assertions, ['project', 'pi', 'PI_OF']))
    system = d.tool('get_system_context', {'entry_id': 'workflow:csv-import'})
    assert system['status'] == 'success' and system['context']['version']
    assert {'schema:mapping', 'code:mapping', 'permission:disclosure'} <= {n['id'] for n in system['context']['nodes']}
    discovery = d.tool('get_system_context', {'entry_id': 'workflow:tool-discovery'})
    assert any(e['type'] == 'EXPOSED_VIA' and e['target'] == 'tool:registry' for e in discovery['context']['edges'])
    revision = system['context']['nodes'][0]['git_revision']
    mirror = tmp_path / 'selected-system-sources'
    for entry in ENTRIES:
        path = mirror / entry['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / entry['path']).read_bytes())
    generated = system_projection(mirror, {n['id']: SCOPE for n in ENTRIES}, revision=revision)
    d.knowledge.system, d.knowledge.system_root = ContextService(generated, d.db, enabled=True), mirror
    monkeypatch.setattr('scidk.agent_tools.knowledge.git_revision', lambda root: revision)
    schema = mirror / 'scidk/pipeline/mapping_schema.json'
    schema.write_text(schema.read_text() + '\n')
    stale = d.tool('get_system_context', {'entry_id': 'workflow:csv-import'})
    assert {'id': 'schema:mapping', 'reason': 'source_changed_or_missing'} in stale['context']['warnings']
    ontology = d.tool('get_ontology_context', {'entry_id': 'label:Person'})
    rel = next(n for n in ontology['context']['nodes'] if n['id'].startswith('relationship:'))
    assert rel['definition']['source_label'] == 'Person' and rel['definition']['target_label'] == 'Project'
    assert rel['definition']['properties']['role']['allowed_values'] == ['PI']
    assert rel['ontology_version'] == d.ledger.ontology.version
    assert all(s['hash'] for s in rel['sources'])
    path = tmp_path / 'conflicting-person.yaml'
    path.write_text('id: person\nname: Person\nproperties:\n  name:\n    type: integer\n')
    bindings = {key: SCOPE for key in ['catalog', str(path), *['sqlite:' + n['name'] for n in d.definitions]]}
    conflict = ontology_projection([path], d.definitions, bindings=bindings, revision='synthetic-conflict')
    for n in conflict.snapshot()['nodes']:
        d.policy.grant_evidence(d.alice, ContextService.grant_id(n), admin_id=d.reviewer)
    d.knowledge.ontologies['canonical'] = ContextService(conflict, d.db, enabled=True)
    blockers = d.tool('get_ontology_context', {'entry_id': 'ontology:catalog'})
    assert blockers['context']['metadata']['blockers']
    assert not any(n['id'].startswith('label:') for n in blockers['context']['nodes'])
    mondo = d.tool('get_ontology_context', {'catalog': 'MONDO', 'entry_id': 'external:MONDO'})
    assert mondo['status'] == 'success' and 'MONDO:0004992' in json.dumps(mondo)
    eid, evidence = d.evidence()
    body = dict(assertions['pi']['claim'])
    body.pop('entity_ref')
    body['candidate'] = dict(label='SyntheticWorkOrder', source_scope=SCOPE,
        source_identifier={'record_id': d.rows[0]['RecordID'], 'role': 'work-order'}, identity_claims={})
    work_order = d.submit(body, 'synthetic-work-order')
    ref = work_order['claim']['entity_ref']
    raw = d.rows[0]['Disease']
    aid = propose_alignment(d.ledger, target_ref=ref, property_key='disease_alignments', raw_value=raw,
        source_scope=SCOPE, registry=mondo_fixture(), namespace='MONDO', actor='fixture-importer',
        caller_key='mondo-proposal', intake_evidence=evidence)
    claim = d.ledger.get_internal(aid)
    d.policy.grant_evidence(d.alice, aid, admin_id=d.reviewer)
    for evidence_id in claim['claim']['evidence_refs']:
        d.policy.grant_evidence(d.alice, evidence_id, admin_id=d.reviewer)
    proposed = d.tool('get_assertion', {'assertion_id': aid})['assertion']
    payload = proposed['claim']['proposed_value'][0]
    assert proposed['curation_status'] == 'proposed' and proposed['claim']['epistemic_status'] == 'inferred'
    assert payload['original_value'] == raw and bytes.fromhex(payload['original_utf8_hex']).decode() == raw
    assert payload['concept']['accession'] == 'MONDO:0004992'
    assert ref not in d.graph.nodes and explain(d, claim, profile='overview') == REFUSAL
    with sqlite3.connect(d.ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions WHERE assertion_id=?', (aid,)).fetchone()[0] == 0
        assert json.loads(conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (eid,)).fetchone()[0]) == evidence


def test_existing_dms_export_is_a_global_human_draft_not_selected_dataset(scenario, monkeypatch):
    from plugins.nih_dms import routes as dms_routes
    from tests.test_nih_dms_plan import FakeGraph as DmsGraph
    d = scenario
    d.app.register_blueprint(dms_routes.bp)
    assertions = d.mapped_assertions()
    d.apply(accept(d, assertions, ['project', 'pi', 'pi.name', 'project.project_id', 'PI_OF']))
    labels = {assertions[k]['claim']['entity_ref']: assertions[k]['claim']['candidate']['label'] for k in ('project', 'pi')}
    nodes = [{'labels': [labels[ref]], 'properties': props} for ref, props in d.graph.nodes.items()]
    graph = DmsGraph(nodes=nodes, relationships=[{'type': 'PI_OF', 'properties': {}}])
    monkeypatch.setattr(dms_routes, '_neo4j_client', lambda: graph)
    out = d.human.get('/api/plugins/nih_dms/draft_plan?format=json&dataset_id=synthetic-not-a-filter')
    assert out.status_code == 200 and out.json['status'] == 'ok'
    assert out.json['summary']['records'] == 2 and out.json['summary']['files'] == 0
    assert '[REPOSITORY_NAME]' in out.json['markdown'] and '[RETENTION_PERIOD]' in out.json['markdown']
    assert 'draft' in out.json['markdown'].lower()
    # Supplying a dataset parameter does not add an actual dataset predicate.
    assert all('synthetic-not-a-filter' not in query for query in graph.queries)
    client = d.app.test_client()
    headers = {'Authorization': 'Bearer ' + d.tokens['alice']['token']}
    assert client.get('/api/plugins/nih_dms/draft_plan?format=json', headers=headers).json == REFUSAL
