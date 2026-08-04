"""
Blueprint for the Maps Canvas (interactive whiteboarding) feature.

Push 1 scope:
- GET /api/canvas/nodes/search: search instance-level nodes in Neo4j so users can
  pull real Project/Dataset/Person/Lab nodes onto the canvas.

Canvas state is provisional and lives client-side (Cytoscape) until later pushes
add session persistence, named layers, and commit. Nothing here writes to Neo4j.
"""
from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, jsonify, request, current_app, g

from ..decorators import require_role

bp = Blueprint('api_canvas', __name__, url_prefix='/api/canvas')

# Canvas tuning constants (shared with the frontend via GET /api/canvas/config).
CANVAS_FANOUT_THRESHOLD = 20   # subtree size above which we collapse to an ellipsis node
CANVAS_LAZY_LOAD_LIMIT = 50    # max children pulled when expanding an ellipsis
CANVAS_MAX_DEPTH = 3           # max hops when expanding


@bp.get('/config')
def canvas_config():
    return jsonify({
        'status': 'ok',
        'CANVAS_FANOUT_THRESHOLD': CANVAS_FANOUT_THRESHOLD,
        'CANVAS_LAZY_LOAD_LIMIT': CANVAS_LAZY_LOAD_LIMIT,
        'CANVAS_MAX_DEPTH': CANVAS_MAX_DEPTH,
    }), 200


def _settings_db():
    return current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')


def _current_user_id() -> str:
    """Identify the user for per-user canvas session storage.

    Uses the id/username set on ``g`` by the auth middleware; falls back to
    'anonymous' when auth is disabled (dev/test) so the feature still works.
    """
    return (
        getattr(g, 'scidk_user_id', None)
        or getattr(g, 'scidk_user', None)
        or 'anonymous'
    )


def _json_safe(value: Any) -> Any:
    """Best-effort conversion of Neo4j property values to JSON-serializable ones.

    Neo4j properties are mostly primitives, but temporal/spatial types need
    coercion. Lists are handled recursively.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # Neo4j temporal types expose isoformat(); fall back to str otherwise.
    iso = getattr(value, 'isoformat', None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass
    return str(value)


def _display_name(props: Dict[str, Any], node_id: str) -> str:
    """Pick a human-friendly label for a node from common property names."""
    for key in ('name', 'title', 'display_name', 'filename', 'label', 'path', 'id'):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return f'#{node_id}'


@bp.get('/nodes/search')
def search_nodes():
    """Search instance nodes in Neo4j for the canvas node picker.

    Query params:
        q      (str)          required search text (case-insensitive substring)
        label  (str,optional) restrict to a single node label
        limit  (int,optional) max results, default 20 (capped at 100)

    Returns 200 with:
        {"status": "ok", "results": [{id, label, name, properties}, ...]}
    """
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    q = (request.args.get('q') or '').strip()
    label = (request.args.get('label') or '').strip()
    try:
        limit = int(request.args.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    if not q:
        return jsonify({'status': 'ok', 'results': []}), 200

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return jsonify({
            'status': 'error',
            'error': 'Neo4j not configured. Configure a connection in Settings.',
        }), 500

    # Case-insensitive substring match across common string properties.
    # Label filter is applied via parameter so we never interpolate user input
    # into the query (a dynamic label in the pattern would be an injection risk).
    cypher = (
        "MATCH (n) "
        "WHERE ($label = '' OR $label IN labels(n)) "
        "AND ("
        "  toLower(coalesce(n.name, '')) CONTAINS $q "
        "  OR toLower(coalesce(n.title, '')) CONTAINS $q "
        "  OR toLower(coalesce(n.display_name, '')) CONTAINS $q "
        "  OR toLower(coalesce(n.filename, '')) CONTAINS $q "
        "  OR toLower(coalesce(n.path, '')) CONTAINS $q "
        "  OR toLower(coalesce(toString(n.id), '')) CONTAINS $q "
        ") "
        "RETURN id(n) AS id, elementId(n) AS element_id, labels(n) AS labels, properties(n) AS props "
        "LIMIT $limit"
    )
    params = {'q': q.lower(), 'label': label, 'limit': limit}

    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            rows = client.execute_read(cypher, params)
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001 - surface connection/query errors to UI
        return jsonify({'status': 'error', 'error': str(e)}), 500

    results: List[Dict[str, Any]] = []
    for row in rows:
        node_id = str(row.get('id'))
        labels = row.get('labels') or []
        props = {k: _json_safe(v) for k, v in (row.get('props') or {}).items()}
        results.append({
            'id': node_id,
            'element_id': row.get('element_id'),
            'label': labels[0] if labels else 'Node',
            'labels': labels,
            'name': _display_name(props, node_id),
            'properties': props,
        })

    return jsonify({'status': 'ok', 'results': results}), 200


@bp.get('/relationship-types')
def relationship_types():
    """Return the relationship types present in the Neo4j schema (for the edge
    relationship-type picker)."""
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return jsonify({'status': 'error', 'error': 'Neo4j not configured.'}), 500
    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            rows = client.execute_read(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN relationshipType ORDER BY relationshipType"
            )
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        return jsonify({'status': 'error', 'error': str(e)}), 500

    types = [r.get('relationshipType') for r in rows if r.get('relationshipType')]
    return jsonify({'status': 'ok', 'relationship_types': types}), 200


# --- Per-user canvas session (survives browser refresh; not a named layer) ---
@bp.get('/session')
def load_session():
    from ...services.canvas_service import get_canvas_service

    svc = get_canvas_service(db_path=_settings_db())
    data = svc.load_session(_current_user_id())
    if not data:
        return jsonify({'status': 'ok', 'canvas': None}), 200
    return jsonify({'status': 'ok', 'canvas': data['canvas'], 'updated_at': data['updated_at']}), 200


@bp.post('/session')
def save_session():
    from ...services.canvas_service import get_canvas_service

    body = request.get_json(silent=True) or {}
    canvas = body.get('canvas', body)  # accept {canvas:{...}} or a bare canvas object
    svc = get_canvas_service(db_path=_settings_db())
    saved_at = svc.save_session(_current_user_id(), canvas)
    return jsonify({'status': 'ok', 'saved_at': saved_at}), 200


@bp.delete('/session')
def clear_session():
    from ...services.canvas_service import get_canvas_service

    svc = get_canvas_service(db_path=_settings_db())
    svc.clear_session(_current_user_id())
    return jsonify({'status': 'ok'}), 200


# --- Canvas query library ---
@bp.get('/queries')
def list_queries():
    from ...services.canvas_service import get_canvas_service

    svc = get_canvas_service(db_path=_settings_db())
    return jsonify({'status': 'ok', 'queries': svc.list_queries()}), 200


@bp.post('/queries')
def create_query():
    from ...services.canvas_service import get_canvas_service

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    cypher = (body.get('cypher') or '').strip()
    if not name or not cypher:
        return jsonify({'status': 'error', 'error': 'name and cypher are required'}), 400
    svc = get_canvas_service(db_path=_settings_db())
    q = svc.create_query(name, cypher, created_by=_current_user_id())
    return jsonify({'status': 'ok', 'query': q}), 201


@bp.delete('/queries/<query_id>')
def delete_query(query_id: str):
    from ...services.canvas_service import get_canvas_service

    svc = get_canvas_service(db_path=_settings_db())
    ok = svc.delete_query(query_id)
    return jsonify({'status': 'ok', 'deleted': ok}), (200 if ok else 404)


# --- Named saved layers (stored in saved_maps via SavedMapsService) ---
@bp.get('/layers')
def list_layers():
    from ...services.saved_maps_service import get_saved_maps_service

    svc = get_saved_maps_service(db_path=_settings_db())
    maps = svc.list_maps(limit=int(request.args.get('limit', 100)))
    # Lightweight list view — omit heavy snapshot_json payloads.
    layers = [
        {
            'layer_id': m.id,
            'name': m.name,
            'display_mode': m.display_mode,
            'created_at': m.created_at,
            'updated_at': m.updated_at,
            'snapshot_saved_at': m.snapshot_saved_at,
        }
        for m in maps
    ]
    return jsonify({'status': 'ok', 'layers': layers}), 200


@bp.post('/layers')
def create_layer():
    from ...services.saved_maps_service import get_saved_maps_service

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'status': 'error', 'error': 'name is required'}), 400
    svc = get_saved_maps_service(db_path=_settings_db())
    m = svc.save_map(
        name=name,
        description=body.get('description'),
        display_mode=body.get('display_mode') or 'instance',
        layers=body.get('layers') or [],
        snapshot_json=body.get('snapshot_json'),
    )
    return jsonify({'status': 'ok', 'layer_id': m.id, 'layer': m.to_dict()}), 201


@bp.get('/layers/<layer_id>')
def get_layer(layer_id: str):
    from ...services.saved_maps_service import get_saved_maps_service

    svc = get_saved_maps_service(db_path=_settings_db())
    m = svc.get_map(layer_id)
    if not m:
        return jsonify({'status': 'error', 'error': 'not found'}), 404
    return jsonify({'status': 'ok', 'layer': m.to_dict()}), 200


@bp.delete('/layers/<layer_id>')
def delete_layer(layer_id: str):
    from ...services.saved_maps_service import get_saved_maps_service

    svc = get_saved_maps_service(db_path=_settings_db())
    ok = svc.delete_map(layer_id)
    return jsonify({'status': 'ok', 'deleted': ok}), (200 if ok else 404)


def _snapshot_from_request():
    """Pull a canvas snapshot from the request body ({snapshot|canvas:{...}} or bare)."""
    body = request.get_json(silent=True) or {}
    return body.get('snapshot') or body.get('canvas') or body


# --- Commit provisional elements to Neo4j (admin only) ---
@bp.post('/commit')
@require_role('admin')
def commit_canvas():
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params
    from ...services.canvas_service import build_commit_plan

    snapshot = _snapshot_from_request()
    plan = build_commit_plan(snapshot)
    preview = str(request.args.get('preview') or '').lower() in ('1', 'true', 'yes')

    summary = {
        'provisional_nodes': len(plan['node_decls']),
        'provisional_edges': len(plan['rels']),
        'skipped': plan['skipped'],
    }
    if preview:
        return jsonify({'status': 'ok', 'preview': True, 'plan': summary,
                        'nodes': plan['node_decls']}), 200

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return jsonify({'status': 'error', 'error': 'Neo4j not configured.'}), 500

    result = {'written_nodes': 0, 'written_relationships': 0, 'errors': []}
    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            # One MERGE path: nodes first (keyed on name), then edges matched by
            # (label, name). MERGE finds the just-written or pre-existing node.
            wd = client.write_declared_nodes(plan['node_decls'], plan['rels'])
            result['written_nodes'] += wd.get('written_nodes', 0)
            result['written_relationships'] += wd.get('written_relationships', 0)
            result['errors'].extend(wd.get('errors', []))
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        return jsonify({'status': 'error', 'error': str(e)}), 500

    result['skipped'] = plan['skipped']
    result['status'] = 'ok' if not result['errors'] else 'partial'
    return jsonify(result), 200


# --- Exports (download provisional changes as runnable scripts) ---
from flask import Response  # noqa: E402

# Exports only serialize a client-supplied snapshot, so they are read-like and
# do not need /commit's admin gate — but they should not be open either. Every
# authenticated role is listed rather than a single 'staff' role because there
# is no staff role: auth_users constrains role to ('admin', 'user')
# (core/auth.py:60) and require_role is a plain membership test, not a
# hierarchy, so @require_role('staff') would 403 every real user.
_EXPORT_ROLES = ('admin', 'user')


def _layer_name_from_request() -> str:
    body = request.get_json(silent=True) or {}
    return (body.get('layer_name') or body.get('name') or 'canvas')


@bp.post('/export/cypher')
@require_role(*_EXPORT_ROLES)
def export_cypher():
    from ...services.canvas_service import generate_cypher

    text = generate_cypher(_snapshot_from_request(), _layer_name_from_request())
    return Response(
        text, mimetype='text/plain',
        headers={'Content-Disposition': 'attachment; filename="canvas.cypher"'},
    )


@bp.post('/export/python')
@require_role(*_EXPORT_ROLES)
def export_python():
    from ...services.canvas_service import generate_python_fs

    text = generate_python_fs(_snapshot_from_request(), _layer_name_from_request())
    return Response(
        text, mimetype='text/x-python',
        headers={'Content-Disposition': 'attachment; filename="canvas_reorg.py"'},
    )


@bp.post('/export/rocrate')
@require_role(*_EXPORT_ROLES)
def export_rocrate():
    from ...services.canvas_service import generate_rocrate_export

    text = generate_rocrate_export(_snapshot_from_request(), _layer_name_from_request())
    return Response(
        text, mimetype='application/ld+json',
        headers={'Content-Disposition': 'attachment; filename="ro-crate-metadata.json"'},
    )


# --- Snapshot diff support (Item 4): which loaded nodes still exist in Neo4j ---
@bp.post('/nodes/verify')
def verify_nodes():
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    body = request.get_json(silent=True) or {}
    element_ids = [str(x) for x in (body.get('element_ids') or []) if x]
    if not element_ids:
        return jsonify({'status': 'ok', 'existing': [], 'missing': []}), 200

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return jsonify({'status': 'error', 'error': 'Neo4j not configured.'}), 500
    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            rows = client.execute_read(
                "MATCH (n) WHERE elementId(n) IN $ids RETURN elementId(n) AS eid",
                {'ids': element_ids},
            )
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        return jsonify({'status': 'error', 'error': str(e)}), 500

    existing = {r.get('eid') for r in rows}
    missing = [e for e in element_ids if e not in existing]
    return jsonify({'status': 'ok', 'existing': sorted(existing), 'missing': missing}), 200


# --- Ellipsis expansion (Item 5): a node's outgoing neighbours ---
@bp.post('/nodes/expand')
def expand_node():
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    body = request.get_json(silent=True) or {}
    element_id = body.get('element_id')
    if not element_id:
        return jsonify({'status': 'error', 'error': 'element_id required'}), 400
    try:
        limit = int(body.get('limit') or CANVAS_LAZY_LOAD_LIMIT)
    except (TypeError, ValueError):
        limit = CANVAS_LAZY_LOAD_LIMIT
    limit = max(1, min(limit, CANVAS_LAZY_LOAD_LIMIT))

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return jsonify({'status': 'error', 'error': 'Neo4j not configured.'}), 500
    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            total = client.execute_read(
                "MATCH (n)-[r]->(m) WHERE elementId(n) = $id RETURN count(m) AS total",
                {'id': element_id},
            )
            total_count = (total[0].get('total') if total else 0) or 0
            rows = client.execute_read(
                "MATCH (n)-[r]->(m) WHERE elementId(n) = $id "
                "RETURN id(m) AS id, elementId(m) AS element_id, labels(m) AS labels, "
                "properties(m) AS props, type(r) AS rel LIMIT $limit",
                {'id': element_id, 'limit': limit},
            )
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        return jsonify({'status': 'error', 'error': str(e)}), 500

    children = []
    for r in rows:
        props = {k: _json_safe(v) for k, v in (r.get('props') or {}).items()}
        labels = r.get('labels') or []
        children.append({
            'id': str(r.get('id')),
            'element_id': r.get('element_id'),
            'label': labels[0] if labels else 'Node',
            'name': _display_name(props, str(r.get('id'))),
            'relationship': r.get('rel'),
            'properties': props,
        })
    return jsonify({
        'status': 'ok',
        'total': total_count,
        'threshold': CANVAS_FANOUT_THRESHOLD,
        'children': children,
    }), 200


@bp.put('/layers/<layer_id>')
def update_layer(layer_id: str):
    """Update a saved layer's snapshot (Item 4 Refresh: overwrite snapshot)."""
    from ...services.saved_maps_service import get_saved_maps_service

    body = request.get_json(silent=True) or {}
    updates = {}
    if 'snapshot_json' in body:
        updates['snapshot_json'] = body.get('snapshot_json')
    if 'name' in body:
        updates['name'] = body.get('name')
    if 'display_mode' in body:
        updates['display_mode'] = body.get('display_mode')
    svc = get_saved_maps_service(db_path=_settings_db())
    m = svc.update_map(layer_id, **updates)
    if not m:
        return jsonify({'status': 'error', 'error': 'not found'}), 404
    return jsonify({'status': 'ok', 'layer': m.to_dict()}), 200
