"""Canonical adapter projection. Conflicts block the entire catalog, conservatively.

Explicit snapshots only; never query Neo4j or the production LabelService DB.
"""
from copy import deepcopy
from pathlib import Path
import yaml

from scidk.curation.contracts import ContractError, ConflictError, digest
from scidk.curation.ontology import Ontology
from scidk.schema.registry import _LabelRegistry
from .projection import Projection, content_hash


def ontology_projection(yaml_paths, sqlite_definitions, *, bindings=None, revision,
                        applicability='knowledge-context/1'):
    bindings = bindings or {}
    yaml_paths = sorted(map(Path, yaml_paths))
    sqlite_definitions = deepcopy(sqlite_definitions)
    sources, definitions, blockers = [], [], []
    for path in yaml_paths:
        source = str(path)
        try:
            data = path.read_bytes()
            definitions.append(_LabelRegistry()._parse_yaml(source))
            sources.append({'path': source, 'hash': content_hash(data), 'valid': True})
        except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
            sources.append({'path': source, 'hash': None, 'valid': False})
            blockers.append({'kind': 'invalid_source', 'source': source})
    for definition in sqlite_definitions:
        sources.append({'path': 'sqlite:' + definition['name'],
                        'hash': digest('catalog', definition), 'valid': True})
    for source in sources:
        source['source_scope'] = deepcopy(bindings.get(source['path']))
    nodes, edges = [], []
    for source in sources:
        id = 'ontology-source:' + digest('source', source['path'])
        nodes.append(dict(id=id, type='document', sources=[source], git_revision=revision,
                          applicability=applicability, visibility='restricted',
                          source_scope=deepcopy(bindings.get(source['path']))))
    source_ids = [n['id'] for n in nodes]
    version, labels = None, {}
    try:
        if blockers or any(d is None for d in definitions):
            raise ContractError('Invalid source document')
        ontology = Ontology(definitions, sqlite_definitions)
        snapshot = ontology.snapshot()
        version, labels = snapshot['version'], snapshot['labels']
        for name, label in labels.items():
            for rel in label['relationships']:
                other = rel['to_label']
                subject, target = (name, other) if rel['direction'] == 'outgoing' else (other, name)
                ontology.relationship(subject, rel['type'], target)
                # Check endpoint declarations even when no property values exist.
                declarations = []
                for endpoint, peer, direction in ((subject, target, 'outgoing'), (target, subject, 'incoming')):
                    declarations += [r['properties'] for r in ontology.label(endpoint)['relationships']
                                     if r['type'] == rel['type'] and r['to_label'] == peer and r['direction'] == direction]
                if any(d != declarations[0] for d in declarations):
                    raise ConflictError('Endpoint relationship property definitions disagree')
    except (ContractError, ConflictError, ValueError, TypeError, KeyError, AttributeError) as exc:
        blockers.append({'kind': 'catalog_validation_blocker', 'message': str(exc)})
        labels = {}  # No partial authoritative catalog, no silent winner.

    # The root contains no source definitions. Traversal reaches all source nodes;
    # the root itself still needs an explicit Resource and metadata grant.
    common = dict(sources=deepcopy(sources), git_revision=revision, applicability=applicability,
                  visibility='restricted', source_scope=deepcopy(bindings.get('catalog')))
    nodes.append(dict(common, id='ontology:catalog', type='schema', ontology_version=version,
                      authoritative=not blockers, blockers=blockers))
    edges += [dict(source='ontology:catalog', type='DOCUMENTED_BY', target=id) for id in source_ids]
    for name, label in sorted(labels.items()):
        id = 'label:' + name
        nodes.append(dict(common, id=id, type='schema', name=name, definition=label,
                          ontology_version=version, policy_label=name))
        edges.append(dict(source='ontology:catalog', type='DECLARES', target=id))
        edges += [dict(source=id, type='DOCUMENTED_BY', target=sid) for sid in source_ids]
        for key, prop in sorted(label['properties'].items()):
            pid = id + '/property:' + key
            nodes.append(dict(common, id=pid, type='schema', name=name, policy_label=name,
                              definition={'properties': {key: prop}}, ontology_version=version))
            edges.append(dict(source=id, type='HAS_PROPERTY', target=pid))
        for rel in label['relationships']:
            subject, target = ((name, rel['to_label']) if rel['direction'] == 'outgoing'
                               else (rel['to_label'], name))
            rid = 'relationship:' + digest('relationship-definition', [subject, rel['type'], target, rel])
            nodes.append(dict(common, id=rid, type='schema', name=rel['type'], policy_label=rel['type'],
                              definition={'predicate': rel['type'], 'source_label': subject,
                                          'target_label': target, 'declaration': rel,
                                          'properties': {p['name']: p for p in rel['properties']}},
                              ontology_version=version))
            edges += [dict(source=id, type='DECLARES', target=rid),
                      dict(source=rid, type='SOURCE_LABEL', target='label:' + subject),
                      dict(source=rid, type='TARGET_LABEL', target='label:' + target)]
    return Projection(nodes, edges, {'domain': 'ontology', 'generated': True,
                                     'ontology_version': version, 'blockers': blockers})
