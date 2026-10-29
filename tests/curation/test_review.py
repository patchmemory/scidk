import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from scidk.curation.contracts import ConflictError, ContractError
from scidk.curation.review import AuthorizationError, ReviewService
from .test_foundation import foundation, node, property_body, submit_node


class FakeGraph:
    """Transactional graph semantics, including persistent operation markers."""
    target = 'disposable-fixture/neo4j'

    def __init__(self):
        self.nodes, self.edges, self.markers = {}, {}, {}
        self.fail = False
        self.commits = 0

    def apply_batch(self, operations):
        nodes, edges, markers = copy.deepcopy((self.nodes, self.edges, self.markers))
        outcomes = {}
        ordered = sorted(operations, key=lambda op: {'node': 0, 'relationship': 1, 'property': 2}[op['claim']['target_kind']])
        for op in ordered:
            oid = op['operation_id']
            if oid in markers:
                assert markers[oid][0] == op['operation_hash']
                outcomes[oid] = markers[oid][1]
                continue
            body = op['claim']
            if not op['obsolete'] and op['action'] == 'accept':
                kind = body['target_kind']
                if kind == 'node':
                    nodes.setdefault(body['entity_ref'], {'fact_id': op['fact_id'], 'source_scope': body['source_scope']})
                elif kind == 'relationship':
                    if body['subject_ref'] not in nodes or body['object_ref'] not in nodes:
                        raise ConflictError('Missing endpoints')
                    edges.setdefault(op['fact_id'], {'subject': body['subject_ref'], 'object': body['object_ref']})
                else:
                    target = nodes.get(body['target_ref'], edges.get(body['target_ref']))
                    if target is None:
                        raise ConflictError('Missing property target')
                    key, value = body['property_key'], body['proposed_value']
                    if key in target and target[key] != value and target[key] not in op.get('replaceable_values', []):
                        raise ConflictError('Existing graph conflict')
                    target[key] = value
            outcome = 'obsolete' if op['obsolete'] else 'applied'
            markers[oid] = (op['operation_hash'], outcome)
            outcomes[oid] = outcome
            if self.fail:
                raise RuntimeError('Injected transaction failure')
        self.nodes, self.edges, self.markers = nodes, edges, markers
        self.commits += 1
        return outcomes


@pytest.fixture
def review_service(foundation):
    ledger, _, eid = foundation
    service = ReviewService(ledger, lambda reviewer: reviewer == 'human')
    return ledger, eid, service, FakeGraph()


def decision(service, aid, action='accept', **extra):
    preview = service.preview(aid, reviewer='human')
    body = {'action': action, 'expected_revision': preview['expected_revision'],
            'preview_digest': preview['preview_digest'], 'rationale': 'Reviewed synthetic fixture', **extra}
    return service.review(aid, body, reviewer='human')


def test_review_and_materialization_separate_node_properties(review_service):
    ledger, eid, service, graph = review_service
    person = submit_node(ledger, eid)
    accepted = decision(service, person['assertion_id'])
    assert ledger.get_internal(person['assertion_id'])['curation_status'] == 'accepted'
    assert graph.nodes == {}
    service.materialize([accepted['operation_id']], reviewer='human', graph=graph)
    ref = person['claim']['entity_ref']
    assert 'name' not in graph.nodes[ref]
    graph.nodes[ref]['legacy_provenance'] = 'keep me'
    body = property_body(ledger, eid)
    aid = ledger.submit(body, actor='human', caller_key='name')
    prop = decision(service, aid)
    service.materialize([prop['operation_id']], reviewer='human', graph=graph)
    assert graph.nodes[ref]['name'] == body['proposed_value']
    assert graph.nodes[ref]['legacy_provenance'] == 'keep me'
    assert ledger.get_internal(aid)['claim']['epistemic_status'] == 'inferred'
    assert service.materialize([prop['operation_id']], reviewer='human', graph=graph)[0]['outcome'] == 'applied'
    assert len(graph.nodes) == 1


def test_authorization_rationale_and_revision(review_service):
    ledger, eid, service, graph = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    for reviewer in (None, '', 'agent', 'ordinary-user'):
        with pytest.raises(AuthorizationError):
            service.preview(aid, reviewer=reviewer)
        with pytest.raises(AuthorizationError):
            service.review(aid, {}, reviewer=reviewer)
        with pytest.raises(AuthorizationError):
            service.materialize(['unknown'], reviewer=reviewer, graph=graph)
    preview = service.preview(aid, reviewer='human')
    body = dict(action='accept', expected_revision=0, preview_digest=preview['preview_digest'], rationale=' ')
    with pytest.raises(ContractError):
        service.review(aid, body, reviewer='human')
    body['rationale'] = 'Review'
    body['preview_digest'] = 'stale'
    with pytest.raises(ConflictError):
        service.review(aid, body, reviewer='human')
    body['preview_digest'] = preview['preview_digest']
    service.review(aid, body, reviewer='human')
    with pytest.raises(ConflictError):
        service.review(aid, body, reviewer='human')
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM outbox').fetchone()[0] == 1


def test_concurrent_review_single_winner(review_service):
    ledger, eid, service, _ = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    preview = service.preview(aid, reviewer='human')
    body = dict(action='accept', expected_revision=0, preview_digest=preview['preview_digest'], rationale='Review')
    def run(_):
        try:
            return service.review(aid, body, reviewer='human')['decision_id']
        except ConflictError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len([result for result in pool.map(run, range(8)) if result]) == 1


def test_preview_invalidates_when_fact_support_changes(review_service):
    ledger, eid, service, _ = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    preview = service.preview(aid, reviewer='human')
    ledger.submit(node(ledger, eid), actor='human', caller_key='another-observation')
    with pytest.raises(ConflictError):
        service.review(aid, dict(action='accept', expected_revision=0,
                       preview_digest=preview['preview_digest'], rationale='Review'), reviewer='human')


def edge_proposal(ledger, eid, person, project):
    body = node(ledger, eid)
    del body['candidate']
    body.update(target_kind='relationship', subject_ref=person['claim']['entity_ref'],
                predicate='PI_OF', object_ref=project['claim']['entity_ref'], qualifiers={})
    return ledger.submit(body, actor='human', caller_key='edge')


def test_relationship_requires_accepted_materialized_endpoints(review_service):
    ledger, eid, service, graph = review_service
    person, project = submit_node(ledger, eid), submit_node(ledger, eid, 'Project')
    edge_id = edge_proposal(ledger, eid, person, project)
    edge = decision(service, edge_id)
    with pytest.raises(ConflictError, match='dependency'):
        service.materialize([edge['operation_id']], reviewer='human', graph=graph)
    people = decision(service, person['assertion_id'])
    projects = decision(service, project['assertion_id'])
    # Reverse topology input still executes in dependency order in one transaction.
    service.materialize([edge['operation_id'], projects['operation_id'], people['operation_id']], reviewer='human', graph=graph)
    assert len(graph.edges) == 1
    graph.nodes.pop(person['claim']['entity_ref'])
    second = ledger.submit(dict(ledger.get_internal(edge_id)['claim'], qualifiers={'role': 'another'}),
                           actor='human', caller_key='edge2')
    op = decision(service, second)
    with pytest.raises(ConflictError, match='Missing endpoints'):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert len(graph.edges) == 1


def test_conflicting_properties_and_nondestructive_supersession(review_service):
    ledger, eid, service, graph = review_service
    person = submit_node(ledger, eid)
    p = decision(service, person['assertion_id'])
    service.materialize([p['operation_id']], reviewer='human', graph=graph)
    body = property_body(ledger, eid)
    first = ledger.submit(body, actor='human', caller_key='first-name')
    first_op = decision(service, first)
    service.materialize([first_op['operation_id']], reviewer='human', graph=graph)
    # Independent supporting assertion survives supersession of one assertion.
    support = ledger.submit(body, actor='human', caller_key='support')
    support_op = decision(service, support)
    service.materialize([support_op['operation_id']], reviewer='human', graph=graph)
    body['proposed_value'] = 'Corrected name'
    replacement = ledger.submit(body, actor='human', caller_key='replacement')
    with pytest.raises(ConflictError):
        decision(service, replacement)
    supersede = decision(service, first, 'supersede', superseded_by=replacement)
    service.materialize([supersede['operation_id']], reviewer='human', graph=graph)
    assert graph.nodes[person['claim']['entity_ref']]['name'] == 'New synthetic name'
    with pytest.raises(ConflictError):
        decision(service, replacement)
    decision(service, support, 'supersede', superseded_by=replacement)
    correction = decision(service, replacement)
    service.materialize([correction['operation_id']], reviewer='human', graph=graph)
    assert graph.nodes[person['claim']['entity_ref']]['name'] == 'Corrected name'
    assert ledger.get_internal(first)['curation_status'] == 'superseded'


def test_graph_conflict_never_silently_overwritten(review_service):
    ledger, eid, service, graph = review_service
    person = submit_node(ledger, eid)
    op = decision(service, person['assertion_id'])
    service.materialize([op['operation_id']], reviewer='human', graph=graph)
    graph.nodes[person['claim']['entity_ref']]['name'] = 'Legacy protected name'
    aid = ledger.submit(property_body(ledger, eid), actor='human', caller_key='property')
    op = decision(service, aid)
    with pytest.raises(ConflictError):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert graph.nodes[person['claim']['entity_ref']]['name'] == 'Legacy protected name'


def test_atomic_batch_rollback_and_retry(review_service):
    ledger, eid, service, graph = review_service
    first, second = submit_node(ledger, eid), submit_node(ledger, eid, 'Project')
    ops = [decision(service, state['assertion_id'])['operation_id'] for state in (first, second)]
    graph.fail = True
    with pytest.raises(RuntimeError):
        service.materialize(ops, reviewer='human', graph=graph)
    assert not graph.nodes and not graph.markers
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
    graph.fail = False
    service.materialize(ops, reviewer='human', graph=graph)
    assert len(graph.nodes) == 2


def test_crash_after_graph_commit_and_reconciliation(review_service):
    ledger, eid, service, graph = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    op = decision(service, aid)
    def crash():
        raise RuntimeError('Crash after graph commit')
    with pytest.raises(RuntimeError):
        service.materialize([op['operation_id']], reviewer='human', graph=graph, after_graph_commit=crash)
    assert len(graph.nodes) == len(graph.markers) == 1
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
    result = service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert result[0]['outcome'] == 'applied'
    assert len(graph.nodes) == len(graph.markers) == 1
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 1
        for table in ('receipts', 'outbox'):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f'DELETE FROM {table}')


def test_revoked_evidence_and_reviewer_block_application(review_service):
    ledger, eid, service, graph = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    op = decision(service, aid)
    ledger.can_read_evidence = lambda *args: False
    with pytest.raises(ContractError):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    ledger.can_read_evidence = lambda *args: True
    service.authorize_reviewer = lambda *args: False
    with pytest.raises(AuthorizationError):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert not graph.nodes


def test_rejection_and_stale_outbox_never_apply_facts(review_service):
    ledger, eid, service, graph = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    rejected = decision(service, aid, 'reject')
    service.materialize([rejected['operation_id']], reviewer='human', graph=graph)
    assert not graph.nodes
    new = ledger.submit(node(ledger, eid), actor='human', caller_key='new')
    replacement = ledger.submit(node(ledger, eid), actor='human', caller_key='replacement')
    accepted = decision(service, new)
    decision(service, new, 'supersede', superseded_by=replacement)
    result = service.materialize([accepted['operation_id']], reviewer='human', graph=graph)
    assert result[0]['outcome'] == 'obsolete'
    assert not graph.nodes


def test_crash_then_supersession_reconciles_original_applied_outcome(review_service):
    ledger, eid, service, graph = review_service
    person = submit_node(ledger, eid)
    op = decision(service, person['assertion_id'])
    service.materialize([op['operation_id']], reviewer='human', graph=graph)
    body = property_body(ledger, eid)
    aid = ledger.submit(body, actor='human', caller_key='first-property')
    original = decision(service, aid)
    def crash():
        raise RuntimeError('after commit')
    with pytest.raises(RuntimeError):
        service.materialize([original['operation_id']], reviewer='human', graph=graph, after_graph_commit=crash)
    body['proposed_value'] = 'Replacement after crash'
    replacement = ledger.submit(body, actor='human', caller_key='new-property')
    decision(service, aid, 'supersede', superseded_by=replacement)
    assert service.materialize([original['operation_id']], reviewer='human', graph=graph)[0]['outcome'] == 'applied'
    corrected = decision(service, replacement)
    service.materialize([corrected['operation_id']], reviewer='human', graph=graph)
    assert graph.nodes[person['claim']['entity_ref']]['name'] == 'Replacement after crash'


def test_graph_target_cannot_change_after_receipt(review_service):
    ledger, eid, service, graph = review_service
    op = decision(service, submit_node(ledger, eid)['assertion_id'])
    service.materialize([op['operation_id']], reviewer='human', graph=graph)
    graph.target = 'another-graph'
    with pytest.raises(ConflictError, match='another graph'):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)


def test_changed_ontology_blocks_application(review_service):
    from scidk.curation.ontology import Ontology
    from .test_foundation import catalog
    ledger, eid, service, graph = review_service
    op = decision(service, submit_node(ledger, eid)['assertion_id'])
    definitions = catalog()
    definitions[0]['properties'].append({'name': 'another', 'type': 'string'})
    ledger.ontology = Ontology([], definitions)
    with pytest.raises(ConflictError, match='version'):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert not graph.nodes


def test_protected_property_fails_closed_before_graph_write(review_service):
    from scidk.curation.ontology import Ontology
    from .test_foundation import catalog
    ledger, eid, service, graph = review_service
    definitions = catalog()
    definitions[0]['properties'][0]['sanitize'] = 'redact'
    ledger.ontology = Ontology([], definitions)
    person = submit_node(ledger, eid)
    op = decision(service, person['assertion_id'])
    service.materialize([op['operation_id']], reviewer='human', graph=graph)
    prop = ledger.submit(property_body(ledger, eid), actor='human', caller_key='protected-property')
    op = decision(service, prop)
    with pytest.raises(ConflictError, match='sanitization'):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert 'name' not in graph.nodes[person['claim']['entity_ref']]


def test_decision_and_outbox_commit_atomically(review_service):
    ledger, eid, service, _ = review_service
    aid = submit_node(ledger, eid)['assertion_id']
    with sqlite3.connect(ledger.path) as conn:
        conn.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox "
                     "BEGIN SELECT RAISE(ABORT, 'fixture outbox failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        decision(service, aid)
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM decisions').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM outbox').fetchone()[0] == 0
    assert ledger.get_internal(aid)['curation_status'] == 'proposed'


def test_concurrent_materialization_serializes_receipts(review_service):
    ledger, eid, service, graph = review_service
    op = decision(service, submit_node(ledger, eid)['assertion_id'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.materialize([op['operation_id']], reviewer='human', graph=graph), range(8)))
    assert all(result[0]['outcome'] == 'applied' for result in results)
    assert len(graph.nodes) == len(graph.markers) == graph.commits == 1


def test_first_commit_crash_still_pins_graph_target(review_service):
    ledger, eid, service, graph = review_service
    op = decision(service, submit_node(ledger, eid)['assertion_id'])
    def crash():
        raise RuntimeError('after first graph commit')
    with pytest.raises(RuntimeError):
        service.materialize([op['operation_id']], reviewer='human', graph=graph, after_graph_commit=crash)
    with sqlite3.connect(ledger.path) as conn:
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
        assert conn.execute('SELECT graph_target FROM graph_binding').fetchone()[0] == graph.target
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            conn.execute('DELETE FROM graph_binding')
    graph.target = 'other-graph'
    with pytest.raises(ConflictError, match='another graph'):
        service.materialize([op['operation_id']], reviewer='human', graph=graph)
    assert len(graph.nodes) == graph.commits == 1
