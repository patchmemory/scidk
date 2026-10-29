import copy
import json
from pathlib import Path
import sqlite3
import unicodedata

import pytest

from scidk.agent_tools.security import REFUSAL, BoundIdentity
from scidk.curation.contracts import ContractError
from scidk.curation.ledger import Ledger, migrate
from scidk.curation.ontology import Ontology
from scidk.knowledge.external import mondo_fixture, ExternalRegistry, propose_alignment
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.projection import Projection, ContextService, system_projection
from scidk.knowledge.system_manifest import ENTRIES
from tests.curation.test_foundation import foundation, SCOPE, catalog
from tests.security.test_disclosure import secured

ROOT = Path(__file__).resolve().parents[2]


def test_deterministic_system_and_csv_acceptance():
    a, b = system_projection(ROOT), system_projection(ROOT)
    assert a.snapshot() == b.snapshot() and a.version == b.version
    result = a.traverse('workflow:csv-import')
    ids = {n['id'] for n in result['nodes']}
    assert {'doc:intake', 'schema:mapping', 'code:intake', 'code:mapping',
            'permission:disclosure', 'code:disclosure'} <= ids
    assert {'DOCUMENTED_BY', 'IMPLEMENTED_BY', 'REQUIRES', 'VALIDATED_BY'} <= {e['type'] for e in result['edges']}
    for n in a.snapshot()['nodes']:
        assert n['sources'][0]['valid'] and n['sources'][0]['hash']
        assert n['git_revision'] and n['applicability'] and n['visibility'] == 'restricted'
    assert not a.freshness(ROOT, revision=a.snapshot()['nodes'][0]['git_revision'], applicability='knowledge-context/1')
    assert len([n for n in a.snapshot()['nodes'] if n['type'] == 'workflow']) == 8
    assert a.traverse('workflow:tool-discovery')['edges']


def mirror_manifest(tmp_path):
    for entry in ENTRIES:
        path = tmp_path / entry['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / entry['path']).read_bytes())


@pytest.mark.parametrize('change', ['hash', 'missing', 'symbol', 'section', 'revision', 'version'])
def test_stale_source_and_versions(tmp_path, change):
    mirror_manifest(tmp_path)
    a = system_projection(tmp_path, revision='r1')
    path = tmp_path / 'scidk/pipeline/mapping_engine.py'
    if change == 'hash':
        path.write_text(path.read_text() + '\n# drift\n')
    elif change == 'missing':
        path.unlink()
    elif change == 'symbol':
        path.write_text('class MappingEngineRenamed: pass\n')
    elif change == 'section':
        (tmp_path / 'plugins/sharepoint_intake/README.md').write_text('# Other\n')
    warnings = a.freshness(tmp_path, revision='r2' if change == 'revision' else 'r1',
                           applicability='v2' if change == 'version' else 'knowledge-context/1')
    assert warnings
    if change == 'hash':
        assert a.version != system_projection(tmp_path, revision='r1').version


def test_missing_paths_never_valid_and_symlink_escape(tmp_path):
    a = system_projection(tmp_path, revision='r1')
    assert all(not n['sources'][0]['valid'] for n in a.snapshot()['nodes'])
    (tmp_path / 'tools').symlink_to(ROOT / 'tools', target_is_directory=True)
    with pytest.raises(ContractError, match='inside repository'):
        system_projection(tmp_path, revision='r1')


@pytest.mark.parametrize('kwargs', [{'depth': -1}, {'depth': 7}, {'depth': True}, {'limit': 0}, {'limit': 257}, {'limit': 1}])
def test_bounded_traversal(kwargs):
    with pytest.raises(ContractError):
        system_projection(ROOT).traverse('workflow:csv-import', **kwargs)


def test_ontology_relationship_properties_and_directions():
    definitions = catalog()
    definitions[0]['properties'][0].update(key=True, allowed_values=['Synthetic'])
    definitions[0]['relationships'][0]['properties'] = [{'name': 'role', 'type': 'string'}]
    graph = ontology_projection([], definitions, revision='r1')
    result = graph.traverse('label:Person')
    rel = next(n for n in result['nodes'] if n['id'].startswith('relationship:'))
    assert rel['definition']['source_label'] == 'Person'
    assert rel['definition']['target_label'] == 'Project'
    assert rel['definition']['properties']['role']['type'] == 'string'
    person = next(n for n in result['nodes'] if n['id'] == 'label:Person')
    prop = person['definition']['properties']['name']
    assert prop['key'] and prop['allowed_values'] == ['Synthetic']
    assert result['metadata']['ontology_version'] == Ontology([], definitions).version
    assert all(s['hash'] for n in result['nodes'] for s in n['sources'])
    Ontology([], definitions).relationship('Person', 'PI_OF', 'Project')
    with pytest.raises(ContractError):
        Ontology([], definitions).relationship('Project', 'PI_OF', 'Person')


@pytest.mark.parametrize('problem', ['catalog', 'missing_endpoint', 'endpoint_properties', 'matching_key'])
def test_ontology_blockers(tmp_path, problem):
    definitions, paths = catalog(), []
    if problem == 'catalog':
        path = tmp_path / 'person.yaml'
        path.write_text('id: person\nname: Person\nproperties:\n  name:\n    type: integer\n')
        paths = [path]
    elif problem == 'missing_endpoint':
        definitions.pop()
    elif problem == 'matching_key':
        definitions[0]['matching_key'] = 'undeclared'
    else:
        definitions[1]['relationships'] = [{'type': 'PI_OF', 'to_label': 'Person', 'direction': 'incoming',
                                            'properties': [{'name': 'role', 'type': 'string'}]}]
    graph = ontology_projection(paths, definitions, revision='r1')
    snapshot = graph.snapshot()
    assert snapshot['metadata']['blockers']
    assert not any(n['id'].startswith('label:') for n in snapshot['nodes'])
    assert not next(n for n in snapshot['nodes'] if n['id'] == 'ontology:catalog')['authoritative']
    with pytest.raises(ContractError):
        graph.traverse('label:Person')


@pytest.mark.parametrize('identifier', ['MONDO:0004992', 'mondo:0004992', 'MONDO_0004992',
                                      'http://purl.obolibrary.org/obo/MONDO_0004992'])
def test_mondo_normalization(identifier):
    registry = mondo_fixture()
    assert registry.normalize('MONDO', identifier) == 'MONDO:0004992'
    assert registry.resolve('MONDO', identifier)['concept']['label'] == 'cancer'


@pytest.mark.parametrize('identifier', ['https://evil.example/MONDO_0004992', 'MONDO:4992', 'MONDO:0004992?x=1', '../MONDO:0004992'])
def test_no_arbitrary_identifiers_or_urls(identifier):
    with pytest.raises(ContractError):
        mondo_fixture().normalize('MONDO', identifier)


def test_registration_pinning_nonontology_and_no_bulk_fetch():
    record = mondo_fixture().resolve('MONDO', 'cancer')
    registration, concept = record['registration'], record['concept']
    registry = ExternalRegistry()
    registration['resource_kind'] = 'literature'
    registration['metadata'] = {'format': 'future-specific-adapter'}
    registry.register(registration, [concept])
    with pytest.raises(ContractError, match='pinned'):
        registry.register(registration, [concept])
    registration['resolver']['mode'] = 'http'
    with pytest.raises(ContractError, match='offline'):
        ExternalRegistry().register(registration, [concept])
    with pytest.raises(ContractError, match='unambiguous'):
        registry.resolve('MONDO', 'unknown disease')
    registration['resolver']['mode'] = 'offline'
    concept['version'] = 'unversioned'
    with pytest.raises(ContractError, match='mismatch'):
        ExternalRegistry().register(registration, [concept])


@pytest.mark.parametrize('raw,extra_synonym', [('  Malignant Neoplasm  ', None), ('  Cance\u0301r  ', 'cancér')])
def test_work_order_alignment_is_fixture_only_proposed_inferred(foundation, tmp_path, raw, extra_synonym):
    _, evidence, _ = foundation
    # User-approved isolated synthetic catalog. Never a bundled operational label.
    ontology = Ontology([], [{'name': 'SyntheticWorkOrder', 'properties': [
        {'name': 'disease_alignments', 'type': 'list',
         'description': 'Fixture-only structured raw-value/MONDO candidate alignments'}]}])
    path = tmp_path / 'alignment.sqlite'
    migrate(path)
    ledger = Ledger(path, ontology, lambda actor, ev: actor == 'human')
    eid = ledger.add_evidence(evidence)
    node = dict(domain='research', target_kind='node', ontology_version=ontology.version,
                epistemic_status='observed', method='synthetic-work-order', visibility='restricted',
                source_scope=SCOPE, evidence_refs=[eid], candidate=dict(label='SyntheticWorkOrder',
                source_scope=SCOPE, source_identifier={'record_id': 'wo:1', 'role': 'work-order'},
                identity_claims={}))
    ref = ledger.get_internal(ledger.submit(node, actor='human', caller_key='wo'))['claim']['entity_ref']
    registry = mondo_fixture()
    if extra_synonym:
        record = registry.resolve('MONDO', 'cancer')
        record['concept']['synonyms'].append(extra_synonym)
        registry = ExternalRegistry()
        registry.register(record['registration'], [record['concept']])
    aid = propose_alignment(ledger, target_ref=ref, property_key='disease_alignments', raw_value=raw,
                            source_scope=SCOPE, registry=registry, namespace='MONDO',
                            actor='human', caller_key='alignment', intake_evidence=evidence)
    result = ledger.get_internal(aid)
    assert result['curation_status'] == 'proposed' and result['claim']['epistemic_status'] == 'inferred'
    payload = result['claim']['proposed_value'][0]
    assert payload['original_value'] == unicodedata.normalize('NFC', raw)
    assert bytes.fromhex(payload['original_utf8_hex']).decode('utf-8') == raw
    assert payload['match_semantics'] == 'related'
    assert payload['concept']['accession'] == 'MONDO:0004992'
    assert payload['registration']['metadata']['upstream_release_verified'] is False
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM outbox').fetchone()[0] == 0
    assert ledger.get_internal(aid)['claim']['evidence_refs']


def authorized_system(s):
    graph = system_projection(ROOT, {e['id']: SCOPE for e in ENTRIES})
    for n in graph.snapshot()['nodes']:
        s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
    return graph, ContextService(graph, s.db, enabled=True)


def test_context_disclosure_requires_policy_and_explicit_metadata_grants(secured):
    s = secured
    graph = system_projection(ROOT, {e['id']: SCOPE for e in ENTRIES})
    assert ContextService(graph, s.db).read('workflow:csv-import', s.identity) == REFUSAL
    assert ContextService(graph, s.db, enabled=True).read('workflow:csv-import', s.identity) == REFUSAL
    graph, service = authorized_system(s)
    result = service.read('workflow:csv-import', s.identity)
    assert result['status'] == 'success'
    assert 'mapping_schema.json' in json.dumps(result)
    s.store.grant_resource(s.alice, 'synthetic', 'resource-1', admin_id=s.admin, allow=False)
    assert service.read('workflow:csv-import', s.identity) == REFUSAL


@pytest.mark.parametrize('denial', ['provenance', 'source_provenance', 'policy', 'identity', 'destination', 'property', 'high', 'unknown', 'nested_source'])
def test_context_fail_closed(secured, denial):
    s = secured
    graph, service = authorized_system(s)
    start, identity = 'workflow:csv-import', s.identity
    if denial in {'provenance', 'source_provenance', 'nested_source'}:
        snapshot = graph.snapshot()
        node = next(n for n in snapshot['nodes'] if n['id'] == start)
        if denial == 'provenance':
            node['source_scope'] = None
        else:
            node['sources'][0]['source_scope'] = None if denial == 'source_provenance' else dict(SCOPE, resource_id='secret')
        graph = Projection(snapshot['nodes'], snapshot['edges'])
        for n in graph.snapshot()['nodes']:
            s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
        service = ContextService(graph, s.db, enabled=True)
    elif denial == 'policy':
        service = ContextService(graph, None, enabled=True)
    elif denial == 'identity':
        identity = BoundIdentity(s.bob, 'http', s.token['id'])
    elif denial == 'destination':
        s.store.revoke_destination('parley', admin_id=s.admin)
    elif denial == 'property':
        with sqlite3.connect(s.db) as conn:
            conn.execute("INSERT INTO agent_sharing VALUES ('KnowledgeContext','sources','redact',NULL,NULL)")
    elif denial == 'high':
        s.store.classify('synthetic', 'resource-1', 'high', admin_id=s.admin)
    else:
        start = 'secret:does-not-exist'
    assert service.read(start, identity) == REFUSAL


def test_public_external_registry_still_requires_source_policy(secured):
    s = secured
    graph = mondo_fixture().projection('MONDO', source_scope=SCOPE, revision='r1')
    service = ContextService(graph, s.db, enabled=True)
    assert service.read('external:MONDO', s.identity)['status'] == 'success'
    s.store.grant_resource(s.alice, 'synthetic', 'resource-1', admin_id=s.admin, allow=False)
    assert service.read('external:MONDO', s.identity) == REFUSAL


def test_ontology_context_requires_every_source_even_depth_zero(secured):
    s = secured
    bindings = {'catalog': SCOPE, 'sqlite:Person': SCOPE, 'sqlite:Project': dict(SCOPE, resource_id='secret')}
    graph = ontology_projection([], catalog(), bindings=bindings, revision='r1')
    for n in graph.snapshot()['nodes']:
        s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
    service = ContextService(graph, s.db, enabled=True)
    assert service.read('label:Person', s.identity, depth=0) == REFUSAL
    bindings['sqlite:Project'] = SCOPE
    graph = ontology_projection([], catalog(), bindings=bindings, revision='r1')
    for n in graph.snapshot()['nodes']:
        s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
    service = ContextService(graph, s.db, enabled=True)
    assert service.read('label:Person', s.identity)['status'] == 'success'
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO agent_sharing VALUES ('Person','name','hash',NULL,NULL)")
    assert service.read('label:Person', s.identity) == REFUSAL


def test_missing_and_malformed_ontology_sources_block(tmp_path):
    path = tmp_path / 'broken.yaml'
    for value in (None, 'properties: [broken'):
        if value:
            path.write_text(value)
        graph = ontology_projection([path], [], revision='r1')
        assert graph.snapshot()['metadata']['blockers']
        assert not any(n['id'].startswith('label:') for n in graph.snapshot()['nodes'])


def test_snapshot_freshness_for_catalogs():
    a = ontology_projection([], catalog(), revision='r1')
    assert not a.compare(ontology_projection([], catalog(), revision='r1'))
    changed = catalog()
    changed[0]['properties'][0]['description'] = 'changed definition'
    b = ontology_projection([], changed, revision='r1')
    assert a.compare(b) and a.version != b.version


def test_distinct_source_identifier_semantics():
    registry = ExternalRegistry()
    registration = dict(namespace='PubMed', resource_kind='literature',
                        source_uri='https://pubmed.ncbi.nlm.nih.gov/', version='offline-demo/1',
                        identifier_format='[0-9]+', resolver=dict(mode='offline', identifier_style='identity',
                        uri_prefix='https://pubmed.ncbi.nlm.nih.gov/'), retrieved_at='2026-10-29T00:00:00Z',
                        citation='Synthetic literature fixture', visibility='restricted')
    concept = dict(accession='123', uri='https://pubmed.ncbi.nlm.nih.gov/123', label='Synthetic title',
                   synonyms=[], namespace='PubMed', version='offline-demo/1', citation='Fixture',
                   provenance={'method': 'fixture'})
    registry.register(registration, [concept])
    assert registry.normalize('PubMed', concept['uri']) == '123'
    assert registry.resolve('PubMed', '123')['registration']['resource_kind'] == 'literature'


def test_relationship_property_modes_apply_inside_label_definition(secured):
    s = secured
    definitions = catalog()
    definitions[0]['relationships'][0]['properties'] = [{'name': 'role', 'type': 'string'}]
    bindings = {key: SCOPE for key in ['catalog', 'sqlite:Person', 'sqlite:Project']}
    graph = ontology_projection([], definitions, bindings=bindings, revision='r1')
    for n in graph.snapshot()['nodes']:
        s.store.grant_evidence(s.alice, ContextService.grant_id(n), admin_id=s.admin)
    service = ContextService(graph, s.db, enabled=True)
    assert service.read('label:Person', s.identity, depth=0)['status'] == 'success'
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO agent_sharing VALUES ('PI_OF','role','redact',NULL,NULL)")
    assert service.read('label:Person', s.identity, depth=0) == REFUSAL
