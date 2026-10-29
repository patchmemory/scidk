"""Bounded assertion inspection/submission; no decision or graph-write methods.

Ledger.get_internal is never serialized directly. Unaccepted references require
source/evidence/property authorization independently of graph presence.
"""
from contextlib import closing
import json
import sqlite3

from .security import DisclosureDenied
from .capabilities import require_proposal
from ..curation.contracts import digest
from ..curation.ledger import Ledger


def _evidence(policy, eid, evidence):
    policy.resource(evidence.get('source_scope'))
    policy.evidence_metadata(eid, evidence)


class AssertionAccess:
    def __init__(self, ledger, facts):
        self.ledger, self.facts = ledger, facts

    @staticmethod
    def history_grant_id(assertion_id, history):
        return digest('decision-history', [assertion_id, history])

    def _reference(self, conn, policy, reference, domain, visited):
        if not isinstance(reference, str) or reference in visited or len(visited) > 8:
            raise DisclosureDenied()
        if reference.startswith('fact:'):
            rows = conn.execute('SELECT assertion_id,body FROM assertions WHERE fact_id=? ORDER BY assertion_id LIMIT 51',
                                (reference,)).fetchall()
        else:
            rows = conn.execute("SELECT assertion_id,body FROM assertions WHERE json_extract(body,'$.entity_ref')=? "
                                "ORDER BY assertion_id LIMIT 51", (reference,)).fetchall()
        if not rows or len(rows) > 50:
            raise DisclosureDenied()
        labels = set()
        for aid, encoded in rows:
            claim = json.loads(encoded)
            if claim['domain'] != domain:
                raise DisclosureDenied()
            safe, label = self._claim(conn, policy, claim, visited | {reference})
            labels.add(label)
        if len(labels) != 1:
            raise DisclosureDenied()
        return labels.pop()

    def _claim(self, conn, policy, claim, visited=None, *, proposal=False):
        visited = visited or set()
        policy.resource(claim.get('source_scope'))
        if claim.get('visibility') not in {'public', 'restricted'} or claim.get('ontology_version') != self.ledger.ontology.version:
            raise DisclosureDenied()
        refs = claim.get('evidence_refs')
        if not isinstance(refs, list) or not refs or len(refs) > 50:
            raise DisclosureDenied()
        for eid in refs:
            row = conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (eid,)).fetchone()
            if not row:
                raise DisclosureDenied()
            evidence = json.loads(row[0])
            if evidence.get('source_scope') != claim['source_scope']:
                raise DisclosureDenied()
            _evidence(policy, eid, evidence)
        for field in claim:
            policy.property('Assertion', field)
        kind, domain = claim['target_kind'], claim['domain']
        safe = {k: claim[k] for k in ('domain', 'target_kind', 'ontology_version', 'epistemic_status')}
        if kind == 'node':
            label = claim['candidate']['label']
            self.ledger.ontology.label(label)
            for key in ('entity_ref', 'label'):
                policy.property(label, key)
            safe.update(label=label)
            if 'entity_ref' in claim:
                safe['entity_ref'] = claim['entity_ref']
            # Identity/source-record claims are never released by node existence.
            if proposal:
                for key, value in claim['candidate']['identity_claims'].items():
                    prop = self.ledger.ontology.property(label, key, value)
                    policy.property(label, key)
                    if prop.get('sanitize', 'none') != 'none':
                        raise DisclosureDenied()
        elif kind == 'property':
            label = self._reference(conn, policy, claim['target_ref'], domain, visited)
            policy.property(label, claim['property_key'])
            if claim['target_ref'].startswith('fact:'):
                row = conn.execute('SELECT body FROM assertions WHERE fact_id=? LIMIT 1', (claim['target_ref'],)).fetchone()
                target = json.loads(row[0])
                if target['target_kind'] != 'relationship':
                    raise DisclosureDenied()
                subject = self.ledger._entity(conn, target['subject_ref'], domain)
                obj = self.ledger._entity(conn, target['object_ref'], domain)
                prop = self.ledger.ontology.relationship_property(subject, target['predicate'], obj,
                                                                claim['property_key'], claim['proposed_value'])
            else:
                prop = self.ledger.ontology.property(label, claim['property_key'], claim['proposed_value'])
            if prop.get('sanitize', 'none') != 'none':
                raise DisclosureDenied()
            safe.update(target_ref=claim['target_ref'], property_key=claim['property_key'], proposed_value=claim['proposed_value'])
        elif kind == 'relationship':
            subject = self._reference(conn, policy, claim['subject_ref'], domain, visited)
            obj = self._reference(conn, policy, claim['object_ref'], domain, visited)
            label = claim['predicate']
            self.ledger.ontology.relationship(subject, label, obj)
            for key in ('subject_ref', 'object_ref', *claim['qualifiers']):
                policy.property(label, key)
            safe.update(subject_ref=claim['subject_ref'], object_ref=claim['object_ref'],
                        predicate=label, qualifiers=claim['qualifiers'])
        else:
            raise DisclosureDenied()
        for key in safe:
            policy.property(label, key)
        return safe, label

    def inspect(self, policy, assertion_id, *, include_history=False):
        with closing(sqlite3.connect(self.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('BEGIN')
            row = conn.execute('SELECT fact_id,body FROM assertions WHERE assertion_id=?', (assertion_id,)).fetchone()
            if not row:
                raise DisclosureDenied()
            fact_id, encoded = row
            claim = json.loads(encoded)
            safe, label = self._claim(conn, policy, claim)
            # Explicit record metadata permission for IDs and review rationale.
            policy.evidence_metadata(assertion_id, {'visibility': 'restricted'})
            decisions = conn.execute('SELECT action,revision,rationale,created_at FROM decisions WHERE assertion_id=? '
                                     'ORDER BY revision DESC LIMIT 51', (assertion_id,)).fetchall()
            if len(decisions) > 50:
                raise DisclosureDenied()
            current = decisions[0] if decisions else None
            if current:
                policy.property('Decision', 'rationale')
            status = {'accept': 'accepted', 'reject': 'rejected', 'supersede': 'superseded'}[current[0]] if current else 'proposed'
            evidence = []
            for eid in claim['evidence_refs']:
                ev = json.loads(conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (eid,)).fetchone()[0])
                item = {'evidence_id': eid, 'citation': ev['citation'], 'version': ev['version']}
                for key in item:
                    policy.property('EvidenceSource', key)
                evidence.append(item)
            result = dict(assertion_id=assertion_id, fact_id=fact_id, claim=safe,
                          curation_status=status, revision=current[1] if current else 0,
                          rationale=current[2] if current else None, evidence=evidence)
            if include_history:
                history = [dict(action=d[0], revision=d[1], rationale=d[2], created_at=d[3]) for d in decisions]
                policy.evidence_metadata(self.history_grant_id(assertion_id, history), {'visibility': 'restricted'})
                for item in history:
                    for key in item:
                        policy.property('Decision', key)
                result['decision_history'] = history
            for key in result:
                policy.property('Assertion', key)
            for key in ('fact_id', 'assertion_id'):
                policy.property(label, key)
            return result

    def explain(self, policy, identity, fact_id, *, include_evidence=True, allow_unsupported=False):
        current = self.facts.read_fact(fact_id, identity, include_evidence=include_evidence)
        if current['status'] == 'success':
            return current
        if not allow_unsupported:
            raise DisclosureDenied()
        # Only explicitly permitted ledger assertions can explain unsupported
        # facts. Unknown/legacy/unclassified and inaccessible facts remain identical.
        with closing(sqlite3.connect(self.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
            rows = conn.execute('SELECT assertion_id FROM assertions WHERE fact_id=? ORDER BY assertion_id LIMIT 51',
                                (fact_id,)).fetchall()
        if not rows or len(rows) > 50:
            raise DisclosureDenied()
        assertions = [self.inspect(policy, row[0]) for row in rows]
        # An accepted decision without current applied/nonconflicting support is
        # never presented as an accepted fact. No backend shape is consulted.
        for key in ('fact_id', 'curation_status', 'assertion_statuses', 'citations'):
            policy.property('Assertion', key)
        return {'status': 'success', 'fact': {'fact_id': fact_id, 'curation_status': 'not_currently_supported',
                'assertion_statuses': sorted({a['curation_status'] for a in assertions}),
                'citations': [e for a in assertions for e in a['evidence']] if include_evidence else []}}

    def submit(self, policy, body, *, caller_key):
        require_proposal(policy, body.get('source_scope'))
        # Keep the shared ledger callback immutable; this private instance binds
        # evidence access to this principal and policy transaction only.
        actor = 'agent-user:' + str(policy.user_id)
        def can_read(who, evidence):
            if who != actor:
                return False
            _evidence(policy, digest('evidence', evidence), evidence)
            return True
        ledger = Ledger(self.ledger.path, self.ledger.ontology, can_read)
        with ledger._connection() as conn:
            claim = ledger._validate(conn, body, actor)
            _, label = self._claim(conn, policy, claim, proposal=True)
            for key in ('assertion_id', 'submission_status', 'validation', 'ontology_version'):
                policy.property('Assertion', key)
                policy.property(label, key)
        # A supersedes field is a proposed lineage link, not a review decision.
        # Inspect its target independently to avoid ID-based existence probes.
        if body.get('supersedes'):
            self.inspect(policy, body['supersedes'])
        aid = ledger.submit(body, actor=actor, caller_key=caller_key)
        return {'status': 'success', 'assertion_id': aid, 'submission_status': 'recorded',
                'validation': 'valid', 'ontology_version': ledger.ontology.version}
