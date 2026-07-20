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

from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('api_canvas', __name__, url_prefix='/api/canvas')


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
