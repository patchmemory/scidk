"""
scidk/schema/registry.py

LabelRegistry — loads, caches, and validates Label YAML definitions.

The registry is the source of truth for all node schemas in SciDK.
It is consulted by:
  - sanitization.py (to get sanitization rules per label)
  - generate_stubs.py (to generate Python stub classes)
  - neo4j_client.py (to push constraints and indexes)
  - the Module Registry UI (to validate interpreter/link headers)

Label definitions live in scidk/labels/. Built-in labels ship with SciDK.
User-defined labels are added via the UI or by dropping YAML files in the
configured labels directory.

Usage:
    from scidk.schema.registry import LabelRegistry

    # Get a label definition
    label = LabelRegistry.get("Sample")

    # List all registered labels
    all_labels = LabelRegistry.all()

    # Reload from disk (after adding a new label)
    LabelRegistry.reload()
"""

from __future__ import annotations
import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PropertyDefinition:
    """Parsed property definition from Label YAML."""
    name: str
    type: str                          # string | integer | float | boolean | list
    required: bool = False
    key: bool = False                  # is this the MERGE key property?
    description: str = ""
    sanitize: str = "none"            # none | redact | hash | bin | encode | truncate
    sanitize_config: Dict = field(default_factory=dict)
    allowed_values: List = field(default_factory=list)
    default: Any = None


@dataclass
class RelationshipDefinition:
    """Parsed relationship definition from Label YAML."""
    type: str                          # relationship type e.g. PART_OF
    to_label: str                      # target node label
    direction: str = "outgoing"        # outgoing | incoming
    required: bool = False
    description: str = ""


@dataclass
class LabelDefinition:
    """Fully parsed Label definition loaded from YAML."""
    id: str
    name: str
    version: str
    description: str
    neo4j_label: str
    plural: str
    properties: Dict[str, PropertyDefinition]
    relationships: List[RelationshipDefinition]
    indexes: List[Dict]
    test_fixture: Dict
    source_path: str
    content_hash: str                  # SHA-256 of YAML content for out-of-sync detection

    @property
    def key_property(self) -> Optional[str]:
        """Return the name of the key property (used for MERGE)."""
        for prop in self.properties.values():
            if prop.key:
                return prop.name
        return None

    @property
    def sanitization_rules(self) -> Dict[str, Dict]:
        """
        Return sanitization rules in the format expected by apply_sanitization().
        Format: {'property_name': {'rule': 'bin', 'bin_size': 10, ...}}
        """
        rules = {}
        for prop_name, prop_def in self.properties.items():
            if prop_def.sanitize != 'none':
                rule_config = {'rule': prop_def.sanitize}
                rule_config.update(prop_def.sanitize_config)
                rules[prop_name] = rule_config
        return rules

    @property
    def required_properties(self) -> List[str]:
        """Return names of required properties."""
        return [name for name, prop in self.properties.items() if prop.required]

    def generate_cypher_constraints(self) -> List[str]:
        """Generate Cypher statements to create Neo4j constraints and indexes."""
        statements = []
        neo4j_label = self.neo4j_label

        for index_def in self.indexes:
            prop = index_def['property']
            index_type = index_def.get('type', 'standard')

            if index_type == 'unique':
                statements.append(
                    f"CREATE CONSTRAINT {neo4j_label.lower()}_{prop}_unique IF NOT EXISTS "
                    f"FOR (n:{neo4j_label}) REQUIRE n.{prop} IS UNIQUE"
                )
            else:
                statements.append(
                    f"CREATE INDEX {neo4j_label.lower()}_{prop}_idx IF NOT EXISTS "
                    f"FOR (n:{neo4j_label}) ON (n.{prop})"
                )

        return statements


class _LabelRegistry:
    """
    Singleton registry for Label definitions.
    Loaded once at startup, reloadable on demand.
    """

    def __init__(self):
        self._labels: Dict[str, LabelDefinition] = {}
        self._loaded = False
        self._label_dirs: List[str] = []

    def _default_label_dirs(self) -> List[str]:
        """Return default directories to search for Label YAML files."""
        module_dir = os.path.dirname(os.path.dirname(__file__))
        dirs = [
            os.path.join(module_dir, 'labels', 'builtin'),
            os.path.join(module_dir, 'labels'),
        ]
        # User-configured labels directory (from SciDK settings)
        user_dir = os.environ.get('SCIDK_LABELS_DIR')
        if user_dir and os.path.isdir(user_dir):
            dirs.append(user_dir)
        return [d for d in dirs if os.path.isdir(d)]

    def load(self, label_dirs: Optional[List[str]] = None):
        """Load all Label definitions from YAML files."""
        self._label_dirs = label_dirs or self._default_label_dirs()
        self._labels = {}

        for label_dir in self._label_dirs:
            for filename in sorted(os.listdir(label_dir)):
                if not filename.endswith('.yaml') and not filename.endswith('.yml'):
                    continue
                filepath = os.path.join(label_dir, filename)
                try:
                    label_def = self._parse_yaml(filepath)
                    if label_def:
                        self._labels[label_def.neo4j_label] = label_def
                        logger.debug(f"Loaded label: {label_def.neo4j_label} from {filepath}")
                except Exception as e:
                    logger.error(f"Failed to load label from {filepath}: {e}")

        self._loaded = True
        logger.info(f"LabelRegistry loaded {len(self._labels)} labels")

    def reload(self):
        """Reload all labels from disk. Use after adding or changing Label definitions."""
        self._loaded = False
        self.load(self._label_dirs or None)

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def get(self, label_name: str) -> Optional[LabelDefinition]:
        """Get a label definition by Neo4j label name. Returns None if not found."""
        self._ensure_loaded()
        return self._labels.get(label_name)

    def all(self) -> Dict[str, LabelDefinition]:
        """Return all registered label definitions."""
        self._ensure_loaded()
        return dict(self._labels)

    def register(self, label_def: LabelDefinition):
        """Register a label definition programmatically (e.g. from tests)."""
        self._labels[label_def.neo4j_label] = label_def
        self._loaded = True

    def _parse_yaml(self, filepath: str) -> Optional[LabelDefinition]:
        """Parse a Label YAML file into a LabelDefinition."""
        with open(filepath, 'r') as f:
            content = f.read()

        data = yaml.safe_load(content)
        if not data:
            return None

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Parse properties
        properties = {}
        for prop_name, prop_data in data.get('properties', {}).items():
            properties[prop_name] = PropertyDefinition(
                name=prop_name,
                type=prop_data.get('type', 'string'),
                required=prop_data.get('required', False),
                key=prop_data.get('key', False),
                description=prop_data.get('description', ''),
                sanitize=prop_data.get('sanitize', 'none'),
                sanitize_config=prop_data.get('sanitize_config', {}),
                allowed_values=prop_data.get('allowed_values', []),
                default=prop_data.get('default'),
            )

        # Parse relationships
        relationships = []
        for rel_data in data.get('relationships', []):
            relationships.append(RelationshipDefinition(
                type=rel_data['type'],
                to_label=rel_data['to_label'],
                direction=rel_data.get('direction', 'outgoing'),
                required=rel_data.get('required', False),
                description=rel_data.get('description', ''),
            ))

        return LabelDefinition(
            id=data['id'],
            name=data['name'],
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            neo4j_label=data.get('neo4j_label', data['name']),
            plural=data.get('plural', data['name'] + 's'),
            properties=properties,
            relationships=relationships,
            indexes=data.get('indexes', []),
            test_fixture=data.get('test_fixture', {}),
            source_path=filepath,
            content_hash=content_hash,
        )


# Singleton instance
LabelRegistry = _LabelRegistry()
