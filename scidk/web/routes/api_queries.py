"""
Blueprint for saved query library API routes.

Endpoints for managing user's saved Cypher queries.
"""
from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('queries', __name__, url_prefix='/api/queries')


def _get_query_service():
    """Get QueryService instance using settings DB path from config."""
    from ...services.query_service import get_query_service
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_query_service(db_path=db_path)


@bp.get('')
def list_queries():
    """List all saved queries.

    Query params:
        limit (int): Maximum number of queries (default 100)
        offset (int): Number to skip (default 0)
        sort_by (str): Sort field (default 'updated_at')

    Returns:
        200: {"queries": [{...}, ...]}
    """
    query_service = _get_query_service()

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    sort_by = request.args.get('sort_by', 'updated_at')

    queries = query_service.list_queries(limit=limit, offset=offset, sort_by=sort_by)

    return jsonify({
        'queries': [q.to_dict() for q in queries]
    }), 200


@bp.post('')
def save_query():
    """Save a new query.

    Request body:
        {
            "name": "Query Name",
            "query": "MATCH (n) RETURN n",
            "description": "Optional description",
            "tags": ["tag1", "tag2"],
            "metadata": {}
        }

    Returns:
        201: {"query": {...}}
        400: {"error": "Missing required field"}
    """
    query_service = _get_query_service()

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    query = data.get('query', '').strip()
    description = data.get('description')
    tags = data.get('tags')
    metadata = data.get('metadata')

    if not name:
        return jsonify({'error': 'Missing query name'}), 400

    if not query:
        return jsonify({'error': 'Missing query text'}), 400

    saved_query = query_service.save_query(
        name=name,
        query=query,
        description=description,
        tags=tags,
        metadata=metadata
    )

    return jsonify({
        'query': saved_query.to_dict()
    }), 201


@bp.get('/<query_id>')
def get_query(query_id):
    """Get a specific query.

    Returns:
        200: {"query": {...}}
        404: {"error": "Query not found"}
    """
    query_service = _get_query_service()

    query = query_service.get_query(query_id)
    if not query:
        return jsonify({'error': 'Query not found'}), 404

    return jsonify({
        'query': query.to_dict()
    }), 200


@bp.put('/<query_id>')
def update_query(query_id):
    """Update a saved query.

    Request body:
        {
            "name": "New Name",
            "query": "New query text",
            "description": "New description",
            "tags": ["new", "tags"]
        }

    Returns:
        200: {"success": true}
        404: {"error": "Query not found"}
    """
    query_service = _get_query_service()

    data = request.get_json() or {}
    name = data.get('name')
    query = data.get('query')
    description = data.get('description')
    tags = data.get('tags')
    metadata = data.get('metadata')

    success = query_service.update_query(
        query_id=query_id,
        name=name,
        query=query,
        description=description,
        tags=tags,
        metadata=metadata
    )

    if not success:
        return jsonify({'error': 'Query not found'}), 404

    return jsonify({'success': True}), 200


@bp.delete('/<query_id>')
def delete_query(query_id):
    """Delete a saved query.

    Returns:
        200: {"success": true}
        404: {"error": "Query not found"}
    """
    query_service = _get_query_service()

    success = query_service.delete_query(query_id)

    if not success:
        return jsonify({'error': 'Query not found'}), 404

    return jsonify({'success': True}), 200


@bp.post('/<query_id>/use')
def record_usage(query_id):
    """Record that a query was used (increments use_count).

    Returns:
        200: {"success": true}
        404: {"error": "Query not found"}
    """
    query_service = _get_query_service()

    success = query_service.record_usage(query_id)

    if not success:
        return jsonify({'error': 'Query not found'}), 404

    return jsonify({'success': True}), 200


@bp.get('/search')
def search_queries():
    """Search queries by name, text, or description.

    Query params:
        q (str): Search term
        limit (int): Maximum results (default 50)

    Returns:
        200: {"queries": [{...}, ...]}
    """
    query_service = _get_query_service()

    search_term = request.args.get('q', '')
    limit = request.args.get('limit', 50, type=int)

    if not search_term:
        return jsonify({'queries': []}), 200

    queries = query_service.search_queries(search_term=search_term, limit=limit)

    return jsonify({
        'queries': [q.to_dict() for q in queries]
    }), 200
