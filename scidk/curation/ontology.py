"""Read-only, explicit reconciliation of YAML and LabelService snapshots.

Callers supply snapshots; this module never opens LabelService's live database.
Load YAML files independently, rather than using the last-definition-wins registry.
"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from scidk.schema.registry import _LabelRegistry
from .contracts import ConflictError, ContractError, canonical, digest, identifier


def _property(raw):
    identifier(raw['name'])
    if raw['type'] not in {'string', 'integer', 'float', 'boolean', 'list'}:
        raise ContractError('Unsupported property type')
    # Preserve all constraints, including sanitization, in comparison and revision.
    result = dict(raw)
    for key, default in {'required': False, 'key': False, 'description': '',
                         'sanitize': 'none', 'sanitize_config': {},
                         'allowed_values': [], 'default': None}.items():
        result.setdefault(key, deepcopy(default))
    return result


def _label(name, properties, relationships, indexes):
    identifier(name)
    props = {}
    for raw in properties:
        prop = _property(raw)
        if prop['name'] in props:
            raise ConflictError('Duplicate property definition')
        props[prop['name']] = prop
    rels = []
    for raw in relationships:
        rel = dict(raw)
        if 'target_label' in rel:
            if 'to_label' in rel and rel['to_label'] != rel['target_label']:
                raise ConflictError('Ambiguous relationship target')
            rel['to_label'] = rel.pop('target_label')
        identifier(rel['type'])
        identifier(rel['to_label'])
        rel.setdefault('direction', 'outgoing')
        rel.setdefault('required', False)
        rel.setdefault('description', '')
        rel.setdefault('properties', [])
        rel['properties'] = sorted([_property(p) for p in rel['properties']], key=canonical)
        if rel['direction'] not in {'outgoing', 'incoming'}:
            raise ContractError('Invalid relationship direction')
        rels.append(rel)
    return {'name': name, 'properties': props,
            'relationships': sorted(rels, key=canonical), 'indexes': sorted(indexes, key=canonical)}


class Ontology:
    def __init__(self, yaml_definitions, sqlite_definitions):
        labels, sources = {}, []
        for definition in yaml_definitions:
            label = _label(definition.neo4j_label,
                           [asdict(p) for p in definition.properties.values()],
                           [asdict(r) for r in definition.relationships], definition.indexes)
            self._merge(labels, label)
            sources.append({'source': definition.source_path, 'hash': definition.content_hash})
        for definition in sqlite_definitions:
            props = deepcopy(definition.get('properties', []))
            matching_key = definition.get('matching_key')
            if matching_key:
                if matching_key not in {p['name'] for p in props}:
                    raise ConflictError('Matching key is not declared')
                for prop in props:
                    if prop['name'] == matching_key:
                        prop['key'] = True
            label = _label(definition['name'], props, definition.get('relationships', []),
                           definition.get('indexes', []))
            self._merge(labels, label)
            sources.append({'source': 'sqlite:' + definition['name'], 'hash': digest('catalog', definition)})
        self._labels = deepcopy(labels)
        self._sources = sorted(sources, key=canonical)
        self.version = digest('ontology', {'labels': labels, 'sources': self._sources})

    @staticmethod
    def _merge(labels, label):
        name = label['name']
        if name in labels and labels[name] != label:
            raise ConflictError('Ontology catalogs disagree; administrator reconciliation required')
        labels[name] = label

    @classmethod
    def from_yaml_paths(cls, paths, sqlite_definitions):
        parser = _LabelRegistry()
        definitions = []
        for path in sorted(map(Path, paths)):
            definition = parser._parse_yaml(str(path))
            if definition is None:
                raise ContractError('Empty ontology document')
            definitions.append(definition)
        return cls(definitions, sqlite_definitions)

    def snapshot(self):
        return deepcopy({'version': self.version, 'labels': self._labels, 'sources': self._sources})

    def label(self, name):
        identifier(name)
        if name not in self._labels:
            raise ContractError('Undeclared label; catalog reconciliation required')
        return deepcopy(self._labels[name])

    def property(self, label, key, value):
        prop = self.label(label)['properties'].get(identifier(key))
        self._validate_property(prop, value)
        return prop

    @staticmethod
    def _validate_property(prop, value):
        if prop is None:
            raise ContractError('Undeclared property')
        types = {'string': (str,), 'integer': (int,), 'float': (int, float),
                 'boolean': (bool,), 'list': (list,)}
        if type(value) not in types[prop['type']]:
            raise ContractError('Incorrect property type')
        canonical(value)  # Also reject NaN/Infinity inside lists.
        if prop['allowed_values'] and value not in prop['allowed_values']:
            raise ContractError('Value outside declared vocabulary')

    def relationship(self, subject_label, predicate, object_label):
        identifier(predicate)
        self.label(object_label)
        subject = self.label(subject_label)
        target = self.label(object_label)
        if any(r['type'] == predicate and r['to_label'] == object_label and r['direction'] == 'outgoing'
               for r in subject['relationships']):
            return
        if any(r['type'] == predicate and r['to_label'] == subject_label and r['direction'] == 'incoming'
               for r in target['relationships']):
            return
        raise ContractError('Undeclared relationship or invalid endpoint direction')

    def relationship_property(self, subject_label, predicate, object_label, key, value):
        self.relationship(subject_label, predicate, object_label)
        definitions = []
        for label, other, direction in ((subject_label, object_label, 'outgoing'),
                                         (object_label, subject_label, 'incoming')):
            for rel in self.label(label)['relationships']:
                if rel['type'] == predicate and rel['to_label'] == other and rel['direction'] == direction:
                    definitions.append(rel['properties'])
        if any(definition != definitions[0] for definition in definitions):
            raise ConflictError('Endpoint relationship property definitions disagree')
        prop = next((p for p in definitions[0] if p['name'] == key), None)
        self._validate_property(prop, value)
        return prop
