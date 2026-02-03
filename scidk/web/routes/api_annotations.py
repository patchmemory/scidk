"""
Blueprint for Annotations API routes.

Provides REST endpoints for:
- Relationships CRUD
- Sync queue management
"""
from flask import Blueprint, jsonify, request
import time

from ...core import annotations_sqlite as ann

bp = Blueprint('annotations', __name__, url_prefix='/api')


@bp.route('/relationships', methods=['POST'])
def create_relationship():
    """
    Create a new relationship between entities.

    Request body:
    {
        "from_id": "file_abc123",
        "to_id": "file_def456",
        "type": "GENERATED_BY",
        "properties": {"confidence": 0.95, "method": "auto"}  # optional
    }

    Returns:
    {
        "id": 123,
        "from_id": "file_abc123",
        "to_id": "file_def456",
        "type": "GENERATED_BY",
        "properties_json": "{...}",
        "created": 1234567890.123
    }
    """
    data = request.get_json(force=True, silent=True) or {}

    from_id = data.get('from_id')
    to_id = data.get('to_id')
    rel_type = data.get('type')

    if not from_id or not to_id or not rel_type:
        return jsonify({
            'status': 'error',
            'error': 'Missing required fields: from_id, to_id, type'
        }), 400

    # Serialize properties if present
    properties = data.get('properties')
    properties_json = None
    if properties is not None:
        import json
        try:
            properties_json = json.dumps(properties)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'error': f'Invalid properties format: {str(e)}'
            }), 400

    created_ts = time.time()

    try:
        result = ann.create_relationship(
            from_id=from_id,
            to_id=to_id,
            rel_type=rel_type,
            properties_json=properties_json,
            created_ts=created_ts
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to create relationship: {str(e)}'
        }), 500


@bp.route('/relationships', methods=['GET'])
def list_relationships():
    """
    List relationships for a given entity/file.

    Query parameters:
    - file_id: Required. Entity/file ID to query relationships for.

    Returns:
    {
        "relationships": [
            {
                "id": 123,
                "from_id": "file_abc123",
                "to_id": "file_def456",
                "type": "GENERATED_BY",
                "properties_json": "{...}",
                "created": 1234567890.123
            },
            ...
        ],
        "count": 2,
        "file_id": "file_abc123"
    }
    """
    file_id = request.args.get('file_id')

    if not file_id:
        return jsonify({
            'status': 'error',
            'error': 'Missing required query parameter: file_id'
        }), 400

    try:
        relationships = ann.list_relationships(entity_id=file_id)
        return jsonify({
            'relationships': relationships,
            'count': len(relationships),
            'file_id': file_id
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to list relationships: {str(e)}'
        }), 500


@bp.route('/relationships/<int:rel_id>', methods=['DELETE'])
def delete_relationship(rel_id):
    """
    Delete a relationship by ID.

    Returns:
    {
        "status": "deleted",
        "id": 123
    }
    """
    try:
        deleted = ann.delete_relationship(rel_id=rel_id)
        if deleted:
            return jsonify({'status': 'deleted', 'id': rel_id})
        else:
            return jsonify({
                'status': 'error',
                'error': 'Relationship not found'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to delete relationship: {str(e)}'
        }), 500


@bp.route('/sync', methods=['POST'])
def enqueue_sync():
    """
    Enqueue an item for background sync/projection.

    Request body:
    {
        "entity_type": "relationship",
        "entity_id": "123",
        "action": "create",
        "payload": {"target": "neo4j", "batch": true}  # optional
    }

    Returns:
    {
        "status": "enqueued",
        "sync_id": 456,
        "entity_type": "relationship",
        "entity_id": "123",
        "action": "create"
    }
    """
    data = request.get_json(force=True, silent=True) or {}

    entity_type = data.get('entity_type')
    entity_id = data.get('entity_id')
    action = data.get('action')

    if not entity_type or not entity_id or not action:
        return jsonify({
            'status': 'error',
            'error': 'Missing required fields: entity_type, entity_id, action'
        }), 400

    # Serialize payload if present
    payload = data.get('payload')
    payload_str = None
    if payload is not None:
        import json
        try:
            payload_str = json.dumps(payload)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'error': f'Invalid payload format: {str(e)}'
            }), 400

    created_ts = time.time()

    try:
        sync_id = ann.enqueue_sync(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload_str,
            created_ts=created_ts
        )
        return jsonify({
            'status': 'enqueued',
            'sync_id': sync_id,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'action': action
        }), 201
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to enqueue sync: {str(e)}'
        }), 500


@bp.route('/sync/queue', methods=['GET'])
def list_sync_queue():
    """
    List unprocessed items in the sync queue.

    Query parameters:
    - limit: Maximum number of items to return (default: 100)

    Returns:
    {
        "queue": [
            {
                "id": 456,
                "entity_type": "relationship",
                "entity_id": "123",
                "action": "create",
                "payload": "{...}",
                "created": 1234567890.123
            },
            ...
        ],
        "count": 5
    }
    """
    limit = request.args.get('limit', 100, type=int)

    try:
        queue = ann.dequeue_unprocessed(limit=limit)
        return jsonify({
            'queue': queue,
            'count': len(queue)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to list sync queue: {str(e)}'
        }), 500


@bp.route('/sync/<int:sync_id>/mark-processed', methods=['POST'])
def mark_sync_processed(sync_id):
    """
    Mark a sync queue item as processed.

    Returns:
    {
        "status": "marked_processed",
        "id": 456
    }
    """
    try:
        processed_ts = time.time()
        marked = ann.mark_processed(item_id=sync_id, processed_ts=processed_ts)
        if marked:
            return jsonify({
                'status': 'marked_processed',
                'id': sync_id,
                'processed_at': processed_ts
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Sync item not found'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Failed to mark as processed: {str(e)}'
        }), 500
