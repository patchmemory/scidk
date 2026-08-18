"""Turn a row stream into node and relationship declarations.

This is the half of ETL that plugins do not own. A plugin yields raw
``{column: value}`` dicts (:meth:`~scidk.pipeline.plugin_base.DataSourcePlugin.fetch`);
a mapping config says what those columns *mean*; this module applies the one to
the other and produces declarations
:meth:`~scidk.services.neo4j_client.Neo4jClient.write_declared_nodes` accepts.

The config format is specified by ``mapping_schema.json``, next to this file, and
``plugins/sharepoint_intake/configs/aipt_intake_mapping.json`` is the reference
instance. Two forms of node mapping exist because two shapes of source column
exist:

* **Column-per-property** — ``properties: [{name, column, transform}]``. One
  column, one property.
* **Transform-per-node** — ``source: {column, transform}`` plus
  ``property_map``. One column expands into several properties, because
  ``"Jane Smith <j@mit.edu>"`` is a name *and* an address.

Two guarantees this module owes the rest of the Pipeline
--------------------------------------------------------
**Nothing unsafe reaches Cypher.** ``write_declared_nodes`` interpolates labels,
relationship types and property *names* into the query string unquoted, so every
identifier a config names is checked against
:mod:`scidk.pipeline.identifiers` at :meth:`MappingEngine.validate` time —
before a single row is read, because these names come from config and not from
data, and so cannot become invalid mid-run.

**A bad cell never aborts a run.** A :class:`~scidk.pipeline.transforms.TransformError`
is caught, attributed to its row index and property name, and recorded on the
:class:`RowMapping`. The default ``on_row_error`` is ``record_and_continue``; the
runner decides what to do with the record.
"""
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from .identifiers import check_identifier
from .transforms import CORE_TRANSFORMS, TransformError

__all__ = [
    "DeclarationCollector",
    "MappingConfigError",
    "MappingEngine",
    "ResolvedNode",
    "RowMapping",
    "ValidationReport",
    "load_mapping_schema",
    "validate_against_schema",
]

#: Path to the JSON Schema this module's configs conform to.
SCHEMA_PATH = Path(__file__).with_name("mapping_schema.json")

#: A ``transform_args`` key whose *value* names a source column, by convention:
#: exactly ``column``/``columns``, or any key ending in ``_col``/``_column``
#: (``prefer_col``, ``fallback_column``). Used only to report missing columns by
#: name — never to resolve a value, which is always the transform's own job. A
#: transform taking a column name under some other key still works; its column
#: just will not appear in the missing-column report.
_COLUMN_ARG_NAMES = frozenset({"column", "columns"})
_COLUMN_ARG_SUFFIXES = ("_col", "_column", "_cols", "_columns")

#: ``{Placeholder}`` in a fallback template. Deliberately not ``str.format``:
#: a template is user-supplied, and ``format`` would expose attribute and index
#: access, and raise on a column the row happens not to have.
_TEMPLATE_FIELD_RE = re.compile(r"\{([^{}]+)\}")

#: Row index made available to fallback templates, so a synthesized key can be
#: made unique without inventing randomness (which would break re-runs).
ROW_INDEX_PLACEHOLDER = "__row_index__"

#: Sentinel for "this property was never assigned", distinct from "assigned
#: None". Only the latter is a resolved-but-empty property.
_UNSET = object()


class MappingConfigError(ValueError):
    """The mapping config cannot be used. Raised before any row is read."""


def load_mapping_schema() -> Dict[str, Any]:
    """Return the parsed contents of ``mapping_schema.json``."""
    return _load_schema_cached()


@lru_cache(maxsize=1)
def _load_schema_cached() -> Dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_against_schema(config: Mapping[str, Any]) -> List[str]:
    """Structurally validate ``config`` against ``mapping_schema.json``.

    Args:
        config: The parsed mapping config.

    Returns:
        Human-readable messages, each naming the JSON path that failed. Empty
        when the config is structurally valid.

    Raises:
        MappingConfigError: ``jsonschema`` is not installed. Structural
            validation is a declared dependency of the Pipeline, not an optional
            nicety — silently skipping it would turn a typo back into the runtime
            surprise this schema exists to prevent.
    """
    try:
        import jsonschema
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise MappingConfigError(
            "jsonschema is required to validate a mapping config; "
            "install it (it is in requirements.txt)"
        ) from e

    validator = jsonschema.Draft202012Validator(_load_schema_cached())
    errors = []
    for err in sorted(validator.iter_errors(dict(config)), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{location}: {err.message}")
    return errors


@dataclass
class ValidationReport:
    """Outcome of validating a mapping config. ``ok`` gates a run."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


@dataclass(frozen=True)
class ResolvedNode:
    """One node a single row produced, ready to declare.

    Attributes:
        mapping_id: ``id`` of the ``node_mappings`` entry that produced it. Two
            roles can share a label, so this — not the label — identifies which
            relationship endpoints it satisfies.
        label: Validated Cypher label.
        key_property: The property MERGE keys on, chosen from the mapping's
            ``key_property`` preference order by what this row actually filled.
        properties: Property name → value, including the key.
    """

    mapping_id: str
    label: str
    key_property: str
    properties: Dict[str, Any]

    @property
    def key_value(self) -> Any:
        return self.properties[self.key_property]

    @property
    def match(self) -> Dict[str, Any]:
        """The ``from_match``/``to_match`` dict identifying this node."""
        return {self.key_property: self.key_value}

    def to_decl(self) -> Dict[str, Any]:
        """The ``write_declared_nodes`` node declaration for this node."""
        return {
            "label": self.label,
            "key_property": self.key_property,
            "properties": dict(self.properties),
        }

    def identity(self) -> Tuple[str, str, str]:
        """Dedup key: label plus merge key, per ``deduplicate_nodes_by``."""
        return (self.label, self.key_property, str(self.key_value))


@dataclass
class RowMapping:
    """What one row produced, including what went wrong with it.

    A row with errors may still have produced nodes — a failed optional Person
    does not invalidate the Project on the same row. ``skipped`` means the row
    produced nothing at all because ``row_filter`` rejected it.
    """

    row_index: int
    nodes: List[ResolvedNode] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None


def _is_empty(value: Any) -> bool:
    """Whether a resolved value should be treated as absent.

    ``0`` and ``False`` are values, not absences — a count of zero and a "No"
    answer are both data worth writing.
    """
    if value is _UNSET or value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _normalize(value: Any) -> Any:
    """Strip surrounding whitespace off raw string cells.

    Deliberate, and not the plugin's job: the plugin's contract is to yield the
    source verbatim. But ``"CAC-2024-0042 "`` and ``"CAC-2024-0042"`` are the
    same protocol, and merging on the unstripped form would create two Projects.
    """
    if isinstance(value, str):
        return value.strip()
    return value


class DeclarationCollector:
    """Accumulate resolved nodes and relationships, deduplicated.

    Implements ``options.deduplicate_nodes_by: ["label", "key"]``: when the
    submitter and PI columns of one row resolve to the same address, that is one
    Person with two relationships, not two Persons.

    Properties are *merged* rather than overwritten — a second sighting of a node
    fills in properties the first sighting left empty but never replaces a value
    already present. Two sightings of the same key with genuinely conflicting
    values are reported in :attr:`conflicts` rather than silently resolved, since
    which one is right is a data question the Pipeline cannot answer.

    Memory is proportional to the number of *distinct* nodes, not to the number
    of rows, so a source larger than RAM still collects — but a source with a
    distinct key per row does not. Flush in batches for those; see
    :meth:`drain`.
    """

    def __init__(self) -> None:
        self._nodes: Dict[Tuple[str, str, str], ResolvedNode] = {}
        self._node_order: List[Tuple[str, str, str]] = []
        self._rels: Dict[str, Dict[str, Any]] = {}
        self.conflicts: List[str] = []

    def add_row(self, mapping: RowMapping) -> None:
        for node in mapping.nodes:
            self.add_node(node)
        for rel in mapping.relationships:
            self.add_relationship(rel)

    def add_node(self, node: ResolvedNode) -> None:
        identity = node.identity()
        existing = self._nodes.get(identity)
        if existing is None:
            self._nodes[identity] = node
            self._node_order.append(identity)
            return
        merged = dict(existing.properties)
        for key, value in node.properties.items():
            if _is_empty(value):
                continue
            current = merged.get(key, _UNSET)
            if _is_empty(current):
                merged[key] = value
            elif current != value:
                self.conflicts.append(
                    f"{node.label}({node.key_property}={node.key_value!r}): "
                    f"property {key!r} seen as {current!r} and {value!r}; kept {current!r}"
                )
        self._nodes[identity] = ResolvedNode(
            existing.mapping_id, existing.label, existing.key_property, merged
        )

    def add_relationship(self, rel: Mapping[str, Any]) -> None:
        self._rels.setdefault(_rel_identity(rel), dict(rel))

    def node_decls(self) -> List[Dict[str, Any]]:
        return [self._nodes[i].to_decl() for i in self._node_order]

    def relationship_decls(self) -> List[Dict[str, Any]]:
        return list(self._rels.values())

    def __len__(self) -> int:
        return len(self._nodes) + len(self._rels)

    def drain(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return the accumulated declarations and reset, keeping conflicts.

        For batched writes. MERGE is idempotent, so a node re-collected in a
        later batch is written again harmlessly; a relationship whose endpoints
        were written in an earlier batch still MATCHes them, because every write
        autocommits.
        """
        nodes, rels = self.node_decls(), self.relationship_decls()
        self._nodes.clear()
        self._node_order.clear()
        self._rels.clear()
        return nodes, rels


def _rel_identity(rel: Mapping[str, Any]) -> str:
    """Stable dedup key for a relationship declaration."""
    return json.dumps(
        [
            rel.get("type"),
            rel.get("from_label"),
            sorted((str(k), str(v)) for k, v in (rel.get("from_match") or {}).items()),
            rel.get("to_label"),
            sorted((str(k), str(v)) for k, v in (rel.get("to_match") or {}).items()),
        ],
        sort_keys=True,
        default=str,
    )


class MappingEngine:
    """Applies one mapping config to a row stream.

    Stateless across rows: :meth:`map_row` reads only its arguments, so rows can
    be mapped in any order and a failure on one cannot corrupt another.

    Args:
        config: The parsed mapping config.
        transform_library: The plugin's transforms, from
            :meth:`~scidk.pipeline.plugin_base.DataSourcePlugin.transform_library`.
            Layered over :data:`~scidk.pipeline.transforms.CORE_TRANSFORMS`; a
            plugin shadowing a core name is reported as a warning by
            :meth:`validate`, not silently accepted.
        vocabulary: Allowed terms per field, overriding the config's
            ``default_vocabulary``. This is where a deployment injects the
            vocabulary list it pulled from SharePoint.
    """

    def __init__(
        self,
        config: Mapping[str, Any],
        transform_library: Optional[Mapping[str, Callable]] = None,
        vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        if not isinstance(config, Mapping):
            raise MappingConfigError(
                f"mapping config must be a JSON object, got {type(config).__name__}"
            )
        self.config: Dict[str, Any] = dict(config)
        self._plugin_transforms: Dict[str, Callable] = dict(transform_library or {})
        self.transforms: Dict[str, Callable] = {**CORE_TRANSFORMS, **self._plugin_transforms}

        self.node_mappings: List[Dict[str, Any]] = list(self.config.get("node_mappings") or [])
        self.relationship_mappings: List[Dict[str, Any]] = list(
            self.config.get("relationship_mappings") or []
        )
        self.options: Dict[str, Any] = dict(self.config.get("options") or {})
        self._nodes_by_id: Dict[str, Dict[str, Any]] = {}
        for mapping in self.node_mappings:
            mapping_id = mapping.get("id")
            if isinstance(mapping_id, str):
                self._nodes_by_id.setdefault(mapping_id, mapping)

        self._vocabulary = self._build_vocabulary(vocabulary)
        #: Identifiers already checked against :mod:`scidk.pipeline.identifiers`.
        #: The check is repeated on the write path so "nothing unsafe reaches
        #: Cypher" holds even when a caller skipped validate(); memoizing keeps
        #: that from being a regex match per property per row.
        self._approved_identifiers: Set[str] = set()

    # ------------------------------------------------------------- options

    @property
    def omit_empty_properties(self) -> bool:
        """Whether an empty property is left off the node. Defaults to True."""
        return bool(self.options.get("omit_empty_properties", True))

    @property
    def abort_on_row_error(self) -> bool:
        """Whether the runner should stop at the first failing row."""
        return str(self.options.get("on_row_error") or "record_and_continue") == "abort"

    # ---------------------------------------------------------- validation

    def validate(self) -> ValidationReport:
        """Check the config structurally and semantically. No rows are read.

        Structural checks come from ``mapping_schema.json``. The semantic ones
        cannot be expressed in JSON Schema: that relationship endpoints name
        node mappings that exist, that every transform name resolves, that a
        ``key_property`` is a property the mapping actually declares.

        Identifiers are re-checked here even though the schema constrains their
        pattern, so the guarantee that nothing unsafe reaches Cypher does not
        depend on which validation layer ran.

        Returns:
            ValidationReport: ``ok`` is False if the config must not be run.
        """
        report = ValidationReport()
        report.errors.extend(validate_against_schema(self.config))

        seen_ids: Set[str] = set()
        for index, mapping in enumerate(self.node_mappings):
            where = f"node_mappings[{index}]"
            mapping_id = mapping.get("id")
            if not isinstance(mapping_id, str) or not mapping_id:
                report.errors.append(f"{where}: 'id' is required")
            elif mapping_id in seen_ids:
                report.errors.append(
                    f"{where}: duplicate id {mapping_id!r} — relationship_mappings "
                    "reference nodes by id, so ids must be unique"
                )
            else:
                seen_ids.add(mapping_id)
            self._validate_node_mapping(mapping, where, report)

        for index, rel in enumerate(self.relationship_mappings):
            where = f"relationship_mappings[{index}]"
            problem = check_identifier(rel.get("type"), "relationship type")
            if problem:
                report.errors.append(f"{where}: {problem}")
            for end in ("from", "to"):
                ref = rel.get(end)
                if ref not in self._nodes_by_id:
                    report.errors.append(
                        f"{where}: {end!r} references node mapping {ref!r}, which is not declared"
                    )

        self._validate_vocabulary(report)

        shadowed = sorted(set(self._plugin_transforms) & set(CORE_TRANSFORMS))
        for name in shadowed:
            report.warnings.append(
                f"plugin transform {name!r} shadows the core transform of the same name; "
                "the plugin's version will be used"
            )
        return report

    def _validate_node_mapping(
        self, mapping: Mapping[str, Any], where: str, report: ValidationReport
    ) -> None:
        problem = check_identifier(mapping.get("label"), "label")
        if problem:
            report.errors.append(f"{where}: {problem}")

        declared = self._declared_property_names(mapping)
        for name in sorted(declared):
            problem = check_identifier(name, "property name")
            if problem:
                report.errors.append(f"{where}: {problem}")

        keys = mapping.get("key_property")
        key_list = [keys] if isinstance(keys, str) else list(keys or [])
        if not key_list:
            report.errors.append(f"{where}: 'key_property' is required")
        for key in key_list:
            problem = check_identifier(key, "key_property")
            if problem:
                report.errors.append(f"{where}: {problem}")
            elif key not in declared:
                report.errors.append(
                    f"{where}: key_property {key!r} is not among the properties this "
                    f"mapping declares ({sorted(declared)})"
                )

        for name in mapping.get("skip_when_all_empty") or []:
            if name not in declared:
                report.errors.append(
                    f"{where}: skip_when_all_empty names {name!r}, which this mapping "
                    "does not declare as a property"
                )

        if mapping.get("cardinality") == "many" and "source" not in mapping:
            report.errors.append(
                f"{where}: cardinality 'many' requires the 'source'/'property_map' form — "
                "a column-per-property mapping can only produce one node per row"
            )

        for name, arg_where in self._transform_names(mapping):
            if name not in self.transforms:
                report.errors.append(
                    f"{where}.{arg_where}: unknown transform {name!r}. Available: "
                    f"{sorted(self.transforms)}"
                )

    def _validate_vocabulary(self, report: ValidationReport) -> None:
        check = self.config.get("vocabulary_check") or {}
        if not check:
            return
        transform = check.get("multi_value_transform")
        if transform and transform not in self.transforms:
            report.errors.append(
                f"vocabulary_check.multi_value_transform: unknown transform {transform!r}"
            )
        all_props: Set[str] = set()
        for mapping in self.node_mappings:
            all_props |= self._declared_property_names(mapping)
        for field_name in check.get("fields") or []:
            if field_name not in all_props:
                report.warnings.append(
                    f"vocabulary_check.fields names {field_name!r}, which no node mapping "
                    "declares as a property — it will never be checked"
                )

    @staticmethod
    def _declared_property_names(mapping: Mapping[str, Any]) -> Set[str]:
        """Property names a node mapping produces, in either form."""
        if mapping.get("properties"):
            return {
                spec.get("name")
                for spec in mapping["properties"]
                if isinstance(spec, Mapping) and spec.get("name")
            }
        return {v for v in (mapping.get("property_map") or {}).values() if v}

    def unknown_transforms(self) -> List[Tuple[str, str]]:
        """Transform names the config uses that neither library supplies.

        Returns:
            ``(name, where)`` pairs. Empty means the run is reproducible from the
            config plus the transform libraries alone — the Pipeline's R.
        """
        unknown: List[Tuple[str, str]] = []
        for index, mapping in enumerate(self.node_mappings):
            label = mapping.get("id") or f"node_mappings[{index}]"
            for name, where in self._transform_names(mapping):
                if name not in self.transforms:
                    unknown.append((name, f"{label}.{where}"))
        splitter = (self.config.get("vocabulary_check") or {}).get("multi_value_transform")
        if splitter and splitter not in self.transforms:
            unknown.append((splitter, "vocabulary_check.multi_value_transform"))
        return unknown

    @staticmethod
    def _transform_names(mapping: Mapping[str, Any]) -> Iterator[Tuple[str, str]]:
        """Every transform a node mapping names, with where it was named."""
        for index, spec in enumerate(mapping.get("properties") or []):
            if not isinstance(spec, Mapping):
                continue
            if spec.get("transform"):
                yield spec["transform"], f"properties[{index}].transform"
            fallback = spec.get("fallback") or {}
            if fallback.get("transform"):
                yield fallback["transform"], f"properties[{index}].fallback.transform"
        source = mapping.get("source") or {}
        if source.get("transform"):
            yield source["transform"], "source.transform"
        if (source.get("fallback") or {}).get("transform"):
            yield source["fallback"]["transform"], "source.fallback.transform"

    # ------------------------------------------------------------- columns

    def mapped_columns(self) -> Set[str]:
        """Every source column this config reads, by name.

        Used to report missing columns before a run rather than discovering them
        as empty properties afterwards. Includes columns named indirectly through
        ``transform_args`` (see :data:`_COLUMN_ARG_NAMES`) and inside fallback
        templates.
        """
        columns: Set[str] = set()

        for column in (self.config.get("row_filter") or {}).get("require_any_non_empty") or []:
            columns.add(column)

        for mapping in self.node_mappings:
            condition = mapping.get("condition") or {}
            if condition.get("column"):
                columns.add(condition["column"])

            for spec in mapping.get("properties") or []:
                if not isinstance(spec, Mapping):
                    continue
                columns |= self._columns_from_spec(spec)
                fallback = spec.get("fallback") or {}
                columns |= self._columns_from_spec(fallback)
                if fallback.get("template"):
                    columns |= {
                        name
                        for name in _TEMPLATE_FIELD_RE.findall(fallback["template"])
                        if name != ROW_INDEX_PLACEHOLDER
                    }

            source = mapping.get("source") or {}
            columns |= self._columns_from_spec(source)
            columns |= self._columns_from_spec(source.get("fallback") or {})

        return {c for c in columns if isinstance(c, str) and c}

    @staticmethod
    def _columns_from_spec(spec: Mapping[str, Any]) -> Set[str]:
        """Columns named directly by ``column`` or indirectly in ``transform_args``."""
        columns: Set[str] = set()
        if spec.get("column"):
            columns.add(spec["column"])
        for key, value in (spec.get("transform_args") or {}).items():
            names = key in _COLUMN_ARG_NAMES or key.endswith(_COLUMN_ARG_SUFFIXES)
            if not names:
                continue
            if isinstance(value, str):
                columns.add(value)
            elif isinstance(value, (list, tuple)):
                columns |= {v for v in value if isinstance(v, str)}
        return columns

    def missing_columns(self, available: Iterable[str]) -> List[str]:
        """Mapped columns absent from ``available``, sorted, by name.

        Args:
            available: Column names the source actually has, from
                :meth:`~scidk.pipeline.plugin_base.DataSourcePlugin.find`.
        """
        have = set(available or [])
        return sorted(self.mapped_columns() - have)

    def column_problems(self, available: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Split absent columns into the ones that break a run and the rest.

        Not every missing column is fatal, and treating them alike would refuse to
        run a config that is merely broader than one particular export. A mapping
        config written for a SharePoint list that also carries legacy ``_orig``
        columns still works against an export that dropped them: those properties
        are simply omitted.

        A missing column blocks the run when it makes a node impossible rather
        than incomplete:

        * every column that could fill a ``required`` property is gone (unless the
          property has a template fallback, which always yields *something*);
        * every column that could fill any ``key_property`` candidate is gone, so
          no merge key can ever resolve — fatal for a required node, merely
          informative for an ``optional`` one, which is then just absent;
        * every ``row_filter`` column is gone, so every row would be rejected and
          the run would read the whole source and write nothing.

        Args:
            available: Column names the source actually has.

        Returns:
            ``(blocking, informational)`` — both lists of human-readable messages.
        """
        have = set(available or [])
        missing = self.mapped_columns() - have
        if not missing:
            return [], []

        blocking: List[str] = []
        informational: List[str] = []

        filter_columns = set(
            (self.config.get("row_filter") or {}).get("require_any_non_empty") or []
        )
        if filter_columns and filter_columns <= missing:
            blocking.append(
                f"row_filter requires a non-empty value in {sorted(filter_columns)}, and none "
                "of those columns exist — every row would be rejected"
            )

        for index, mapping in enumerate(self.node_mappings):
            mapping_id = mapping.get("id") or f"node_mappings[{index}]"
            per_property = self._property_columns(mapping)

            for spec in mapping.get("properties") or []:
                if not isinstance(spec, Mapping) or not spec.get("required"):
                    continue
                if (spec.get("fallback") or {}).get("template"):
                    continue  # a template always resolves to a non-empty string
                sources = per_property.get(spec.get("name")) or set()
                if sources and sources <= missing:
                    blocking.append(
                        f"{mapping_id}.{spec.get('name')} is required but every column that "
                        f"could fill it is absent: {sorted(sources)}"
                    )

            keys = mapping.get("key_property")
            key_names = [keys] if isinstance(keys, str) else list(keys or [])
            key_columns: Set[str] = set()
            for name in key_names:
                key_columns |= per_property.get(name) or set()
            if key_columns and key_columns <= missing:
                message = (
                    f"{mapping_id} can never resolve a merge key: every column feeding "
                    f"key_property {key_names} is absent: {sorted(key_columns)}"
                )
                if mapping.get("optional"):
                    informational.append(f"{message} — the node will simply not be created")
                else:
                    blocking.append(message)

        for column in sorted(missing):
            informational.append(
                f"column {column!r} is mapped but not present in the source; "
                "the properties it feeds will be omitted"
            )
        return blocking, informational

    def property_columns(self) -> Dict[str, Dict[str, List[str]]]:
        """``{mapping_id: {property_name: [column, ...]}}`` for the whole config.

        Which columns feed which property, which is the question a failure report
        has to answer: the engine attributes a transform error to a *property*,
        and the user is looking at a spreadsheet of *columns*. More than one column
        per property because of fallbacks, and because a transform may name its
        columns in ``transform_args`` rather than taking a ``column`` of its own.
        """
        out: Dict[str, Dict[str, List[str]]] = {}
        for index, mapping in enumerate(self.node_mappings):
            mapping_id = str(mapping.get("id") or f"node_mappings[{index}]")
            out[mapping_id] = {
                name: sorted(columns)
                for name, columns in self._property_columns(mapping).items()
            }
        return out

    def _property_columns(self, mapping: Mapping[str, Any]) -> Dict[str, Set[str]]:
        """Property name → every column that could fill it.

        More than one because of fallbacks, and because a transform may name its
        columns in ``transform_args`` rather than taking a ``column`` of its own.
        """
        per_property: Dict[str, Set[str]] = {}

        for spec in mapping.get("properties") or []:
            if not isinstance(spec, Mapping) or not spec.get("name"):
                continue
            fallback = spec.get("fallback") or {}
            columns = self._columns_from_spec(spec) | self._columns_from_spec(fallback)
            if fallback.get("template"):
                columns |= {
                    name
                    for name in _TEMPLATE_FIELD_RE.findall(fallback["template"])
                    if name != ROW_INDEX_PLACEHOLDER
                }
            per_property[spec["name"]] = columns

        source = mapping.get("source") or {}
        if source:
            # One column feeds every property the transform's output maps onto.
            shared = self._columns_from_spec(source) | self._columns_from_spec(
                source.get("fallback") or {}
            )
            for target in (mapping.get("property_map") or {}).values():
                per_property[target] = set(shared)

        return per_property

    # --------------------------------------------------------------- rows

    def map_rows(self, rows: Iterable[Mapping[str, Any]], start_index: int = 0) -> Iterator[RowMapping]:
        """Map a row stream lazily, one :class:`RowMapping` per input row."""
        for offset, row in enumerate(rows):
            yield self.map_row(row, start_index + offset)

    def map_row(self, row: Mapping[str, Any], row_index: int = 0) -> RowMapping:
        """Map one raw row onto nodes and relationships.

        Args:
            row: A raw ``{column: value}`` dict as the plugin yielded it.
            row_index: Position in the stream, used in messages and available to
                fallback templates as ``{__row_index__}``.

        Returns:
            RowMapping: nodes, relationships, and anything that went wrong.
            Never raises for bad data — that is what ``errors`` is for.
        """
        result = RowMapping(row_index=row_index)
        row = row if isinstance(row, Mapping) else {}

        rejection = self._row_filter_rejection(row)
        if rejection is not None:
            result.skipped = True
            result.skip_reason = rejection
            on_reject = (self.config.get("row_filter") or {}).get("on_reject")
            if str(on_reject or "record_error") == "record_error":
                result.errors.append(f"row {row_index}: {rejection}")
            return result

        by_mapping: Dict[str, List[ResolvedNode]] = {}
        for index, mapping in enumerate(self.node_mappings):
            mapping_id = mapping.get("id")
            if not isinstance(mapping_id, str) or not mapping_id:
                result.errors.append(
                    f"row {row_index}: node_mappings[{index}] has no 'id'; skipped"
                )
                continue
            nodes = self._resolve_node_mapping(mapping, mapping_id, row, row_index, result)
            if nodes:
                by_mapping[mapping_id] = nodes
                result.nodes.extend(nodes)

        for rel in self.relationship_mappings:
            for source_node in by_mapping.get(rel.get("from"), ()):
                for target_node in by_mapping.get(rel.get("to"), ()):
                    result.relationships.append({
                        "type": rel["type"],
                        "from_label": source_node.label,
                        "from_match": source_node.match,
                        "to_label": target_node.label,
                        "to_match": target_node.match,
                    })

        return result

    def _row_filter_rejection(self, row: Mapping[str, Any]) -> Optional[str]:
        """Reason ``row_filter`` rejects this row, or None to keep it."""
        row_filter = self.config.get("row_filter") or {}
        required = row_filter.get("require_any_non_empty") or []
        if not required:
            return None
        if any(not _is_empty(_normalize(row.get(column))) for column in required):
            return None
        return str(
            row_filter.get("error_message")
            or f"no non-empty value in any of {list(required)}"
        )

    # ----------------------------------------------------- node resolution

    def _resolve_node_mapping(
        self,
        mapping: Mapping[str, Any],
        mapping_id: str,
        row: Mapping[str, Any],
        row_index: int,
        result: RowMapping,
    ) -> List[ResolvedNode]:
        """Resolve one ``node_mappings`` entry against one row."""
        condition = mapping.get("condition")
        if condition and not self._condition_holds(condition, row):
            return []

        if mapping.get("properties"):
            candidates = self._properties_form(mapping, mapping_id, row, row_index, result)
        else:
            candidates = self._source_form(mapping, mapping_id, row, row_index, result)

        nodes: List[ResolvedNode] = []
        for props in candidates:
            node = self._finalize(mapping, mapping_id, props, row_index, result)
            if node is not None:
                nodes.append(node)
        return nodes

    @staticmethod
    def _condition_holds(condition: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
        """Whether a ``condition`` matches, comparing as strings when both are text."""
        actual = _normalize(row.get(condition.get("column")))
        expected = condition.get("equals")
        if isinstance(expected, str) and isinstance(actual, str):
            return actual.casefold() == expected.strip().casefold()
        return actual == expected

    def _properties_form(
        self,
        mapping: Mapping[str, Any],
        mapping_id: str,
        row: Mapping[str, Any],
        row_index: int,
        result: RowMapping,
    ) -> List[Dict[str, Any]]:
        """Column-per-property form: at most one node per row."""
        props: Dict[str, Any] = {}
        for spec in mapping["properties"]:
            name = spec.get("name")
            try:
                value = self._property_value(spec, row, row_index)
            except TransformError as e:
                result.errors.append(f"row {row_index}: {mapping_id}.{name}: {e}")
                value = None
            if _is_empty(value) and spec.get("required"):
                result.errors.append(
                    f"row {row_index}: {mapping_id}.{name} is required but resolved empty; "
                    "no node produced for this row"
                )
                return []
            props[name] = value
        return [props]

    def _source_form(
        self,
        mapping: Mapping[str, Any],
        mapping_id: str,
        row: Mapping[str, Any],
        row_index: int,
        result: RowMapping,
    ) -> List[Dict[str, Any]]:
        """Transform-per-node form: one column expands into several properties."""
        source = mapping.get("source") or {}
        try:
            produced = self._transform_value(source, row, row_index)
        except TransformError as e:
            result.errors.append(f"row {row_index}: {mapping_id}.source: {e}")
            return []

        if _is_empty(produced) and source.get("fallback"):
            try:
                produced = self._transform_value(source["fallback"], row, row_index)
            except TransformError as e:
                result.errors.append(f"row {row_index}: {mapping_id}.source.fallback: {e}")
                return []

        if _is_empty(produced):
            return []

        many = mapping.get("cardinality") == "many"
        if many:
            entries = list(produced) if isinstance(produced, (list, tuple)) else [produced]
        elif isinstance(produced, (list, tuple)):
            result.errors.append(
                f"row {row_index}: {mapping_id}.source returned "
                f"{len(produced)} values but cardinality is 'one'"
            )
            return []
        else:
            entries = [produced]

        property_map: Dict[str, str] = dict(mapping.get("property_map") or {})
        out: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                result.errors.append(
                    f"row {row_index}: {mapping_id}.source returned a "
                    f"{type(entry).__name__} where property_map needs an object"
                )
                continue
            out.append({target: entry.get(source_key) for source_key, target in property_map.items()})
        return out

    def _property_value(
        self, spec: Mapping[str, Any], row: Mapping[str, Any], row_index: int
    ) -> Any:
        """Resolve one property, consulting its fallback only if it comes up empty."""
        value = self._transform_value(spec, row, row_index)
        fallback = spec.get("fallback")
        if _is_empty(value) and fallback:
            if fallback.get("template"):
                value = self._interpolate(fallback["template"], row, row_index)
            else:
                value = self._transform_value(fallback, row, row_index)
        return value

    def _transform_value(
        self, spec: Mapping[str, Any], row: Mapping[str, Any], row_index: int
    ) -> Any:
        """Read a column and/or apply a transform, per one spec fragment.

        Three shapes: a bare column, a column through a transform, and a
        transform with no column at all — the last is how ``sp_colresolution``
        chooses *between* two columns, which no single-column form can express.
        """
        name = spec.get("transform")
        column = spec.get("column")
        args = dict(spec.get("transform_args") or {})

        if not name:
            return _normalize(row.get(column)) if column else None

        transform = self.transforms.get(name)
        if transform is None:
            # validate() reports this; reaching here means the caller skipped it.
            raise TransformError(f"unknown transform {name!r}")
        if _accepts_row(transform):
            args["row"] = row
        if column is None:
            return transform(**args)
        return transform(_normalize(row.get(column)), **args)

    @staticmethod
    def _interpolate(template: str, row: Mapping[str, Any], row_index: int) -> str:
        """Fill ``{Column}`` placeholders from the row; ``{__row_index__}`` from the index.

        A placeholder naming a column the row does not have interpolates empty
        rather than raising — a template exists to synthesize a key from whatever
        the row does have.
        """
        def substitute(match: "re.Match[str]") -> str:
            field_name = match.group(1).strip()
            if field_name == ROW_INDEX_PLACEHOLDER:
                return str(row_index)
            value = _normalize(row.get(field_name))
            return "" if value is None else str(value)

        return _TEMPLATE_FIELD_RE.sub(substitute, template)

    def _finalize(
        self,
        mapping: Mapping[str, Any],
        mapping_id: str,
        props: Dict[str, Any],
        row_index: int,
        result: RowMapping,
    ) -> Optional[ResolvedNode]:
        """Apply skip rules, choose the merge key, and build the node."""
        skip_when = mapping.get("skip_when_all_empty")
        if skip_when and all(_is_empty(props.get(name)) for name in skip_when):
            return None

        keys = mapping.get("key_property")
        preference = [keys] if isinstance(keys, str) else list(keys or [])
        key_property = next((k for k in preference if not _is_empty(props.get(k))), None)
        if key_property is None:
            if not mapping.get("optional"):
                result.errors.append(
                    f"row {row_index}: {mapping_id} has no non-empty key property "
                    f"(tried {preference}); no node produced"
                )
            return None

        key_value = props[key_property]
        if isinstance(key_value, (list, tuple, set, dict)):
            result.errors.append(
                f"row {row_index}: {mapping_id} merge key {key_property!r} resolved to a "
                f"{type(key_value).__name__}; a merge key must be a scalar"
            )
            return None

        if self.omit_empty_properties:
            final = {k: v for k, v in props.items() if k == key_property or not _is_empty(v)}
        else:
            final = dict(props)

        # Last gate before these names become Cypher. validate() already checked
        # them, but this node is about to be interpolated into a query string, so
        # the guarantee is enforced here too rather than assumed.
        unsafe = self._first_unsafe_identifier(mapping.get("label"), key_property, final)
        if unsafe is not None:
            result.errors.append(f"row {row_index}: {mapping_id}: {unsafe}")
            return None

        self._check_vocabulary(mapping_id, final, row_index, result)
        return ResolvedNode(
            mapping_id=mapping_id,
            label=str(mapping["label"]),
            key_property=key_property,
            properties=final,
        )

    def _first_unsafe_identifier(
        self, label: Any, key_property: str, props: Mapping[str, Any]
    ) -> Optional[str]:
        """Reason this node cannot be written, or None. Memoized per identifier."""
        candidates = [(label, "label"), (key_property, "key_property")]
        candidates += [(name, "property name") for name in props]
        for value, kind in candidates:
            # Non-strings are never cached: they may be unhashable, and
            # check_identifier rejects them anyway.
            if isinstance(value, str) and value in self._approved_identifiers:
                continue
            problem = check_identifier(value, kind)
            if problem:
                return problem
            self._approved_identifiers.add(str(value))
        return None

    # --------------------------------------------------------- vocabulary

    def _build_vocabulary(
        self, override: Optional[Mapping[str, Sequence[str]]]
    ) -> Dict[str, Set[str]]:
        """Allowed terms per field, as written. ``override`` replaces per field.

        Kept in source case so ``match: exact`` and ``match: case_insensitive``
        can both be answered from one table; folding happens at compare time.
        """
        check = self.config.get("vocabulary_check") or {}
        terms: Dict[str, Set[str]] = {}
        for field_name, values in (check.get("default_vocabulary") or {}).items():
            terms[field_name] = {str(v).strip() for v in values or ()}
        for field_name, values in (override or {}).items():
            terms[field_name] = {str(v).strip() for v in values or ()}
        return terms

    def _check_vocabulary(
        self,
        mapping_id: str,
        props: Mapping[str, Any],
        row_index: int,
        result: RowMapping,
    ) -> None:
        """Report property values outside their controlled vocabulary.

        A soft check by default: an unexpected term is a data-quality signal, not
        a reason to refuse to record the row. ``severity: error`` promotes it.
        """
        check = self.config.get("vocabulary_check") or {}
        if not check.get("enabled"):
            return
        fields = set(check.get("fields") or ())
        splitter = self.transforms.get(check.get("multi_value_transform") or "")
        exact = str(check.get("match") or "case_insensitive") == "exact"
        sink = result.errors if str(check.get("severity") or "warning") == "error" else result.warnings

        for field_name in fields & set(props):
            allowed = self._vocabulary.get(field_name)
            if not allowed:
                continue
            pool = allowed if exact else {term.casefold() for term in allowed}
            raw = props[field_name]
            if isinstance(raw, (list, tuple)):
                values = list(raw)
            elif splitter is not None and isinstance(raw, str):
                try:
                    values = splitter(raw)
                except TransformError:
                    values = [raw]
            else:
                values = [raw]
            for value in values:
                if _is_empty(value):
                    continue
                text = str(value).strip()
                if (text if exact else text.casefold()) not in pool:
                    sink.append(
                        f"row {row_index}: {mapping_id}.{field_name} value {text!r} is not "
                        "in the configured vocabulary"
                    )


@lru_cache(maxsize=256)
def _accepts_row_cached(transform: Callable) -> bool:
    try:
        return "row" in inspect.signature(transform).parameters
    except (TypeError, ValueError):  # builtins and C callables have no signature
        return False


def _accepts_row(transform: Callable) -> bool:
    """Whether a transform wants the whole row alongside its arguments.

    The convention that makes ``sp_colresolution`` expressible: a transform
    declaring a ``row`` parameter is choosing between columns rather than
    converting one, so the engine hands it the row.
    """
    try:
        return _accepts_row_cached(transform)
    except TypeError:  # unhashable callable
        return _accepts_row_cached.__wrapped__(transform)
