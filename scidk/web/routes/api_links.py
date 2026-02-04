"""
Blueprint for Links API routes.

Provides REST endpoints for:
- Link definitions CRUD
- Preview and execution of link jobs
- Job status tracking
"""
from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('links', __name__, url_prefix='/api')


def _get_link_service():
    """Get or create LinkService instance."""
    from ...services.link_service import LinkService
    if 'link_service' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}
        current_app.extensions['scidk']['link_service'] = LinkService(current_app)
    return current_app.extensions['scidk']['link_service']


@bp.route('/links', methods=['GET'])
def list_links():
    """
    Get all link definitions.

    Returns:
    {
        "status": "success",
        "links": [
            {
                "id": "uuid",
                "name": "Author to File",
                "source_type": "csv",
                "target_type": "label",
                "match_strategy": "property",
                "relationship_type": "AUTHORED",
                ...
            }
        ]
    }
    """
    try:
        service = _get_link_service()
        links = service.list_link_definitions()
        return jsonify({
            'status': 'success',
            'links': links
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/<link_id>', methods=['GET'])
def get_link(link_id):
    """
    Get a specific link definition by ID.

    Returns:
    {
        "status": "success",
        "link": {...}
    }
    """
    try:
        service = _get_link_service()
        link = service.get_link_definition(link_id)

        if not link:
            return jsonify({
                'status': 'error',
                'error': f'Link "{link_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'link': link
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links', methods=['POST'])
def create_or_update_link():
    """
    Create or update a link definition.

    Request body:
    {
        "id": "optional-uuid",
        "name": "Author to File",
        "source_type": "csv",
        "source_config": {
            "csv_data": "name,email,file_path\\nAlice,alice@ex.com,file1.txt"
        },
        "target_type": "label",
        "target_config": {
            "label": "File"
        },
        "match_strategy": "property",
        "match_config": {
            "source_field": "file_path",
            "target_field": "path"
        },
        "relationship_type": "AUTHORED",
        "relationship_props": {
            "date": "2024-01-15"
        }
    }

    Returns:
    {
        "status": "success",
        "link": {...}
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        if not data.get('name'):
            return jsonify({
                'status': 'error',
                'error': 'Link name is required'
            }), 400

        service = _get_link_service()
        link = service.save_link_definition(data)

        return jsonify({
            'status': 'success',
            'link': link
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


@bp.route('/links/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    """
    Delete a link definition.

    Returns:
    {
        "status": "success",
        "message": "Link deleted"
    }
    """
    try:
        service = _get_link_service()
        deleted = service.delete_link_definition(link_id)

        if not deleted:
            return jsonify({
                'status': 'error',
                'error': f'Link "{link_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'message': f'Link "{link_id}" deleted'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/<link_id>/preview', methods=['POST'])
def preview_link(link_id):
    """
    Preview link matches (dry-run).

    Request body (optional):
    {
        "limit": 10
    }

    Returns:
    {
        "status": "success",
        "matches": [
            {
                "source": {"name": "Alice", "email": "alice@ex.com", ...},
                "target": {"path": "file1.txt", ...}
            }
        ],
        "count": 5
    }
    """
    try:
        service = _get_link_service()
        link = service.get_link_definition(link_id)

        if not link:
            return jsonify({
                'status': 'error',
                'error': f'Link "{link_id}" not found'
            }), 404

        data = request.get_json(force=True, silent=True) or {}
        limit = data.get('limit', 10)

        matches = service.preview_matches(link, limit=limit)

        return jsonify({
            'status': 'success',
            'matches': matches,
            'count': len(matches)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/<link_id>/execute', methods=['POST'])
def execute_link(link_id):
    """
    Execute link job (create relationships in Neo4j).

    Returns:
    {
        "status": "success",
        "job_id": "uuid"
    }
    """
    try:
        service = _get_link_service()
        job_id = service.execute_link_job(link_id)

        return jsonify({
            'status': 'success',
            'job_id': job_id
        }), 200
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


@bp.route('/links/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get job status and progress.

    Returns:
    {
        "status": "success",
        "job": {
            "id": "uuid",
            "link_def_id": "uuid",
            "status": "completed",
            "preview_count": 0,
            "executed_count": 23,
            "error": null,
            "started_at": 1234567890.123,
            "completed_at": 1234567895.456
        }
    }
    """
    try:
        service = _get_link_service()
        job = service.get_job_status(job_id)

        if not job:
            return jsonify({
                'status': 'error',
                'error': f'Job "{job_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'job': job
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/jobs', methods=['GET'])
def list_jobs():
    """
    List recent link jobs.

    Query params:
    - limit: Maximum number of jobs to return (default: 20)

    Returns:
    {
        "status": "success",
        "jobs": [...]
    }
    """
    try:
        limit = int(request.args.get('limit', 20))
        service = _get_link_service()
        jobs = service.list_jobs(limit=limit)

        return jsonify({
            'status': 'success',
            'jobs': jobs
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
