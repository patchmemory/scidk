"""Opt-in driver integration. Never infer disposability from localhost.

All four SCIDK_CURATION_TEST_NEO4J_* variables below and an explicit disposable
acknowledgement are required. The database name must start scidk_curation_test_.
Only this test's randomly named entities/markers are removed in cleanup.
"""
import os
import uuid

import pytest

from scidk.curation.contracts import ConflictError
from scidk.curation.materializer import Neo4jMaterializer


@pytest.mark.integration
def test_disposable_neo4j_transaction_and_marker_replay():
    names = ('URI', 'DATABASE', 'USERNAME', 'PASSWORD')
    config = {key: os.environ.get('SCIDK_CURATION_TEST_NEO4J_' + key) for key in names}
    if os.environ.get('SCIDK_CURATION_TEST_DISPOSABLE') != '1' or not all(config.values()):
        pytest.skip('Explicit disposable Neo4j configuration not supplied')
    if not config['DATABASE'].startswith('scidk_curation_test_'):
        pytest.fail('Disposable curation database must use scidk_curation_test_ prefix')
    from neo4j import GraphDatabase
    tag = uuid.uuid4().hex
    refs = ['entity:' + tag + ':person', 'entity:' + tag + ':project']
    driver = GraphDatabase.driver(config['URI'], auth=(config['USERNAME'], config['PASSWORD']))
    graph = Neo4jMaterializer(driver, database=config['DATABASE'], target=config['URI'] + '/' + config['DATABASE'])
    scope = {'namespace': 'synthetic-test', 'resource_id': tag}
    def op(name, kind, **claim):
        return {'operation_id': tag + ':' + name, 'operation_hash': tag + ':hash:' + name,
                'action': 'accept', 'obsolete': False, 'fact_id': 'fact:' + tag + ':' + name,
                'claim': {'target_kind': kind, 'source_scope': scope, **claim}}
    person = op('person', 'node', candidate={'label': 'Person'}, entity_ref=refs[0])
    project = op('project', 'node', candidate={'label': 'Project'}, entity_ref=refs[1])
    prop = op('name', 'property', target_ref=refs[0], property_key='name', proposed_value='Synthetic PI')
    edge = op('edge', 'relationship', subject_ref=refs[0], object_ref=refs[1], predicate='PI_OF', qualifiers={})
    missing = op('missing', 'relationship', subject_ref=refs[0], object_ref='entity:missing:' + tag, predicate='PI_OF', qualifiers={})
    ids = [item['operation_id'] for item in (person, project, prop, edge, missing)]
    try:
        with pytest.raises(ConflictError):
            graph.apply_batch([person, missing])
        with driver.session(database=config['DATABASE']) as session:
            assert session.run('MATCH (n:SciDKCuratedEntity {entity_ref:$ref}) RETURN count(n) AS count', ref=refs[0]).single()['count'] == 0
        graph.apply_batch([edge, prop, project, person])
        graph.apply_batch([person, project, prop, edge])
        with driver.session(database=config['DATABASE']) as session:
            row = session.run('MATCH (n:SciDKCuratedEntity {entity_ref:$ref}) RETURN n.name AS name, n.created_at AS created', ref=refs[0]).single()
            assert row['name'] == 'Synthetic PI' and row['created'] is not None
            assert session.run('MATCH ()-[r:PI_OF {fact_id:$fid}]->() RETURN count(r) AS count', fid=edge['fact_id']).single()['count'] == 1
            assert session.run('MATCH (o:SciDKCurationOperation) WHERE o.operation_id IN $ids RETURN count(o) AS count', ids=ids).single()['count'] == 4
    finally:
        with driver.session(database=config['DATABASE']) as session:
            session.run('MATCH (n:SciDKCuratedEntity) WHERE n.entity_ref IN $refs DETACH DELETE n', refs=refs).consume()
            session.run('MATCH (o:SciDKCurationOperation) WHERE o.operation_id IN $ids DELETE o', ids=ids).consume()
        driver.close()
