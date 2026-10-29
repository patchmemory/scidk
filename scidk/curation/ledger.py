"""Explicitly migrated, append-only evidence/assertion ledger; no web integration.

Trusted internal callers must supply the authenticated actor and an evidence
access callback. This is not an agent-safe read API or a review authorization API.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .contracts import (CONTRACT, ConflictError, ContractError, canonical, digest,
                        entity_ref, fact_id, fields, text)

SCHEMA_VERSION = 1
_TABLES = ('evidence', 'assertions', 'decisions', 'submissions')
_DDL = '''
CREATE TABLE curation_schema (version INTEGER PRIMARY KEY, contract TEXT NOT NULL);
CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE assertions (
    assertion_id TEXT PRIMARY KEY, fact_id TEXT NOT NULL, actor TEXT NOT NULL,
    body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX assertions_fact ON assertions(fact_id);
CREATE INDEX assertions_entity ON assertions(json_extract(body, '$.entity_ref'), json_extract(body, '$.domain'));
CREATE TABLE decisions (
    decision_id TEXT PRIMARY KEY, assertion_id TEXT NOT NULL REFERENCES assertions,
    revision INTEGER NOT NULL CHECK (revision > 0),
    action TEXT NOT NULL CHECK (action IN ('accept','reject','supersede')),
    reviewer_id TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL,
    superseded_by TEXT REFERENCES assertions,
    UNIQUE(assertion_id, revision)
);
CREATE TABLE submissions (
    actor TEXT NOT NULL, caller_key TEXT NOT NULL, body_hash TEXT NOT NULL,
    assertion_id TEXT NOT NULL REFERENCES assertions,
    PRIMARY KEY(actor, caller_key)
);
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def migrate(path):
    """Explicit initialization only; refuse existing databases with unrelated tables."""
    path = Path(path)
    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables:
            if tables != {*_TABLES, 'curation_schema'}:
                raise ConflictError('Not an isolated curation database')
            if conn.execute('SELECT version, contract FROM curation_schema').fetchall() != [(SCHEMA_VERSION, CONTRACT)]:
                raise ConflictError('Unsupported ledger version')
            return
        triggers = '\n'.join(
            f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'append-only curation ledger'); END;"
            for table in (*_TABLES, 'curation_schema') for action in ('UPDATE', 'DELETE'))
        conn.executescript('BEGIN IMMEDIATE;\n' + _DDL + triggers +
                           f"\nINSERT INTO curation_schema VALUES ({SCHEMA_VERSION}, '{CONTRACT}');\nCOMMIT;")
    finally:
        conn.close()


class Ledger:
    def __init__(self, path, ontology, can_read_evidence):
        self.path = Path(path).resolve()
        self.ontology = ontology
        if not callable(can_read_evidence):
            raise ContractError('Evidence authorization callback required')
        self.can_read_evidence = can_read_evidence
        # mode=rw prevents accidental creation; construction never migrates.
        with self._connection() as conn:
            if conn.execute('SELECT version, contract FROM curation_schema').fetchall() != [(SCHEMA_VERSION, CONTRACT)]:
                raise ConflictError('Unsupported ledger version')

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True)
        conn.row_factory = None
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def add_evidence(self, body):
        fields(body, ('source_type', 'source_id', 'source_scope', 'citation', 'version',
                      'accessed_at', 'content_hash', 'locator', 'retrieval_method',
                      'visibility', 'derivation_root'), ('uri', 'excerpt', 'run_ref'))
        fields(body['source_scope'], ('namespace', 'resource_id'))
        for value in body['source_scope'].values():
            text(value)
        for key in ('source_type', 'source_id', 'citation', 'version', 'accessed_at',
                    'content_hash', 'locator', 'retrieval_method', 'visibility', 'derivation_root'):
            text(body[key])
        encoded = canonical(body)
        evidence_id = digest('evidence', body)
        with self._connection() as conn:
            conn.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?)', (evidence_id, encoded, now()))
        return evidence_id

    def _entity(self, conn, ref, domain):
        text(ref)
        rows = conn.execute("SELECT body FROM assertions WHERE json_extract(body, '$.entity_ref')=? "
                            "AND json_extract(body, '$.domain')=? ORDER BY assertion_id",
                            (ref, domain)).fetchall()
        # Candidates are ledger identities, never caller-supplied label hints.
        for (body,) in rows:
            claim = json.loads(body)
            if claim['target_kind'] == 'node' and claim['entity_ref'] == ref and claim['domain'] == domain:
                return claim['candidate']['label']
        raise ContractError('Unknown entity reference in domain')

    def _validate(self, conn, body, actor):
        body = json.loads(canonical(body))
        common = ('domain', 'target_kind', 'ontology_version', 'epistemic_status',
                  'method', 'visibility', 'source_scope', 'evidence_refs')
        optional = ('confidence', 'confidence_method', 'supersedes', 'agent', 'validity')
        kind = body.get('target_kind') if isinstance(body, dict) else None
        kinds = {'node': ('candidate',), 'property': ('target_ref', 'property_key', 'proposed_value'),
                 'relationship': ('subject_ref', 'predicate', 'object_ref', 'qualifiers')}
        if kind not in kinds:
            raise ContractError('Invalid target kind')
        fields(body, (*common, *kinds[kind]), optional)
        if body['domain'] not in {'system', 'ontology', 'research'}:
            raise ContractError('Invalid knowledge domain')
        if body['ontology_version'] != self.ontology.version:
            raise ConflictError('Ontology version mismatch')
        if body['epistemic_status'] not in {'observed', 'inferred', 'confirmed'}:
            raise ContractError('Invalid epistemic status')
        for key in ('method', 'visibility'):
            text(body[key])
        fields(body['source_scope'], ('namespace', 'resource_id'))
        for value in body['source_scope'].values():
            text(value)
        if 'confidence' in body:
            score = body['confidence']
            if type(score) not in (int, float) or not 0 <= score <= 1:
                raise ContractError('Invalid confidence')
            text(body.get('confidence_method'))
        if 'agent' in body:
            fields(body['agent'], ('name', 'model', 'version'))
            for value in body['agent'].values():
                text(value)
        if 'validity' in body:
            fields(body['validity'], (), ('valid_from', 'valid_to'))
            for value in body['validity'].values():
                text(value)
        refs = body['evidence_refs']
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs):
            raise ContractError('Evidence references required and unique')
        for ref in refs:
            row = conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (ref,)).fetchone()
            if row is None:
                raise ContractError('Evidence unavailable')
            evidence = json.loads(row[0])
            if not self.can_read_evidence(actor, evidence):
                raise ContractError('Evidence unavailable')
            # Conservative first-stage policy: cross-resource corroboration needs
            # an explicitly authorized multi-source review contract in stage 2.
            if evidence['source_scope'] != body['source_scope']:
                raise ContractError('Evidence source scope mismatch')
        claim = json.loads(canonical(body))
        if kind == 'node':
            claim['entity_ref'] = entity_ref(claim['candidate'])
            self.ontology.label(claim['candidate']['label'])
            if claim['candidate']['source_scope'] != claim['source_scope']:
                raise ContractError('Candidate source scope mismatch')
        elif kind == 'property':
            target = conn.execute('SELECT body FROM assertions WHERE fact_id=? ORDER BY assertion_id',
                                  (claim['target_ref'],)).fetchone()
            if target:
                target = json.loads(target[0])
                if target['target_kind'] != 'relationship' or target['domain'] != claim['domain']:
                    raise ContractError('Invalid relationship property target')
                subject = self._entity(conn, target['subject_ref'], claim['domain'])
                obj = self._entity(conn, target['object_ref'], claim['domain'])
                self.ontology.relationship_property(subject, target['predicate'], obj,
                                                    claim['property_key'], claim['proposed_value'])
            else:
                label = self._entity(conn, claim['target_ref'], claim['domain'])
                self.ontology.property(label, claim['property_key'], claim['proposed_value'])
        else:
            fields(claim['qualifiers'], (), ('role', 'valid_from', 'valid_to'))
            for value in claim['qualifiers'].values():
                text(value)
            subject = self._entity(conn, claim['subject_ref'], claim['domain'])
            obj = self._entity(conn, claim['object_ref'], claim['domain'])
            self.ontology.relationship(subject, claim['predicate'], obj)
        if 'supersedes' in claim:
            row = conn.execute('SELECT fact_id FROM assertions WHERE assertion_id=?', (text(claim['supersedes']),)).fetchone()
            if not row or row[0] != fact_id(claim):
                raise ContractError('Supersession must refer to the same fact')
        return claim

    def submit(self, body, *, actor, caller_key):
        text(actor)
        text(caller_key)
        body_hash = digest('submission', body)
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # Revalidate access even on replay; revoked access must not leak IDs.
            claim = self._validate(conn, body, actor)
            existing = conn.execute('SELECT body_hash, assertion_id FROM submissions WHERE actor=? AND caller_key=?',
                                    (actor, caller_key)).fetchone()
            if existing:
                if existing[0] != body_hash:
                    raise ConflictError('Idempotency key reused with different input')
                return existing[1]
            assertion_id = 'assertion:' + uuid.uuid4().hex
            conn.execute('INSERT INTO assertions VALUES (?,?,?,?,?)',
                         (assertion_id, fact_id(claim), actor, canonical(claim), now()))
            conn.execute('INSERT INTO submissions VALUES (?,?,?,?)',
                         (actor, caller_key, body_hash, assertion_id))
            return assertion_id

    def get_internal(self, assertion_id):
        """Trusted service read only. Must not be exposed through a route/tool."""
        with self._connection() as conn:
            row = conn.execute('SELECT fact_id, actor, body, created_at FROM assertions WHERE assertion_id=?',
                               (assertion_id,)).fetchone()
            if row is None:
                raise ContractError('Assertion unavailable')
            decisions = conn.execute('SELECT action, revision FROM decisions WHERE assertion_id=? ORDER BY revision DESC',
                                     (assertion_id,)).fetchall()
            return {'assertion_id': assertion_id, 'fact_id': row[0], 'proposed_by': row[1],
                    'claim': json.loads(row[2]), 'created_at': row[3],
                    'curation_status': {'accept': 'accepted', 'reject': 'rejected', 'supersede': 'superseded'}[decisions[0][0]] if decisions else 'proposed',
                    'revision': decisions[0][1] if decisions else 0}
