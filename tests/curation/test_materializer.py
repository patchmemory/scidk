"""Driver-boundary tests: exercise production adapter, not the semantic FakeGraph."""
from contextlib import contextmanager

import pytest

from scidk.curation.contracts import ConflictError
from scidk.curation.materializer import Neo4jMaterializer


class Driver:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.queries = []
        self.committed = False
        self.transactions = 0

    @contextmanager
    def session(self, *, database):
        assert database == 'disposable'
        yield self

    def execute_write(self, function, operations):
        self.transactions += 1
        result = function(self, operations)
        self.committed = True
        return result

    def run(self, query, **params):
        self.queries.append((query, params))
        return next(self.responses)


def operation(kind, **claim):
    return {'operation_id': 'op-' + kind, 'operation_hash': 'hash-' + kind,
            'action': 'accept', 'fact_id': 'fact:' + kind, 'obsolete': False,
            'claim': {'target_kind': kind, 'source_scope': {'namespace': 'fixture', 'resource_id': 'r1'}, **claim}}


def test_single_transaction_for_nodes_relationship_and_individual_property():
    node = operation('node', candidate={'label': 'Person'}, entity_ref='entity:p')
    edge = operation('relationship', predicate='PI_OF', subject_ref='entity:p', object_ref='entity:project', qualifiers={})
    prop = operation('property', property_key='name', target_ref='entity:p', proposed_value='Reviewed name')
    driver = Driver([[], [{'valid': True, 'fact_id': 'fact:node'}], [{'id': 'op-node'}],
                     [], [{'fact_id': 'fact:relationship'}], [{'id': 'op-relationship'}],
                     [], [{'value': None}], [{'ref': 'entity:p'}], [{'id': 'op-property'}]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    outcomes = adapter.apply_batch([prop, edge, node])
    assert outcomes == {'op-node': 'applied', 'op-relationship': 'applied', 'op-property': 'applied'}
    assert driver.transactions == 1 and driver.committed
    queries = [query for query, _ in driver.queries]
    assert any('ON CREATE SET n:Person' in query for query in queries)
    assert any('MERGE (s)-[r:PI_OF {fact_id:$fact_id}]->(t)' in query for query in queries)
    assert any('SET n.`name`=$value' in query for query in queries)
    assert any('SET n.`name`=n.`name` RETURN' in query for query in queries)
    assert not any('SET n =' in query or 'DELETE' in query for query in queries)
    assert not any('identity_claims' in str(params) for _, params in driver.queries)


def test_missing_endpoint_aborts_transaction_and_marker():
    driver = Driver([[], []])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    edge = operation('relationship', predicate='PI_OF', subject_ref='entity:p', object_ref='entity:missing', qualifiers={})
    with pytest.raises(ConflictError, match='missing'):
        adapter.apply_batch([edge])
    assert not driver.committed
    assert not any('CREATE (o:' in query for query, _ in driver.queries)


def test_property_conflict_aborts_and_preserves_value():
    driver = Driver([[], [{'value': 'Legacy name'}]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    prop = operation('property', property_key='name', target_ref='entity:p', proposed_value='New')
    with pytest.raises(ConflictError, match='conflicts'):
        adapter.apply_batch([prop])
    assert not driver.committed
    assert not any('=$value' in query for query, _ in driver.queries)


def test_known_superseded_value_can_be_replaced():
    driver = Driver([[], [{'value': 'Old reviewed'}], [{'ref': 'entity:p'}], [{'id': 'op-property'}]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    prop = operation('property', property_key='name', target_ref='entity:p', proposed_value='New reviewed')
    prop['replaceable_values'] = ['Old reviewed']
    adapter.apply_batch([prop])
    assert driver.committed


def test_crash_replay_uses_marker_instead_of_rewriting_fact():
    driver = Driver([[{'hash': 'hash-node', 'outcome': 'applied'}]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    node = operation('node', candidate={'label': 'Person'}, entity_ref='entity:p')
    # A previously committed operation remains applied even after supersession.
    node['obsolete'] = True
    assert adapter.apply_batch([node]) == {'op-node': 'applied'}
    assert len(driver.queries) == 1


def test_marker_hash_mismatch_aborts():
    driver = Driver([[{'hash': 'different', 'outcome': 'applied'}]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    with pytest.raises(ConflictError, match='marker mismatch'):
        adapter.apply_batch([operation('node', candidate={'label': 'Person'}, entity_ref='entity:p')])
    assert not driver.committed


@pytest.mark.parametrize('key', ['fact_id', 'source_scope', 'created_at', 'entity_ref', 'curation_status'])
def test_reserved_provenance_cannot_be_overwritten(key):
    driver = Driver([[]])
    adapter = Neo4jMaterializer(driver, database='disposable', target='fixture/disposable')
    prop = operation('property', property_key=key, target_ref='entity:p', proposed_value='spoof')
    with pytest.raises(ConflictError, match='provenance'):
        adapter.apply_batch([prop])
    assert not driver.committed
