"""Selected, pinned offline vocabulary records. No network resolver or scraping.

Resource kinds and resolver metadata are opaque extensibility points, not claims
that literature, metadata standards, pathways and ontologies share semantics.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re
import unicodedata
from urllib.parse import urlsplit

from scidk.curation.contracts import ContractError, canonical, digest
from .projection import Projection, content_hash


class ExternalRegistry:
    def __init__(self):
        self._registrations, self._concepts = {}, {}

    def register(self, registration, concepts):
        registration, concepts = deepcopy(registration), deepcopy(concepts)
        required = {'namespace', 'source_uri', 'version', 'identifier_format', 'resolver',
                    'retrieved_at', 'citation', 'visibility', 'resource_kind'}
        if not required <= registration.keys() or any(not registration[k] for k in required):
            raise ContractError('Incomplete external registration')
        namespace = registration['namespace']
        if not isinstance(namespace, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', namespace):
            raise ContractError('Invalid namespace')
        if namespace in self._registrations:
            raise ContractError('Namespace already pinned')
        if registration['visibility'] not in {'public', 'restricted'}:
            raise ContractError('Invalid visibility')
        if not urlsplit(registration['source_uri']).scheme:
            raise ContractError('Source URI required')
        datetime.fromisoformat(registration['retrieved_at'].replace('Z', '+00:00'))
        resolver = registration['resolver']
        if (resolver.get('mode') != 'offline' or
                set(resolver) != {'mode', 'uri_prefix', 'identifier_style'} or
                resolver['identifier_style'] not in {'obo', 'identity'}):
            raise ContractError('Only offline resolvers supported')
        re.compile(registration['identifier_format'])
        if len(concepts) > 128:
            raise ContractError('Selected concept bound exceeded')
        selected = {}
        for concept in concepts:
            if not {'accession', 'uri', 'label', 'synonyms', 'namespace', 'version',
                    'citation', 'provenance'} <= concept.keys():
                raise ContractError('Incomplete selected concept')
            if (concept['namespace'] != namespace or concept['version'] != registration['version'] or
                    not isinstance(concept['synonyms'], list) or not concept['label'] or
                    not all(isinstance(s, str) and s for s in concept['synonyms']) or
                    not concept['citation'] or not concept['provenance']):
                raise ContractError('Concept provenance/version mismatch')
            accession = self._normalize(registration, concept['accession'])
            if accession != concept['accession'] or concept['uri'] != self._uri(registration, accession):
                raise ContractError('Concept identifier/URI mismatch')
            if accession in selected:
                raise ContractError('Duplicate selected concept')
            selected[accession] = concept
        # Atomic registration after every selected record validates.
        canonical([registration, selected])
        self._registrations[namespace], self._concepts[namespace] = registration, selected

    @staticmethod
    def _uri(registration, accession):
        suffix = accession.replace(':', '_') if registration['resolver']['identifier_style'] == 'obo' else accession
        return registration['resolver']['uri_prefix'] + suffix

    @staticmethod
    def _normalize(registration, value):
        if not isinstance(value, str):
            raise ContractError('Identifier must be a string')
        value = unicodedata.normalize('NFC', value).strip()
        prefix, namespace = registration['resolver']['uri_prefix'], registration['namespace']
        if value.startswith(prefix):
            value = value[len(prefix):]
        if registration['resolver']['identifier_style'] == 'obo':
            value = value.replace('_', ':')
        if registration['resolver']['identifier_style'] == 'obo' and value.lower().startswith(namespace.lower() + ':'):
            value = namespace + value[len(namespace):]
        if not re.fullmatch(registration['identifier_format'], value):
            raise ContractError('Invalid external identifier')
        return value

    def normalize(self, namespace, value):
        return self._normalize(self._registrations[namespace], value)

    def resolve(self, namespace, raw_value):
        """Exact selected identifier/label/synonym lookup, no fuzzy medical inference."""
        registration = self._registrations[namespace]
        try:
            accession = self.normalize(namespace, raw_value)
        except ContractError:
            accession = None
        term = unicodedata.normalize('NFC', raw_value).strip().casefold()
        matches = [c for c in self._concepts[namespace].values()
                   if c['accession'] == accession or term in
                   {unicodedata.normalize('NFC', t).strip().casefold() for t in [c['label'], *c['synonyms']]}]
        if len(matches) != 1:
            raise ContractError('No unambiguous selected concept')
        return deepcopy({'original_value': raw_value, 'concept': matches[0],
                         'registration': registration, 'match_semantics': 'related',
                         'epistemic_status': 'inferred', 'curation_status': 'proposed'})

    def projection(self, namespace, *, source_scope, revision):
        registration = self._registrations[namespace]
        sources = [{'path': registration['source_uri'], 'hash': digest('registration', registration), 'valid': True,
                    'source_scope': deepcopy(source_scope)}]
        common = dict(sources=sources, source_scope=deepcopy(source_scope),
                      visibility=registration['visibility'], git_revision=revision,
                      applicability=registration['version'])
        root = 'external:' + namespace
        nodes = [dict(common, id=root, type='schema', registration=deepcopy(registration))]
        edges = []
        for accession, concept in sorted(self._concepts[namespace].items()):
            id = 'concept:' + accession
            concept_common = deepcopy(common)
            concept_common['sources'][0]['hash'] = digest('selected-concept', [registration, concept])
            nodes.append(dict(concept_common, id=id, type='schema', concept=deepcopy(concept)))
            edges.append(dict(source=root, type='DECLARES', target=id))
        return Projection(nodes, edges, {'domain': 'ontology', 'generated': True})


def mondo_fixture():
    data = json.loads((Path(__file__).parent / 'fixtures' / 'mondo.json').read_text())
    registry = ExternalRegistry()
    registry.register(data['registration'], data['concepts'])
    return registry


def propose_alignment(ledger, *, target_ref, property_key, raw_value, source_scope,
                      registry, namespace, actor, caller_key, intake_evidence):
    """Submit an inferred PROPERTY proposal to an explicitly governed schema.

    Does not create ontology definitions, accept decisions, or materialize. The
    approved demo supplies a synthetic list property, whose structured value
    preserves raw input, match semantics and pinned concept identity. Operational
    schemas without that property fail existing Stage 1 validation.
    """
    if intake_evidence.get('source_scope') != source_scope:
        raise ContractError('Intake evidence source scope mismatch')
    match = registry.resolve(namespace, raw_value)
    # Stage 1 canonical JSON normalizes Unicode to NFC. Retain the original
    # UTF-8 bytes as well so a decomposed source string is exactly recoverable.
    payload = {'original_value': raw_value, 'original_utf8_hex': raw_value.encode('utf-8').hex(),
               'match_semantics': match['match_semantics'],
               'concept': match['concept'], 'registration': match['registration']}
    evidence = deepcopy(intake_evidence)
    evidence.update(source_scope=deepcopy(source_scope), source_type='derived_alignment',
                    content_hash=content_hash(canonical(payload).encode()),
                    retrieval_method='offline-selected-concept/1', excerpt=canonical(payload),
                    uri=match['concept']['uri'])
    # Preserve intake citation/version/root; pinned external citation/provenance is
    # additional derived content, not a claim that MONDO owns the intake Resource.
    evidence_id = ledger.add_evidence(evidence)
    body = dict(domain='research', target_kind='property', ontology_version=ledger.ontology.version,
                epistemic_status='inferred', method='offline-selected-concept/1',
                visibility=evidence['visibility'], source_scope=deepcopy(source_scope),
                evidence_refs=[evidence_id], target_ref=target_ref, property_key=property_key,
                proposed_value=[payload])
    return ledger.submit(body, actor=actor, caller_key=caller_key)
