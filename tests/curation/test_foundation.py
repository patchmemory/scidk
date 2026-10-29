import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from scidk.curation.contracts import ConflictError, ContractError, canonical, entity_ref
from scidk.curation.ledger import Ledger, migrate
from scidk.curation.ontology import Ontology
from scidk.schema.registry import _LabelRegistry


SCOPE = {'namespace': 'synthetic', 'resource_id': 'resource-1'}


def catalog():
    return [
        {'name': 'Person', 'properties': [{'name': 'name', 'type': 'string'},
                                        {'name': 'age', 'type': 'integer'}],
         'relationships': [{'type': 'PI_OF', 'target_label': 'Project'}]},
        {'name': 'Project', 'properties': [{'name': 'name', 'type': 'string'}]},
    ]


@pytest.fixture
def foundation(tmp_path):
    path = tmp_path / 'curation.sqlite'
    migrate(path)
    ontology = Ontology([], catalog())
    ledger = Ledger(path, ontology, lambda actor, evidence: actor == 'human')
    evidence = {'source_type': 'export', 'source_id': 'export-1', 'source_scope': SCOPE,
                'citation': 'Synthetic fixture', 'version': '1', 'accessed_at': '2026-10-29T00:00:00Z',
                'content_hash': 'sha256:synthetic', 'locator': 'row:1', 'retrieval_method': 'fixture',
                'visibility': 'restricted', 'derivation_root': 'export-1'}
    evidence_id = ledger.add_evidence(evidence)
    return ledger, evidence, evidence_id


def node(ledger, evidence_id, label='Person', record='row:1'):
    return {'domain': 'research', 'target_kind': 'node', 'ontology_version': ledger.ontology.version,
            'epistemic_status': 'inferred', 'method': 'fixture', 'visibility': 'restricted',
            'source_scope': SCOPE, 'evidence_refs': [evidence_id],
            'candidate': {'label': label, 'source_scope': SCOPE,
                          'source_identifier': {'record_id': record, 'role': 'PI'},
                          'identity_claims': {'name': 'Synthetic Person'}}}


def submit_node(ledger, evidence_id, label='Person', record='row:1'):
    body = node(ledger, evidence_id, label, record)
    assertion = ledger.submit(body, actor='human', caller_key=label + record)
    return ledger.get_internal(assertion)


def property_body(ledger, evidence_id):
    person = submit_node(ledger, evidence_id)
    body = node(ledger, evidence_id)
    del body['candidate']
    body.update(target_kind='property', target_ref=person['claim']['entity_ref'],
                property_key='name', proposed_value='New synthetic name')
    return body


def test_explicit_migration_and_refuse_existing_database(tmp_path):
    path = tmp_path / 'missing.sqlite'
    with pytest.raises(sqlite3.OperationalError):
        Ledger(path, Ontology([], []), lambda *args: True)
    assert not path.exists()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE file_index (id TEXT)')
    with pytest.raises(ConflictError):
        migrate(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('file_index',)]


def test_evidence_lineage_immutability_and_reopen(foundation):
    ledger, evidence, eid = foundation
    assert ledger.add_evidence(evidence) == eid
    second = dict(evidence, derivation_root='export-2', locator='row:2')
    assert ledger.add_evidence(second) != eid
    result = submit_node(ledger, eid)
    migrate(ledger.path)  # idempotent, no data loss
    reopened = Ledger(ledger.path, ledger.ontology, ledger.can_read_evidence)
    assert reopened.get_internal(result['assertion_id']) == result
    with sqlite3.connect(ledger.path) as conn:
        for table in ('evidence', 'assertions', 'submissions', 'curation_schema'):
            for operation in ('UPDATE', 'DELETE'):
                query = f'UPDATE {table} SET ' + {'evidence': 'body=body', 'assertions': 'body=body',
                        'submissions': 'actor=actor', 'curation_schema': 'version=version'}[table] if operation == 'UPDATE' else f'DELETE FROM {table}'
                with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                    conn.execute(query)


def test_actor_scoped_idempotency_and_atomic_concurrency(foundation):
    ledger, _, eid = foundation
    body = node(ledger, eid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: ledger.submit(body, actor='human', caller_key='key'), range(8)))
    assert len(set(ids)) == 1
    changed = copy.deepcopy(body)
    changed['method'] = 'another method'
    with pytest.raises(ConflictError):
        ledger.submit(changed, actor='human', caller_key='key')
    other = Ledger(ledger.path, ledger.ontology, lambda *args: True)
    assert other.submit(body, actor='other-human', caller_key='key') != ids[0]
    denied = Ledger(ledger.path, ledger.ontology, lambda *args: False)
    with pytest.raises(ContractError, match='unavailable'):
        denied.submit(body, actor='human', caller_key='key')


def test_source_scoped_people_and_normalized_ids(foundation):
    ledger, _, eid = foundation
    first = node(ledger, eid)['candidate']
    other = copy.deepcopy(first)
    other['source_identifier']['record_id'] = 'row:2'
    assert entity_ref(first) != entity_ref(other)
    other = copy.deepcopy(first)
    other['source_scope']['resource_id'] = 'resource-2'
    assert entity_ref(first) != entity_ref(other)
    other = copy.deepcopy(first)
    other['identity_claims']['email'] = 'synthetic@example.invalid'
    assert entity_ref(first) == entity_ref(other)
    a = copy.deepcopy(first)
    a['source_identifier']['record_id'] = 'caf\u00e9'
    b = copy.deepcopy(a)
    b['source_identifier']['record_id'] = 'cafe\u0301'
    assert entity_ref(a) == entity_ref(b)


def test_separate_fact_identity_and_conflicting_claims(foundation):
    ledger, _, eid = foundation
    body = property_body(ledger, eid)
    first = ledger.get_internal(ledger.submit(body, actor='human', caller_key='property1'))
    body['proposed_value'] = 'Conflicting synthetic name'
    second = ledger.get_internal(ledger.submit(body, actor='human', caller_key='property2'))
    assert first['fact_id'] == second['fact_id']
    assert first['assertion_id'] != second['assertion_id']
    assert first['curation_status'] == 'proposed'
    assert first['claim']['epistemic_status'] == 'inferred'
    person = submit_node(ledger, eid)
    assert person['fact_id'] != first['fact_id']
    body['supersedes'] = first['assertion_id']
    ledger.submit(body, actor='human', caller_key='replacement')
    body['supersedes'] = person['assertion_id']
    with pytest.raises(ContractError, match='same fact'):
        ledger.submit(body, actor='human', caller_key='wrong-replacement')


def test_relationship_direction_and_domain(foundation):
    ledger, _, eid = foundation
    person = submit_node(ledger, eid)
    project = submit_node(ledger, eid, 'Project')
    body = node(ledger, eid)
    del body['candidate']
    body.update(target_kind='relationship', subject_ref=person['claim']['entity_ref'],
                predicate='PI_OF', object_ref=project['claim']['entity_ref'], qualifiers={})
    first = ledger.get_internal(ledger.submit(body, actor='human', caller_key='relationship'))
    assert first['fact_id'] != person['fact_id']
    second = ledger.get_internal(ledger.submit(body, actor='human', caller_key='relationship2'))
    assert second['fact_id'] == first['fact_id']
    body['subject_ref'], body['object_ref'] = body['object_ref'], body['subject_ref']
    with pytest.raises(ContractError, match='direction'):
        ledger.submit(body, actor='human', caller_key='backwards')
    body['domain'] = 'system'
    with pytest.raises(ContractError, match='domain'):
        ledger.submit(body, actor='human', caller_key='wrong-domain')


@pytest.mark.parametrize('change', [
    {'ontology_version': 'old'}, {'confidence': float('nan'), 'confidence_method': 'test'},
    {'confidence': float('inf'), 'confidence_method': 'test'}, {'confidence': True},
    {'confidence': 1.1, 'confidence_method': 'test'}, {'confidence': 0.5},
    {'epistemic_status': 'accepted'}, {'domain': 'fourth'}, {'evidence_refs': []},
    {'evidence_refs': ['missing']}, {'proposed_by': 'spoofed'}, {'visibility': ''},
])
def test_invalid_contracts_fail_without_writes(foundation, change):
    ledger, _, eid = foundation
    body = dict(node(ledger, eid), **change)
    with pytest.raises(ContractError):
        ledger.submit(body, actor='human', caller_key='invalid')
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM assertions').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 0


@pytest.mark.parametrize('key,value', [('age', True), ('age', '42'), ('unknown', 'x'), ('name', None)])
def test_property_type_enforcement(foundation, key, value):
    ledger, _, eid = foundation
    body = property_body(ledger, eid)
    body.update(property_key=key, proposed_value=value)
    with pytest.raises(ContractError):
        ledger.submit(body, actor='human', caller_key='bad-property')


def test_undeclared_labels_and_bad_identifiers(foundation):
    ledger, _, eid = foundation
    for label in ('Undeclared', 'Person` SET x=1'):
        with pytest.raises(ContractError):
            ledger.submit(node(ledger, eid, label), actor='human', caller_key='bad-label')


def test_catalog_conflicts_and_source_revisions(tmp_path):
    path = tmp_path / 'person.yaml'
    path.write_text('id: person\nname: Person\nproperties:\n  name:\n    type: string\n')
    parsed = _LabelRegistry()._parse_yaml(str(path))
    sqlite = [{'name': 'Person', 'properties': [{'name': 'name', 'type': 'string'}]}]
    ontology = Ontology([parsed], sqlite)
    assert ontology.label('Person')['properties']['name']['type'] == 'string'
    sqlite[0]['properties'][0]['type'] = 'integer'
    with pytest.raises(ConflictError, match='reconciliation'):
        Ontology([parsed], sqlite)
    changed = copy.deepcopy(parsed)
    changed.content_hash = 'another-source-version'
    assert Ontology([changed], []).version != Ontology([parsed], []).version
    snapshot = ontology.snapshot()
    snapshot['labels'].clear()
    assert ontology.label('Person')


def test_yaml_duplicates_not_silently_overwritten(tmp_path):
    paths = [tmp_path / 'one.yaml', tmp_path / 'two.yaml']
    for path, type_name in zip(paths, ('string', 'integer')):
        path.write_text(f'id: person\nname: Person\nproperties:\n  name:\n    type: {type_name}\n')
    with pytest.raises(ConflictError):
        Ontology.from_yaml_paths(paths, [])


def test_nonfinite_and_unicode_key_collisions_rejected():
    for value in ({'x': float('nan')}, {'caf\u00e9': 1, 'cafe\u0301': 2}):
        with pytest.raises(ContractError):
            canonical(value)


def test_relationship_property_and_epistemic_history(foundation):
    ledger, _, eid = foundation
    definitions = catalog()
    definitions[0]['relationships'][0]['properties'] = [{'name': 'role', 'type': 'string'}]
    ledger.ontology = Ontology([], definitions)
    person = submit_node(ledger, eid)
    project = submit_node(ledger, eid, 'Project')
    body = node(ledger, eid)
    del body['candidate']
    body.update(target_kind='relationship', subject_ref=person['claim']['entity_ref'],
                predicate='PI_OF', object_ref=project['claim']['entity_ref'], qualifiers={})
    relationship = ledger.get_internal(ledger.submit(body, actor='human', caller_key='edge'))
    prop = property_body(ledger, eid)
    prop.update(target_ref=relationship['fact_id'], property_key='role', proposed_value='PI')
    ledger.submit(prop, actor='human', caller_key='edge-property')
    prop['proposed_value'] = 12
    with pytest.raises(ContractError):
        ledger.submit(prop, actor='human', caller_key='bad-edge-property')
    # Exercise the append-only storage contract without introducing a review API.
    with sqlite3.connect(ledger.path) as conn:
        conn.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)',
                     ('decision-1', relationship['assertion_id'], 1, 'accept', 'reviewer',
                      'Synthetic storage test', '2026-10-29', None))
    reviewed = ledger.get_internal(relationship['assertion_id'])
    assert reviewed['curation_status'] == 'accepted'
    assert reviewed['claim']['epistemic_status'] == 'inferred'
    with sqlite3.connect(ledger.path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            conn.execute("UPDATE decisions SET action='reject'")
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            conn.execute('DELETE FROM decisions')


def test_source_scopes_and_evidence_authorization(foundation):
    ledger, evidence, eid = foundation
    body = node(ledger, eid)
    body['candidate'] = copy.deepcopy(body['candidate'])
    body['candidate']['source_scope'] = dict(SCOPE, resource_id='another-resource')
    with pytest.raises(ContractError, match='scope mismatch'):
        ledger.submit(body, actor='human', caller_key='wrong-candidate-scope')
    second = copy.deepcopy(evidence)
    second['source_scope'] = dict(SCOPE, resource_id='another-resource')
    other_id = ledger.add_evidence(second)
    body = node(ledger, other_id)
    with pytest.raises(ContractError, match='scope mismatch'):
        ledger.submit(body, actor='human', caller_key='wrong-evidence-scope')
    with pytest.raises(ContractError, match='unavailable'):
        ledger.submit(node(ledger, eid), actor='agent', caller_key='denied')


def test_multiple_evidence_same_fact_preserves_independent_roots(foundation):
    ledger, evidence, eid = foundation
    first = submit_node(ledger, eid)
    second_evidence = dict(evidence, source_id='independent-export', derivation_root='independent-export')
    second_id = ledger.add_evidence(second_evidence)
    body = node(ledger, second_id)
    body['evidence_refs'].append(eid)
    second = ledger.get_internal(ledger.submit(body, actor='human', caller_key='corroboration'))
    assert first['fact_id'] == second['fact_id']
    assert len(second['claim']['evidence_refs']) == 2
    assert first['claim']['evidence_refs'] == [eid]


def test_incoming_relationship_declaration_and_constraints():
    definitions = catalog()
    definitions[0]['relationships'] = []
    definitions[1]['relationships'] = [{'type': 'PI_OF', 'target_label': 'Person', 'direction': 'incoming'}]
    definitions[0]['properties'][0]['allowed_values'] = ['Synthetic Person']
    ontology = Ontology([], definitions)
    ontology.relationship('Person', 'PI_OF', 'Project')
    with pytest.raises(ContractError):
        ontology.relationship('Project', 'PI_OF', 'Person')
    with pytest.raises(ContractError):
        ontology.property('Person', 'name', 'Other')
