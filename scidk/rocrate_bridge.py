"""The graph <-> RO-Crate bridge: one place that knows how SciDK maps to a crate.

RO-Crate is how SciDK data leaves the building — to a repository, to a
collaborator, to NextSEEK. Three entry points, because there are three real
situations:

``build_from_map(map_id, driver, output_dir)``
    A Maps canvas layer, exported as it stands. The canvas's
    ``generate_rocrate_export()`` is now a thin wrapper over this.
``build_from_selection(node_ids, driver, output_dir)``
    A Files page selection, resolved against Neo4j.
``ingest_crate(crate_path, driver)``
    Someone else's crate, read back into the graph.

**Export is hand-rolled; import uses the ``rocrate`` library.** That split is
deliberate rather than lazy. The library is file-oriented: it wants to
materialize a crate directory whose entities correspond to files on disk, and
most SciDK entities — a Project, a Person, a Protocol, a provisional node a user
just drew — have no file at all. Building a document in memory is both simpler
and more faithful. Reading is the opposite case: ``@id`` resolution, entity
typing and the spec's quirks are exactly what the library is good at, and
hand-rolling a JSON-LD reader would be fragile in ways a hand-rolled writer is
not. See ``ingest_crate`` for what parsing normalizes.

**Nothing here copies file bytes.** Every crate SciDK produces is a *referenced*
crate: the metadata document points at files where they already live. That is
what makes an export of a 15TB imaging cohort a 200KB file.

Mapping, which is the part worth stating once:

===================  =========================================================
Node label           Crate entity
``Dataset``/``File``  ``File``
anything else        ``Dataset``
===================  =========================================================

===================  =========================================================
Edge type            Crate property
``CONTAINS``         ``hasPart`` — multi-parent needs no special case, because a
                     child simply appears in every parent's array
``ATTACHED_TO``      ``mentions``
anything else        ``relation``, carrying the original type in ``name`` so it
                     survives a round trip through :func:`ingest_crate`
===================  =========================================================
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .pipeline.identifiers import LABEL_RE, PROPERTY_RE, REL_RE
from .services.canvas_service import instance_elements

__all__ = [
    'CONFORMS_TO',
    'CRATE_CONTEXT',
    'CRATE_KEY_PROPERTY',
    'FILE_LABELS',
    'IMPORT_RECORD_SOURCE',
    'METADATA_FILENAME',
    'build_from_map',
    'build_from_selection',
    'crate_document',
    'crate_json',
    'crate_metadata_path',
    'ingest_crate',
]

#: RO-Crate 1.1. Bumping this is a format migration, not a config change: the
#: context URL and the ``conformsTo`` id have to move together.
CRATE_CONTEXT = 'https://w3id.org/ro/crate/1.1/context'
CONFORMS_TO = 'https://w3id.org/ro/crate/1.1'

#: The one filename the spec fixes. Callers that need the written path should ask
#: :func:`crate_metadata_path` rather than re-joining this themselves.
METADATA_FILENAME = 'ro-crate-metadata.json'

#: Labels whose nodes describe something with bytes behind it, so they become
#: crate ``File`` entities. Everything else becomes a ``Dataset``.
FILE_LABELS = ('Dataset', 'File')

#: Node properties copied straight onto an entity, in emission order. Kept short
#: on purpose: a crate consumer understands these, and a SciDK-internal property
#: name in a published crate is noise at best.
ENTITY_PROPERTIES = ('description', 'dateCreated')

#: A snapshot node may carry ``_crate``: crate properties already in the target
#: vocabulary, merged onto the entity after :data:`ENTITY_PROPERTIES`. This is
#: how :func:`build_from_selection` gets ``contentUrl`` and friends onto a File
#: entity without the pure serializer having to know anything about Neo4j
#: property names. Mirrors the existing ``_space`` convention on canvas
#: elements. Canvas snapshots never set it, which is why the golden masters in
#: ``tests/fixtures/rocrate/`` are unaffected by its existence.
CRATE_FACET_KEY = '_crate'

#: Labels a path lookup searches in :func:`build_from_selection`. The Files page
#: selects files and folders, and these are the labels a scan commit writes for
#: them (``web/helpers.py``); restricting the query keeps it index-backed instead
#: of scanning every node in the graph. Anything else must be selected by
#: elementId.
PATH_LABELS = ('File', 'Folder')

#: Stamped on every node :func:`ingest_crate` writes, so an imported entity is
#: distinguishable from one SciDK observed itself. Required by Cycle 7 Task A.
IMPORT_RECORD_SOURCE = 'ro_crate_import'

#: Property imported nodes MERGE on. Not the raw crate ``@id``: those are
#: relative (``a.txt``, ``./``) and would collide across crates. See
#: :func:`_crate_key`.
CRATE_KEY_PROPERTY = 'crate_id'

#: Crate members the spec defines rather than the data — never entities to write.
_NON_ENTITY_IDS = (METADATA_FILENAME, 'ro-crate-metadata.jsonld', 'ro-crate-preview.html')

#: Property names on an imported entity that carry a reference to another
#: entity, mapped to the SciDK relationship type. The inverse of the export's
#: edge mapping.
_IMPORT_EDGE_MAP = {'hasPart': 'CONTAINS', 'mentions': 'ATTACHED_TO'}

#: Fallback when a ``relation`` entry does not name its original type.
_IMPORT_DEFAULT_REL = 'RELATED_TO'


# --------------------------------------------------------------------------
# The pure serializer. No Neo4j, no filesystem, no Flask.
# --------------------------------------------------------------------------

def _entity_id(node_id: str, node: Dict[str, Any]) -> str:
    """The ``@id`` for a canvas/graph node.

    A committed node keeps its Neo4j elementId, which makes the crate traceable
    back to the graph it came from. A provisional one has no such id, so it gets
    a uuid5 over its canvas id — deterministic, so re-exporting the same canvas
    produces the same crate rather than a diff of nothing but identifiers.
    """
    if not node.get('provisional') and node.get('element_id'):
        return str(node.get('element_id'))
    return f"#{uuid.uuid5(uuid.NAMESPACE_URL, str(node_id))}"


def _entity_type(node: Dict[str, Any]) -> str:
    """``File`` or ``Dataset``, per :data:`FILE_LABELS`."""
    return 'File' if str(node.get('label')) in FILE_LABELS else 'Dataset'


def crate_document(
    snapshot: Dict[str, Any],
    root_name: str = 'canvas',
    *,
    root_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Serialize a graph snapshot as an RO-Crate 1.1 metadata document.

    This is the single implementation of the mapping described in the module
    docstring; both builders go through it, so a crate from the Files page and a
    crate from the Maps canvas cannot drift apart.

    Args:
        snapshot: ``{'nodes': [...], 'edges': [...]}`` in canvas shape. Nodes
            carry ``id``, ``label``, ``name``, ``properties``, optionally
            ``element_id``, ``provisional`` and :data:`CRATE_FACET_KEY`. Edges
            carry ``source``, ``target``, ``relationship``. Schema-space elements
            (``_space: "schema"``) are dropped: a schema element describes a
            label *type*, its ``properties`` is a list of names rather than a
            map, and a crate describes entities.
        root_name: ``name`` of the root Dataset — the layer or selection name.
        root_extra: Extra properties for the root entity (``license``,
            ``datePublished``, ``description``). Emitted after ``name`` and
            before ``hasPart``. The canvas path passes nothing, which is what
            keeps its output byte-identical to the pre-bridge implementation.

    Returns:
        The document, ready for :func:`json.dumps`.
    """
    nodes = instance_elements((snapshot or {}).get('nodes'))
    edges = instance_elements((snapshot or {}).get('edges'))
    by_id = {str(n.get('id')): n for n in nodes}

    # One entity per node, keyed by @id.
    id_by_node: Dict[str, str] = {}
    entities: Dict[str, Dict[str, Any]] = {}
    for node_id, node in by_id.items():
        eid = _entity_id(node_id, node)
        id_by_node[node_id] = eid
        props = node.get('properties') or {}
        entity: Dict[str, Any] = {'@id': eid, '@type': _entity_type(node)}
        name = node.get('name') or props.get('name')
        if name:
            entity['name'] = str(name)
        for key in ENTITY_PROPERTIES:
            if props.get(key):
                entity[key] = props.get(key)
        for key, value in (node.get(CRATE_FACET_KEY) or {}).items():
            if value is not None:
                entity[key] = value
        entities[eid] = entity

    # Edges. An edge whose endpoint is not on the canvas is dropped rather than
    # emitted as a dangling @id, which would make the crate invalid.
    has_incoming_contains = set()
    for e in edges:
        src_id, tgt_id = str(e.get('source')), str(e.get('target'))
        if src_id not in id_by_node or tgt_id not in id_by_node:
            continue
        src_ent = entities[id_by_node[src_id]]
        tgt_ref = {'@id': id_by_node[tgt_id]}
        rel = (e.get('relationship') or '').strip().upper()
        if rel == 'CONTAINS':
            src_ent.setdefault('hasPart', []).append(tgt_ref)
            has_incoming_contains.add(tgt_id)
        elif rel == 'ATTACHED_TO':
            src_ent.setdefault('mentions', []).append(tgt_ref)
        else:
            src_ent.setdefault('relation', []).append(
                {'@id': id_by_node[tgt_id], 'name': (e.get('relationship') or '').strip()}
            )

    # The root Dataset holds every top-level node — one with no incoming
    # CONTAINS. A multi-parent node is not top level and appears only under its
    # parents, which is the whole point of using hasPart.
    root: Dict[str, Any] = {'@id': './', '@type': 'Dataset', 'name': root_name}
    for key, value in (root_extra or {}).items():
        if value is not None:
            root[key] = value
    root['hasPart'] = [
        {'@id': id_by_node[nid]} for nid in by_id if nid not in has_incoming_contains
    ]

    graph: List[Dict[str, Any]] = [
        {
            '@type': 'CreativeWork',
            '@id': METADATA_FILENAME,
            'conformsTo': {'@id': CONFORMS_TO},
            'about': {'@id': './'},
        },
        root,
    ]
    graph.extend(entities.values())

    return {'@context': CRATE_CONTEXT, '@graph': graph}


def crate_json(
    snapshot: Dict[str, Any],
    root_name: str = 'canvas',
    *,
    root_extra: Optional[Dict[str, Any]] = None,
) -> str:
    """:func:`crate_document` as the text of ``ro-crate-metadata.json``."""
    doc = crate_document(snapshot, root_name, root_extra=root_extra)
    return json.dumps(doc, indent=2, ensure_ascii=False)


def crate_metadata_path(output_dir: str) -> Path:
    """Where a crate written to ``output_dir`` puts its metadata document."""
    return Path(output_dir) / METADATA_FILENAME


def _write_crate(text: str, output_dir: Optional[str]) -> Optional[Path]:
    """Write ``ro-crate-metadata.json`` into ``output_dir``, if one was given.

    Only the metadata document is written. A referenced crate has no payload
    directory to populate — see the module docstring.
    """
    if not output_dir:
        return None
    target = crate_metadata_path(output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return target


# --------------------------------------------------------------------------
# Export: a saved map
# --------------------------------------------------------------------------

def build_from_map(
    map_id: Optional[str] = None,
    driver: Any = None,
    output_dir: Optional[str] = None,
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    layer_name: Optional[str] = None,
    service: Any = None,
) -> str:
    """Build a crate from a canvas layer.

    Two ways in, because the two callers hold different things. The Maps page
    posts the live canvas, which has no ``map_id`` yet — it passes ``snapshot``.
    Anything working from a named layer passes ``map_id`` and the snapshot is
    read from the ``saved_maps`` row.

    Args:
        map_id: A saved map's id. Its stored ``snapshot_json`` is exported and,
            unless ``layer_name`` overrides it, its name titles the crate.
        driver: Accepted for symmetry with the other two builders and unused: a
            saved map carries its own snapshot, so this path needs no database.
            Passing one does nothing.
        output_dir: When set, ``ro-crate-metadata.json`` is written there too.
        snapshot: A snapshot to export directly, instead of loading one.
            Takes precedence over ``map_id``.
        layer_name: ``name`` of the root Dataset. Defaults to the saved map's
            name, or ``'canvas'``.
        service: A :class:`~scidk.services.saved_maps_service.SavedMapsService`.
            Injected by callers that know which settings DB they are on (and by
            tests); defaults to the process-wide one.

    Returns:
        The text of ``ro-crate-metadata.json``.

    Raises:
        ValueError: Neither ``snapshot`` nor ``map_id`` given, or ``map_id`` does
            not exist.
    """
    if snapshot is None:
        if not map_id:
            raise ValueError('build_from_map needs either a snapshot or a map_id')
        if service is None:
            from .services.saved_maps_service import get_saved_maps_service
            service = get_saved_maps_service()
        saved = service.get_map(str(map_id))
        if saved is None:
            raise ValueError(f'no saved map with id {map_id!r}')
        snapshot = getattr(saved, 'snapshot_json', None) or {'nodes': [], 'edges': []}
        if layer_name is None:
            layer_name = getattr(saved, 'name', None)

    text = crate_json(snapshot, layer_name or 'canvas')
    _write_crate(text, output_dir)
    return text


# --------------------------------------------------------------------------
# Export: a Files page selection
# --------------------------------------------------------------------------

def _content_url(path: Any) -> Optional[str]:
    """A resolvable URL for a stored path, or None.

    Three shapes reach us, because SciDK indexes three kinds of location: an
    already-absolute URL, an rclone remote (``remote:some/dir``), and a local or
    mounted absolute path. Same conversion as ``/api/ro-crates/referenced``
    performs, minus its ``Path.resolve()`` — resolving here would follow symlinks
    and rewrite a path that the graph deliberately recorded as it was seen.
    """
    if not path or not isinstance(path, str):
        return None
    if '://' in path:
        return path
    # A colon that is not part of a scheme means an rclone remote. Guard against
    # a Windows drive letter ("C:\...") being read as a remote named "C".
    colon = path.find(':')
    if colon > 1:
        remote, rest = path[:colon], path[colon + 1:].lstrip('/')
        return f'rclone://{remote}/{rest}' if rest else f'rclone://{remote}/'
    return f'file://{path}'


def _iso_from_epoch(value: Any) -> Optional[str]:
    """An epoch timestamp as an ISO 8601 string, or None if it is not one."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def _display_name(props: Dict[str, Any], fallback: str) -> str:
    """A human-readable name for a graph node.

    Same property preference the canvas node picker uses, so a node is called the
    same thing on the canvas and in a crate. ``:Folder`` nodes carry only a
    path, hence the basename at the end.
    """
    for key in ('name', 'title', 'display_name', 'filename'):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value
    path = props.get('path')
    if isinstance(path, str) and path.strip():
        return path.rstrip('/').rsplit('/', 1)[-1] or path
    return fallback


def _file_facets(props: Dict[str, Any], include_files: bool) -> Dict[str, Any]:
    """Crate properties describing the bytes behind a ``File`` entity.

    ``include_files=False`` drops ``contentUrl`` and keeps the rest. That is the
    real difference the Files page toggle makes: the pointer at the bytes is the
    part that discloses internal paths and host layout, while size, format,
    checksum and modification date are just description. A metadata-only crate
    still says exactly what the files *are* — it just does not say where.
    """
    facets: Dict[str, Any] = {}
    if include_files:
        facets['contentUrl'] = _content_url(props.get('path'))
    size = props.get('size_bytes', props.get('size'))
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        facets['contentSize'] = int(size)
    if props.get('mime_type'):
        facets['encodingFormat'] = props.get('mime_type')
    modified = _iso_from_epoch(props.get('modified'))
    if modified:
        facets['dateModified'] = modified
    # SciDK checksums are sha256 (core/filesystem.py), which RO-Crate spells out
    # as its own property rather than a generic "checksum".
    if props.get('checksum'):
        facets['sha256'] = props.get('checksum')
    return {k: v for k, v in facets.items() if v is not None}


#: Selected nodes, by elementId. Split from the path lookup below so each query
#: can use an index; ``elementId(n) IN`` never matches a path and vice versa, so
#: both can be handed the same untyped identifier list without any sniffing.
_SELECT_BY_ELEMENT_ID = (
    'MATCH (n) WHERE elementId(n) IN $ids '
    'RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS properties'
)

_SELECT_BY_PATH = (
    'MATCH (n) WHERE ({label_predicate}) AND n.path IN $ids '
    'RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS properties'
)

#: Relationships *among* the selected nodes. Edges to anything outside the
#: selection are left out: the crate describes what was selected, and a
#: reference to an entity that is not in the document is invalid RO-Crate.
_SELECT_EDGES = (
    'MATCH (a)-[r]->(b) '
    'WHERE elementId(a) IN $ids AND elementId(b) IN $ids '
    'RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS relationship'
)


def _snapshot_from_neo4j(
    node_ids: Sequence[str], driver: Any, include_files: bool
) -> Dict[str, Any]:
    """Resolve selected identifiers into a canvas-shaped snapshot.

    Accepts elementIds and paths in one list, because the Files page identifies
    a row by its path while the graph pages identify a node by its elementId,
    and asking the caller to sort them out would push a Neo4j detail into the UI.
    """
    ids = [str(x) for x in (node_ids or []) if str(x).strip()]
    if not ids:
        return {'nodes': [], 'edges': []}

    label_predicate = ' OR '.join(f'n:{label}' for label in PATH_LABELS)
    rows: List[Dict[str, Any]] = []
    rows.extend(driver.execute_read(_SELECT_BY_ELEMENT_ID, {'ids': ids}) or [])
    rows.extend(
        driver.execute_read(_SELECT_BY_PATH.format(label_predicate=label_predicate), {'ids': ids})
        or []
    )

    nodes: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        element_id = str(row.get('element_id') or '')
        if not element_id or element_id in nodes:
            continue
        props = dict(row.get('properties') or {})
        labels = list(row.get('labels') or [])
        # A multi-labelled node is attributed to its first label, matching how
        # the rest of SciDK picks a node's display label.
        label = str(labels[0]) if labels else 'Node'
        node: Dict[str, Any] = {
            'id': element_id,
            'element_id': element_id,
            'label': label,
            'name': _display_name(props, element_id),
            'provisional': False,
            'properties': props,
        }
        if label in FILE_LABELS:
            node[CRATE_FACET_KEY] = _file_facets(props, include_files)
        nodes[element_id] = node

    edges: List[Dict[str, Any]] = []
    if nodes:
        for row in driver.execute_read(_SELECT_EDGES, {'ids': list(nodes)}) or []:
            edges.append({
                'source': str(row.get('source')),
                'target': str(row.get('target')),
                'relationship': str(row.get('relationship') or ''),
                'provisional': False,
            })

    return {'nodes': list(nodes.values()), 'edges': edges}


def build_from_selection(
    node_ids: Sequence[str],
    driver: Any,
    output_dir: Optional[str] = None,
    *,
    name: str = 'SciDK selection',
    license: Optional[str] = None,
    description: Optional[str] = None,
    include_files: bool = True,
    date_published: Optional[str] = None,
) -> str:
    """Build a crate from a Files page selection.

    Args:
        node_ids: Selected identifiers — Neo4j elementIds, paths, or a mix.
            Anything that resolves to no node is simply absent from the crate;
            an empty selection is the caller's error to report (see
            ``POST /api/rocrate/build``), not a crate to build.
        driver: Anything exposing ``execute_read(query, params) -> [dict]``,
            i.e. a :class:`~scidk.services.neo4j_client.Neo4jClient`. Named
            ``driver`` per the Cycle 7 spec; a bare ``neo4j.Driver`` has no
            ``execute_read`` of this shape, so pass the client.
        output_dir: When set, ``ro-crate-metadata.json`` is written there too.
        name: ``name`` of the root Dataset.
        license: Root ``license``. A crate without one tells a repository
            nothing about reuse, so the Files page always asks.
        description: Root ``description``, when the caller has one.
        include_files: See :func:`_file_facets` — whether entities point at
            their bytes.
        date_published: Root ``datePublished``. Defaults to today (UTC).

    Returns:
        The text of ``ro-crate-metadata.json``. Empty selection yields a valid
        crate with an empty ``hasPart`` rather than an exception, so a caller
        that has already validated its input does not have to catch anything.
    """
    snapshot = _snapshot_from_neo4j(node_ids, driver, include_files)
    root_extra = {
        'description': description,
        'license': license,
        'datePublished': date_published or datetime.now(timezone.utc).date().isoformat(),
    }
    text = crate_json(snapshot, name, root_extra=root_extra)
    _write_crate(text, output_dir)
    return text


# --------------------------------------------------------------------------
# Import: someone else's crate
# --------------------------------------------------------------------------

def _crate_key(crate: Any, crate_path: str) -> str:
    """A stable prefix that makes a crate's relative ``@id``s globally unique.

    Crate ids are relative by design — ``./``, ``a.txt``, ``#alice`` — so they
    collide the moment a second crate is imported. They need a prefix, and it has
    to be the same prefix every time the same crate is imported or re-importing
    duplicates the whole graph.

    The library's own ``canonical_id()`` is not usable for this: with no declared
    identifier it mints a fresh ``arcp://uuid,<random>`` base on *every parse*,
    so two reads of one directory produce two different sets of ids.

    So: the root Dataset's ``identifier`` when it is an absolute URI — a DOI or
    similar, which is exactly the persistent identifier RO-Crate asks publishers
    to declare, and which dedupes correctly no matter where the crate was
    downloaded to. Otherwise the crate's own location, which is stable per
    machine and honest about what it is.
    """
    try:
        identifier = crate.root_dataset.get('identifier')
    except Exception:  # noqa: BLE001 - a crate with no readable root is handled by the caller
        identifier = None
    if isinstance(identifier, dict):
        identifier = identifier.get('@id')
    if isinstance(identifier, str) and '://' in identifier:
        return identifier
    return f'file://{os.path.abspath(crate_path)}'


def _import_label(entity_type: Any) -> Optional[str]:
    """The SciDK label for a crate entity's ``@type``.

    ``File`` and ``Dataset`` are the two types the spec gives structural meaning,
    and they map onto the pair a scan already writes: a crate ``Dataset`` is a
    directory, which is a ``:Folder``. Every other type (``Person``,
    ``SoftwareApplication``, a domain type from a profile) becomes a label of its
    own name — the ordinary JSON-LD-to-property-graph reading, and the only one
    that does not throw away what the crate said.

    Returns None when the type cannot be a Cypher label, since
    ``write_declared_nodes`` interpolates labels unquoted.
    """
    if isinstance(entity_type, (list, tuple)):
        # A multi-typed entity is attributed to its first type, as elsewhere.
        entity_type = entity_type[0] if entity_type else None
    name = str(entity_type or '').strip()
    if name == 'Dataset':
        return 'Folder'
    if not LABEL_RE.match(name):
        return None
    return name


def _is_reference(value: Any) -> bool:
    return isinstance(value, dict) and '@id' in value


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _import_properties(raw: Dict[str, Any], skipped: List[str], entity_id: str) -> Dict[str, Any]:
    """The scalar properties of a crate entity, as Neo4j properties.

    References (``{"@id": ...}``) are relationships, handled separately. A
    property name that is not a legal Cypher identifier is skipped and reported:
    ``write_declared_nodes`` interpolates property *names* unquoted, so a crate
    using ``schema:name`` cannot be written verbatim, and silently mangling it
    would be worse than saying so.
    """
    props: Dict[str, Any] = {}
    for key, value in raw.items():
        if key in ('@id', '@type'):
            continue
        if _is_reference(value) or (isinstance(value, list) and any(map(_is_reference, value))):
            continue
        if not PROPERTY_RE.match(str(key)):
            skipped.append(f'{entity_id}: property {key!r} is not a valid Cypher identifier')
            continue
        if _scalar(value):
            props[key] = value
        elif isinstance(value, list) and all(map(_scalar, value)):
            props[key] = list(value)
        else:
            skipped.append(f'{entity_id}: property {key!r} has a value Neo4j cannot store')
    return props


def _resolve_reference(
    target_id: str, labels_by_id: Dict[str, Tuple[str, str]]
) -> Optional[Tuple[str, str]]:
    """Find the entity a reference points at, tolerating the library's rewriting.

    ``ROCrate`` normalizes a Dataset's ``@id`` to end in ``/`` and rewrites the
    ``hasPart`` references it recognizes to match — but a reference sitting inside
    a structure it treats as opaque data (our own ``relation`` entries, or a
    profile's own term) keeps the id as written. So ``#x`` and ``#x/`` can both
    appear in one parsed crate meaning the same entity, and matching only exactly
    would drop every ``relation`` edge on a re-import of SciDK's own export.
    """
    for candidate in (target_id, target_id.rstrip('/'), target_id + '/'):
        found = labels_by_id.get(candidate)
        if found is not None:
            return found
    return None


def _import_relationships(
    raw: Dict[str, Any],
    source_key: str,
    source_label: str,
    labels_by_id: Dict[str, Tuple[str, str]],
    skipped: List[str],
    entity_id: str,
) -> List[Dict[str, Any]]:
    """Relationship declarations for one entity's references.

    ``hasPart`` and ``mentions`` invert the export mapping. ``relation`` carries
    the original SciDK type in its ``name``, so a crate SciDK produced round
    trips back to the relationship types it started with. Any other property
    holding a reference (``author``, ``about``, a profile's own term) becomes a
    relationship named after the property, upper-cased — otherwise importing an
    external crate would keep the entities and throw away the structure.
    """
    rels: List[Dict[str, Any]] = []
    for key, value in raw.items():
        if key in ('@id', '@type'):
            continue
        if _is_reference(value):
            refs = [value]
        elif isinstance(value, list):
            refs = [v for v in value if _is_reference(v)]
        else:
            continue
        if not refs:
            continue
        for ref in refs:
            target_id = str(ref.get('@id'))
            target = _resolve_reference(target_id, labels_by_id)
            if target is None:
                skipped.append(f'{entity_id}: {key} -> {target_id!r} is not an entity in this crate')
                continue
            target_label, target_key = target
            if key == 'relation':
                candidate = str(ref.get('name') or '').strip().upper()
                rel_type = candidate if REL_RE.match(candidate) else _IMPORT_DEFAULT_REL
            elif key in _IMPORT_EDGE_MAP:
                rel_type = _IMPORT_EDGE_MAP[key]
            else:
                candidate = str(key).strip().upper()
                if not REL_RE.match(candidate):
                    skipped.append(f'{entity_id}: {key!r} cannot be a relationship type')
                    continue
                rel_type = candidate
            rels.append({
                'type': rel_type,
                'from_label': source_label,
                'from_match': {CRATE_KEY_PROPERTY: source_key},
                'to_label': target_label,
                'to_match': {CRATE_KEY_PROPERTY: target_key},
            })
    return rels


def ingest_crate(crate_path: str, driver: Any) -> Dict[str, Any]:
    """Read an external RO-Crate into the graph.

    Parsing is delegated to the ``rocrate`` library, which is the half of this
    module the library is genuinely better at. Note that it *normalizes* as it
    reads — a ``Dataset``'s ``@id`` gains a trailing ``/``, a missing
    ``datePublished`` is filled in — so the ids written here are the parsed ones,
    consistently on both ends of every relationship.

    Every node is stamped ``record_source: 'ro_crate_import'`` and MERGEd on
    :data:`CRATE_KEY_PROPERTY`, so re-importing the same crate updates rather
    than duplicates. See :func:`_crate_key` for what makes that key stable.

    Args:
        crate_path: A crate directory or zip — whatever ``ROCrate`` accepts.
        driver: Anything exposing
            ``write_declared_nodes(nodes, relationships) -> dict``, i.e. a
            :class:`~scidk.services.neo4j_client.Neo4jClient`.

    Returns:
        ``{'status', 'crate_key', 'crate_path', 'entities', 'written_nodes',
        'written_relationships', 'errors', 'skipped'}``. ``status`` is ``'ok'``
        when nothing was skipped and nothing failed, otherwise ``'partial'``.
        ``skipped`` explains every entity, property and reference left out —
        importing someone else's crate always leaves something out, and a silent
        drop is indistinguishable from a bug.

    Raises:
        RuntimeError: The ``rocrate`` library is not installed, or the crate
            cannot be parsed. Both are deployment/input errors a caller should
            surface rather than half-import around.
    """
    try:
        from rocrate.rocrate import ROCrate  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised by a skipped test
        raise RuntimeError(
            'Reading an RO-Crate needs the rocrate library: pip install "rocrate>=0.15.0" '
            '(it is in requirements.txt)'
        ) from exc

    try:
        crate = ROCrate(crate_path)
    except Exception as exc:  # noqa: BLE001 - any parse failure is one answer to the caller
        raise RuntimeError(f'could not read RO-Crate at {crate_path!r}: {exc}') from exc

    crate_key = _crate_key(crate, crate_path)
    skipped: List[str] = []

    # First pass: decide each entity's label and key, so the second pass can
    # resolve both ends of a reference without ordering assumptions.
    raw_by_id: Dict[str, Dict[str, Any]] = {}
    labels_by_id: Dict[str, Tuple[str, str]] = {}
    for entity in crate.get_entities():
        entity_id = str(entity.id)
        if entity_id in _NON_ENTITY_IDS:
            continue
        label = _import_label(entity.type)
        if label is None:
            skipped.append(f'{entity_id}: @type {entity.type!r} cannot be a Neo4j label')
            continue
        raw_by_id[entity_id] = dict(entity.properties())
        labels_by_id[entity_id] = (label, f'{crate_key}#{entity_id}')

    node_decls: List[Dict[str, Any]] = []
    rel_decls: List[Dict[str, Any]] = []
    for entity_id, raw in raw_by_id.items():
        label, key = labels_by_id[entity_id]
        props = _import_properties(raw, skipped, entity_id)
        props.update({
            CRATE_KEY_PROPERTY: key,
            'crate_entity_id': entity_id,
            'crate_source': crate_key,
            'record_source': IMPORT_RECORD_SOURCE,
        })
        node_decls.append({
            'label': label,
            'key_property': CRATE_KEY_PROPERTY,
            'properties': props,
        })
        rel_decls.extend(
            _import_relationships(raw, key, label, labels_by_id, skipped, entity_id)
        )

    written = driver.write_declared_nodes(node_decls, rel_decls)
    errors = list(written.get('errors') or [])
    return {
        'status': 'ok' if not errors and not skipped else 'partial',
        'crate_key': crate_key,
        'crate_path': str(crate_path),
        'entities': len(node_decls),
        'written_nodes': written.get('written_nodes', 0),
        'written_relationships': written.get('written_relationships', 0),
        'errors': errors,
        'skipped': skipped,
    }
