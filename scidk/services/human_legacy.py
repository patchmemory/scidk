"""Explicit immutable source-bound legacy snapshots, human only; no graph query."""
from copy import deepcopy
import json
import sqlite3
from contextlib import closing

from ..agent_tools.security import DisclosureDenied
from ..curation.contracts import digest


class LegacySnapshot:
    def __init__(self, ontology, records, *, ledger):
        self.ledger = ledger
        if not isinstance(records, list) or len(records) > 128 or len(json.dumps(records).encode()) > 131072:
            raise DisclosureDenied()
        self._records = {}
        for record in deepcopy(records):
            if set(record) != {'record_key', 'source_scope', 'evidence_id', 'label', 'properties'}:
                raise DisclosureDenied()
            if not isinstance(record['record_key'], str) or not record['record_key'] or not record['evidence_id']:
                raise DisclosureDenied()
            ontology.label(record['label'])
            for key, value in record['properties'].items():
                # Locators and internal IDs are never legacy display fields.
                if key.lower() in {'id', 'path', 'host', 'uri', 'url', 'locator', 'source_identifier', 'element_id'}:
                    raise DisclosureDenied()
                prop = ontology.property(record['label'], key, value)
                if prop.get('sanitize', 'none') != 'none':
                    raise DisclosureDenied()
            ref = 'legacy:' + digest('human-legacy', [record['source_scope'], record['record_key']])
            if ref in self._records:
                raise DisclosureDenied()
            self._records[ref] = record

    def read(self, policy, ref):
        record = self._records.get(ref)
        if not record:
            raise DisclosureDenied()
        policy.resource(record['source_scope'])
        with closing(sqlite3.connect(self.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
            row = conn.execute('SELECT body FROM evidence WHERE evidence_id=?', (record['evidence_id'],)).fetchone()
        if not row:
            raise DisclosureDenied()
        evidence = json.loads(row[0])
        if evidence.get('source_scope') != record['source_scope']:
            raise DisclosureDenied()
        policy.resource(evidence.get('source_scope'))
        policy.evidence_metadata(record['evidence_id'], evidence)
        policy.evidence_metadata(ref, {'visibility': 'restricted'})
        for key in ('entity_ref', 'label', 'curation_status'):
            policy.property(record['label'], key)
        properties = {}
        for key, value in record['properties'].items():
            try:
                policy.property(record['label'], key)
            except DisclosureDenied:
                continue
            properties[key] = deepcopy(value)
        return dict(id=ref, type=record['label'], properties=properties, support=[],
                    curation_status='legacy/unreviewed', materialization_status='unverified',
                    epistemic_status='unverified')

    def search(self, policy, q, label):
        nodes = []
        for ref in sorted(self._records):
            try:
                node = self.read(policy, ref)
            except DisclosureDenied:
                continue
            if (not label or label == node['type']) and q.casefold() in json.dumps(
                    [node['type'], node['properties']], ensure_ascii=False).casefold():
                nodes.append(node)
        return nodes
