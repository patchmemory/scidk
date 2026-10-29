"""Neo4j transactional adapter. Requires an explicitly supplied driver/database.

No credential discovery, graph DDL, startup connection or background worker.
Deployments must provision the approved entity_ref uniqueness constraint and a
unique SciDKCurationOperation.operation_id constraint on a disposable graph first.
Only one ledger/serialized materializer may own a curated graph in v0.1.
"""
from .contracts import ConflictError, canonical, identifier

RESERVED = {'entity_ref', 'fact_id', 'source_scope', 'created_at', 'updated_at', 'curation_status'}


class Neo4jMaterializer:
    def __init__(self, driver, *, database, target):
        if not database or not target:
            raise ValueError('Explicit graph database and stable target identity required')
        self.driver, self.database, self.target = driver, database, target

    def apply_batch(self, operations):
        with self.driver.session(database=self.database) as session:
            return session.execute_write(self._apply, operations)

    @staticmethod
    def _one(tx, query, **params):
        rows = list(tx.run(query, **params))
        if len(rows) != 1:
            raise ConflictError('Graph target missing or ambiguous')
        return rows[0]

    def _apply(self, tx, operations):
        # Preserve topology dependencies within a batch, independent of input order.
        ordered = sorted(operations, key=lambda op: {'node': 0, 'relationship': 1, 'property': 2}[op['claim']['target_kind']])
        outcomes = {}
        for operation in ordered:
            operation_id, operation_hash = operation['operation_id'], operation['operation_hash']
            markers = list(tx.run('MATCH (o:SciDKCurationOperation {operation_id:$id}) RETURN o.operation_hash AS hash, o.outcome AS outcome', id=operation_id))
            if markers:
                if len(markers) != 1 or markers[0]['hash'] != operation_hash:
                    raise ConflictError('Graph operation marker mismatch')
                outcomes[operation_id] = markers[0]['outcome']
                continue
            claim = operation['claim']
            if not operation['obsolete'] and operation['action'] == 'accept':
                self._fact(tx, operation, claim)
            self._one(tx, 'CREATE (o:SciDKCurationOperation {operation_id:$id, operation_hash:$hash, outcome:$outcome}) RETURN o.operation_id AS id',
                      id=operation_id, hash=operation_hash, outcome='obsolete' if operation['obsolete'] else 'applied')
            outcomes[operation_id] = 'obsolete' if operation['obsolete'] else 'applied'
        return outcomes

    def _fact(self, tx, operation, claim):
        base = {'fact_id': operation['fact_id'], 'scope': canonical(claim['source_scope'])}
        kind = claim['target_kind']
        if kind == 'node':
            label = identifier(claim['candidate']['label'])
            # Only existence and operational provenance: identity_claims stay in ledger.
            row = self._one(tx,
                f'MERGE (n:SciDKCuratedEntity {{entity_ref:$ref}}) '
                f'ON CREATE SET n:{label}, n.fact_id=$fact_id, n.source_scope=$scope, '
                "n.created_at=datetime(), n.curation_status='accepted' "
                f'RETURN n:{label} AS valid, n.fact_id AS fact_id',
                ref=claim['entity_ref'], **base)
            if not row['valid'] or row['fact_id'] != operation['fact_id']:
                raise ConflictError('Existing entity identity conflicts with curated node')
        elif kind == 'relationship':
            predicate = identifier(claim['predicate'])
            self._one(tx,
                'MATCH (s:SciDKCuratedEntity {entity_ref:$subject}), (t:SciDKCuratedEntity {entity_ref:$object}) '
                f'MERGE (s)-[r:{predicate} {{fact_id:$fact_id}}]->(t) '
                'ON CREATE SET r.source_scope=$scope, r.qualifiers=$qualifiers, r.created_at=datetime(), '
                "r.curation_status='accepted' RETURN r.fact_id AS fact_id",
                subject=claim['subject_ref'], object=claim['object_ref'], qualifiers=canonical(claim['qualifiers']), **base)
        else:
            key = identifier(claim['property_key'])
            if key in RESERVED:
                raise ConflictError('Operational provenance properties cannot be overwritten')
            ref = claim['target_ref']
            if ref.startswith('entity:'):
                match = 'MATCH (n:SciDKCuratedEntity {entity_ref:$ref}) '
            else:
                match = 'MATCH (:SciDKCuratedEntity)-[n {fact_id:$ref}]->(:SciDKCuratedEntity) '
            # Acquire the property write lock before comparing, so a concurrent
            # canonical writer cannot change it between our read and SET.
            row = self._one(tx, match + f'SET n.`{key}`=n.`{key}` RETURN n.`{key}` AS value', ref=ref)
            value = claim['proposed_value']
            if isinstance(value, list) and (any(type(v) not in (str, int, float, bool) for v in value) or
                                           len({type(v) for v in value}) > 1):
                raise ConflictError('Neo4j property lists require homogeneous scalar values')
            # No last-writer-wins overwrite of an existing unsupported graph value.
            if row['value'] is not None and canonical(row['value']) != canonical(value):
                if not any(canonical(row['value']) == canonical(old) for old in operation.get('replaceable_values', [])):
                    raise ConflictError('Graph property conflicts with reviewed value')
            self._one(tx, match + f'SET n.`{key}`=$value, n.updated_at=datetime() RETURN $ref AS ref',
                      ref=ref, value=value)
