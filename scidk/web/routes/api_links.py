"""
Blueprint for Links API routes (DEPRECATED).

**DEPRECATED**: This module is kept for backward compatibility only.
Use api_integrations.py instead. All /api/links/* endpoints redirect to /api/integrations/*

Provides REST endpoints for:
- Link definitions CRUD (deprecated, use integrations)
- Preview and execution of link jobs (deprecated, use integrations)
- Job status tracking (deprecated, use integrations)
"""
from flask import Blueprint, jsonify, request, current_app, redirect, url_for
import logging

logger = logging.getLogger(__name__)

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

    **DEPRECATED**: Use /api/integrations instead.

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
    logger.warning("DEPRECATED: /api/links endpoint called. Use /api/integrations instead.")
    try:
        service = _get_link_service()
        links = service.list_all_links()  # NEW: Uses unified method
        return jsonify({
            'status': 'success',
            'links': links
        }), 200
    except Exception as e:
        logger.exception("Failed to list links")
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


@bp.route('/links/available-labels', methods=['GET'])
def get_available_labels():
    """
    Get list of available labels for dropdown population.

    Returns:
    {
        "status": "success",
        "labels": [
            {"name": "Person", "properties": [...]},
            {"name": "File", "properties": [...]}
        ]
    }
    """
    try:
        from ...services.label_service import LabelService
        label_service = LabelService(current_app)
        labels = label_service.list_labels()

        return jsonify({
            'status': 'success',
            'labels': labels
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/migrate', methods=['POST'])
def migrate_links():
    """
    Migrate existing link definitions to Label→Label model.

    Returns:
    {
        "status": "success",
        "report": {
            "migrated": [...],
            "skipped": [...],
            "errors": [...]
        }
    }
    """
    try:
        from ...services.link_migration import migrate_all_links, generate_migration_report
        service = _get_link_service()

        results = migrate_all_links(service)
        report_text = generate_migration_report(results)

        return jsonify({
            'status': 'success',
            'results': results,
            'report': report_text
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/discovered', methods=['GET'])
def discover_relationships():
    """
    Discover existing relationship types in connected Neo4j databases.

    Query params:
    - profile: Optional profile name to query specific database

    Returns:
    {
        "status": "success",
        "relationships": [
            {
                "source_label": "Sample",
                "rel_type": "DERIVED_FROM",
                "target_label": "File",
                "triple_count": 42,
                "database": "PRIMARY" | "profile_name"
            }
        ]
    }
    """
    try:
        profile = request.args.get('profile')
        service = _get_link_service()

        relationships = service.discover_relationships(profile_name=profile)

        return jsonify({
            'status': 'success',
            'relationships': relationships
        }), 200
    except Exception as e:
        logger.exception("Failed to discover relationships")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/import-triples/preview', methods=['POST'])
def preview_triple_import():
    """
    Preview triples that would be imported from an external database.

    Body:
    {
        "source_database": "External DB Name",
        "rel_type": "DERIVED_FROM",
        "source_label": "Sample",
        "target_label": "File"
    }

    Returns:
    {
        "status": "success",
        "preview": [
            {
                "source_node": {"id": "...", "label": "Sample", "properties": {...}},
                "relationship": {"type": "DERIVED_FROM", "properties": {...}},
                "target_node": {"id": "...", "label": "File", "properties": {...}}
            }
        ],
        "total_count": 1523,
        "preview_hash": "abc123...",
        "showing": 100
    }
    """
    try:
        data = request.get_json()
        service = _get_link_service()

        result = service.preview_triple_import(
            source_database=data.get('source_database'),
            rel_type=data.get('rel_type'),
            source_label=data.get('source_label'),
            target_label=data.get('target_label')
        )

        if result.get('status') == 'error':
            return jsonify(result), 400

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Failed to preview triple import")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/import-triples/commit', methods=['POST'])
def commit_triple_import():
    """
    Commit triple import from external database to primary.

    Body:
    {
        "source_database": "External DB Name",
        "rel_type": "DERIVED_FROM",
        "source_label": "Sample",
        "target_label": "File",
        "preview_hash": "abc123..."
    }

    Returns:
    {
        "status": "success",
        "triples_imported": 1523,
        "duration_seconds": 12.34
    }
    """
    try:
        data = request.get_json()
        service = _get_link_service()

        result = service.commit_triple_import(
            source_database=data.get('source_database'),
            rel_type=data.get('rel_type'),
            source_label=data.get('source_label'),
            target_label=data.get('target_label'),
            preview_hash=data.get('preview_hash')
        )

        if result.get('status') == 'error':
            return jsonify(result), 400

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Failed to commit triple import")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/<link_id>/export-csv', methods=['POST'])
def export_matches_csv(link_id):
    """
    Export candidate matches to CSV for human validation (fuzzy/CONTAINS).

    Body:
    {
        "limit": 100  // optional, default all matches
    }

    Returns CSV file with columns:
    source_id, source_label, source_props, target_id, target_label, target_props, match_score, validated
    """
    try:
        import csv
        from io import StringIO
        from flask import make_response

        data = request.get_json() or {}
        service = _get_link_service()

        # Get link definition
        link = service.get_link(link_id)
        if not link:
            return jsonify({'status': 'error', 'error': 'Link not found'}), 404

        # Generate preview matches
        matches = service.preview_link(link_id, limit=data.get('limit'))
        if matches.get('status') == 'error':
            return jsonify(matches), 400

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['source_id', 'source_label', 'source_props', 'target_id', 'target_label', 'target_props', 'match_score', 'validated'])

        for match in matches.get('matches', []):
            source = match.get('source', {})
            target = match.get('target', {})
            writer.writerow([
                source.get('id', ''),
                link.get('source_label', ''),
                str(source),
                target.get('id', ''),
                link.get('target_label', ''),
                str(target),
                match.get('score', ''),
                ''  # Empty validated column for human to fill
            ])

        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=matches_{link_id}.csv'
        return response

    except Exception as e:
        logger.exception("Failed to export CSV")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.route('/links/<link_id>/import-csv', methods=['POST'])
def import_validated_csv(link_id):
    """
    Import validated matches from CSV and create relationships.

    Expects CSV file with 'validated' column marked as 'yes'/'true'/'1' for valid matches.

    Returns:
    {
        "status": "success",
        "relationships_created": 42,
        "rows_processed": 100,
        "rows_validated": 42
    }
    """
    try:
        import csv
        from io import StringIO

        if 'file' not in request.files:
            return jsonify({'status': 'error', 'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'error': 'Empty filename'}), 400

        # Read CSV
        content = file.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        service = _get_link_service()
        link = service.get_link(link_id)
        if not link:
            return jsonify({'status': 'error', 'error': 'Link not found'}), 404

        # Process validated rows
        validated_matches = []
        rows_processed = 0
        rows_validated = 0

        for row in reader:
            rows_processed += 1
            validated = row.get('validated', '').lower()
            if validated in ['yes', 'true', '1', 'y']:
                rows_validated += 1
                validated_matches.append({
                    'source_id': row.get('source_id'),
                    'target_id': row.get('target_id'),
                    'match_score': row.get('match_score')
                })

        # Create relationships for validated matches only
        relationships_created = service.create_validated_relationships(
            link_id=link_id,
            matches=validated_matches
        )

        return jsonify({
            'status': 'success',
            'relationships_created': relationships_created,
            'rows_processed': rows_processed,
            'rows_validated': rows_validated
        }), 200

    except Exception as e:
        logger.exception("Failed to import validated CSV")
        return jsonify({'status': 'error', 'error': str(e)}), 500
