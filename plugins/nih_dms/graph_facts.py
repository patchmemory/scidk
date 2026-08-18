"""Read the graph once and return what a DMS plan needs to know.

Every Neo4j and SQLite read in this plugin happens here, so that
:mod:`plugins.nih_dms.generator` is a pure function from :class:`GraphFacts` to
markdown — which is what makes the prose testable without a database.

The queries are chosen to be honest rather than convenient:

* **Label counts** come from the count store, one ``count(n)`` per label. Exact
  and effectively free. A node with two labels is counted under both, which is
  said in the plan rather than silently averaged away.
* **Format distribution** aggregates every ``:File`` node. This is a real scan
  (~4s on the 5.1M-file AIPT graph) and it is the default anyway, because a
  bounded prefix of that graph is demonstrably wrong about the lab's data — see
  the note on :data:`~plugins.nih_dms.config.FILE_SAMPLE_LIMIT`.
* **Modalities** are discovered from ``db.schema.nodeTypeProperties`` and
  ``db.schema.relTypeProperties``, so a property is only queried for its values
  when it actually exists. Nothing is probed blindly.
* **PHI** is read from the same schema procedures, which describe current nodes,
  and cross-checked against ``db.propertyKeys``. The two are reported separately
  because they mean different things: a key in the key store with no node
  carrying it is a weaker signal than a property on live data, and conflating
  them would put a false PHI warning in a grant application.

Nothing here raises for a *missing* fact. An absent modality property, an empty
``label_profile`` and a ``sharing_modes`` column that does not exist yet (it
arrives in Cycle 9 Task A) are all normal states, and each becomes a visible
prompt in the draft. The one thing that does raise is an unusable graph
connection, because a DMS plan with no data behind it must not be handed to a
researcher as though it were finished.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import config as cfg

logger = logging.getLogger(__name__)

#: Labels and property names are interpolated into Cypher rather than
#: parameterized — Neo4j does not accept them as parameters. Everything
#: interpolated is read back out of the database's own schema procedures, but it
#: is still checked against this pattern first: the cost of being wrong is a
#: Cypher injection through a label name, and the check is one line.
#: (Same guard pattern as ``canvas_service._LABEL_RE``.)
_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class GraphUnavailable(RuntimeError):
    """No usable graph connection, so there are no facts to report.

    Raised rather than returning empty facts: a plan generated from nothing would
    look like a plan, and the whole value of this plugin is that its numbers are
    real.
    """


def _safe_ident(name: Any) -> Optional[str]:
    """Return ``name`` if it is safe to interpolate into Cypher, else ``None``."""
    text = str(name or '')
    return text if _IDENT_RE.match(text) else None


# --------------------------------------------------------------------- facts


@dataclass(frozen=True)
class FormatRow:
    """One file format observed in the graph."""

    extension: str          # '.tif', or '' for files with no extension
    count: int
    bytes: int
    format_name: str        # 'TIFF', or 'Unclassified' when not in the table
    standard: Optional[str] # the community standard, when one is known


@dataclass(frozen=True)
class ModalityFinding:
    """Distinct values of one property that names a modality, assay or protocol."""

    source: str                       # 'Sample.modality' / 'DERIVED_FROM.protocol_title'
    on_relationship: bool
    values: Tuple[Tuple[str, int], ...]   # (value, count), commonest first
    truncated: bool                   # more distinct values than we listed


@dataclass(frozen=True)
class PHIHit:
    """A property name that looks like a direct identifier."""

    property_name: str
    #: Where it was seen: a label, a relationship type, a ``label_profile`` row,
    #: or ``'(property key store)'`` for the weaker key-store-only signal.
    location: str
    #: 'graph' — on current nodes or relationships (strong).
    #: 'label_profile' — named in the schema layer (strong: someone curated it).
    #: 'property_key_store' — the key exists but no current node carries it (weak).
    evidence: str


@dataclass(frozen=True)
class GraphFacts:
    """Everything the four DMS sections are derived from."""

    label_counts: Tuple[Tuple[str, int], ...] = ()
    labels_truncated: bool = False
    relationship_counts: Tuple[Tuple[str, int], ...] = ()

    file_count: int = 0
    file_bytes: int = 0
    formats: Tuple[FormatRow, ...] = ()
    formats_truncated: bool = False
    #: None when the format breakdown is exact; the cap when it was sampled.
    format_sample_limit: Optional[int] = None
    #: Files whose ``mime_type`` is set, and the commonest values. Reported
    #: because coverage is partial on real graphs (4.6M of 5.1M null on AIPT) and
    #: a plan should not imply otherwise.
    mime_known: int = 0
    mime_types: Tuple[Tuple[str, int], ...] = ()

    modalities: Tuple[ModalityFinding, ...] = ()
    collection_profiles: Tuple[ModalityFinding, ...] = ()

    phi_hits: Tuple[PHIHit, ...] = ()

    #: {label: {property: mode}} from ``label_profile.sharing_modes``.
    sharing_modes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: False when the column does not exist yet (pre-Cycle 9), which is not the
    #: same as "exists and is empty" and is worded differently in the draft.
    sharing_modes_supported: bool = False
    #: Labels curated in ``label_profile`` — used to decide whether the schema
    #: layer was rich enough for its PHI scan to mean anything.
    profiled_labels: Tuple[str, ...] = ()

    #: From ``publication.dms.*`` settings. None where unset.
    repository: Optional[str] = None
    retention_years: Optional[str] = None
    sharing_mode: Optional[str] = None
    access_contact: Optional[str] = None

    #: Non-fatal problems worth showing the user next to the draft.
    warnings: Tuple[str, ...] = ()

    @property
    def total_nodes(self) -> int:
        """Sum of per-label counts.

        Greater than the true node count when nodes carry several labels, and
        equal to it when they do not. Named ``total_nodes`` and explained in the
        plan text rather than presented as gospel.
        """
        return sum(count for _, count in self.label_counts)

    @property
    def has_phi(self) -> bool:
        """Any PHI signal at all, including the weak key-store-only one."""
        return bool(self.phi_hits)

    @property
    def confirmed_phi_hits(self) -> Tuple[PHIHit, ...]:
        """PHI seen on live data or curated in the schema layer."""
        return tuple(h for h in self.phi_hits if h.evidence != 'property_key_store')


# ------------------------------------------------------------------- Neo4j


def _read(client: Any, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run a read query through whatever client shape we were handed.

    ``Neo4jClient.execute_read`` is the normal case; a bare neo4j driver is
    accepted too so the plugin can be pointed at a driver directly (which is what
    :mod:`scidk.rocrate_bridge` does, and what the tests' fake exposes).
    """
    if hasattr(client, 'execute_read'):
        return list(client.execute_read(query, params or {}))
    if hasattr(client, 'session'):
        with client.session() as session:
            return [dict(record) for record in session.run(query, **(params or {}))]
    raise GraphUnavailable(
        'The object passed as a graph client can neither execute_read() nor open a session().'
    )


def _read_optional(client: Any, query: str, what: str,
                   warnings: List[str]) -> List[Dict[str, Any]]:
    """Run a query whose failure should degrade the plan, not abort it.

    Used for the schema procedures and the format scan. ``db.schema.*`` needs
    privileges a read-only role may not have, and a plan missing its modality
    table is far more useful than a 500.
    """
    try:
        return _read(client, query)
    except Exception as exc:  # noqa: BLE001 - a missing fact is a fact about the plan
        logger.warning('nih_dms: %s failed: %s', what, exc)
        warnings.append(f'Could not read {what}: {exc}')
        return []


def _label_counts(client: Any, warnings: List[str]) -> Tuple[Tuple[Tuple[str, int], ...], bool]:
    """Per-label node counts from the count store, commonest first.

    The label list is the one read that is *not* allowed to degrade. Every section
    is derived from it, and a failure here is indistinguishable downstream from an
    empty graph — which would put "this graph holds no nodes" into a document
    describing a graph holding millions. So it raises instead.
    """
    try:
        rows = _read(client, 'CALL db.labels()')
    except Exception as exc:  # noqa: BLE001 - not a degradable fact
        raise GraphUnavailable(
            f'Could not read the graph\'s label list, so there is nothing reliable to '
            f'describe: {exc}'
        ) from exc

    labels = [_safe_ident(r.get('label')) for r in rows]
    labels = [l for l in labels if l]

    truncated = len(labels) > cfg.MAX_LABELS
    counts: List[Tuple[str, int]] = []
    for label in labels[:cfg.MAX_LABELS]:
        try:
            got = _read(client, f'MATCH (n:`{label}`) RETURN count(n) AS c')
        except Exception as exc:  # noqa: BLE001 - skip the label, keep the plan
            logger.warning('nih_dms: count for label %s failed: %s', label, exc)
            continue
        count = int((got[0] if got else {}).get('c') or 0)
        if count:
            counts.append((label, count))

    counts.sort(key=lambda pair: (-pair[1], pair[0]))
    return tuple(counts), truncated


def _relationship_counts(client: Any, warnings: List[str]) -> Tuple[Tuple[str, int], ...]:
    """Per-type relationship counts from the count store, commonest first."""
    rows = _read_optional(client, 'CALL db.relationshipTypes()',
                          'the relationship type list', warnings)
    types = [_safe_ident(r.get('relationshipType')) for r in rows]

    counts: List[Tuple[str, int]] = []
    for rel_type in [t for t in types if t][:cfg.MAX_LABELS]:
        try:
            got = _read(client, f'MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS c')
        except Exception as exc:  # noqa: BLE001 - skip the type, keep the plan
            logger.warning('nih_dms: count for relationship %s failed: %s', rel_type, exc)
            continue
        count = int((got[0] if got else {}).get('c') or 0)
        if count:
            counts.append((rel_type, count))

    counts.sort(key=lambda pair: (-pair[1], pair[0]))
    return tuple(counts)


def _property_keys(client: Any, warnings: List[str]) -> List[str]:
    """Every property key the database has minted. Reads a token store; instant."""
    return [
        str(row.get('propertyKey'))
        for row in _read_optional(client, 'CALL db.propertyKeys()',
                                  'the property key list', warnings)
        if row.get('propertyKey')
    ]


def _rel_schema_properties(client: Any, warnings: List[str]) -> Dict[str, List[str]]:
    """``{rel_type: [property, ...]}`` for relationships that currently exist."""
    rel_props: Dict[str, List[str]] = {}
    for row in _read_optional(client, 'CALL db.schema.relTypeProperties()',
                              'the relationship property schema', warnings):
        prop = row.get('propertyName')
        if not prop:
            continue  # a type with no properties at all
        # relTypeProperties reports the type as ":`DERIVED_FROM`".
        rel_type = str(row.get('relType') or '').strip(':`')
        if not rel_type:
            continue
        rel_props.setdefault(rel_type, [])
        if str(prop) not in rel_props[rel_type]:
            rel_props[rel_type].append(str(prop))
    return rel_props


def _node_schema_properties(client: Any, warnings: List[str]) -> Dict[str, List[str]]:
    """``{label: [property, ...]}`` for nodes that currently exist.

    The expensive call in this module — ~9s on the 5.1M-node AIPT graph, because
    it inspects the node store rather than a counter. :func:`_schema_properties`
    decides whether it is needed at all.
    """
    node_props: Dict[str, List[str]] = {}
    for row in _read_optional(client, 'CALL db.schema.nodeTypeProperties()',
                              'the node property schema', warnings):
        prop = row.get('propertyName')
        if not prop:
            continue  # a label with no properties at all
        for label in row.get('nodeLabels') or []:
            node_props.setdefault(str(label), [])
            if str(prop) not in node_props[str(label)]:
                node_props[str(label)].append(str(prop))
    return node_props


def _schema_properties(client: Any, warnings: List[str], deep: bool = False) -> Tuple[
    Dict[str, List[str]], Dict[str, List[str]]
]:
    """``({label: [property, ...]}, {rel_type: [property, ...]})`` for current data.

    Read from ``db.schema.nodeTypeProperties`` / ``relTypeProperties``, which
    describe what is on nodes and relationships *now*. That distinction is the
    whole point for PHI: ``db.propertyKeys`` also lists keys whose last node was
    deleted, and a plan must not warn about identifiers the graph no longer holds
    as though they were present.

    Both procedures are skipped when the cheap key store proves there is nothing
    to find, and the node procedure — the 9s one — is additionally skipped when
    the relationship schema already accounts for every property we were looking
    for. Two exceptions to that shortcut, because they are the cases where being
    fast is worth less than being right:

    * any PHI-shaped key in the key store forces the full node read, since a
      missed identifier is the expensive mistake here;
    * ``deep=True`` forces it unconditionally.

    When the shortcut does apply, a property present on both a relationship and a
    node would have only its relationship occurrence reported. That is a modality
    listing being less complete, never a PHI warning being missed, and it is
    recorded in ``warnings`` rather than passed off as a full inventory.
    """
    keys = _property_keys(client, warnings)
    canonical_keys = {cfg.canonical_property(k): k for k in keys}

    phi_candidates = {c for c in canonical_keys if c in cfg.PHI_CANONICAL}
    modality_wanted = {cfg.canonical_property(n) for n in cfg.MODALITY_PROPERTIES}
    modality_candidates = {c for c in canonical_keys if c in modality_wanted}

    if not deep and not phi_candidates and not modality_candidates:
        # Nothing in the graph is named like a modality or an identifier, so
        # neither procedure can tell us anything we would print.
        return {}, {}

    rel_props = _rel_schema_properties(client, warnings)
    explained = {
        cfg.canonical_property(prop)
        for props in rel_props.values() for prop in props
    }

    need_nodes = (
        deep
        or bool(phi_candidates)                       # never shortcut PHI
        or bool(modality_candidates - explained)      # something rels didn't explain
    )
    if not need_nodes:
        found = ', '.join(sorted(canonical_keys[c] for c in modality_candidates))
        warnings.append(
            'Modality properties were found on relationships '
            f'({found}), so the per-label property scan was skipped to keep this '
            'fast. Pass deep=1 to scan node properties as well.'
        )
        return {}, rel_props

    return _node_schema_properties(client, warnings), rel_props


@dataclass(frozen=True)
class _FileScan:
    """Everything one pass over the ``:File`` nodes yields."""

    formats: Tuple[FormatRow, ...] = ()
    formats_truncated: bool = False
    file_count: int = 0
    file_bytes: int = 0
    mime_known: int = 0
    mime_types: Tuple[Tuple[str, int], ...] = ()


def _file_scan(client: Any, sample_limit: Optional[int], warnings: List[str]) -> _FileScan:
    """Format distribution, totals and MIME coverage — from a single pass.

    Grouping by ``(extension, mime_type)`` rather than running one query per
    figure turns three scans of the file store into one: on the AIPT graph 6.8s
    instead of 11s, for 308 rows that are then folded in Python. The totals are
    sums over every group, so they stay exact rather than being the top-N subtotal.

    Extensions are folded to lower case, so ``.TIF`` and ``.tif`` are one format —
    a real index holds both, and splitting them would overstate the format count.
    """
    scope = f'MATCH (f:File) WITH f LIMIT {int(sample_limit)}' if sample_limit else 'MATCH (f:File)'
    rows = _read_optional(
        client,
        f'{scope} RETURN toLower(coalesce(f.extension, "")) AS ext, f.mime_type AS mime, '
        f'count(*) AS c, sum(f.size_bytes) AS b',
        'the file format distribution', warnings,
    )
    if not rows:
        return _FileScan()

    by_ext: Dict[str, List[int]] = {}       # ext -> [count, bytes]
    by_mime: Dict[str, int] = {}
    file_count = 0
    file_bytes = 0
    mime_known = 0

    for row in rows:
        ext = str(row.get('ext') or '')
        count = int(row.get('c') or 0)
        size = int(row.get('b') or 0)

        entry = by_ext.setdefault(ext, [0, 0])
        entry[0] += count
        entry[1] += size
        file_count += count
        file_bytes += size

        mime = row.get('mime')
        if mime:
            mime_known += count
            by_mime[str(mime)] = by_mime.get(str(mime), 0) + count

    ranked = sorted(by_ext.items(), key=lambda item: (-item[1][0], item[0]))
    formats = tuple(
        FormatRow(
            extension=ext,
            count=totals[0],
            bytes=totals[1],
            format_name=cfg.FORMAT_STANDARDS.get(ext, ('Unclassified', None))[0],
            standard=cfg.FORMAT_STANDARDS.get(ext, ('Unclassified', None))[1],
        )
        for ext, totals in ranked[:cfg.MAX_FORMATS]
    )

    mime_types = tuple(
        sorted(by_mime.items(), key=lambda item: (-item[1], item[0]))
    )[:cfg.DISTINCT_VALUE_LIMIT]

    return _FileScan(
        formats=formats,
        formats_truncated=len(ranked) > cfg.MAX_FORMATS,
        file_count=file_count,
        file_bytes=file_bytes,
        mime_known=mime_known,
        mime_types=mime_types,
    )


def _distinct_values(client: Any, owner: str, prop: str, on_relationship: bool,
                     warnings: List[str]) -> Optional[ModalityFinding]:
    """Distinct non-null values of one property, commonest first."""
    safe_owner, safe_prop = _safe_ident(owner), _safe_ident(prop)
    if not safe_owner or not safe_prop:
        return None

    pattern = (f'MATCH ()-[x:`{safe_owner}`]->()' if on_relationship
               else f'MATCH (x:`{safe_owner}`)')
    rows = _read_optional(
        client,
        f'{pattern} WHERE x.`{safe_prop}` IS NOT NULL '
        f'RETURN x.`{safe_prop}` AS v, count(*) AS c '
        f'ORDER BY c DESC LIMIT {cfg.DISTINCT_VALUE_LIMIT + 1}',
        f'values of {owner}.{prop}', warnings,
    )
    if not rows:
        return None

    truncated = len(rows) > cfg.DISTINCT_VALUE_LIMIT
    values = tuple(
        (str(r.get('v')), int(r.get('c') or 0))
        for r in rows[:cfg.DISTINCT_VALUE_LIMIT]
        if str(r.get('v') or '').strip()
    )
    if not values:
        return None

    return ModalityFinding(
        source=f'{owner}.{prop}',
        on_relationship=on_relationship,
        values=values,
        truncated=truncated,
    )


def _modalities(client: Any, node_props: Dict[str, List[str]],
                rel_props: Dict[str, List[str]],
                node_counts: Dict[str, int],
                warnings: List[str]) -> Tuple[Tuple[ModalityFinding, ...],
                                              Tuple[ModalityFinding, ...]]:
    """Modality/assay findings, and collection-profile findings, from the graph.

    Only properties that the schema says exist are queried, and the total number
    of value queries is capped — on a wide graph this could otherwise become
    dozens of scans for one page load.
    """
    wanted = {cfg.canonical_property(name) for name in cfg.MODALITY_PROPERTIES}

    candidates: List[Tuple[str, str, bool]] = []
    for label, props in sorted(node_props.items()):
        for prop in props:
            if cfg.canonical_property(prop) in wanted:
                candidates.append((label, prop, False))
    for rel_type, props in sorted(rel_props.items()):
        for prop in props:
            if cfg.canonical_property(prop) in wanted:
                candidates.append((rel_type, prop, True))

    modalities: List[ModalityFinding] = []
    for owner, prop, on_rel in candidates[:cfg.MAX_MODALITY_QUERIES]:
        finding = _distinct_values(client, owner, prop, on_rel, warnings)
        if finding:
            modalities.append(finding)
    if len(candidates) > cfg.MAX_MODALITY_QUERIES:
        warnings.append(
            f'{len(candidates)} properties could describe a modality; the draft reports the '
            f'first {cfg.MAX_MODALITY_QUERIES}.'
        )

    # Collection profiles need no discovery: config already says which label
    # carries them, and the value query simply returns nothing when the property
    # is absent. So these survive the node-schema shortcut above, which matters —
    # Dataset.type is the one thing on the AIPT graph that states how a collection
    # is structured.
    profiles: List[ModalityFinding] = []
    for label, props in cfg.COLLECTION_PROFILE_PROPERTIES.items():
        if label not in node_counts:
            continue  # the label does not exist here at all
        for prop in props:
            finding = _distinct_values(client, label, prop, False, warnings)
            if finding:
                profiles.append(finding)

    return tuple(modalities), tuple(profiles)


def _phi_from_graph(client: Any, node_props: Dict[str, List[str]],
                    rel_props: Dict[str, List[str]],
                    warnings: List[str]) -> List[PHIHit]:
    """PHI-looking property names on current nodes/relationships, plus key-store hits."""
    hits: List[PHIHit] = []
    seen: set = set()

    for owner_map, evidence_scope in ((node_props, 'label'), (rel_props, 'relationship')):
        for owner, props in sorted(owner_map.items()):
            for prop in props:
                if cfg.canonical_property(prop) in cfg.PHI_CANONICAL:
                    key = (prop, owner)
                    if key not in seen:
                        seen.add(key)
                        hits.append(PHIHit(
                            property_name=prop,
                            location=(owner if evidence_scope == 'label'
                                      else f'[:{owner}] relationship'),
                            evidence='graph',
                        ))

    # The key store is the wider net: it names every property key the database has
    # ever minted. Anything it finds that the schema procedures did not is
    # recorded, but as its own weaker evidence class — a deleted-data key must not
    # read as live PHI.
    attributed = {prop for prop, _ in seen}
    for prop in _property_keys(client, warnings):
        if (prop and prop not in attributed
                and cfg.canonical_property(prop) in cfg.PHI_CANONICAL):
            attributed.add(prop)
            hits.append(PHIHit(
                property_name=prop,
                location='(property key store)',
                evidence='property_key_store',
            ))

    return hits


# ------------------------------------------------------------------ SQLite


def _json_names(raw: Any) -> List[str]:
    """Property names out of a ``label_profile`` JSON array column."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, dict):
        return [str(k) for k in parsed]
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return []


def _label_profile_facts(conn: Optional[sqlite3.Connection],
                         warnings: List[str]) -> Tuple[
    List[PHIHit], Dict[str, Dict[str, str]], bool, Tuple[str, ...]
]:
    """PHI hits, sharing modes, whether the column exists, and profiled labels.

    ``sharing_modes`` is added to ``label_profile`` by Cycle 9 Task A. Until then
    the column is absent, which is why its presence is probed rather than assumed
    — and why "not supported yet" is reported distinctly from "supported but
    unset". They call for different sentences in the plan.
    """
    if conn is None:
        return [], {}, False, ()

    try:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(label_profile)')}
    except sqlite3.Error as exc:
        logger.warning('nih_dms: label_profile unreadable: %s', exc)
        warnings.append(f'Could not read the schema layer (label_profile): {exc}')
        return [], {}, False, ()

    if not columns:
        warnings.append(
            'The schema layer has no label_profile table, so no curated property names '
            'were available to scan for identifiers.'
        )
        return [], {}, False, ()

    has_sharing_modes = 'sharing_modes' in columns
    selected = ['label_name', 'always_include', 'never_include']
    if has_sharing_modes:
        selected.append('sharing_modes')

    try:
        rows = list(conn.execute(f'SELECT {", ".join(selected)} FROM label_profile'))
    except sqlite3.Error as exc:
        logger.warning('nih_dms: label_profile query failed: %s', exc)
        warnings.append(f'Could not read the schema layer (label_profile): {exc}')
        return [], {}, has_sharing_modes, ()

    hits: List[PHIHit] = []
    sharing: Dict[str, Dict[str, str]] = {}
    profiled: List[str] = []
    seen: set = set()

    for row in rows:
        label = str(row[0] or '')
        profiled.append(label)

        # Property names a curator has named for this label. A PHI name here is
        # strong evidence: somebody wrote it down deliberately.
        for prop in _json_names(row[1]) + _json_names(row[2]):
            if cfg.canonical_property(prop) in cfg.PHI_CANONICAL:
                key = (prop, label)
                if key not in seen:
                    seen.add(key)
                    hits.append(PHIHit(
                        property_name=prop,
                        location=f'{label} (schema layer)',
                        evidence='label_profile',
                    ))

        if has_sharing_modes and len(row) > 3 and row[3]:
            try:
                modes = json.loads(row[3])
            except (TypeError, ValueError):
                warnings.append(f'label_profile.sharing_modes for {label} is not valid JSON.')
                continue
            if isinstance(modes, dict) and modes:
                sharing[label] = {str(k): str(v) for k, v in modes.items()}
                for prop in modes:
                    if cfg.canonical_property(prop) in cfg.PHI_CANONICAL:
                        key = (str(prop), label)
                        if key not in seen:
                            seen.add(key)
                            hits.append(PHIHit(
                                property_name=str(prop),
                                location=f'{label} (schema layer)',
                                evidence='label_profile',
                            ))

    return hits, sharing, has_sharing_modes, tuple(profiled)


def _settings(getter: Any, warnings: List[str]) -> Dict[str, Optional[str]]:
    """Read the four ``publication.dms.*`` settings; unset stays None."""
    values: Dict[str, Optional[str]] = {
        'repository': None, 'retention_years': None,
        'sharing_mode': None, 'access_contact': None,
    }
    if getter is None:
        return values

    for field_name, key in (
        ('repository', cfg.SETTING_REPOSITORY),
        ('retention_years', cfg.SETTING_RETENTION_YEARS),
        ('sharing_mode', cfg.SETTING_SHARING_MODE),
        ('access_contact', cfg.SETTING_ACCESS_CONTACT),
    ):
        try:
            raw = getter(key, None)
        except Exception as exc:  # noqa: BLE001 - an unreadable setting is a placeholder
            logger.warning('nih_dms: setting %s unreadable: %s', key, exc)
            warnings.append(f'Could not read the {key} setting: {exc}')
            continue
        text = str(raw).strip() if raw is not None else ''
        if text:
            values[field_name] = text

    mode = values['sharing_mode']
    if mode and mode not in cfg.SHARING_MODES:
        warnings.append(
            f'The configured sharing mode {mode!r} is not one of '
            f'{", ".join(sorted(cfg.SHARING_MODES))}; the draft asks for a choice instead.'
        )
        values['sharing_mode'] = None

    return values


# ------------------------------------------------------------------ collect


def collect_facts(client: Any,
                  sqlite_conn: Optional[sqlite3.Connection] = None,
                  setting_getter: Any = None,
                  sample_limit: Optional[int] = None,
                  deep: bool = False) -> GraphFacts:
    """Gather every fact the plan is built from.

    Args:
        client: A connected ``Neo4jClient`` or a neo4j driver. Required — there is
            no fixture fallback, by design.
        sqlite_conn: Open connection to ``scidk_settings.db``, for the schema
            layer. Optional; without it the plan says the schema layer was not
            consulted rather than claiming a clean PHI scan.
        setting_getter: ``get_setting(key, default)``. Optional.
        sample_limit: Cap the file scan at this many ``:File`` nodes. Trades
            accuracy for latency and is recorded in the output; omit it for the
            exact aggregate, which is the default and what the plan should say.
        deep: Always read the per-label property schema, even when the cheap
            checks show it cannot add anything. Costs ~9s on an AIPT-scale graph;
            see :func:`_schema_properties` for exactly what it buys.

    Returns:
        GraphFacts

    Raises:
        GraphUnavailable: no client, or the graph cannot answer the one query
            every section depends on.
    """
    if client is None:
        raise GraphUnavailable(
            'No Neo4j connection is configured, so there is no graph to describe. '
            'Configure one in Settings → Connections and try again.'
        )

    warnings: List[str] = []

    # One probe first: if this fails the graph is unusable, and every section
    # would be empty. Better to say so than to emit a plan-shaped placeholder.
    try:
        _read(client, 'RETURN 1 AS ok')
    except GraphUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GraphUnavailable(f'Could not query Neo4j: {exc}') from exc

    label_counts, labels_truncated = _label_counts(client, warnings)
    relationship_counts = _relationship_counts(client, warnings)
    node_props, rel_props = _schema_properties(client, warnings, deep=deep)

    if any(label == 'File' for label, _ in label_counts):
        scan = _file_scan(client, sample_limit, warnings)
    else:
        scan = _FileScan()
        warnings.append(
            'The graph holds no :File nodes, so the plan describes no file formats. '
            'Scan a directory and commit the scan to Neo4j to populate this section.'
        )

    modalities, collection_profiles = _modalities(
        client, node_props, rel_props, dict(label_counts), warnings)
    phi_hits = _phi_from_graph(client, node_props, rel_props, warnings)

    profile_hits, sharing_modes, sharing_supported, profiled_labels = _label_profile_facts(
        sqlite_conn, warnings)

    # Merge, keeping one entry per (property, location).
    merged: List[PHIHit] = list(phi_hits)
    known = {(h.property_name, h.location) for h in merged}
    for hit in profile_hits:
        if (hit.property_name, hit.location) not in known:
            known.add((hit.property_name, hit.location))
            merged.append(hit)

    settings = _settings(setting_getter, warnings)

    return GraphFacts(
        label_counts=label_counts,
        labels_truncated=labels_truncated,
        relationship_counts=relationship_counts,
        file_count=scan.file_count,
        file_bytes=scan.file_bytes,
        formats=scan.formats,
        formats_truncated=scan.formats_truncated,
        format_sample_limit=sample_limit,
        mime_known=scan.mime_known,
        mime_types=scan.mime_types,
        modalities=modalities,
        collection_profiles=collection_profiles,
        phi_hits=tuple(merged),
        sharing_modes=sharing_modes,
        sharing_modes_supported=sharing_supported,
        profiled_labels=profiled_labels,
        repository=settings['repository'],
        retention_years=settings['retention_years'],
        sharing_mode=settings['sharing_mode'],
        access_contact=settings['access_contact'],
        warnings=tuple(warnings),
    )
