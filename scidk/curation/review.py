"""Human-authorized review, optimistic previews and serialized materialization.

The injected authorizer must resolve current existing-user grants on every call.
These are trusted application services, never registered agent tools.
"""
import json
import uuid

from .contracts import ConflictError, ContractError, canonical, digest, fields, text
from .ledger import now


class AuthorizationError(ContractError):
    pass


class ReviewService:
    def __init__(self, ledger, authorize_reviewer):
        self.ledger = ledger
        self.authorize_reviewer = authorize_reviewer

    def authorize(self, reviewer):
        if not reviewer or not self.authorize_reviewer(reviewer):
            raise AuthorizationError('Named authorized human reviewer required')

    @staticmethod
    def state(conn, assertion_id):
        row = conn.execute('SELECT fact_id, body FROM assertions WHERE assertion_id=?', (assertion_id,)).fetchone()
        if row is None:
            raise ContractError('Assertion unavailable')
        decision = conn.execute('SELECT revision, action FROM decisions WHERE assertion_id=? ORDER BY revision DESC LIMIT 1',
                                (assertion_id,)).fetchone()
        return {'assertion_id': assertion_id, 'fact_id': row[0], 'claim': json.loads(row[1]),
                'revision': decision[0] if decision else 0,
                'action': decision[1] if decision else 'propose'}

    def validate(self, conn, state, reviewer):
        body = dict(state['claim'])
        body.pop('entity_ref', None)
        self.ledger._validate(conn, body, reviewer)

    def fact_states(self, conn, fact_id):
        return [self.state(conn, row[0]) for row in conn.execute(
            'SELECT assertion_id FROM assertions WHERE fact_id=? ORDER BY assertion_id', (fact_id,))]

    def dependencies(self, conn, state):
        claim = state['claim']
        if claim['target_kind'] == 'node':
            return []
        refs = [claim['target_ref']] if claim['target_kind'] == 'property' else [claim['subject_ref'], claim['object_ref']]
        result = []
        for ref in refs:
            rows = conn.execute("SELECT assertion_id FROM assertions WHERE fact_id=? OR "
                                "(json_extract(body, '$.entity_ref')=? AND json_extract(body, '$.domain')=?) ORDER BY assertion_id",
                                (ref, ref, claim['domain'])).fetchall()
            candidates = [self.state(conn, row[0]) for row in rows]
            result.append({'ref': ref, 'states': [{'assertion_id': s['assertion_id'], 'revision': s['revision'],
                                                  'action': s['action']} for s in candidates]})
        return result

    def _preview(self, conn, assertion_id, reviewer):
        state = self.state(conn, assertion_id)
        self.validate(conn, state, reviewer)
        others = self.fact_states(conn, state['fact_id'])
        # Do not disclose hidden conflict IDs, even to a reviewer of another source.
        for other in others:
            self.validate(conn, other, reviewer)
        dependencies = self.dependencies(conn, state)
        for dependency in dependencies:
            for item in dependency['states']:
                self.validate(conn, self.state(conn, item['assertion_id']), reviewer)
        conflicts = [s['assertion_id'] for s in others
                     if s['assertion_id'] != assertion_id and s['action'] == 'accept'
                     and state['claim']['target_kind'] == 'property'
                     and s['claim']['proposed_value'] != state['claim']['proposed_value']]
        snapshot = {'assertion_id': assertion_id, 'fact_id': state['fact_id'],
                    'expected_revision': state['revision'], 'claim': state['claim'],
                    'ontology_revision': self.ledger.ontology.version,
                    'source_hashes': self.ledger.ontology.snapshot()['sources'],
                    'evidence_hashes': [{'evidence_id': ref, 'content_hash': json.loads(conn.execute(
                        'SELECT body FROM evidence WHERE evidence_id=?', (ref,)).fetchone()[0])['content_hash']}
                        for ref in state['claim']['evidence_refs']],
                    'dependencies': dependencies, 'conflict_ids': conflicts,
                    'support': [{'assertion_id': s['assertion_id'], 'revision': s['revision'], 'action': s['action']} for s in others],
                    'validation_errors': [], 'diff': {'target_kind': state['claim']['target_kind'],
                                                     'proposed': state['claim']}}
        snapshot['preview_digest'] = digest('preview', snapshot)
        return snapshot

    def preview(self, assertion_id, *, reviewer):
        self.authorize(reviewer)
        with self.ledger._connection() as conn:
            conn.execute('BEGIN')
            return self._preview(conn, assertion_id, reviewer)

    def review(self, assertion_id, body, *, reviewer):
        self.authorize(reviewer)
        fields(body, ('action', 'expected_revision', 'preview_digest', 'rationale'), ('superseded_by',))
        text(body['rationale'])
        text(body['preview_digest'])
        if type(body['expected_revision']) is not int or body['expected_revision'] < 0:
            raise ContractError('Invalid expected revision')
        if body['action'] not in {'accept', 'reject', 'supersede'}:
            raise ContractError('Invalid review action')
        with self.ledger._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = self.state(conn, assertion_id)
            preview = self._preview(conn, assertion_id, reviewer)
            if current['revision'] != body['expected_revision'] or preview['preview_digest'] != body['preview_digest']:
                raise ConflictError('Stale review revision or preview')
            if body['action'] == 'accept' and preview['conflict_ids']:
                raise ConflictError('Resolve accepted property conflicts before acceptance')
            if current['action'] != 'propose' and body['action'] != 'supersede':
                raise ConflictError('Reviewed assertion requires explicit supersession')
            replacement = body.get('superseded_by')
            if body['action'] == 'supersede':
                if current['action'] != 'accept' or not replacement or replacement == assertion_id:
                    raise ConflictError('Only accepted assertions can be superseded by a replacement')
                other = self.state(conn, replacement)
                self.validate(conn, other, reviewer)
                if other['fact_id'] != current['fact_id'] or other['action'] in {'reject', 'supersede'}:
                    raise ConflictError('Replacement must support the same fact')
            elif replacement is not None:
                raise ContractError('Replacement only valid for supersession')
            decision_id = 'decision:' + uuid.uuid4().hex
            revision = current['revision'] + 1
            conn.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)',
                         (decision_id, assertion_id, revision, body['action'], reviewer, body['rationale'], now(), replacement))
            operation = {'assertion_id': assertion_id, 'decision_id': decision_id,
                         'revision': revision, 'action': body['action'], 'reviewer': reviewer,
                         'fact_id': current['fact_id'], 'claim': current['claim']}
            operation_id = digest('operation', operation)
            operation_hash = digest('operation-body', operation)
            conn.execute('INSERT INTO outbox VALUES (?,?,?,?)', (operation_id, operation_hash, canonical(operation), now()))
            return {'decision_id': decision_id, 'revision': revision, 'operation_id': operation_id,
                    'curation_status': {'accept': 'accepted', 'reject': 'rejected', 'supersede': 'superseded'}[body['action']],
                    'materialization_status': 'pending'}

    def materialize(self, operation_ids, *, reviewer, graph, after_graph_commit=None):
        """Hold the SQLite writer lock through the graph transaction and receipt.

        One ledger / one serialized worker is required. A graph operation marker
        makes a committed graph transaction recoverable after a process crash.
        """
        self.authorize(reviewer)
        if not isinstance(operation_ids, list) or not operation_ids or len(set(operation_ids)) != len(operation_ids):
            raise ContractError('Unique operation IDs required')
        text(graph.target)
        # Commit the target binding BEFORE graph I/O: a crash before the first
        # receipt must not let retries silently choose a different database.
        with self.ledger._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for operation_id in operation_ids:
                row = conn.execute('SELECT body FROM outbox WHERE operation_id=?', (operation_id,)).fetchone()
                if not row:
                    raise ContractError('Operation unavailable')
                self.validate(conn, self.state(conn, json.loads(row[0])['assertion_id']), reviewer)
            binding = conn.execute('SELECT graph_target FROM graph_binding WHERE singleton=1').fetchone()
            if binding and binding[0] != graph.target:
                raise ConflictError('Ledger is already bound to another graph target')
            if not binding:
                conn.execute('INSERT INTO graph_binding VALUES (1,?)', (graph.target,))
        with self.ledger._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            targets = conn.execute('SELECT DISTINCT graph_target FROM receipts').fetchall()
            if any(target[0] != graph.target for target in targets):
                raise ConflictError('Ledger is already bound to another graph target')
            pending, results = [], []
            for operation_id in operation_ids:
                row = conn.execute('SELECT operation_hash, body FROM outbox WHERE operation_id=?', (operation_id,)).fetchone()
                if not row:
                    raise ContractError('Operation unavailable')
                operation = json.loads(row[1])
                state = self.state(conn, operation['assertion_id'])
                self.validate(conn, state, reviewer)
                receipt = conn.execute('SELECT operation_hash, graph_target, outcome FROM receipts WHERE operation_id=?', (operation_id,)).fetchone()
                if receipt:
                    if receipt[0] != row[0] or receipt[1] != graph.target:
                        raise ConflictError('Receipt target or operation mismatch')
                    results.append({'operation_id': operation_id, 'outcome': receipt[2]})
                    continue
                obsolete = state['revision'] != operation['revision']
                operation.update(operation_id=operation_id, operation_hash=row[0], obsolete=obsolete)
                if not obsolete and operation['action'] == 'accept':
                    if state['claim']['domain'] != 'research':
                        raise ConflictError('Only research assertions materialize in Neo4j')
                    others = self.fact_states(conn, state['fact_id'])
                    for other in others:
                        self.validate(conn, other, reviewer)
                    if state['claim']['target_kind'] == 'property':
                        self._property_storage_policy(conn, state['claim'])
                        if any(s['action'] == 'accept' and s['claim']['proposed_value'] != state['claim']['proposed_value'] for s in others):
                            raise ConflictError('Conflicting accepted property support')
                        # Only earlier, explicitly superseded curated values may be replaced.
                        operation['replaceable_values'] = [s['claim']['proposed_value'] for s in others
                                                           if s['action'] == 'supersede' and self._was_applied(conn, s['assertion_id'])]
                    for dep in self.dependencies(conn, state):
                        candidates = [self.state(conn, item['assertion_id']) for item in dep['states']]
                        if not any(s['action'] == 'accept' and (self._was_applied(conn, s['assertion_id']) or
                                   self._in_batch(conn, s['assertion_id'], operation_ids)) for s in candidates):
                            raise ConflictError('Accepted materialized dependency required')
                        for candidate in candidates:
                            self.validate(conn, candidate, reviewer)
                pending.append(operation)
            # Graph implementation MUST atomically apply all operations and markers.
            if pending:
                outcomes = graph.apply_batch(pending)
                if not isinstance(outcomes, dict) or set(outcomes) != {op['operation_id'] for op in pending} or any(
                        value not in {'applied', 'obsolete'} for value in outcomes.values()):
                    raise ConflictError('Invalid graph transaction outcomes')
                if after_graph_commit:
                    after_graph_commit()
                for operation in pending:
                    outcome = outcomes[operation['operation_id']]
                    conn.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',
                                 (operation['operation_id'], operation['operation_hash'], graph.target, outcome, now()))
                    results.append({'operation_id': operation['operation_id'], 'outcome': outcome})
            return results

    def _property_storage_policy(self, conn, claim):
        ontology = self.ledger.ontology
        target = conn.execute('SELECT body FROM assertions WHERE fact_id=? LIMIT 1', (claim['target_ref'],)).fetchone()
        if target:
            edge = json.loads(target[0])
            prop = ontology.relationship_property(
                self.ledger._entity(conn, edge['subject_ref'], claim['domain']), edge['predicate'],
                self.ledger._entity(conn, edge['object_ref'], claim['domain']),
                claim['property_key'], claim['proposed_value'])
        else:
            prop = ontology.property(self.ledger._entity(conn, claim['target_ref'], claim['domain']),
                                     claim['property_key'], claim['proposed_value'])
        # The existing pipeline sanitizer fails open on errors. Do not reuse that
        # behavior for curation or accidentally write raw protected values.
        if prop.get('sanitize', 'none') != 'none':
            raise ConflictError('Property requires a reviewed fail-closed sanitization adapter')

    @staticmethod
    def _was_applied(conn, assertion_id):
        return conn.execute("SELECT 1 FROM outbox o JOIN receipts r USING(operation_id) "
                            "WHERE json_extract(o.body, '$.assertion_id')=? AND json_extract(o.body, '$.action')='accept' "
                            "AND r.outcome='applied' LIMIT 1", (assertion_id,)).fetchone() is not None

    @staticmethod
    def _in_batch(conn, assertion_id, operation_ids):
        for operation_id in operation_ids:
            row = conn.execute("SELECT 1 FROM outbox WHERE operation_id=? AND json_extract(body, '$.assertion_id')=? "
                               "AND json_extract(body, '$.action')='accept' AND json_extract(body, '$.revision')="
                               '(SELECT MAX(revision) FROM decisions WHERE assertion_id=?)',
                               (operation_id, assertion_id, assertion_id)).fetchone()
            if row:
                return True
        return False
