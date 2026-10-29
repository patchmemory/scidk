"""Bounded, internal-only disclosure of applied, currently supported ledger facts.

No graph payloads are trusted. No tool/route is registered here. A future fixed
agent template can call read_fact; arbitrary query results cannot use this path.
"""
import json
from contextlib import closing
import sqlite3

from .security import DisclosureDenied, PolicyStore, REFUSAL
from ..curation.contracts import canonical


class FactDisclosure:
    def __init__(self, ledger, settings_db, *, graph_target):
        self.ledger, self.store, self.graph_target = ledger, PolicyStore(settings_db), graph_target

    def read_fact(self, fact_id, identity, *, include_evidence=False):
        try:
            with self.store.resolve(identity) as policy:
                with closing(sqlite3.connect(self.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
                    conn.execute('PRAGMA query_only=ON')
                    conn.execute('BEGIN')
                    result = self._fact(conn, policy, fact_id, include_evidence, set())
                return {'status': 'success', 'fact': result}
        except Exception:
            # Includes malformed policy/ledger, unknown IDs and backend errors.
            # No existence signal, citation identifier, exception or count escapes.
            return dict(REFUSAL)

    def _fact(self, conn, policy, fact_id, include_evidence, visited):
        if not isinstance(fact_id, str) or fact_id in visited or len(visited) > 8:
            raise DisclosureDenied()
        visited = visited | {fact_id}
        if conn.execute('SELECT graph_target FROM graph_binding WHERE singleton=1').fetchone() != (self.graph_target,):
            raise DisclosureDenied()
        rows = conn.execute("SELECT a.assertion_id,a.body,d.decision_id,d.revision FROM assertions a "
            "JOIN decisions d ON d.assertion_id=a.assertion_id "
            "WHERE a.fact_id=? AND d.action='accept' AND d.revision=(SELECT MAX(revision) FROM decisions WHERE assertion_id=a.assertion_id) "
            "ORDER BY a.assertion_id LIMIT 51", (fact_id,)).fetchall()
        if not rows or len(rows) > 50:
            raise DisclosureDenied()
        claims, citations = [], []
        for assertion_id, encoded, decision_id, revision in rows:
            claim = json.loads(encoded)
            if claim.get('domain') != 'research' or claim.get('ontology_version') != self.ledger.ontology.version:
                raise DisclosureDenied()
            if claim.get('visibility') not in {'public', 'restricted'}:
                raise DisclosureDenied()
            policy.resource(claim.get('source_scope'))
            receipt = conn.execute("SELECT 1 FROM outbox o JOIN receipts r USING(operation_id) "
                "WHERE json_extract(o.body,'$.decision_id')=? AND json_extract(o.body,'$.assertion_id')=? "
                "AND json_extract(o.body,'$.revision')=? AND r.outcome='applied' AND r.graph_target=? "
                "AND o.operation_hash=r.operation_hash LIMIT 1", (decision_id, assertion_id, revision, self.graph_target)).fetchone()
            if not receipt:
                raise DisclosureDenied()
            refs = claim.get('evidence_refs')
            if not isinstance(refs, list) or not refs:
                raise DisclosureDenied()
            for evidence_id in refs:
                row = conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (evidence_id,)).fetchone()
                if not row:
                    raise DisclosureDenied()
                evidence = json.loads(row[0])
                policy.resource(evidence.get('source_scope'))
                if evidence.get('visibility') not in {'public', 'restricted'}:
                    raise DisclosureDenied()
                if include_evidence:
                    policy.evidence_metadata(evidence_id, evidence)
                    citation = {}
                    # Locators, IDs, URIs and excerpts are deliberately not exported.
                    for key in ('citation', 'version'):
                        policy.property('EvidenceSource', key)
                        citation[key] = evidence[key]
                    if citation not in citations:
                        citations.append(citation)
            claims.append(claim)
        claim = claims[0]
        kind = claim['target_kind']
        result = {'fact_id': fact_id, 'target_kind': kind, 'curation_status': 'accepted',
                  'materialization_status': 'applied',
                  'epistemic_status': sorted({c['epistemic_status'] for c in claims})}
        if kind == 'node':
            label, ref = claim['candidate']['label'], claim['entity_ref']
            for key in ('fact_id', 'entity_ref'):
                policy.property(label, key)
            result.update(label=label, entity_ref=ref)
            # Existence does not authorize any identity claims or node properties.
        elif kind == 'property':
            values = {canonical(c['proposed_value']) for c in claims}
            if len(values) != 1:
                raise DisclosureDenied()
            target = self._reference(conn, policy, claim['target_ref'], visited)
            label = target.get('label') or target['predicate']
            for key in (claim['property_key'], 'fact_id', 'entity_ref'):
                policy.property(label, key)
            # Do not expose raw protected values which the materializer would refuse.
            if target['target_kind'] == 'node':
                prop = self.ledger.ontology.property(label, claim['property_key'], claim['proposed_value'])
            else:
                subject_label = self.ledger._entity(conn, target['subject_ref'], 'research')
                object_label = self.ledger._entity(conn, target['object_ref'], 'research')
                prop = self.ledger.ontology.relationship_property(subject_label, label, object_label,
                                                                 claim['property_key'], claim['proposed_value'])
            if prop.get('sanitize', 'none') != 'none':
                raise DisclosureDenied()
            result.update(target_ref=claim['target_ref'], property_key=claim['property_key'], value=claim['proposed_value'])
        elif kind == 'relationship':
            self._reference(conn, policy, claim['subject_ref'], visited)
            self._reference(conn, policy, claim['object_ref'], visited)
            for key in ('fact_id', 'subject_ref', 'object_ref', *claim['qualifiers']):
                policy.property(claim['predicate'], key)
            result.update(subject_ref=claim['subject_ref'], object_ref=claim['object_ref'],
                          predicate=claim['predicate'], qualifiers=claim['qualifiers'])
        else:
            raise DisclosureDenied()
        for key in result:
            policy.property(label if kind == 'node' else (label if kind == 'property' else claim['predicate']), key)
        if include_evidence:
            result['citations'] = citations
        return result

    def _reference(self, conn, policy, reference, visited):
        if reference.startswith('fact:'):
            return self._fact(conn, policy, reference, False, visited)
        ids = conn.execute("SELECT DISTINCT fact_id FROM assertions WHERE json_extract(body,'$.entity_ref')=? "
                           "AND json_extract(body,'$.domain')='research' LIMIT 2", (reference,)).fetchall()
        if len(ids) != 1:
            raise DisclosureDenied()
        return self._fact(conn, policy, ids[0][0], False, visited)
