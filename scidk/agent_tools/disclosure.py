"""What may leave SciDK toward an AI: ``filter_for_agent``.

Every tool result passes through :func:`filter_for_agent` before any adapter
(MCP, HTTP, OpenAI functions, SciDK's own chat) sends it anywhere. It never
changes stored data; it only decides what an AI sees. This is the start of the
roadmap's sovereignty filter (Cycle 9), so later masking modes extend it.

Policy:
- Each ``(label, property)`` has a ``sharing_mode`` (table ``agent_sharing`` in
  the settings DB). Only ``raw`` (the default) and ``hidden`` are implemented;
  any other mode fails closed and is treated as ``hidden``.
- Records from a high-risk Resource are withheld whole. Graph nodes don't yet
  record which Resource wrote them, so this is a hook: a node with a
  ``source_id`` in ``policy.withheld_sources`` is withheld (Task 2 adds risk).
- Withheld data is never silently missing: the result carries a ``disclosure``
  note the model can repeat.

Values whose label is unknown (map projections, ``properties(n)``, rows from
``RETURN n.x AS y``) are handled conservatively: a key hidden on *any* label is
dropped from a label-less map, and :func:`check_cypher` refuses queries that
read a hidden property name directly, or read properties in ways the filter
can't follow (dynamic keys, APOC), while anything is hidden.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

RAW = 'raw'
HIDDEN = 'hidden'
#: Modes a user can set today. The roadmap's pseudonymized / simulated /
#: randomized are accepted in storage but filtered as hidden until built.
SETTABLE_MODES = (RAW, HIDDEN)

#: Keys the tool layer adds to serialized graph values; never filtered.
META_KEYS = frozenset({'_labels', '_type', '_id', '_start', '_end'})


@dataclass(frozen=True)
class SharingPolicy:
    #: (label, property) -> mode, for every non-raw setting.
    modes: Dict[Tuple[str, str], str] = field(default_factory=dict)
    withheld_sources: FrozenSet[str] = frozenset()

    @property
    def hidden_anywhere(self) -> Set[str]:
        return {prop for (_label, prop), mode in self.modes.items() if mode != RAW}

    def is_hidden(self, labels: Iterable[str], prop: str) -> bool:
        return any(self.modes.get((label, prop), RAW) != RAW for label in labels)

    @property
    def empty(self) -> bool:
        return not self.modes and not self.withheld_sources


# ── Storage ─────────────────────────────────────────────────────────────────

def _connect(settings_db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(settings_db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agent_sharing ("
        " label TEXT NOT NULL, property TEXT NOT NULL, mode TEXT NOT NULL,"
        " updated_at REAL, updated_by TEXT, PRIMARY KEY (label, property))")
    return conn


def load_policy(settings_db: Optional[str]) -> SharingPolicy:
    """The current policy. Raises if the settings DB can't be read: a tool that
    can't tell what is hidden must not answer as if nothing were."""
    if not settings_db:
        return SharingPolicy()
    conn = _connect(settings_db)
    try:
        rows = conn.execute("SELECT label, property, mode FROM agent_sharing").fetchall()
    finally:
        conn.close()
    return SharingPolicy(modes={(l, p): m for l, p, m in rows if m != RAW})


def list_modes(settings_db: str) -> List[Dict[str, Any]]:
    conn = _connect(settings_db)
    try:
        rows = conn.execute(
            "SELECT label, property, mode, updated_at, updated_by FROM agent_sharing "
            "ORDER BY label, property").fetchall()
    finally:
        conn.close()
    return [dict(zip(('label', 'property', 'mode', 'updated_at', 'updated_by'), r)) for r in rows]


def set_mode(settings_db: str, label: str, prop: str, mode: str, user: Optional[str] = None) -> None:
    if mode not in SETTABLE_MODES:
        raise ValueError(f"sharing_mode must be one of {', '.join(SETTABLE_MODES)}")
    conn = _connect(settings_db)
    try:
        if mode == RAW:
            conn.execute("DELETE FROM agent_sharing WHERE label=? AND property=?", (label, prop))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO agent_sharing(label, property, mode, updated_at, updated_by) "
                "VALUES (?,?,?,?,?)", (label, prop, mode, time.time(), user))
        conn.commit()
    finally:
        conn.close()


# ── Cypher pre-check ────────────────────────────────────────────────────────

_APOC = re.compile(r'\bapoc\s*\.', re.IGNORECASE)
# A '[' after one of these opens a list literal, not a subscript.
_LIST_AFTER = frozenset({'IN', 'RETURN', 'WITH', 'UNWIND', 'AND', 'OR', 'XOR', 'NOT', 'WHERE',
                         'THEN', 'ELSE', 'WHEN', 'CASE', 'BY', 'AS', 'ANY', 'ALL', 'NONE',
                         'SINGLE', 'DISTINCT', 'YIELD', 'IS', 'CONTAINS', 'STARTS', 'ENDS'})
_SAFE_SUBSCRIPT = re.compile(r"^\s*(?:-?\d*\s*\.\.\s*-?\d*|-?\d+|'[^']*'|\"[^\"]*\")\s*$")


def _dynamic_subscript(cypher: str) -> bool:
    """True if the query subscripts a value with a computed key (n[$k], n[x]).

    Integer indexes, integer slices and string-literal keys are fine (a literal
    naming a hidden property is caught by name). List literals, relationship
    patterns (-[r]->) and label lists aren't subscripts at all.
    """
    for m in re.finditer(r'\[', cypher):
        before = cypher[:m.start()].rstrip()
        if not before or not (before[-1].isalnum() or before[-1] in '_`)]'):
            continue
        word = re.search(r'(\w+)$', before)
        if word and word.group(1).upper() in _LIST_AFTER:
            continue
        depth, end = 1, m.end()
        while end < len(cypher) and depth:
            depth += {'[': 1, ']': -1}.get(cypher[end], 0)
            end += 1
        if not _SAFE_SUBSCRIPT.match(cypher[m.end():end - 1]):
            return True
    return False


def check_cypher(cypher: str, policy: SharingPolicy,
                 parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """None if the query may run, else why not.

    Only applies while something is hidden. Refuses reading a hidden property
    name (``n.ssn``, ``{.ssn}``, ``n['ssn']``), dynamic keys the filter can't
    resolve (``n[$key]``), and APOC (``apoc.convert.toJson(n)`` turns a node
    into a string the filter can't look inside).
    """
    hidden = policy.hidden_anywhere
    if not hidden:
        return None
    for prop in sorted(hidden):
        name = re.escape(prop)
        if re.search(rf"\.\s*`?{name}`?(?![\w`])", cypher) or re.search(rf"\[\s*['\"]{name}['\"]\s*\]", cypher):
            return (f"This query reads the property `{prop}`, which sharing settings hide from AI tools. "
                    "Ask without it, or ask an admin to change the setting in Entities.")
    if _dynamic_subscript(cypher):
        return ("Dynamic property access (n[key]) isn't allowed while sharing settings hide properties; "
                "name the properties you need.")
    if _APOC.search(cypher):
        return "APOC procedures aren't allowed while sharing settings hide properties."
    for value in (parameters or {}).values():
        if isinstance(value, str) and value in hidden:
            return f"A query parameter names the hidden property `{value}`."
    return None


# ── The filter ──────────────────────────────────────────────────────────────

@dataclass
class _Tally:
    properties: int = 0
    records: int = 0
    labels: Set[str] = field(default_factory=set)


def _filter_value(value: Any, policy: SharingPolicy, tally: _Tally, hidden_any: Set[str]) -> Any:
    if isinstance(value, dict):
        labels = value.get('_labels') or ([value['_type']] if value.get('_type') else None)
        if policy.withheld_sources and value.get('source_id') in policy.withheld_sources:
            tally.records += 1
            return None
        out = {}
        for key, item in value.items():
            if key in META_KEYS:
                out[key] = item
                continue
            hide = policy.is_hidden(labels, key) if labels else key in hidden_any
            if hide:
                tally.properties += 1
                tally.labels.update(labels or ['(unlabelled)'])
                continue
            out[key] = _filter_value(item, policy, tally, hidden_any)
        return out
    if isinstance(value, list):
        return [_filter_value(v, policy, tally, hidden_any) for v in value]
    return value


def filter_for_agent(result: Dict[str, Any], policy: SharingPolicy) -> Dict[str, Any]:
    """Return ``result`` with everything the policy withholds removed, plus a note.

    Walks the whole result, so a tool can't leak by putting records under an
    unexpected key. Graph values must already be serialized to dicts carrying
    ``_labels`` / ``_type`` (tools_graph.serialize).
    """
    if policy.empty:
        return result
    tally = _Tally()
    filtered = _filter_value(result, policy, tally, policy.hidden_anywhere)
    if tally.properties or tally.records:
        parts = []
        if tally.records:
            parts.append(f"{tally.records} record(s) withheld (from a high-risk source)")
        if tally.properties:
            parts.append(f"{tally.properties} property value(s) withheld on "
                         f"{', '.join(sorted(tally.labels))}")
        filtered['disclosure'] = {
            'withheld_records': tally.records,
            'withheld_properties': tally.properties,
            'note': '; '.join(parts) + ' by SciDK sharing settings. Say so rather than '
                    'answering as if the data does not exist.',
        }
    return filtered
