"""Governed workspace HTTP adapters over real isolated policy/review/ledger."""
import copy
import json
import sqlite3

import pytest

from scidk.web.routes.ui import bp
from scidk.agent_tools.security import REFUSAL
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.projection import ContextService, system_projection
from scidk.knowledge.system_manifest import ENTRIES
from .conftest import ROOT, SCOPE, OTHER_SCOPE
from .test_prompt12 import session


@pytest.fixture
def workspace(scenario):
    d = scenario
    from scidk.services.human_policy import HumanPolicyStore
    human = HumanPolicyStore(d.db)
    human.initialize(admin_id=d.reviewer)
    for uid in (d.alice, d.bob):
        human.grant_purpose(uid, 'research_browse', 'medium', admin_id=d.reviewer)
    d.app.register_blueprint(bp)
    d.app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_KNOWLEDGE_WORKSPACE_ENABLED=True)
    client = session(d)
    return d, client


def post(client, operation, body=None, domain='research'):
    return client.post(f'/api/knowledge/{domain}/{operation}', json={} if body is None else body)


def accept(d, assertions):
    d.apply([d.review(a).json['operation_id'] for a in assertions.values()])


def test_current_support_search_inspect_and_neighbors(workspace):
    d, client = workspace
    records = d.mapped_assertions()
    ref = records['pi']['claim']['entity_ref']
    assert post(client, 'search').json['result']['nodes'] == []
    assert post(client, 'inspect', {'id': ref}).json == REFUSAL
    accept(d, records)
    out = post(client, 'search', {'q': 'Synthetic Investigator', 'label': 'Person'})
    assert out.status_code == 200, out.json
    node = out.json['result']['nodes'][0]
    assert node['id'] == ref and node['curation_status'] == 'accepted'
    assert node['properties']['name'] == 'Dr Synthetic Investigator'
    assert 'source_identifier' not in json.dumps(out.json)
    assert 'RecordID:' not in json.dumps(out.json)
    inspected = post(client, 'inspect', {'id': ref})
    assert inspected.json['result']['nodes'][0]['support'][0]['citations']
    expanded = post(client, 'expand', {'id': ref}).json['result']
    assert len(expanded['nodes']) == 2 and len(expanded['edges']) == 1
    assert expanded['edges'][0]['type'] == 'PI_OF'
    edge = post(client, 'inspect', {'id': records['PI_OF']['fact_id']})
    assert edge.status_code == 200 and len(edge.json['result']['nodes']) == 2
    assert post(client, 'search', {'q': 'secret identity-only value'}).json['result']['nodes'] == []


def test_restricted_records_do_not_leak_via_discovery_or_context_switch(workspace):
    d, client = workspace
    permitted = d.mapped_assertions()
    private = d.mapped_assertions(scope=OTHER_SCOPE, actor='fixture-importer')
    accept(d, permitted); accept(d, private)
    hidden = private['pi']['claim']['entity_ref']
    assert hidden not in json.dumps(post(client, 'search').json)
    for operation in ('inspect', 'expand'):
        assert post(client, operation, {'id': hidden}).json == REFUSAL
        assert post(client, operation, {'id': 'unknown'}).json == REFUSAL
    # The same stable text is not authority to select a different context domain.
    assert post(client, 'context', {'id': hidden}, domain='system').json == REFUSAL
    assert post(client, 'context', {'id': hidden}, domain='ontology').json == REFUSAL
    ref = permitted['pi']['claim']['entity_ref']
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Person','name','hidden')")
    assert post(client, 'search', {'q': 'Synthetic Investigator'}).json['result']['nodes'] == []
    assert 'name' not in post(client, 'inspect', {'id': ref}).json['result']['nodes'][0]['properties']
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_resource_grant WHERE user_id=?', (d.alice,))
    assert post(client, 'search').json['result']['nodes'] == []
    assert post(client, 'expand', {'id': ref}).json == REFUSAL


def test_evidence_and_applied_receipts_required(workspace):
    d, client = workspace
    records = d.mapped_assertions(); accept(d, records)
    ref = records['pi']['claim']['entity_ref']
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_evidence_grant WHERE user_id=?', (d.alice,))
    assert post(client, 'inspect', {'id': ref}).json == REFUSAL
    assert post(client, 'search').json['result']['nodes'] == []
    for eid in records['pi']['claim']['evidence_refs']:
        d.policy.grant_evidence(d.alice, eid, admin_id=d.reviewer)
    assert post(client, 'inspect', {'id': ref}).status_code == 200
    replacement_body = {k: v for k, v in records['pi']['claim'].items() if k != 'entity_ref'}
    replacement = d.ledger.submit(replacement_body, actor='fixture-importer', caller_key='replacement')
    assert d.review(records['pi'], action='supersede', superseded_by=replacement).status_code == 200
    assert post(client, 'inspect', {'id': ref}).json == REFUSAL
    assert post(client, 'search', {'label': 'Person'}).json['result']['nodes'] == []


def test_system_traversal_ontology_definitions_and_conflicts(workspace):
    d, client = workspace
    system = post(client, 'context', {'id': 'workflow:csv-import'}, 'system')
    assert system.status_code == 200, system.json
    result = system.json['result']
    assert 'code:mapping' in {n['id'] for n in result['nodes']}
    assert result['edges'] and all(n['sources'] for n in result['nodes'])
    ontology = post(client, 'context', {'id': 'ontology:catalog'}, 'ontology')
    assert ontology.status_code == 200
    assert 'label:Person' in {n['id'] for n in ontology.json['result']['nodes']}
    bad = copy.deepcopy(d.definitions)
    bad[0]['relationships'][0]['to_label'] = 'AbsentEndpoint'
    projection = ontology_projection([], bad, revision='explicit-conflict-fixture',
        bindings={key: SCOPE for key in ['catalog', *['sqlite:' + row['name'] for row in bad]]})
    for node in projection.snapshot()['nodes']:
        d.policy.grant_evidence(d.alice, ContextService.grant_id(node), admin_id=d.reviewer)
    d.knowledge.ontologies['canonical'] = ContextService(projection, d.db, enabled=True)
    conflict = post(client, 'context', {'id': 'ontology:catalog'}, 'ontology')
    assert conflict.status_code == 200, conflict.json
    assert conflict.json['result']['metadata']['blockers']
    assert not any(n['id'].startswith('label:') for n in conflict.json['result']['nodes'])


def test_system_freshness_warnings_are_authorized(workspace):
    d, client = workspace
    projection = system_projection(ROOT, {entry['id']: SCOPE for entry in ENTRIES}, revision='older-fixture-revision')
    for node in projection.snapshot()['nodes']:
        d.policy.grant_evidence(d.alice, ContextService.grant_id(node), admin_id=d.reviewer)
    d.knowledge.system = ContextService(projection, d.db, enabled=True)
    response = post(client, 'context', {'id': 'workflow:csv-import'}, 'system')
    assert response.status_code == 200
    warnings = response.json['result']['warnings']
    assert warnings and all(w['reason'] == 'git_revision_changed' for w in warnings)
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_evidence_grant WHERE user_id=?', (d.alice,))
    assert post(client, 'context', {'id': 'workflow:csv-import'}, 'system').json == REFUSAL


def test_private_canvas_reuses_storage_and_rechecks_references(workspace):
    d, client = workspace
    records = d.mapped_assertions(); accept(d, records)
    ref = records['pi']['claim']['entity_ref']
    draft = {'elements': [
        {'group': 'nodes', 'data': {'id': ref, 'reference': ref}, 'position': {'x': 12, 'y': 40}},
        {'group': 'nodes', 'data': {'id': 'prov-1', 'provisional': True, 'label': 'Unresolved concept',
                                  'properties': {'name': '<script>draft</script>'}}, 'position': {'x': 50, 'y': 40}},
        {'group': 'edges', 'data': {'id': 'prov-edge', 'provisional': True, 'source': ref, 'target': 'prov-1', 'label': 'Hypothesis'}}],
        'notes': 'Private reasoning; no graph commit'}
    assert post(client, 'save', {'canvas': draft}).status_code == 200
    assert post(client, 'load').json['result'] == draft
    with sqlite3.connect(d.db) as conn:
        assert conn.execute('SELECT user_id,context_id FROM canvas_session').fetchall() == [(str(d.alice), 'knowledge:research:sketch')]
    assert post(client, 'load', domain='system').json['result'] == {}
    bob = session(d, 'bob')
    assert post(bob, 'load').json['result'] == {}
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_resource_grant WHERE user_id=?', (d.alice,))
    assert post(client, 'load').json == REFUSAL
    assert post(client, 'save', {'canvas': draft}).json == REFUSAL


def test_projection_references_pin_source_versions(workspace):
    d, client = workspace
    original = post(client, 'context', {'id': 'workflow:csv-import'}, 'system').json['result']
    draft = {'elements': [{'group': 'nodes', 'data': {'id': 'workflow:csv-import',
        'reference': 'workflow:csv-import', 'reference_version': original['version']}}]}
    assert post(client, 'save', {'canvas': draft}, 'system').status_code == 200
    assert post(client, 'load', domain='system').json['result'] == draft
    projection = system_projection(ROOT, {entry['id']: SCOPE for entry in ENTRIES}, revision='new-source-revision')
    for node in projection.snapshot()['nodes']:
        d.policy.grant_evidence(d.alice, ContextService.grant_id(node), admin_id=d.reviewer)
    d.knowledge.system = ContextService(projection, d.db, enabled=True)
    assert post(client, 'context', {'id': 'workflow:csv-import'}, 'system').status_code == 200
    assert post(client, 'load', domain='system').json == REFUSAL


@pytest.mark.parametrize('operation,body', [
    ('search', {'cypher': 'MATCH (n) RETURN n'}), ('inspect', {'id': '42', 'profile': 'review'}),
    ('search', {'offset': True}), ('expand', {'id': '42', 'user_id': 1}), ('commit', {}),
    ('save', {'canvas': {'elements': [], 'curation_status': 'accepted'}}),
    ('save', {'canvas': {'elements': [{'data': {'id': 'spoof', 'provisional': False}}]}}),
    ('save', {'kind': 'layout', 'canvas': {'preset': 'unknown'}}),
])
def test_no_query_identity_or_write_escape(workspace, operation, body):
    _, client = workspace
    assert post(client, operation, body).json == REFUSAL


def test_anonymous_token_disabled_and_destination_revocation(workspace):
    d, client = workspace
    assert post(d.app.test_client(), 'search').status_code in {401, 403}
    header = {'Authorization': 'Bearer ' + d.tokens['alice']['token']}
    assert client.post('/api/knowledge/research/search', json={}, headers=header).status_code == 403
    d.app.config['SCIDK_KNOWLEDGE_WORKSPACE_ENABLED'] = False
    assert post(client, 'search').json == REFUSAL
    d.app.config['SCIDK_KNOWLEDGE_WORKSPACE_ENABLED'] = True
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_destination_approval')
    assert post(client, 'search').status_code == 200
    assert post(client, 'load').status_code == 200
