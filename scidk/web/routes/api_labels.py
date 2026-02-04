"""
Blueprint for Labels API routes.

Provides REST endpoints for:
- Label definitions CRUD
- Neo4j schema push/pull synchronization
- Schema introspection
"""
from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('labels', __name__, url_prefix='/api')


def _get_label_service():
    """Get or create LabelService instance."""
    from ...services.label_service import LabelService
    if 'label_service' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}
        current_app.extensions['scidk']['label_service'] = LabelService(current_app)
    return current_app.extensions['scidk']['label_service']


@bp.route('/labels', methods=['GET'])
def list_labels():
    """
    Get all label definitions.

    Returns:
    {
        "status": "success",
        "labels": [
            {
                "name": "Project",
                "properties": [{"name": "name", "type": "string", "required": true}],
                "relationships": [{"type": "HAS_FILE", "target_label": "File", "properties": []}],
                "created_at": 1234567890.123,
                "updated_at": 1234567890.123
            }
        ]
    }
    """
    try:
        service = _get_label_service()
        labels = service.list_labels()
        return jsonify({
            'status': 'success',
            'labels': labels
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels/<name>', methods=['GET'])
def get_label(name):
    """
    Get a specific label definition by name.

    Returns:
    {
        "status": "success",
        "label": {...}
    }
    """
    try:
        service = _get_label_service()
        label = service.get_label(name)

        if not label:
            return jsonify({
                'status': 'error',
                'error': f'Label "{name}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'label': label
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels', methods=['POST'])
def create_or_update_label():
    """
    Create or update a label definition.

    Request body:
    {
        "name": "Project",
        "properties": [
            {"name": "name", "type": "string", "required": true},
            {"name": "budget", "type": "number", "required": false}
        ],
        "relationships": [
            {"type": "HAS_FILE", "target_label": "File", "properties": []}
        ]
    }

    Returns:
    {
        "status": "success",
        "label": {...}
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        if not data.get('name'):
            return jsonify({
                'status': 'error',
                'error': 'Label name is required'
            }), 400

        service = _get_label_service()
        label = service.save_label(data)

        return jsonify({
            'status': 'success',
            'label': label
        }), 200
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels/<name>', methods=['DELETE'])
def delete_label(name):
    """
    Delete a label definition.

    Returns:
    {
        "status": "success",
        "message": "Label deleted"
    }
    """
    try:
        service = _get_label_service()
        deleted = service.delete_label(name)

        if not deleted:
            return jsonify({
                'status': 'error',
                'error': f'Label "{name}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'message': f'Label "{name}" deleted'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels/<name>/push', methods=['POST'])
def push_label_to_neo4j(name):
    """
    Push label definition to Neo4j (create constraints/indexes).

    Returns:
    {
        "status": "success",
        "label": "Project",
        "constraints_created": ["name"],
        "indexes_created": []
    }
    """
    try:
        service = _get_label_service()
        result = service.push_to_neo4j(name)

        if result.get('status') == 'error':
            return jsonify(result), 500

        return jsonify(result), 200
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels/pull', methods=['POST'])
def pull_labels_from_neo4j():
    """
    Pull label schema from Neo4j and import as label definitions.

    Returns:
    {
        "status": "success",
        "imported_labels": ["Project", "File"],
        "count": 2
    }
    """
    try:
        service = _get_label_service()
        result = service.pull_from_neo4j()

        if result.get('status') == 'error':
            return jsonify(result), 500

        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/labels/neo4j/schema', methods=['GET'])
def get_neo4j_schema():
    """
    Get current Neo4j schema information.

    Returns:
    {
        "status": "success",
        "labels": ["Project", "File"],
        "relationship_types": ["HAS_FILE"],
        "constraints": [{"name": "constraint_Project_name", "type": "UNIQUENESS"}]
    }
    """
    try:
        service = _get_label_service()
        result = service.get_neo4j_schema()

        if result.get('status') == 'error':
            return jsonify(result), 500

        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
