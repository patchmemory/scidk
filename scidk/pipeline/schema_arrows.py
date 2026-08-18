"""The Pipeline's schema target: Arrows.app JSON in, Arrows.app JSON out.

Cycle 3B Task C. A source's ``schema_json`` column holds an Arrows.app-compatible
document — the same format arrows.app itself exports — so a schema can leave SciDK,
be edited or reviewed by someone without an account, and come back.

Three things live here:

* :func:`parse_arrows` — the validating normalizer. Everything that writes
  ``schema_json`` goes through it, whether the bytes came from an arrows.app
  export, from the schema canvas, or from a future API client.
* :func:`schema_summary` — what the source card and the step indicator show.
* :func:`derive_from_graph` — Option B, the live Neo4j schema as a starting point.

**Why validation is strict about identifiers.** The schema is the mapping target
for Task D, and :func:`~scidk.pipeline.mapping_engine.MappingEngine` writes through
``write_declared_nodes``, which interpolates labels, relationship types and property
*names* into Cypher unquoted (see :mod:`scidk.pipeline.identifiers`). A label of
``Intake Form`` or a property called ``Sample ID`` cannot be written at all, so
accepting one here would mean a schema that looks saved and produces a mapping that
can never run. Rejecting it at import, naming the offender, is the honest failure.

**What is deliberately not enforced:** anything about *style*. Arrows documents
carry a large ``style`` block and per-element style overrides; they round-trip
untouched where present and are otherwise filled in with arrows.app's defaults.
Nothing in SciDK reads them.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .identifiers import LABEL_RE, PROPERTY_RE, REL_RE

__all__ = [
    "SchemaError",
    "EMPTY_SCHEMA",
    "parse_arrows",
    "schema_summary",
    "derive_from_graph",
]

#: Cap on a single import. Not a technical limit — a paste this size is a mistake
#: (a data export rather than a schema), and saying so beats rendering 20k nodes.
MAX_NODES = 2000
MAX_RELATIONSHIPS = 4000

#: How many problems an error message lists before it stops. A malformed export
#: usually has one cause and many symptoms; ten is enough to see the pattern.
MAX_REPORTED_PROBLEMS = 10

#: The default Arrows property type. Arrows writes a type string per property;
#: SciDK does not use it, so an import that omits it gets this.
DEFAULT_PROPERTY_TYPE = "String"

#: A valid, empty schema. Option C (build from scratch) starts here.
EMPTY_SCHEMA: Dict[str, Any] = {"nodes": [], "relationships": []}


class SchemaError(ValueError):
    """An Arrows document that cannot become a schema.

    Carries the full problem list as well as the joined message, so a UI can show
    every offending element at once instead of making the user fix them one
    reload at a time.
    """

    def __init__(self, message: str, problems: Optional[Sequence[str]] = None):
        super().__init__(message)
        self.problems: List[str] = list(problems or [])


# --------------------------------------------------------------- parse/normalize

def parse_arrows(payload: Any) -> Dict[str, Any]:
    """Validate an Arrows document and return it in canonical form.

    Args:
        payload: A parsed Arrows document, or the raw JSON text of one.

    Returns:
        ``{"style": {...}, "nodes": [...], "relationships": [...]}`` where every
        node has ``id``, ``caption``, ``labels``, ``properties`` (a name -> type
        dict), ``position`` and ``style``, and every relationship has ``id``,
        ``type``, ``fromId``, ``toId``, ``properties`` and ``style``.

    Raises:
        SchemaError: With a message naming every problem found, up to
            :data:`MAX_REPORTED_PROBLEMS`. Nothing partial is returned — a schema
            is either usable as a mapping target or it is not.
    """
    document = _as_document(payload)

    nodes_raw = document.get("nodes")
    if not isinstance(nodes_raw, list):
        raise SchemaError(
            "This does not look like an Arrows.app export: it has no \"nodes\" array."
        )
    rels_raw = document.get("relationships")
    if rels_raw is None:
        rels_raw = []
    if not isinstance(rels_raw, list):
        raise SchemaError('"relationships" must be an array.')

    if len(nodes_raw) > MAX_NODES:
        raise SchemaError(
            f"This document has {len(nodes_raw)} nodes; the limit is {MAX_NODES}. "
            "A schema describes label types, not rows — this looks like a data export."
        )
    if len(rels_raw) > MAX_RELATIONSHIPS:
        raise SchemaError(
            f"This document has {len(rels_raw)} relationships; the limit is "
            f"{MAX_RELATIONSHIPS}."
        )

    problems: List[str] = []
    nodes, node_ids = _parse_nodes(nodes_raw, problems)
    relationships = _parse_relationships(rels_raw, node_ids, problems)

    if problems:
        raise SchemaError(_problem_message(problems), problems)

    return {
        "style": document.get("style") if isinstance(document.get("style"), dict) else {},
        "nodes": nodes,
        "relationships": relationships,
    }


def _as_document(payload: Any) -> Dict[str, Any]:
    """Coerce text or an object into a dict, with a readable error either way."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SchemaError(f"The file is not UTF-8 text: {e}") from e
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise SchemaError("Nothing to import — paste or upload an Arrows.app export.")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            # Line/column, because a paste is usually long and the eye needs help.
            raise SchemaError(
                f"That is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})."
            ) from e
    if not isinstance(payload, dict):
        raise SchemaError(
            "An Arrows.app export is a JSON object with \"nodes\" and "
            f"\"relationships\"; this is {type(payload).__name__}."
        )
    return payload


def _parse_nodes(
    nodes_raw: List[Any], problems: List[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Normalize every node. Returns the nodes and an id -> label map."""
    nodes: List[Dict[str, Any]] = []
    node_ids: Dict[str, str] = {}

    for index, raw in enumerate(nodes_raw):
        where = f"node {index + 1}"
        if not isinstance(raw, dict):
            problems.append(f"{where} is not an object.")
            continue

        node_id = str(raw.get("id") or f"n{index}")
        if node_id in node_ids:
            problems.append(f"{where}: duplicate node id {node_id!r}.")
            continue

        labels, label = _node_labels(raw)
        if not label:
            problems.append(
                f"{where} has no label or caption, so there is nothing to map onto."
            )
            continue
        if not LABEL_RE.match(label):
            problems.append(
                f"{where}: {label!r} is not a usable Neo4j label. Labels must start "
                "with a letter or underscore and contain only letters, digits and "
                "underscores — rename it in Arrows.app (e.g. IntakeForm)."
            )
            continue

        properties = _node_properties(raw, where, problems)
        key_property = raw.get("key_property")
        if key_property not in (None, ""):
            key_property = str(key_property)
            if key_property not in properties:
                problems.append(
                    f"{where} ({label}): key_property {key_property!r} is not one of "
                    f"its properties ({', '.join(properties) or 'none'})."
                )
                continue
        else:
            key_property = None

        node: Dict[str, Any] = {
            "id": node_id,
            "position": _position(raw.get("position"), index),
            "caption": str(raw.get("caption") or label),
            "labels": labels,
            "properties": properties,
            "style": raw.get("style") if isinstance(raw.get("style"), dict) else {},
        }
        # SciDK extensions. Arrows.app ignores fields it does not know, so they
        # survive a round trip through it — but nothing here depends on that.
        if key_property:
            node["key_property"] = key_property
        if raw.get("description"):
            node["description"] = str(raw["description"])

        nodes.append(node)
        node_ids[node_id] = label

    return nodes, node_ids


def _node_labels(raw: Dict[str, Any]) -> Tuple[List[str], str]:
    """The node's label list and its primary label.

    Arrows writes both ``labels`` and a ``caption``; a hand-written document may
    have only one of them. The primary label is the first entry of ``labels``,
    falling back to the caption — which is what the arrows.app UI shows and what a
    user editing there would consider the label.
    """
    labels = [str(x).strip() for x in (raw.get("labels") or []) if str(x).strip()]
    if labels:
        return labels, labels[0]
    caption = str(raw.get("caption") or "").strip()
    return ([caption] if caption else []), caption


def _node_properties(
    raw: Dict[str, Any], where: str, problems: List[str]
) -> Dict[str, str]:
    """Normalize a node's properties to ``{name: arrows_type}``.

    Three input shapes are accepted, because three are in circulation: arrows.app
    itself writes an object, the Cycle 3B task description writes a list of
    ``{"name": ...}``, and a hand-rolled export sometimes writes a list of bare
    strings. All three mean the same thing.
    """
    source = raw.get("properties")
    pairs: List[Tuple[str, Any]] = []

    if isinstance(source, dict):
        pairs = list(source.items())
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                pairs.append((str(item.get("name") or ""), item.get("type")))
            elif isinstance(item, str):
                pairs.append((item, None))
            else:
                problems.append(f"{where}: property entry {item!r} is not a name.")
    elif source not in (None, ""):
        problems.append(
            f"{where}: \"properties\" must be an object or an array, not "
            f"{type(source).__name__}."
        )

    properties: Dict[str, str] = {}
    for name, prop_type in pairs:
        name = str(name).strip()
        if not name:
            problems.append(f"{where}: a property has no name.")
            continue
        if not PROPERTY_RE.match(name):
            problems.append(
                f"{where}: {name!r} is not a usable property name. Property names "
                "must start with a letter or underscore and contain only letters, "
                "digits and underscores."
            )
            continue
        properties[name] = str(prop_type or DEFAULT_PROPERTY_TYPE)
    return properties


def _parse_relationships(
    rels_raw: List[Any], node_ids: Dict[str, str], problems: List[str]
) -> List[Dict[str, Any]]:
    """Normalize every relationship, checking both endpoints resolve."""
    relationships: List[Dict[str, Any]] = []
    seen: set = set()

    for index, raw in enumerate(rels_raw):
        where = f"relationship {index + 1}"
        if not isinstance(raw, dict):
            problems.append(f"{where} is not an object.")
            continue

        rel_id = str(raw.get("id") or f"r{index}")
        if rel_id in seen:
            problems.append(f"{where}: duplicate relationship id {rel_id!r}.")
            continue

        rel_type = str(raw.get("type") or "").strip()
        if not rel_type:
            problems.append(f"{where} has no type.")
            continue
        if not REL_RE.match(rel_type):
            problems.append(
                f"{where}: {rel_type!r} is not a usable relationship type. Types must "
                "start with a letter or underscore and contain only letters, digits "
                "and underscores (e.g. PI_OF)."
            )
            continue

        from_id = str(raw.get("fromId") or "")
        to_id = str(raw.get("toId") or "")
        missing = [x for x in (from_id, to_id) if x not in node_ids]
        if missing:
            problems.append(
                f"{where} ({rel_type}) points at node id "
                f"{', '.join(repr(m) for m in missing)}, which is not in this document."
            )
            continue

        properties = _node_properties(raw, f"{where} ({rel_type})", problems)
        relationships.append({
            "id": rel_id,
            "type": rel_type,
            "fromId": from_id,
            "toId": to_id,
            "properties": properties,
            "style": raw.get("style") if isinstance(raw.get("style"), dict) else {},
        })
        seen.add(rel_id)

    return relationships


def _position(raw: Any, index: int) -> Dict[str, float]:
    """A node's Arrows position, or a grid slot when it has none.

    A document without positions still has to lay out somewhere; the canvas
    normalizes whatever it gets into its own viewport on load, so these
    coordinates only need to be distinct and finite.
    """
    if isinstance(raw, dict):
        try:
            x, y = float(raw.get("x", 0) or 0), float(raw.get("y", 0) or 0)
            # NaN/inf survive float() and poison a Cytoscape layout silently.
            if x == x and y == y and abs(x) != float("inf") and abs(y) != float("inf"):
                return {"x": x, "y": y}
        except (TypeError, ValueError):
            pass
    columns = 5
    return {"x": float((index % columns) * 240), "y": float((index // columns) * 180)}


def _problem_message(problems: Sequence[str]) -> str:
    """One readable sentence plus the list, truncated."""
    shown = list(problems[:MAX_REPORTED_PROBLEMS])
    more = len(problems) - len(shown)
    header = (
        "This schema cannot be used as a mapping target:"
        if len(problems) > 1
        else "This schema cannot be used as a mapping target."
    )
    body = " ".join(shown)
    if more > 0:
        body += f" (…and {more} more problem{'s' if more > 1 else ''}.)"
    return f"{header} {body}".strip()


# ------------------------------------------------------------------- summary

def schema_summary(schema: Any) -> Dict[str, Any]:
    """Counts and names for the source card and the Step 2 indicator.

    Tolerant by design: this runs on whatever is already in ``schema_json``,
    including a document written before a validation rule existed. A schema it
    cannot read reports ``defined: False`` rather than raising into a page render.
    """
    if not isinstance(schema, dict):
        return {"defined": False, "labels": [], "relationship_types": [],
                "node_count": 0, "relationship_count": 0, "property_count": 0}

    nodes = schema.get("nodes") or []
    rels = schema.get("relationships") or []
    labels: List[str] = []
    property_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        _, label = _node_labels(node)
        if label and label not in labels:
            labels.append(label)
        props = node.get("properties")
        property_count += len(props) if isinstance(props, (dict, list)) else 0

    types: List[str] = []
    for rel in rels:
        if isinstance(rel, dict):
            rel_type = str(rel.get("type") or "").strip()
            if rel_type and rel_type not in types:
                types.append(rel_type)

    return {
        "defined": bool(nodes),
        "labels": labels,
        "relationship_types": types,
        "node_count": len([n for n in nodes if isinstance(n, dict)]),
        "relationship_count": len([r for r in rels if isinstance(r, dict)]),
        "property_count": property_count,
    }


# --------------------------------------------------- Option B: the live graph

#: Which strategy produced a derived schema, reported to the UI so the user knows
#: whether they are looking at the declared schema or one inferred from data.
STRATEGY_VISUALIZATION = "db.schema.visualization"
STRATEGY_APOC = "apoc.meta.schema"
STRATEGY_SCAN = "relationship scan"

#: Cap on the fallback scan, per the task description.
SCAN_LIMIT = 1000


def derive_from_graph(read: Callable[..., List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Build a schema document from the labels and relationship types in Neo4j.

    Three strategies, tried in order, because ``db.schema.visualization()`` is not
    available on every Neo4j version or edition and APOC is not always installed:

    1. ``CALL db.schema.visualization()`` — the declared schema, cheapest and
       exact. Verified against Neo4j 2025.10.1 Community, which this deployment
       runs.
    2. ``CALL apoc.meta.schema()`` — same information plus property names, when
       APOC is present.
    3. ``MATCH (n)-[r]->(m) RETURN DISTINCT ...`` — a bounded scan. Always works
       and reflects what is actually in the data rather than what was declared.

    Args:
        read: A read-only query runner — ``Neo4jClient.execute_read``. Passed in
            rather than constructed so this stays testable without a database.

    Returns:
        ``{"schema": <arrows document>, "strategy": <str>, "notes": [str]}``.
        An empty graph yields an empty schema and a note saying so, which is a
        result to display rather than an error.
    """
    notes: List[str] = []

    for strategy, builder in (
        (STRATEGY_VISUALIZATION, _derive_via_visualization),
        (STRATEGY_APOC, _derive_via_apoc),
        (STRATEGY_SCAN, _derive_via_scan),
    ):
        try:
            labels = builder(read)
        except Exception as e:  # noqa: BLE001 - an unavailable procedure is expected
            notes.append(f"{strategy} unavailable: {_short(e)}")
            continue
        if labels:
            if strategy != STRATEGY_VISUALIZATION:
                notes.append(f"Derived via {strategy}.")
            _attach_properties(read, labels, notes)
            return {
                "schema": _to_arrows(labels),
                "strategy": strategy,
                "notes": notes,
            }
        notes.append(f"{strategy} returned no labels.")

    notes.append(
        "The graph has no labels yet, so there is no schema to derive. Import from "
        "Arrows.app or build one from scratch."
    )
    return {"schema": dict(EMPTY_SCHEMA), "strategy": None, "notes": notes}


def _to_arrows(labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lay out derived labels as an Arrows document.

    Delegates to :func:`scidk.interpreters.arrows_utils.export_to_arrows`, which is
    already the label-list -> Arrows converter, so there is one implementation of
    that direction rather than two that can drift. Its output then goes back
    through :func:`parse_arrows`, both to normalize property types and so a derived
    schema is held to exactly the same rules as an imported one.
    """
    from ..interpreters.arrows_utils import export_to_arrows

    document = export_to_arrows(labels, layout="circular", scale=1200)
    try:
        return parse_arrows(document)
    except SchemaError:
        # A live graph can legitimately hold a label the mapping engine could
        # never write to (`Sample ID`, say, created by another tool). Dropping
        # those and keeping the rest beats refusing to derive anything.
        return parse_arrows(_drop_unusable(document))


def _drop_unusable(document: Dict[str, Any]) -> Dict[str, Any]:
    """Remove labels/types/properties Cypher cannot address unquoted."""
    kept_ids = set()
    nodes = []
    for node in document.get("nodes") or []:
        _, label = _node_labels(node)
        if not label or not LABEL_RE.match(label):
            continue
        node = dict(node)
        node["properties"] = {
            name: value
            for name, value in (node.get("properties") or {}).items()
            if PROPERTY_RE.match(str(name))
        }
        nodes.append(node)
        kept_ids.add(str(node.get("id")))
    relationships = [
        rel for rel in document.get("relationships") or []
        if REL_RE.match(str(rel.get("type") or ""))
        and str(rel.get("fromId")) in kept_ids
        and str(rel.get("toId")) in kept_ids
    ]
    return {**document, "nodes": nodes, "relationships": relationships}


def _derive_via_visualization(read: Callable[..., Any]) -> List[Dict[str, Any]]:
    """Strategy 1: the virtual graph ``db.schema.visualization()`` returns.

    Its nodes and relationships are driver graph objects, not maps: each node
    carries the label in a ``name`` property, and each relationship's endpoints are
    those same virtual nodes, matched here by element id.
    """
    rows = read("CALL db.schema.visualization()")
    if not rows:
        return []
    row = rows[0]
    by_element: Dict[Any, str] = {}
    order: List[str] = []
    for node in row.get("nodes") or []:
        name = _virtual_node_label(node)
        if not name:
            continue
        by_element[_element_key(node)] = name
        if name not in order:
            order.append(name)

    labels = {name: {"name": name, "properties": [], "relationships": []} for name in order}
    for rel in row.get("relationships") or []:
        rel_type = getattr(rel, "type", None) or (
            rel.get("type") if isinstance(rel, dict) else None
        )
        start = by_element.get(_element_key(getattr(rel, "start_node", None)))
        end = by_element.get(_element_key(getattr(rel, "end_node", None)))
        if not (rel_type and start and end):
            continue
        labels[start]["relationships"].append({"type": str(rel_type), "target_label": end})
    return [labels[name] for name in order]


def _virtual_node_label(node: Any) -> str:
    """The label a ``db.schema.visualization()`` node stands for."""
    if node is None:
        return ""
    try:
        name = node.get("name")
    except AttributeError:
        name = None
    if name:
        return str(name)
    node_labels = getattr(node, "labels", None) or []
    for label in node_labels:
        return str(label)
    return ""


def _element_key(node: Any) -> Any:
    """A hashable identity for a virtual node across the two result shapes."""
    if node is None:
        return None
    return getattr(node, "element_id", None) or getattr(node, "id", None) or id(node)


def _derive_via_apoc(read: Callable[..., Any]) -> List[Dict[str, Any]]:
    """Strategy 2: ``apoc.meta.schema()``, which also carries property names."""
    rows = read("CALL apoc.meta.schema()")
    if not rows:
        return []
    value = rows[0].get("value") or {}
    labels: List[Dict[str, Any]] = []
    for name, entry in value.items():
        if not isinstance(entry, dict) or entry.get("type") != "node":
            continue
        properties = [
            {"name": prop_name, "type": _scidk_type(prop.get("type"))}
            for prop_name, prop in (entry.get("properties") or {}).items()
            if isinstance(prop, dict)
        ]
        relationships = []
        for rel_type, rel in (entry.get("relationships") or {}).items():
            if not isinstance(rel, dict) or rel.get("direction") != "out":
                continue
            for target in rel.get("labels") or []:
                relationships.append({"type": str(rel_type), "target_label": str(target)})
        labels.append({"name": str(name), "properties": properties,
                       "relationships": relationships})

    known = {label["name"] for label in labels}
    for label in labels:
        label["relationships"] = [
            rel for rel in label["relationships"] if rel["target_label"] in known
        ]
    return labels


def _derive_via_scan(read: Callable[..., Any]) -> List[Dict[str, Any]]:
    """Strategy 3: distinct label-type-label triples from the data itself.

    Also asks ``db.labels()`` for labels that participate in no relationship —
    without it, a graph of unconnected nodes derives to nothing at all. That call
    is best-effort: the triples are the part the task specifies.
    """
    rows = read(
        "MATCH (n)-[r]->(m) "
        "RETURN DISTINCT labels(n) AS from_labels, type(r) AS rel_type, "
        "labels(m) AS to_labels "
        f"LIMIT {SCAN_LIMIT}"
    )

    order: List[str] = []
    labels: Dict[str, Dict[str, Any]] = {}

    def ensure(name: str) -> Dict[str, Any]:
        if name not in labels:
            labels[name] = {"name": name, "properties": [], "relationships": []}
            order.append(name)
        return labels[name]

    try:
        for row in read("CALL db.labels() YIELD label RETURN label ORDER BY label"):
            name = str(row.get("label") or "").strip()
            if name:
                ensure(name)
    except Exception:  # noqa: BLE001 - the triples below are the required part
        pass

    seen: set = set()
    for row in rows or []:
        from_labels = row.get("from_labels") or []
        to_labels = row.get("to_labels") or []
        rel_type = str(row.get("rel_type") or "").strip()
        if not (from_labels and to_labels and rel_type):
            continue
        # A multi-labelled node is attributed to its first label, matching how
        # the rest of SciDK picks a node's display label.
        start, end = str(from_labels[0]), str(to_labels[0])
        triple = (start, rel_type, end)
        if triple in seen:
            continue
        seen.add(triple)
        ensure(end)
        ensure(start)["relationships"].append({"type": rel_type, "target_label": end})

    return [labels[name] for name in order]


def _attach_properties(
    read: Callable[..., Any], labels: List[Dict[str, Any]], notes: List[str]
) -> None:
    """Fill in property names from ``db.schema.nodeTypeProperties()``.

    Only for labels that have none yet, so the APOC strategy's richer types are not
    overwritten. Best-effort: a schema with labels and no properties is still a
    usable starting point, and Task D's column mapping is where properties get
    their real definition.
    """
    if all(label.get("properties") for label in labels):
        return
    try:
        rows = read("CALL db.schema.nodeTypeProperties()")
    except Exception as e:  # noqa: BLE001
        notes.append(f"Property names unavailable: {_short(e)}")
        return

    by_label: Dict[str, List[Dict[str, str]]] = {}
    for row in rows or []:
        prop_name = str(row.get("propertyName") or "").strip()
        if not prop_name:
            continue
        types = row.get("propertyTypes") or []
        for label_name in row.get("nodeLabels") or []:
            entries = by_label.setdefault(str(label_name), [])
            if any(entry["name"] == prop_name for entry in entries):
                continue
            entries.append({
                "name": prop_name,
                "type": _scidk_type(types[0] if types else None),
            })

    for label in labels:
        if not label.get("properties"):
            label["properties"] = by_label.get(label["name"], [])


def _scidk_type(neo4j_type: Any) -> str:
    """Map a Neo4j/APOC type name onto the scidk vocabulary arrows_utils speaks."""
    mapping = {
        "String": "string", "STRING": "string",
        "Long": "number", "INTEGER": "number", "Integer": "number",
        "Double": "number", "FLOAT": "number", "Float": "number",
        "Boolean": "boolean", "BOOLEAN": "boolean",
        "Date": "date", "DATE": "date",
        "DateTime": "datetime", "LocalDateTime": "datetime", "DATE_TIME": "datetime",
    }
    return mapping.get(str(neo4j_type), "string")


def _short(error: Exception, limit: int = 160) -> str:
    """A one-line rendering of an exception for a note the user will read."""
    text = " ".join(str(error).split())
    return text[:limit] + ("…" if len(text) > limit else "")
