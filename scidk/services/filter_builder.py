"""Schema-aware filter builder — property type inference and Cypher generation.

Two independent halves, both pure (no Flask, no app context):

``infer_property_types``
    Ask a live graph what properties a label carries and what type each one
    looks like, so a UI can offer the right operators without anyone writing
    Cypher. Bounded to a single sampled round trip per call.

``generate_cypher`` / ``generate_count_cypher``
    Turn a declarative filter definition (see the schema comment below) into a
    parameterized Cypher query. Structural parts — labels, relationship types,
    property keys — are whitelisted through
    :mod:`scidk.pipeline.identifiers`; user-supplied *values* are never
    interpolated, only bound as ``$v0``, ``$v1``, ...

Consumers: the ``/api/schema/*`` routes in ``web/routes/api_graph.py`` and the
``FilterBuilder`` JS component in ``ui/static/js/filter_builder.js``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..pipeline.identifiers import require_identifier

__all__ = [
    "ISO_DATE_RE",
    "NULL_OPS",
    "TWO_VALUE",
    "PropertyInfo",
    "infer_property_types",
    "generate_cypher",
    "generate_count_cypher",
]

#: A value that looks like an ISO-8601 date or datetime prefix.
ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?')

#: How many nodes to sample when inferring property types for a label.
DEFAULT_SAMPLE_SIZE = 100

#: A relationship type safe to interpolate unquoted *and* conformant to the
#: uppercase Cypher convention. Deliberately narrower than
#: :data:`scidk.pipeline.identifiers.REL_RE`, which allows any identifier.
_SAFE_REL_TYPE = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _validate_identifier(name: Any) -> str:
    """Whitelist a label or property key for raw interpolation into Cypher.

    Thin adapter over :func:`scidk.pipeline.identifiers.require_identifier` so
    this module has one obvious name for the guard. ``IdentifierError`` is a
    ``ValueError``, so callers only need to catch ``ValueError``.
    """
    return require_identifier(name, "identifier")


def _validate_rel_type(rel_type: Any) -> str:
    """Whitelist a relationship type for raw interpolation into Cypher.

    Stricter than :func:`_validate_identifier`: relationship types are uppercase
    by Cypher convention and that convention is enforced, not merely suggested.
    Accepting ``Owns_Folder`` alongside ``OWNS_FOLDER`` would let two spellings
    of the same edge coexist in one graph, and Neo4j treats them as unrelated
    types.

    Valid:   ``OWNS``, ``CONTRIBUTED_TO``, ``FUNDED_BY``, ``RELATED_TO``
    Invalid: ``owns``, ``Owns_Folder``, ``123TYPE``, ``TYPE NAME``

    Raises:
        ValueError: ``rel_type`` is missing, not a string, or not uppercase.
    """
    if rel_type is None or (isinstance(rel_type, str) and not rel_type.strip()):
        raise ValueError("relationship type is missing")
    if not isinstance(rel_type, str):
        raise ValueError(
            f"relationship type must be a string, got {type(rel_type).__name__}"
        )
    if not _SAFE_REL_TYPE.match(rel_type):
        raise ValueError(
            f"Invalid relationship type {rel_type!r}. Relationship types must be "
            "uppercase letters, digits, and underscores only, starting with a "
            "letter (e.g. OWNS, CONTRIBUTED_TO, FUNDED_BY)."
        )
    return rel_type


# ---------------------------------------------------------------------------
# Property type inference
# ---------------------------------------------------------------------------

@dataclass
class PropertyInfo:
    name: str
    type: str        # "string" | "number" | "date" | "boolean" | "null"
    nullable: bool   # True if any sampled node lacked a value for it
    sample: Any      # one representative non-null value, or None


def infer_property_types(
    driver,
    label: str,
    database: Optional[str] = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> List[PropertyInfo]:
    """Sample nodes carrying ``label`` and classify each property's data type.

    One round trip: ``sample_size`` nodes are fetched whole and every property
    is classified from that shared sample. Deliberately *not* a query per
    property — on a 5.5M-node label like ``File`` a ``count()`` of missing
    values per property is a full scan each time, and there are dozens of
    properties. The sample is bounded and uses the label index.

    The cost of that is a sample, not a census: a property carried by only a
    handful of nodes may not appear at all, and ``nullable`` reflects the
    sampled nodes rather than the whole label.

    Classification of the non-null values seen for a property:
      - all bool                                   → "boolean"
      - all int/float (and not bool)               → "number"
      - all strings match ISO_DATE_RE              → "date"
      - nothing non-null was sampled               → "null"
      - otherwise                                  → "string"

    Args:
        driver: A connected neo4j driver.
        label: Node label to inspect. Validated as a Cypher identifier.
        database: Neo4j database name, or None for the driver default.
        sample_size: Max nodes to sample.

    Returns:
        One PropertyInfo per property seen, sorted by name.

    Raises:
        ValueError: ``label`` is not a safe Cypher identifier.
    """
    safe_label = _validate_identifier(label)
    limit = max(1, int(sample_size))

    with driver.session(database=database) as session:
        result = session.run(
            f"MATCH (n:{safe_label}) WITH n LIMIT $limit "
            f"RETURN properties(n) AS props",
            {"limit": limit},
        )
        sampled = [dict(record["props"] or {}) for record in result]

    # Union of keys across the sample, plus the values seen for each.
    values_by_prop: Dict[str, List[Any]] = {}
    for props in sampled:
        for key, value in props.items():
            values_by_prop.setdefault(key, []).append(value)

    total_sampled = len(sampled)
    infos: List[PropertyInfo] = []
    for prop in sorted(values_by_prop):
        seen = values_by_prop[prop]
        non_null = [v for v in seen if v is not None]
        # Neo4j does not store null properties, so a node that simply lacks the
        # key is exactly the "value is null" case.
        has_nulls = len(non_null) < total_sampled
        infos.append(PropertyInfo(
            name=prop,
            type=_classify(non_null),
            nullable=has_nulls or not non_null,
            sample=non_null[0] if non_null else None,
        ))
    return infos


def _classify(values: List[Any]) -> str:
    """Map a list of non-null sampled values to one of the five type names."""
    if not values:
        return 'null'
    if all(isinstance(v, bool) for v in values):
        return 'boolean'
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return 'number'
    str_values = [v for v in values if isinstance(v, str)]
    if str_values and all(ISO_DATE_RE.match(str(v)) for v in str_values):
        return 'date'
    return 'string'


# ---------------------------------------------------------------------------
# Cypher generation
# ---------------------------------------------------------------------------
#
# Filter definition schema:
#
# {
#   "blocks": [
#     {
#       "label": "Investigator",
#       "match": "ALL",          // "ALL" = AND between conditions (default)
#                                // "ANY" = OR between conditions
#       "conditions": [
#         {"property": "name", "operator": "contains", "value": "Zhang"},
#         {"property": "email", "operator": "is_not_null"}
#       ]
#     },
#     {
#       "via": {                 // relationship to the previous block
#         "type": "MEMBER_OF",
#         "min_hops": 1,         // default 1
#         "max_hops": 1          // default 1; >1 enables variable-length
#       },
#       "label": "Lab",
#       "match": "ALL",
#       "conditions": [
#         {"property": "name", "operator": "contains", "value": "Sanchez"}
#       ]
#     }
#   ]
# }
#
# Operators by type:
#   string:  equals | not_equals | contains | not_contains |
#            starts_with | ends_with | regex | is_null | is_not_null
#   number:  equals | not_equals | gt | gte | lt | lte | between
#            (between: value is [min, max])
#   date:    before | after | between | is_null | is_not_null
#            (before/after: value is an ISO string or an epoch number)
#   boolean: is_true | is_false
#   null:    is_null | is_not_null

#: Operators that take no value.
NULL_OPS = {'is_null', 'is_not_null', 'is_true', 'is_false'}

#: Operators whose value is a two-element [lo, hi] sequence.
TWO_VALUE = {'between'}


def generate_cypher(filter_def: dict) -> Tuple[str, dict]:
    """Turn a filter definition into a parameterized Cypher query.

    Returns:
        (cypher_string, params_dict)

    Raises:
        ValueError: invalid label, relationship type, property name, or
            operator. User-supplied values are never interpolated into the
            query string.
    """
    body, params, block_count = _generate_body(filter_def)
    return_vars = ", ".join(f"n{i}" for i in range(block_count))
    return body + f"RETURN DISTINCT {return_vars}", params


def generate_count_cypher(filter_def: dict) -> Tuple[str, dict]:
    """Like :func:`generate_cypher`, but counts matches instead of returning them.

    Used to preview result size before committing to a filter.
    """
    body, params, _ = _generate_body(filter_def)
    return body + "RETURN count(*) AS total", params


def _generate_body(filter_def: dict) -> Tuple[str, dict, int]:
    """Build everything up to (but not including) the RETURN clause.

    Shared by both generators so the count query is derived from the same
    structure rather than by rewriting a finished query string.

    Returns:
        (body, params, block_count) — body always ends in a newline.
    """
    blocks = (filter_def or {}).get('blocks') or []
    if not blocks:
        raise ValueError("filter_def must have at least one block")

    params: Dict[str, Any] = {}
    param_idx = [0]   # mutable int in a list so the helper can increment it
    match_parts: List[str] = []
    where_parts: List[str] = []

    for i, block in enumerate(blocks):
        node_var = f"n{i}"
        safe_label = _validate_identifier(block.get('label'))

        if i == 0:
            match_parts.append(f"({node_var}:{safe_label})")
        else:
            via = block.get('via') or {}
            rel_type = _validate_rel_type(via.get('type') or 'RELATES_TO')
            min_h = max(1, _coerce_hops(via.get('min_hops', 1)))
            max_h = max(min_h, _coerce_hops(via.get('max_hops', 1)))

            if min_h == 1 and max_h == 1:
                hop_spec = ""
            elif min_h == max_h:
                hop_spec = f"*{min_h}"
            else:
                hop_spec = f"*{min_h}..{max_h}"

            match_parts.append(f"-[:{rel_type}{hop_spec}]->({node_var}:{safe_label})")

        join_op = "AND" if (block.get('match') or 'ALL') == 'ALL' else "OR"
        cond_parts = []
        for cond in block.get('conditions') or []:
            safe_prop = _validate_identifier(cond.get('property'))
            ref = f"{node_var}.{safe_prop}"
            cond_parts.append(_operator_to_clause(
                ref, cond.get('operator'), cond.get('value'), params, param_idx
            ))

        if cond_parts:
            block_expr = f" {join_op} ".join(cond_parts)
            if len(cond_parts) > 1:
                block_expr = f"({block_expr})"
            where_parts.append(block_expr)

    cypher = "MATCH " + "".join(match_parts) + "\n"
    if where_parts:
        cypher += "WHERE " + "\n  AND ".join(where_parts) + "\n"
    return cypher, params, len(blocks)


def _operator_to_clause(
    ref: str, op: str, value: Any, params: dict, param_idx: list
) -> str:
    """Build a single Cypher WHERE clause fragment, binding any value."""
    if op == 'is_null':
        return f"{ref} IS NULL"
    if op == 'is_not_null':
        return f"{ref} IS NOT NULL"
    if op == 'is_true':
        return f"{ref} = true"
    if op == 'is_false':
        return f"{ref} = false"

    # Everything below binds at least one parameter.
    p = f"v{param_idx[0]}"
    param_idx[0] += 1

    simple = {
        'equals':       ("=", None),
        'not_equals':   ("<>", None),
        'contains':     ("CONTAINS", None),
        'starts_with':  ("STARTS WITH", None),
        'ends_with':    ("ENDS WITH", None),
        'regex':        ("=~", None),
        'gt':           (">", _coerce_num),
        'gte':          (">=", _coerce_num),
        'lt':           ("<", _coerce_num),
        'lte':          ("<=", _coerce_num),
        # Dates are stored either as ISO strings or as epoch numbers; both
        # compare correctly with < and >, so keep whichever we were given.
        'before':       ("<", _coerce_scalar),
        'after':        (">", _coerce_scalar),
    }
    if op in simple:
        cypher_op, coerce = simple[op]
        params[p] = coerce(value) if coerce else value
        return f"{ref} {cypher_op} ${p}"

    if op == 'not_contains':
        params[p] = value
        return f"NOT {ref} CONTAINS ${p}"

    if op == 'between':
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            raise ValueError(f"'between' expects a [min, max] pair, got {value!r}")
        p2 = f"v{param_idx[0]}"
        param_idx[0] += 1
        params[p] = _coerce_scalar(value[0])
        params[p2] = _coerce_scalar(value[1])
        return f"{ref} >= ${p} AND {ref} <= ${p2}"

    raise ValueError(f"Unknown operator: {op!r}")


def _coerce_num(v: Any) -> float:
    """Require a number. For the strictly numeric comparison operators."""
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"Expected a number, got {v!r}")


def _coerce_scalar(v: Any) -> Any:
    """Number if it parses as one, otherwise the value unchanged.

    For operators shared between numbers and dates — ``between`` on a size in
    bytes gets 1000.0, ``between`` on an ISO date keeps '2024-01-01', which is
    what Cypher needs to compare it against a stored string.
    """
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _coerce_hops(v: Any) -> int:
    """Hop counts are interpolated into the query, so they must be real ints."""
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError(f"Expected an integer hop count, got {v!r}")
