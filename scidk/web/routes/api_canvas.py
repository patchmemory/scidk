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

bp = Blueprint('api_canvas', __name__, url_prefix='/api/canvas')


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
        "RETURN id(n) AS id, labels(n) AS labels, properties(n) AS props "
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
