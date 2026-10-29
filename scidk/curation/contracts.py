"""Versioned identities and strict JSON primitives for the isolated ledger."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

CONTRACT = 'curation/0.1.0'


class ContractError(ValueError):
    """Invalid input; messages deliberately exclude source values."""


class ConflictError(ContractError):
    """Catalog, idempotency or concurrent decision conflict."""


def canonical(value):
    """Normalize Unicode before hashing; reject ambiguous normalized object keys."""
    def normalize(item):
        if isinstance(item, str):
            return unicodedata.normalize('NFC', item)
        if isinstance(item, dict):
            result = {}
            for key, val in item.items():
                if not isinstance(key, str):
                    raise ContractError('JSON object keys must be strings')
                key = normalize(key)
                if key in result:
                    raise ContractError('Duplicate normalized key')
                result[key] = normalize(val)
            return result
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if item is None or type(item) in (bool, int, float):
            return item
        raise ContractError('Unsupported JSON value')
    try:
        return json.dumps(normalize(value), sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError('Invalid JSON value') from exc


def digest(kind, value):
    return kind + ':' + hashlib.sha256(canonical([CONTRACT, kind, value]).encode()).hexdigest()


def text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ContractError('Expected nonempty text')
    return unicodedata.normalize('NFC', value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ContractError('Invalid schema identifier')
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ContractError('Missing or unknown fields')


def entity_ref(candidate):
    fields(candidate, ('label', 'source_scope', 'source_identifier', 'identity_claims'))
    identifier(candidate['label'])
    fields(candidate['source_scope'], ('namespace', 'resource_id'))
    fields(candidate['source_identifier'], ('record_id', 'role'))
    for part in (*candidate['source_scope'].values(), *candidate['source_identifier'].values()):
        text(part)
    if not isinstance(candidate['identity_claims'], dict):
        raise ContractError('Identity claims must be an object')
    canonical(candidate['identity_claims'])
    # Claims (including email and names) never implicitly merge sources.
    return digest('entity', {k: candidate[k] for k in ('label', 'source_scope', 'source_identifier')})


def fact_id(claim):
    kind = claim['target_kind']
    identity = {'domain': claim['domain'], 'target_kind': kind}
    keys = {'node': ('entity_ref',), 'property': ('target_ref', 'property_key'),
            'relationship': ('subject_ref', 'predicate', 'object_ref', 'qualifiers')}[kind]
    identity.update({key: claim[key] for key in keys})
    return digest('fact', identity)
