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


@bp.route('/labels/<name>/pull', methods=['POST'])
def pull_label_from_neo4j(name):
    """
    Pull properties for a specific label from Neo4j.

    Returns:
    {
        "status": "success",
        "label": {...},
        "new_properties_count": 3
    }
    """
    try:
        service = _get_label_service()
        result = service.pull_label_properties_from_neo4j(name)

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


@bp.route('/labels/import/arrows', methods=['POST'])
def import_arrows_schema():
    """
    Import schema from Neo4j Arrows.app JSON format.

    Request body:
    {
        "arrows_json": {...},  // Arrows.app JSON format
        "mode": "merge" | "replace"  // default: merge
    }

    Returns:
    {
        "status": "success",
        "imported": {
            "labels": 5,
            "relationships": 8
        },
        "labels": [...]  // Created label definitions
    }
    """
    try:
        from ...interpreters.arrows_utils import import_from_arrows

        data = request.get_json(force=True, silent=True) or {}
        arrows_json = data.get('arrows_json')
        mode = data.get('mode', 'merge')

        if not arrows_json:
            return jsonify({'status': 'error', 'error': 'No arrows_json provided'}), 400

        # Use arrows_utils to parse
        labels_to_create = import_from_arrows(arrows_json)

        # Create labels via service
        service = _get_label_service()
        created = []
        skipped = []
        for label_def in labels_to_create:
            try:
                result = service.save_label(label_def)
                created.append(result)
            except Exception as e:
                # Skip duplicates if merge mode
                if mode == 'merge':
                    skipped.append(label_def['name'])
                    continue
                raise

        total_relationships = sum(len(l.get('relationships', [])) for l in labels_to_create)

        response = {
            'status': 'success',
            'imported': {'labels': len(created), 'relationships': total_relationships},
            'labels': created,
        }

        if skipped:
            response['skipped'] = skipped

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.route('/labels/export/arrows', methods=['GET'])
def export_arrows_schema():
    """
    Export schema to Neo4j Arrows.app JSON format.

    Query params:
    - layout: 'grid' or 'circular' (default: 'grid')
    - scale: position scale factor (default: 1000)

    Returns Arrows-compatible JSON file.
    """
    try:
        from ...interpreters.arrows_utils import export_to_arrows

        service = _get_label_service()
        labels = service.list_labels()

        layout = request.args.get('layout', 'grid')
        scale = int(request.args.get('scale', 1000))

        # Use arrows_utils to generate format
        arrows_json = export_to_arrows(labels, layout=layout, scale=scale)

        response = jsonify(arrows_json)
        response.headers['Content-Disposition'] = 'attachment; filename=scidk-schema.json'
        return response, 200

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.route('/labels/batch/pull', methods=['POST'])
def batch_pull_labels():
    """
    Pull schema from Neo4j for multiple labels.

    Request body:
    {
        "label_names": ["Label1", "Label2", ...]
    }

    Returns:
    {
        "status": "success",
        "results": [...],
        "total_new_properties": 10,
        "total_new_relationships": 5
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        label_names = data.get('label_names', [])

        if not label_names:
            return jsonify({'status': 'error', 'error': 'No label names provided'}), 400

        service = _get_label_service()
        results = []
        total_new_properties = 0
        total_new_relationships = 0

        for name in label_names:
            try:
                result = service.pull_label_properties_from_neo4j(name)
                results.append({'label': name, 'result': result})

                if result.get('status') == 'success':
                    total_new_properties += result.get('new_properties_count', 0)
                    total_new_relationships += result.get('new_relationships_count', 0)
            except Exception as e:
                results.append({'label': name, 'result': {'status': 'error', 'error': str(e)}})

        return jsonify({
            'status': 'success',
            'results': results,
            'total_new_properties': total_new_properties,
            'total_new_relationships': total_new_relationships
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.route('/labels/batch/delete', methods=['POST'])
def batch_delete_labels():
    """
    Delete multiple labels.

    Request body:
    {
        "label_names": ["Label1", "Label2", ...]
    }

    Returns:
    {
        "status": "success",
        "deleted_count": 2,
        "results": [...]
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        label_names = data.get('label_names', [])

        if not label_names:
            return jsonify({'status': 'error', 'error': 'No label names provided'}), 400

        service = _get_label_service()
        results = []
        deleted_count = 0

        for name in label_names:
            try:
                deleted = service.delete_label(name)
                results.append({'label': name, 'deleted': deleted})
                if deleted:
                    deleted_count += 1
            except Exception as e:
                results.append({'label': name, 'error': str(e)})

        return jsonify({
            'status': 'success',
            'deleted_count': deleted_count,
            'results': results
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.route('/labels/<name>/instances', methods=['GET'])
def get_label_instances(name):
    """
    Get instances of a label from Neo4j.

    Query params:
    - limit: max number of instances (default: 100)
    - offset: pagination offset (default: 0)

    Returns:
    {
        "status": "success",
        "instances": [
            {"id": "...", "properties": {"name": "John", "age": 30}},
            ...
        ],
        "total": 150,
        "limit": 100,
        "offset": 0
    }
    """
    try:
        service = _get_label_service()
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        result = service.get_label_instances(name, limit=limit, offset=offset)

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


@bp.route('/labels/<name>/instance-count', methods=['GET'])
def get_label_instance_count(name):
    """
    Get count of instances for a label from Neo4j.

    Returns:
    {
        "status": "success",
        "count": 42
    }
    """
    try:
        service = _get_label_service()
        result = service.get_label_instance_count(name)

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


@bp.route('/labels/<name>/instances/<instance_id>', methods=['PATCH'])
def update_label_instance(name, instance_id):
    """
    Update a single property of a label instance in Neo4j.

    Request body:
    {
        "property": "name",
        "value": "New Value"
    }

    Returns:
    {
        "status": "success",
        "instance": {...}
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        property_name = data.get('property')
        property_value = data.get('value')

        if not property_name:
            return jsonify({
                'status': 'error',
                'error': 'Property name is required'
            }), 400

        service = _get_label_service()
        result = service.update_label_instance(name, instance_id, property_name, property_value)

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


@bp.route('/labels/import/eda', methods=['POST'])
def import_eda_file():
    """
    Import experimental design from NC3Rs EDA file.

    Expects multipart/form-data with 'file' field containing .eda file.

    Returns:
    {
        "status": "success",
        "imported": {
            "labels": 3,
            "relationships": 5
        },
        "labels": [...]
    }
    """
    import tempfile
    import os
    from werkzeug.utils import secure_filename
    from ...interpreters.eda_interpreter import parse_eda_file, eda_to_labels

    try:
        # Check if file present
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'error': 'Empty filename'}), 400

        if not file.filename.endswith('.eda'):
            return jsonify({'status': 'error', 'error': 'File must be .eda format'}), 400

        # Save to temporary file
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.eda') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            # Parse EDA file
            eda_nodes, eda_edges = parse_eda_file(tmp_path)
            labels_to_create = eda_to_labels(eda_nodes, eda_edges)

            # Create labels
            service = _get_label_service()
            created = []
            skipped = []

            for label_def in labels_to_create:
                try:
                    result = service.save_label(label_def)
                    created.append(result)
                except Exception as e:
                    # Skip duplicates
                    skipped.append(label_def['name'])
                    continue

            total_relationships = sum(len(l.get('relationships', [])) for l in labels_to_create)

            response = {
                'status': 'success',
                'imported': {
                    'labels': len(created),
                    'relationships': total_relationships
                },
                'labels': created
            }

            if skipped:
                response['skipped'] = skipped

            return jsonify(response), 200

        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500
