"""What the column-mapping UI needs and the mapping engine does not.

Cycle 3B Task D. Two questions the mapping page asks that no other caller has:

* **Which transforms may I offer, and how is each one used?**
  :func:`describe_transforms` answers by introspecting the callables themselves,
  rather than from a hand-maintained list that would drift the first time a plugin
  published a seventh transform. What the UI actually needs to know is narrower
  than a full signature: whether a transform converts a *cell* or resolves a
  *row*, whether its output is one value or a whole object, and whether it
  requires arguments the UI has no field for.

* **Is this source's mapping defined, and how far?** :func:`mapping_summary` is the
  ``schema_summary`` of ``mapping_json`` — what the source card badge and the Step 3
  indicator read. Tolerant by the same rule: it runs on whatever is in the column,
  including a config hand-written before a rule existed, and reports
  ``defined: False`` rather than raising into a page render.

Neither function validates. :meth:`~scidk.pipeline.mapping_engine.MappingEngine.validate`
is the authority on whether a config can run, and duplicating any of its rules
here would give the UI a second opinion to disagree with.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .transforms import CORE_TRANSFORMS

logger = logging.getLogger(__name__)

__all__ = [
    "RETURNS_LIST",
    "RETURNS_OBJECT",
    "RETURNS_OBJECT_LIST",
    "RETURNS_SCALAR",
    "RETURNS_UNKNOWN",
    "describe_transforms",
    "mapping_summary",
]

#: What a transform's output can be assigned to, derived from its return
#: annotation. The distinction the UI needs is object-vs-scalar: a transform
#: returning ``{"name", "email"}`` cannot fill a single property, it needs the
#: ``source``/``property_map`` form, and offering it in a per-property dropdown
#: would produce a config that writes a dict into a Neo4j property.
RETURNS_SCALAR = "scalar"
RETURNS_LIST = "list"
RETURNS_OBJECT = "object"
RETURNS_OBJECT_LIST = "object_list"
RETURNS_UNKNOWN = "unknown"


def describe_transforms(
    plugin_transforms: Optional[Mapping[str, Callable]] = None
) -> List[Dict[str, Any]]:
    """Describe every transform a mapping config for this source may name.

    Args:
        plugin_transforms: The plugin's library, from
            :func:`~scidk.pipeline.plugin_registry.transform_library_for`.
            Layered over :data:`~scidk.pipeline.transforms.CORE_TRANSFORMS` exactly
            as :class:`~scidk.pipeline.mapping_engine.MappingEngine` layers it, so
            the dropdown offers what the engine will actually resolve — including a
            plugin transform that shadows a core one, flagged as such.

    Returns:
        One dict per transform, sorted by name:

        ``name``
            The name a config uses.
        ``origin``
            ``'core'`` or ``'plugin'``.
        ``shadows_core``
            True for a plugin transform overriding a core name. The engine warns
            about this; the UI says which one it is offering.
        ``takes_row``
            It declares a ``row`` parameter, so it resolves *between* columns
            rather than converting one — the ``sp_colresolution`` convention. Such
            a transform is not attachable to a single column.
        ``takes_value``
            It converts one cell. The negation of ``takes_row``, per that same
            convention.
        ``returns``
            One of the ``RETURNS_*`` constants.
        ``args``
            Extra keyword arguments, ``[{name, required, default}]``. ``required``
            means there is no default, so the config must supply it in
            ``transform_args``.
        ``selectable``
            Whether the UI may offer it as a per-column transform: it converts a
            cell and needs no arguments the mapping page has no field for.
            ``False`` is not "broken" — it means this transform has to be written
            into the JSON by hand, which is where ``column_resolution`` lives.
        ``summary``
            First line of the docstring.
    """
    plugin_transforms = dict(plugin_transforms or {})
    merged: Dict[str, Callable] = {**CORE_TRANSFORMS, **plugin_transforms}

    described: List[Dict[str, Any]] = []
    for name in sorted(merged):
        entry = _describe_one(name, merged[name])
        entry["origin"] = "plugin" if name in plugin_transforms else "core"
        entry["shadows_core"] = name in plugin_transforms and name in CORE_TRANSFORMS
        described.append(entry)
    return described


def _describe_one(name: str, transform: Callable) -> Dict[str, Any]:
    """Introspect one transform, tolerating one that cannot be introspected.

    A C callable or a functools object has no signature; reporting it as usable
    with no arguments is the safe reading, because the engine will call it with a
    value and nothing else.
    """
    try:
        signature = inspect.signature(transform)
        parameters = [
            p for p in signature.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.KEYWORD_ONLY)
        ]
        returns = _classify_return(signature.return_annotation)
    except (TypeError, ValueError):  # pragma: no cover - builtins and C callables
        parameters = []
        returns = RETURNS_UNKNOWN

    # The documented convention: a transform declaring `row` is choosing between
    # columns, so the engine calls it with no cell value at all
    # (MappingEngine._transform_value). That is what makes it un-attachable to a
    # single column rather than merely unusual.
    takes_row = any(p.name == "row" for p in parameters)
    arguments = [p for p in parameters if p.name != "row"]
    if not takes_row and arguments:
        arguments = arguments[1:]  # the first positional is the cell value

    args = [
        {
            "name": p.name,
            "required": p.default is inspect.Parameter.empty,
            "default": p.default if _is_jsonable(p.default) else None,
        }
        for p in arguments
    ]
    return {
        "name": name,
        "takes_row": takes_row,
        "takes_value": not takes_row,
        "returns": returns,
        "args": args,
        "selectable": not takes_row and not any(a["required"] for a in args),
        "summary": _first_line(transform),
    }


def _classify_return(annotation: Any) -> str:
    """Map a return annotation onto a ``RETURNS_*`` constant.

    Matched as text, which handles both forms in circulation: the transform
    modules use ``from __future__ import annotations`` so their annotations arrive
    as strings, while a plugin written without it supplies real typing objects.
    """
    if annotation is inspect.Signature.empty or annotation is None:
        return RETURNS_UNKNOWN
    text = annotation if isinstance(annotation, str) else str(annotation)
    has_dict = "Dict" in text or "dict" in text or "Mapping" in text
    list_at = min(
        (text.index(token) for token in ("List", "list", "Sequence", "Tuple", "tuple")
         if token in text),
        default=-1,
    )
    if has_dict:
        dict_at = min(
            text.index(token) for token in ("Dict", "dict", "Mapping") if token in text
        )
        if list_at != -1 and list_at < dict_at:
            return RETURNS_OBJECT_LIST
        return RETURNS_OBJECT
    if list_at != -1:
        return RETURNS_LIST
    return RETURNS_SCALAR


def _is_jsonable(value: Any) -> bool:
    """Whether a default value can go into a JSON response as itself."""
    return isinstance(value, (str, int, float, bool)) or value is None


def _first_line(transform: Callable) -> str:
    """The first line of a transform's docstring, for the dropdown's help text."""
    doc = inspect.getdoc(transform) or ""
    return doc.strip().split("\n", 1)[0].strip()


# ------------------------------------------------------------------- summary

def mapping_summary(mapping: Any) -> Dict[str, Any]:
    """Counts and names for the source card and the Step 3 indicator.

    Structural only: no plugin is resolved and no transform name is checked, so
    this is safe to call once per source in the list route. Whether the mapping
    can *run* is :meth:`MappingEngine.validate`'s answer and the FAIR check's to
    report.

    Args:
        mapping: Whatever is in ``pipeline_source.mapping_json`` — a parsed
            config, or None.

    Returns:
        ``defined`` is True once at least one node mapping exists. ``roles_by_label``
        is what the relationship panel's role selectors are built from: two entries
        sharing a label are two roles of it, which is how one row produces both a PI
        and a submitter Person.
    """
    empty = {
        "defined": False,
        "labels": [],
        "roles": [],
        "roles_by_label": {},
        "node_mapping_count": 0,
        "relationship_mapping_count": 0,
        "relationship_types": [],
        "property_count": 0,
        "mapped_columns": [],
        "unkeyed_roles": [],
    }
    if not isinstance(mapping, Mapping):
        return empty

    node_mappings = [m for m in (mapping.get("node_mappings") or []) if isinstance(m, Mapping)]
    labels: List[str] = []
    roles: List[str] = []
    roles_by_label: Dict[str, List[str]] = {}
    property_count = 0
    unkeyed: List[str] = []

    for entry in node_mappings:
        label = str(entry.get("label") or "").strip()
        role = str(entry.get("id") or "").strip()
        if label and label not in labels:
            labels.append(label)
        if role:
            roles.append(role)
        if label:
            roles_by_label.setdefault(label, []).append(role)
        property_count += len(_property_names(entry))
        if not entry.get("key_property"):
            unkeyed.append(role or label or "(unnamed)")

    relationships = [
        r for r in (mapping.get("relationship_mappings") or []) if isinstance(r, Mapping)
    ]
    types: List[str] = []
    for rel in relationships:
        rel_type = str(rel.get("type") or "").strip()
        if rel_type and rel_type not in types:
            types.append(rel_type)

    return {
        "defined": bool(node_mappings),
        "labels": labels,
        "roles": roles,
        "roles_by_label": roles_by_label,
        "node_mapping_count": len(node_mappings),
        "relationship_mapping_count": len(relationships),
        "relationship_types": types,
        "property_count": property_count,
        "mapped_columns": _mapped_columns(mapping),
        "unkeyed_roles": unkeyed,
    }


def _property_names(entry: Mapping[str, Any]) -> Sequence[str]:
    """Property names one node mapping declares, in either form.

    Deliberately independent of ``MappingEngine._declared_property_names``: that
    one is private to the engine and answers the same question for validation,
    where a malformed entry must be reported. Here a malformed entry is simply
    not counted.
    """
    if entry.get("properties"):
        return [
            str(spec["name"])
            for spec in entry["properties"]
            if isinstance(spec, Mapping) and spec.get("name")
        ]
    return [str(v) for v in (entry.get("property_map") or {}).values() if v]


def _mapped_columns(mapping: Mapping[str, Any]) -> List[str]:
    """Source columns the config reads, best-effort and without the engine.

    ``MappingEngine.mapped_columns`` is the exact answer and includes columns
    named indirectly inside ``transform_args`` and fallback templates — but
    constructing an engine needs a transform library, which needs the plugin
    resolved. For a card badge saying "12 columns mapped" the direct references
    are enough, and getting them cannot fail on a config the engine would reject.
    """
    columns: List[str] = []

    def note(value: Any) -> None:
        if isinstance(value, str) and value.strip() and value not in columns:
            columns.append(value)

    for entry in mapping.get("node_mappings") or []:
        if not isinstance(entry, Mapping):
            continue
        for spec in entry.get("properties") or []:
            if isinstance(spec, Mapping):
                note(spec.get("column"))
                if isinstance(spec.get("fallback"), Mapping):
                    note(spec["fallback"].get("column"))
        source = entry.get("source")
        if isinstance(source, Mapping):
            note(source.get("column"))
            if isinstance(source.get("fallback"), Mapping):
                note(source["fallback"].get("column"))
    return columns
