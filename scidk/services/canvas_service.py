"""Service for Maps Canvas (Push 2) persistence.

Owns two SQLite tables in the settings DB (scidk_settings.db), colocated with
saved_maps — NOT the path-index DB that scidk/core/migrations.py targets:

- canvas_query_library: reusable Cypher snippets for building canvas layers.
- canvas_session: per-user in-progress canvas state, so a canvas survives a
  browser refresh without touching Neo4j or a named saved map.

Named saved layers (with display_mode/layers/snapshot_json) live in saved_maps
and are handled by SavedMapsService, not here.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
                    user_id TEXT PRIMARY KEY,
                    canvas_json TEXT,
                    updated_at REAL
                )
                """
            )
            conn.commit()
            logger.debug("Ensured canvas_query_library and canvas_session tables exist")
        finally:
            conn.close()

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

    # --- canvas_session (per-user in-progress canvas) ---
    def save_session(self, user_id: str, canvas: Dict[str, Any]) -> float:
        """Upsert the user's current canvas JSON. Returns the save timestamp."""
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO canvas_session (user_id, canvas_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    canvas_json = excluded.canvas_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(canvas or {}), now),
            )
            conn.commit()
        finally:
            conn.close()
        return now

    def load_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return {canvas, updated_at} for the user, or None if no session saved."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT canvas_json, updated_at FROM canvas_session WHERE user_id = ?",
                (user_id,),
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

    def clear_session(self, user_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM canvas_session WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


import re

_REL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_LABEL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def build_commit_plan(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a canvas snapshot into a Neo4j write plan.

    Only *provisional* elements are committed (per the canvas storage model).

    Returns:
        {
          'node_decls': [...],   # for Neo4jClient.write_declared_nodes (name key)
          'name_rels': [...],    # rel decls (>=1 provisional endpoint) for write_declared_nodes
          'id_edges': [...],     # {source_element_id,target_element_id,rel} real->real (elementId MERGE)
          'skipped': [...],      # human-readable reasons for anything dropped
        }
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}

    node_decls: List[Dict[str, Any]] = []
    name_rels: List[Dict[str, Any]] = []
    id_edges: List[Dict[str, Any]] = []
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

    # Provisional edges only.
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

        src_real = not src.get('provisional')
        tgt_real = not tgt.get('provisional')
        src_eid = src.get('element_id')
        tgt_eid = tgt.get('element_id')

        # Real -> real with both elementIds: match by elementId (exact node identity).
        if src_real and tgt_real and src_eid and tgt_eid:
            id_edges.append({'source_element_id': src_eid, 'target_element_id': tgt_eid, 'rel': rel})
            continue

        # Otherwise fall back to name-match via write_declared_nodes.
        src_label, src_name = src.get('label'), src.get('name')
        tgt_label, tgt_name = tgt.get('label'), tgt.get('name')
        if not (src_label and src_name and tgt_label and tgt_name):
            skipped.append(f"edge {rel}: endpoint missing label/name for name-match")
            continue
        name_rels.append({
            'type': rel,
            'from_label': src_label, 'from_match': {'name': src_name},
            'to_label': tgt_label, 'to_match': {'name': tgt_name},
        })

    return {'node_decls': node_decls, 'name_rels': name_rels, 'id_edges': id_edges, 'skipped': skipped}


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

    Node positions/CONTAINS edges imply a folder tree. Directories are created
    with mkdir(parents=True, exist_ok=True); Dataset nodes carrying a `path`
    property are moved with shutil.move (guarded by src.exists()). Nothing runs
    automatically — the admin reviews and runs it manually.
    """
    nodes = (snapshot or {}).get('nodes') or []
    edges = (snapshot or {}).get('edges') or []
    by_id = {str(n.get('id')): n for n in nodes}

    # parent map from CONTAINS edges (source CONTAINS target => parent=source)
    parent = {}
    for e in edges:
        if (e.get('relationship') or '').upper() == 'CONTAINS':
            parent[str(e.get('target'))] = str(e.get('source'))

    def rel_parts(nid: str, _seen=None):
        _seen = _seen or set()
        if nid in _seen or nid not in by_id:
            return []
        _seen.add(nid)
        node = by_id[nid]
        seg = str(node.get('name') or nid)
        p = parent.get(nid)
        return (rel_parts(p, _seen) + [seg]) if p else [seg]

    def pyq(s):
        return repr(str(s))

    L: List[str] = []
    L.append('# Generated by SciDK Canvas Export')
    L.append(f'# Layer: {layer_name!r}')
    L.append('# Review before running — this will reorganize files on disk.')
    L.append('')
    L.append('from pathlib import Path')
    L.append('import shutil')
    L.append('')
    L.append('BASE = Path("/your/data/root")  # <-- update this path')
    L.append('')
    L.append('# Create directory structure')
    dir_nodes = [nid for nid in by_id if any(parent.get(c) == nid for c in by_id) or nid in parent]
    seen_dirs = set()
    for nid in dir_nodes:
        parts = rel_parts(nid)
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
        parts = rel_parts(nid)
        joined = ' / '.join(pyq(p) for p in parts)
        L.append(f'# Dataset: {node.get("name")}')
        L.append(f'src = Path({pyq(src_path)})')
        L.append(f'dst = BASE / {joined}')
        L.append('if src.exists():')
        L.append('    shutil.move(str(src), str(dst))')
        L.append('    print(f"Moved: {src} -> {dst}")')
        L.append('else:')
        L.append('    print(f"WARNING: Source not found: {src}")')
        L.append('')
    return '\n'.join(L)


_canvas_service: Optional[CanvasService] = None


def get_canvas_service(db_path: Optional[str] = None) -> CanvasService:
    global _canvas_service
    if _canvas_service is None or db_path is not None:
        _canvas_service = CanvasService(db_path)
    return _canvas_service
