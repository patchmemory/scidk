"""Service for Maps Canvas (Push 2) persistence.

Owns two SQLite tables in the settings DB (scidk_settings.db), colocated with
saved_maps — NOT the path-index DB that scidk/core/migrations.py targets:

- canvas_query_library: reusable Cypher snippets for building canvas layers.
- canvas_session: per-user, per-context in-progress canvas state, so a canvas
  survives a browser refresh without touching Neo4j or a named saved map.

Named saved layers (with display_mode/layers/snapshot_json) live in saved_maps
and are handled by SavedMapsService, not here.

Canvas contexts
---------------
A session is keyed by ``(user_id, context_id)``. ``context_id`` is a namespaced
string naming *which* canvas: ``''`` is the user's main Maps canvas, and
``pipeline_source:<uuid>`` is the schema canvas scoped to one Pipeline source
(Cycle 3B Task C). Namespaced rather than a bare UUID so a future scope cannot
collide with, or be mistaken for, an existing one.

Deleting whatever a context belongs to must delete its sessions — see
:meth:`CanvasService.clear_context`. Without that, deleting a Pipeline source
would leave its schema canvas behind forever, and a recreated source reusing the
id would inherit it.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: ``context_id`` of the user's main Maps canvas — the scope that existed before
#: contexts did. Empty rather than a name like 'default' so the column's default
#: preserves the pre-context behaviour exactly.
DEFAULT_CONTEXT_ID = ""

#: ``context_id`` prefix for a canvas scoped to one Pipeline source.
PIPELINE_SOURCE_CONTEXT_PREFIX = "pipeline_source:"


def pipeline_source_context(source_id: str) -> str:
    """``context_id`` for a Pipeline source's schema canvas."""
    return f"{PIPELINE_SOURCE_CONTEXT_PREFIX}{source_id}"


class CanvasService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "scidk_settings.db"
        self._ensure_tables_exist()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables_exist(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canvas_query_library (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    created_by TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canvas_session (
                    user_id TEXT NOT NULL,
                    context_id TEXT NOT NULL DEFAULT '',
                    canvas_json TEXT,
                    updated_at REAL,
                    PRIMARY KEY (user_id, context_id)
                )
                """
            )
            self._upgrade_canvas_session_key(conn)
            conn.commit()
            logger.debug("Ensured canvas_query_library and canvas_session tables exist")
        finally:
            conn.close()

    @staticmethod
    def _upgrade_canvas_session_key(conn: sqlite3.Connection) -> None:
        """Move a pre-context canvas_session to the composite primary key.

        The table shipped as ``PRIMARY KEY (user_id)``. SQLite cannot alter a
        primary key in place, so the only route is rebuild-and-copy. Guarded on
        the absence of the ``context_id`` column, which makes this a no-op on
        every construction after the first — and construction happens on every
        request that touches the canvas.

        Existing rows become ``context_id = ''``, the main Maps canvas, so a user
        with a canvas open across this upgrade still finds it there.

        The rename-then-insert order matters: if the process dies between the two
        statements the transaction is uncommitted and SQLite rolls back to the
        original table. There is no window in which the data exists in neither.
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(canvas_session)")}
        if "context_id" in columns:
            return

        logger.info("Upgrading canvas_session to a (user_id, context_id) primary key")
        conn.execute("ALTER TABLE canvas_session RENAME TO canvas_session_pre_context")
        conn.execute(
            """
            CREATE TABLE canvas_session (
                user_id TEXT NOT NULL,
                context_id TEXT NOT NULL DEFAULT '',
                canvas_json TEXT,
                updated_at REAL,
                PRIMARY KEY (user_id, context_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO canvas_session (user_id, context_id, canvas_json, updated_at)
            SELECT user_id, '', canvas_json, updated_at FROM canvas_session_pre_context
            """
        )
        conn.execute("DROP TABLE canvas_session_pre_context")

    # --- canvas_query_library ---
    def list_queries(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM canvas_query_library ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_query(self, name: str, cypher: str, created_by: Optional[str] = None) -> Dict[str, Any]:
        qid = str(uuid.uuid4())
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO canvas_query_library (id, name, cypher, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (qid, name, cypher, created_by, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": qid,
            "name": name,
            "cypher": cypher,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

    def get_query(self, query_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM canvas_query_library WHERE id = ?", (query_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_query(self, query_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM canvas_query_library WHERE id = ?", (query_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # --- canvas_session (per-user, per-context in-progress canvas) ---
    def save_session(
        self, user_id: str, canvas: Dict[str, Any], context_id: str = DEFAULT_CONTEXT_ID
    ) -> float:
        """Upsert one canvas. Returns the save timestamp.

        Args:
            user_id: From ``scidk.web.user_context.current_user_key``.
            canvas: The canvas snapshot to persist.
            context_id: Which canvas. Defaults to the main Maps canvas, so
                existing callers keep their behaviour.
        """
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO canvas_session (user_id, context_id, canvas_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, context_id) DO UPDATE SET
                    canvas_json = excluded.canvas_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, context_id or DEFAULT_CONTEXT_ID, json.dumps(canvas or {}), now),
            )
            conn.commit()
        finally:
            conn.close()
        return now

    def load_session(
        self, user_id: str, context_id: str = DEFAULT_CONTEXT_ID
    ) -> Optional[Dict[str, Any]]:
        """Return {canvas, updated_at}, or None if this context has no session."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT canvas_json, updated_at FROM canvas_session "
                "WHERE user_id = ? AND context_id = ?",
                (user_id, context_id or DEFAULT_CONTEXT_ID),
            ).fetchone()
            if not row:
                return None
            raw = row["canvas_json"]
            return {
                "canvas": json.loads(raw) if raw else {},
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    def clear_session(self, user_id: str, context_id: str = DEFAULT_CONTEXT_ID) -> bool:
        """Delete one user's session in one context."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM canvas_session WHERE user_id = ? AND context_id = ?",
                (user_id, context_id or DEFAULT_CONTEXT_ID),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def clear_context(self, context_id: str) -> int:
        """Delete every user's session in one context. Returns rows removed.

        The cleanup path for deleting whatever the context belongs to. Deleting a
        Pipeline source calls this with ``pipeline_source:<id>``; the source's
        schema canvas is scoped to it, so leaving the rows behind would orphan
        them permanently and hand a stale canvas to any later source that reused
        the id.

        Refuses to be called with an empty ``context_id``: that is the main Maps
        canvas, and wiping every user's working canvas is not something a cleanup
        path should be able to do by passing a blank string.
        """
        if not (context_id or "").strip():
            raise ValueError(
                "clear_context requires a context_id; refusing to delete every "
                "user's main canvas session"
            )
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM canvas_session WHERE context_id = ?", (context_id,)
            )
            conn.commit()
            if cur.rowcount:
                logger.info(
                    "Cleared %d canvas session(s) for context %r", cur.rowcount, context_id
                )
            return cur.rowcount
        finally:
            conn.close()

    def list_contexts(self, user_id: str) -> List[Dict[str, Any]]:
        """Contexts this user has a saved canvas in, most recent first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT context_id, updated_at FROM canvas_session "
                "WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


from ..pipeline.identifiers import LABEL_RE as _LABEL_RE  # noqa: E402
from ..pipeline.identifiers import REL_RE as _REL_RE  # noqa: E402

# These guards were defined here first and the Pipeline needed the same ones, so
# scidk/pipeline/identifiers.py is now the single definition and this module
# imports it. Same pattern, same behaviour — a label or relationship type safe to
# interpolate into Cypher unquoted, which is what both writers do.


def build_commit_plan(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a canvas snapshot into a Neo4j write plan.

    Only *provisional* elements are committed (per the canvas storage model).

    One MERGE path for everything. Nodes MERGE on their business property
    (name); edges MATCH endpoints by (label, name) then MERGE the relationship.
    We trust MERGE: provisional nodes are written first, so by the time edges
    run both endpoints exist (either just written or pre-existing), and re-running
    is idempotent. No elementId/name split — that was overcautious.

    Returns:
        {
          'node_decls': [...],   # for Neo4jClient.write_declared_nodes (name key)
          'rels': [...],         # rel decls for write_declared_nodes (name-matched)
          'skipped': [...],      # human-readable reasons for anything dropped
        }
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}

    node_decls: List[Dict[str, Any]] = []
    rels: List[Dict[str, Any]] = []
    skipped: List[str] = []

    # Provisional nodes -> MERGE on name.
    for n in nodes:
        if not n.get('provisional'):
            continue
        label = n.get('label')
        name = n.get('name') or (n.get('properties') or {}).get('name')
        if not label or not _LABEL_RE.match(str(label)):
            skipped.append(f"node {name!r}: invalid/blank label")
            continue
        if not name:
            skipped.append(f"node with label {label}: missing name")
            continue
        props = dict(n.get('properties') or {})
        props['name'] = name
        node_decls.append({'label': label, 'key_property': 'name', 'properties': props})

    # Provisional edges -> MERGE, endpoints matched by (label, name). One path:
    # MERGE either finds the pre-existing node or the one we just wrote above.
    for e in edges:
        if not e.get('provisional'):
            continue
        rel = (e.get('relationship') or '').strip()
        if not rel or not _REL_RE.match(rel):
            skipped.append(f"edge {e.get('source')}->{e.get('target')}: invalid/blank relationship")
            continue
        src = by_id.get(str(e.get('source')))
        tgt = by_id.get(str(e.get('target')))
        if not src or not tgt:
            skipped.append(f"edge {e.get('source')}->{e.get('target')}: endpoint not on canvas")
            continue

        src_label, src_name = src.get('label'), src.get('name')
        tgt_label, tgt_name = tgt.get('label'), tgt.get('name')
        if not (src_label and src_name and tgt_label and tgt_name):
            skipped.append(f"edge {rel}: endpoint missing label/name for MERGE")
            continue
        rels.append({
            'type': rel,
            'from_label': src_label, 'from_match': {'name': src_name},
            'to_label': tgt_label, 'to_match': {'name': tgt_name},
        })

    return {'node_decls': node_decls, 'rels': rels, 'skipped': skipped}


def _cypher_literal(v: Any) -> str:
    """Render a Python value as a Cypher literal (safe-ish for a reviewable script)."""
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_cypher_literal(x) for x in v) + ']'
    s = str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return f'"{s}"'


def generate_cypher(snapshot: Dict[str, Any], layer_name: str = 'canvas') -> str:
    """Generate a reviewable .cypher script for the provisional elements.

    Nodes MERGE on name; edges MATCH endpoints by (label, name) then MERGE the
    relationship — portable across databases (no internal ids baked in).
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}
    prov_nodes = [n for n in nodes if n.get('provisional')]
    prov_edges = [e for e in edges if e.get('provisional')]

    lines: List[str] = []
    lines.append(f'// SciDK Canvas export — layer: {layer_name}')
    lines.append('// Review before running (Neo4j Browser or cypher-shell).')
    lines.append('// MERGE makes this idempotent.')
    lines.append('')
    lines.append('// --- Before snapshot: current state of the named nodes ---')
    names = [n.get('name') for n in prov_nodes if n.get('name')]
    if names:
        arr = '[' + ', '.join(_cypher_literal(n) for n in names) + ']'
        lines.append(f'MATCH (n) WHERE n.name IN {arr} RETURN n.name AS name, labels(n) AS labels;')
    else:
        lines.append('// (no named provisional nodes)')
    lines.append('')
    lines.append('// --- Provisional nodes ---')
    for n in prov_nodes:
        label = n.get('label') or 'Node'
        name = n.get('name')
        if not name or not _LABEL_RE.match(str(label)):
            continue
        props = {k: v for k, v in (n.get('properties') or {}).items() if k != 'name'}
        merge = f'MERGE (n:{label} {{name: {_cypher_literal(name)}}})'
        if props:
            sets = ', '.join(f'n.{k} = {_cypher_literal(v)}' for k, v in props.items() if _LABEL_RE.match(str(k)))
            if sets:
                merge += f'\n  SET {sets}'
        lines.append(merge + ';')
    lines.append('')
    lines.append('// --- Provisional relationships ---')
    for e in prov_edges:
        rel = (e.get('relationship') or '').strip()
        src, tgt = by_id.get(str(e.get('source'))), by_id.get(str(e.get('target')))
        if not rel or not _REL_RE.match(rel) or not src or not tgt:
            continue
        if not (src.get('name') and tgt.get('name') and src.get('label') and tgt.get('label')):
            continue
        lines.append(
            f'MATCH (a:{src["label"]} {{name: {_cypher_literal(src["name"])}}}), '
            f'(b:{tgt["label"]} {{name: {_cypher_literal(tgt["name"])}}})\n'
            f'  MERGE (a)-[:{rel}]->(b);'
        )
    lines.append('')
    return '\n'.join(lines)


def generate_python_fs(snapshot: Dict[str, Any], layer_name: str = 'canvas') -> str:
    """Generate a conservative pathlib/shutil script from the CONTAINS hierarchy.

    CONTAINS edges imply a folder structure. Directories are created with
    mkdir(parents=True, exist_ok=True); Dataset nodes carrying a `path` property
    are placed at their destination(s). Nothing runs automatically — the admin
    reviews and runs it manually.

    Filesystems are not trees: symlinks, hard links and bind mounts mean a real
    filesystem already has multi-parent structure, and SciDK stores that
    structure faithfully. So does this export — a node with two parents is
    emitted at both paths (one per parent). No "picking one" / last-edge-wins.
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}

    # Parent map from CONTAINS edges (source CONTAINS target => parent=source).
    # A node may have MANY parents — collect every one, don't overwrite.
    parents: Dict[str, List[str]] = {}
    for e in edges:
        if (e.get('relationship') or '').upper() == 'CONTAINS':
            parents.setdefault(str(e.get('target')), []).append(str(e.get('source')))

    def rel_paths(nid: str, _stack=()):  # -> List[List[str]]
        """All root-relative path-part lists for a node (one per parent chain)."""
        node = by_id.get(nid)
        if node is None:
            return []
        seg = str(node.get('name') or nid)
        ps = [p for p in parents.get(nid, []) if p in by_id and p not in _stack and p != nid]
        if not ps:
            return [[seg]]
        out: List[List[str]] = []
        for p in ps:
            for prefix in rel_paths(p, _stack + (nid,)):
                out.append(prefix + [seg])
        return out or [[seg]]

    def pyq(s):
        return repr(str(s))

    L: List[str] = []
    L.append('# Generated by SciDK Canvas Export')
    L.append(f'# Layer: {layer_name!r}')
    L.append('# Review before running — this will reorganize files on disk.')
    L.append('# Multi-parent nodes appear at every path they hold in the graph.')
    L.append('')
    L.append('from pathlib import Path')
    L.append('import shutil')
    L.append('')
    L.append('BASE = Path("/your/data/root")  # <-- update this path')
    L.append('')
    L.append('# Create directory structure')
    # A node participates in the tree if it has children or has a parent.
    has_child = {str(e.get('source')) for e in edges
                 if (e.get('relationship') or '').upper() == 'CONTAINS'}
    dir_nodes = [nid for nid in by_id if nid in has_child or nid in parents]
    seen_dirs = set()
    for nid in dir_nodes:
        for parts in rel_paths(nid):
            key = '/'.join(parts)
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            joined = ' / '.join(pyq(p) for p in parts)
            L.append(f'(BASE / {joined}).mkdir(parents=True, exist_ok=True)')
    L.append('')
    L.append('# Move datasets to their new locations')
    for nid, node in by_id.items():
        if str(node.get('label')) != 'Dataset':
            continue
        src_path = (node.get('properties') or {}).get('path')
        if not src_path:
            continue
        # One destination per parent; a multi-parent node lands at each path.
        dsts = rel_paths(nid)
        L.append(f'# Dataset: {node.get("name")}')
        L.append(f'src = Path({pyq(src_path)})')
        for i, parts in enumerate(dsts):
            joined = ' / '.join(pyq(p) for p in parts)
            L.append(f'dst = BASE / {joined}')
            if i == 0:
                # First path takes the file; later paths mirror it (multi-parent).
                L.append('if src.exists():')
                L.append('    shutil.move(str(src), str(dst))')
                L.append('    print(f"Moved: {src} -> {dst}")')
                L.append('else:')
                L.append('    print(f"WARNING: Source not found: {src}")')
            else:
                L.append('if dst.parent.exists() and not dst.exists():')
                L.append('    shutil.copy2(str(BASE / ' + ' / '.join(pyq(p) for p in dsts[0]) + '), str(dst))')
                L.append('    print(f"Mirrored (multi-parent): {dst}")')
        L.append('')
    return '\n'.join(L)


def generate_rocrate_export(snapshot: Dict[str, Any], layer_name: str = 'canvas') -> str:
    """Serialize a canvas snapshot as a valid RO-Crate 1.1 metadata document.

    RO-Crate is DAG-native: ``hasPart`` lets a child belong to any number of
    parents, so multi-parent graphs need no special casing — each parent simply
    lists the child in its ``hasPart`` array. This is also compatible with
    NextSEEK's DAG-based provenance model. Whatever topology the graph has,
    RO-Crate represents it.

    Returns the JSON text of ``ro-crate-metadata.json``.
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}

    def entity_id(node_id: str, node: Dict[str, Any]) -> str:
        # Real nodes keep their Neo4j elementId; provisional nodes get a stable
        # generated id (uuid5 over the canvas id so re-exports stay consistent).
        if not node.get('provisional') and node.get('element_id'):
            return str(node.get('element_id'))
        return f"#{uuid.uuid5(uuid.NAMESPACE_URL, str(node_id))}"

    def entity_type(node: Dict[str, Any]) -> str:
        # Dataset/File labels map to a File entity; everything else to a Dataset.
        return 'File' if str(node.get('label')) in ('Dataset', 'File') else 'Dataset'

    # Build one entity per canvas node, keyed by @id.
    id_by_node: Dict[str, str] = {}
    entities: Dict[str, Dict[str, Any]] = {}
    for node_id, node in by_id.items():
        eid = entity_id(node_id, node)
        id_by_node[node_id] = eid
        props = node.get('properties') or {}
        entity: Dict[str, Any] = {'@id': eid, '@type': entity_type(node)}
        name = node.get('name') or props.get('name')
        if name:
            entity['name'] = str(name)
        if props.get('description'):
            entity['description'] = props.get('description')
        if props.get('dateCreated'):
            entity['dateCreated'] = props.get('dateCreated')
        entities[eid] = entity

    # Edge mapping. CONTAINS -> hasPart (multi-parent handled natively);
    # ATTACHED_TO -> mentions; anything else -> relation named after the type.
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

    # Root Dataset (the layer) hasPart every top-level node — one with no
    # incoming CONTAINS edge.
    root = {
        '@id': './',
        '@type': 'Dataset',
        'name': layer_name,
        'hasPart': [
            {'@id': id_by_node[nid]} for nid in by_id if nid not in has_incoming_contains
        ],
    }

    graph: List[Dict[str, Any]] = [
        {
            '@type': 'CreativeWork',
            '@id': 'ro-crate-metadata.json',
            'conformsTo': {'@id': 'https://w3id.org/ro/crate/1.1'},
            'about': {'@id': './'},
        },
        root,
    ]
    graph.extend(entities.values())

    doc = {'@context': 'https://w3id.org/ro/crate/1.1/context', '@graph': graph}
    return json.dumps(doc, indent=2, ensure_ascii=False)


_canvas_service: Optional[CanvasService] = None


def get_canvas_service(db_path: Optional[str] = None) -> CanvasService:
    global _canvas_service
    if _canvas_service is None or db_path is not None:
        _canvas_service = CanvasService(db_path)
    return _canvas_service
