"""
scidk/schema/base.py

SciDKNode — the base class for all Label-generated node classes.

This is SciDK's custom ORM layer. It is intentionally thin:
- Provides schema metadata for tab-complete and type checking
- Drives the sanitization pipeline at write time
- Generates Cypher for MERGE operations
- Does NOT abstract Cypher as a query language
- Does NOT manage connections or sessions
- Does NOT implement relationship traversal

Why not neomodel or another graph ORM?
SciDK's Label definitions are user-defined and change at runtime.
Existing ORMs assume static schemas defined at build time and fight
dynamic class generation. The sanitization pipeline also requires
intercepting writes before they reach Neo4j — something existing ORMs
handle awkwardly via signals or subclassed property types.

This base class is ~30 lines. Generated subclasses add typed attributes
for tab-complete. The sanitization pipeline runs in to_cypher_props().
That's the whole ORM.

Usage:
    # In an interpreter:
    from scidk.schema import Sample, ImagingDataset

    dataset = ImagingDataset(
        path=str(file_path.parent),
        modality="microCT",
        voxel_size_um=5.0
    )
    result.node_created(dataset)

    # dataset.merge_cypher() returns the MERGE query and params
    # ready for neo4j_client.write_declared_nodes()
"""

from __future__ import annotations
from dataclasses import dataclass, field, fields, asdict
from typing import Any, Dict, Optional, Tuple


class SciDKNode:
    """
    Base class for all Label-generated node classes.

    Subclasses are auto-generated from Label YAML definitions by:
        scidk labels generate-stubs

    Do not instantiate SciDKNode directly — use generated subclasses.
    Do not call .save() — pass instances to result.node_created() and
    let the write pipeline handle sanitization and MERGE.

    Class attributes (set by generated subclasses):
        _label (str): Neo4j label name e.g. "Sample"
        _key_property (str): Property used for MERGE uniqueness e.g. "sample_id"
        _sanitization (dict): Sanitization rules from Label YAML definition
        _allowed_values (dict): Controlled vocabulary constraints per property
        _required (list): Property names that must not be None
    """

    _label: str = ""
    _key_property: str = ""
    _sanitization: Dict[str, Dict] = {}
    _allowed_values: Dict[str, list] = {}
    _required: list = []

    def __init__(self, **kwargs):
        """
        Set properties from keyword arguments.
        Unknown properties are stored with a raw_ prefix rather than rejected,
        matching the interpreter contract's "parse all, discard nothing" philosophy.
        """
        # Collect known properties from class annotations across the MRO
        known = set()
        for cls in type(self).__mro__:
            for name in getattr(cls, '__annotations__', {}):
                if not name.startswith('_'):
                    known.add(name)

        for key, value in kwargs.items():
            if key.startswith('_'):
                continue
            if known and key not in known:
                # Unknown property — store with raw_ prefix, don't discard
                setattr(self, f"raw_{key}", value)
            else:
                setattr(self, key, value)

    def validate(self) -> list[str]:
        """
        Validate required properties are present.
        Returns list of error strings. Empty list means valid.
        Does NOT raise — validation is separate from instantiation.
        """
        errors = []
        for prop_name in self._required:
            if getattr(self, prop_name, None) is None:
                errors.append(f"{self._label}.{prop_name} is required but not set")
        for prop_name, allowed in self._allowed_values.items():
            value = getattr(self, prop_name, None)
            if value is not None and value not in allowed:
                errors.append(
                    f"{self._label}.{prop_name} value '{value}' not in allowed values: {allowed}"
                )
        return errors

    def to_raw_props(self) -> Dict[str, Any]:
        """
        Return all non-None, non-private properties as a dict.
        This is PRE-sanitization — do not write these to Neo4j directly.
        Use to_cypher_props() for the sanitized version.
        """
        props = {}
        # Include dataclass fields if this is a dataclass subclass
        if hasattr(self.__class__, '__dataclass_fields__'):
            for f in fields(self.__class__):
                val = getattr(self, f.name, None)
                if val is not None and not f.name.startswith('_'):
                    props[f.name] = val
        else:
            # Fall back to instance __dict__ for dynamically generated classes
            for key, val in self.__dict__.items():
                if not key.startswith('_') and val is not None:
                    props[key] = val
        return props

    def to_cypher_props(self) -> Dict[str, Any]:
        """
        Apply sanitization rules and return properties ready for Neo4j write.
        This is the sanitization pipeline entry point.

        Never raises — if a sanitization rule fails, the property is passed
        through unchanged and a warning is logged. A failed sanitization
        should never prevent a scan from completing.
        """
        from scidk.schema.sanitization import apply_sanitization
        raw = self.to_raw_props()
        return apply_sanitization(raw, self._sanitization)

    def merge_cypher(self) -> Tuple[str, Dict]:
        """
        Return (cypher_string, params) for a MERGE operation.

        The returned Cypher uses MERGE on _key_property for idempotency.
        SET n += $props updates all other properties on match or create.

        Usage:
            cypher, params = node.merge_cypher()
            session.run(cypher, **params)

        Returns:
            Tuple of (cypher_string, params_dict)
        """
        if not self._label:
            raise ValueError("SciDKNode subclass must define _label")
        if not self._key_property:
            raise ValueError("SciDKNode subclass must define _key_property")

        props = self.to_cypher_props()
        key_val = props.get(self._key_property)

        if key_val is None:
            raise ValueError(
                f"{self._label}._key_property '{self._key_property}' is None after sanitization. "
                f"Key properties cannot be redacted."
            )

        # Remove key from SET props — it's in the MERGE condition
        set_props = {k: v for k, v in props.items() if k != self._key_property}

        cypher = (
            f"MERGE (n:{self._label} {{{self._key_property}: $key_val}}) "
            f"ON CREATE SET n += $props, n.created_at = timestamp() "
            f"ON MATCH SET n += $props, n.updated_at = timestamp() "
            f"RETURN elementId(n) as node_id, '{self._label}' as label, $key_val as key_val"
        )

        return cypher, {"key_val": key_val, "props": set_props}

    def to_declaration(self) -> Dict:
        """
        Return the node declaration format used by write_declared_nodes().
        This is what interpreter result.node_created() stores in the payload.

        Format matches the extended interpreter contract:
        {
            'label': 'Sample',
            'key_property': 'sample_id',
            'key_value': 'S001',
            'properties': {...sanitized...}
        }
        """
        props = self.to_cypher_props()
        key_val = props.get(self._key_property)
        set_props = {k: v for k, v in props.items() if k != self._key_property}

        return {
            'label': self._label,
            'key_property': self._key_property,
            'key_value': key_val,
            'properties': set_props,
        }

    def __repr__(self):
        props = self.to_raw_props()
        key_val = props.get(self._key_property, '?')
        return f"{self._label}({self._key_property}={key_val!r})"
