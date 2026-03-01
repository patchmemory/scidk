"""
Blueprint for Links API routes.

Use api_integrations.py instead. All /api/links/* endpoints redirect to /api/integrations/*

Provides REST endpoints for:
- Link definitions CRUD
- Preview and execution of link jobs
- Job status tracking
"""
from flask import Blueprint, jsonify, request, current_app, redirect, url_for
import logging
import json

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

    Query params:
    - status: Optional status filter ('active', 'pending', 'available')

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
                "status": "active",
                ...
            }
        ]
    }
    """
    logger.warning("DEPRECATED: /api/links endpoint called. Use /api/integrations instead.")
    try:
        service = _get_link_service()
        links = service.list_all_links()  # NEW: Uses unified method

        # Filter by status if requested
        status_filter = request.args.get('status')
        if status_filter:
            links = [link for link in links if link.get('status') == status_filter]

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


@bp.route('/links/<link_id>/job-status', methods=['GET'])
def get_link_job_status(link_id):
    """
    Check if there's a running job for this link definition.

    Returns:
    {
        "running": true,
        "task_id": "abc123",
        "progress": { task progress dict }
    }
    or
    {
        "running": false
    }
    """
    try:
        tasks = current_app.extensions.get('scidk', {}).get('tasks', {})

        # Find any running task for this link_def_id
        for task_id, task in tasks.items():
            if task.get('link_def_id') == link_id and task.get('status') == 'running':
                return jsonify({
                    'running': True,
                    'task_id': task_id,
                    'progress': {
                        'processed': task.get('processed', 0),
                        'total': task.get('total', 0),
                        'progress': task.get('progress', 0),
                        'status_message': task.get('status_message', ''),
                        'relationships_created': task.get('relationships_created', 0)
                    }
                }), 200

        return jsonify({'running': False}), 200
    except Exception as e:
        logger.exception("Failed to check job status")
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


@bp.route('/links/verify', methods=['POST'])
def verify_active_links():
    """
    Verify all active link definitions against primary Neo4j graph.

    Checks each active link to confirm relationships actually exist.
    Links with no relationships are moved to 'pending' status.

    Returns:
    {
        "status": "success",
        "verified": {
            "link_id_1": 1234,  // relationship count
            "link_id_2": 0,     // stale - moved to pending
            "link_id_3": -1     // verification error
        }
    }
    """
    try:
        service = _get_link_service()
        results = service.verify_active_links()

        return jsonify({
            'status': 'success',
            'verified': results
        }), 200
    except Exception as e:
        logger.exception("Failed to verify active links")
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


@bp.route('/links/discovered/import/preview', methods=['POST'])
def preview_discovered_import():
    """
    Preview stub node import from discovered relationship (dry run).

    Request body:
    {
        "source_label": "Person",
        "target_label": "File",
        "rel_type": "AUTHORED",
        "source_database": "Local Graph",
        "source_uid_property": "id",
        "target_uid_property": "uuid",
        "import_rel_properties": true
    }

    Returns preview statistics without making any changes.
    """
    try:
        data = request.json
        service = _get_link_service()

        preview = service.preview_discovered_import(
            source_label=data['source_label'],
            target_label=data['target_label'],
            rel_type=data['rel_type'],
            source_database=data['source_database'],
            source_uid_property=data['source_uid_property'],
            target_uid_property=data['target_uid_property'],
            import_rel_properties=data.get('import_rel_properties', True)
        )

        return jsonify({
            'status': 'success',
            'preview': preview
        }), 200
    except Exception as e:
        logger.exception("Failed to preview discovered import")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/discovered/adopt', methods=['POST'])
def adopt_discovered_as_definition():
    """
    Adopt a discovered relationship as a formal link definition.

    Creates a new link definition in 'pending' status that can be
    edited and run like any other link.

    Request body:
    {
        "source_label": "Person",
        "target_label": "File",
        "rel_type": "AUTHORED",
        "name": "Optional custom name"
    }

    Returns the created link definition.
    """
    try:
        data = request.json
        service = _get_link_service()

        source_label = data['source_label']
        target_label = data['target_label']
        rel_type = data['rel_type']
        name = data.get('name') or f"{source_label} {rel_type} {target_label}"

        # Create link definition with 'pending' status
        link_definition = {
            'name': name,
            'source_label': source_label,
            'target_label': target_label,
            'relationship_type': rel_type,
            'match_strategy': 'id',  # Default to ID-based matching
            'match_config': {},
            'source_config': {},
            'target_config': {},
            'relationship_props': {},
            'status': 'pending'
        }

        link = service.save_link_definition(link_definition)

        return jsonify({
            'status': 'success',
            'link': link
        }), 200
    except Exception as e:
        logger.exception("Failed to adopt discovered relationship")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/discovered/import', methods=['POST'])
def execute_discovered_import():
    """
    Import stub nodes and relationships from discovered relationship as background task.

    Creates lightweight stub nodes with only UID property, then creates
    relationships between them. Full node enrichment happens later via
    Labels page.

    Automatically creates/updates a Link Definition so the import can be rerun later.

    Request body:
    {
        "source_label": "Person",
        "target_label": "File",
        "rel_type": "AUTHORED",
        "source_database": "Local Graph",
        "source_uid_property": "id",
        "target_uid_property": "uuid",
        "import_rel_properties": true,
        "batch_size": 100
    }

    Returns task_id for polling progress.
    """
    try:
        data = request.json
        service = _get_link_service()

        task_id = service.execute_discovered_import_with_task(
            source_label=data['source_label'],
            target_label=data['target_label'],
            rel_type=data['rel_type'],
            source_database=data['source_database'],
            source_uid_property=data['source_uid_property'],
            target_uid_property=data['target_uid_property'],
            import_rel_properties=data.get('import_rel_properties', True),
            batch_size=data.get('batch_size', 100)
        )

        return jsonify({
            'status': 'success',
            'task_id': task_id
        }), 200
    except Exception as e:
        logger.exception("Failed to start discovered import")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _serialize_neo4j_record(record):
    """
    Convert a Neo4j record to a JSON-serializable dict.

    Handles Node and Relationship objects by extracting their properties.
    """
    result = {}
    for key, value in record.items():
        if hasattr(value, '_properties'):
            # Neo4j Node or Relationship object
            result[key] = dict(value._properties)
            if hasattr(value, 'type'):
                # Relationship
                result[key]['_type'] = value.type
            elif hasattr(value, 'labels'):
                # Node
                result[key]['_labels'] = list(value.labels)
        elif hasattr(value, 'items'):
            # Dict-like object
            result[key] = dict(value)
        else:
            # Scalar value
            result[key] = value
    return result


@bp.route('/neo4j/query', methods=['POST'])
def execute_neo4j_query():
    """
    Execute a Cypher query against a Neo4j database.

    Request body:
    {
        "database": "PRIMARY" or "profile_name",
        "query": "MATCH (n) RETURN n LIMIT 10"
    }

    Returns query results with Neo4j objects serialized to dicts.
    """
    try:
        from ...services.neo4j_client import get_neo4j_client, get_neo4j_client_for_profile

        data = request.json
        database = data.get('database', 'PRIMARY')
        query = data.get('query')

        if not query:
            return jsonify({'status': 'error', 'error': 'Query is required'}), 400

        # Get appropriate client
        if database == 'PRIMARY':
            client = get_neo4j_client()
        else:
            client = get_neo4j_client_for_profile(database)

        if not client:
            return jsonify({'status': 'error', 'error': f'Database {database} not found'}), 404

        try:
            results = client.execute_read(query)

            # Serialize Neo4j objects to JSON-serializable dicts
            serialized_results = [_serialize_neo4j_record(record) for record in results]

            return jsonify({
                'status': 'success',
                'records': serialized_results
            }), 200
        finally:
            if database != 'PRIMARY':
                client.close()

    except Exception as e:
        logger.exception("Failed to execute Neo4j query")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/neo4j/label-properties', methods=['POST'])
def get_label_properties():
    """
    Get properties for a label in a Neo4j database.

    Request body:
    {
        "database": "PRIMARY" or "profile_name",
        "label": "Person"
    }

    Returns list of property names.
    """
    try:
        from ...services.neo4j_client import get_neo4j_client, get_neo4j_client_for_profile

        data = request.json
        database = data.get('database', 'PRIMARY')
        label = data.get('label')

        if not label:
            return jsonify({'status': 'error', 'error': 'Label is required'}), 400

        # Get appropriate client
        if database == 'PRIMARY':
            client = get_neo4j_client()
        else:
            client = get_neo4j_client_for_profile(database)

        if not client:
            return jsonify({'status': 'error', 'error': f'Database {database} not found'}), 404

        try:
            # Query for all property keys on this label
            query = f"""
            MATCH (n:{label})
            UNWIND keys(n) as prop
            RETURN DISTINCT prop
            ORDER BY prop
            """

            results = client.execute_read(query)
            properties = [r['prop'] for r in results if 'prop' in r]

            return jsonify({
                'status': 'success',
                'properties': properties
            }), 200
        finally:
            if database != 'PRIMARY':
                client.close()

    except Exception as e:
        logger.exception("Failed to get label properties")
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


@bp.route('/links/<link_id>/sync-status', methods=['GET'])
def get_link_sync_status(link_id):
    """
    Get sync status for an Active import link.

    Returns sync metadata including:
    - Whether sync is supported (import vs algorithmic link)
    - Last sync count and timestamp
    - Current source count
    - Number of new relationships since last sync

    Returns:
    {
        "status": "success",
        "sync_supported": true,
        "primary_count": 526288,
        "last_synced_at": "2026-02-28T15:30:00",
        "current_source_count": 526291,
        "new_since_sync": 3,
        "source_database": "NExtSEEK-Dev"
    }

    Or if sync not supported (algorithmic/script link):
    {
        "status": "success",
        "sync_supported": false
    }
    """
    try:
        from ...services.neo4j_client import get_neo4j_client_for_profile, get_neo4j_client
        from datetime import datetime

        service = _get_link_service()
        link = service.get_link_definition(link_id)

        if not link:
            return jsonify({
                'status': 'error',
                'error': f'Link "{link_id}" not found'
            }), 404

        # Check if this is an import link (has source_database in match_config)
        match_config = json.loads(link.get('match_config', '{}')) if isinstance(link.get('match_config'), str) else link.get('match_config', {})
        source_database = match_config.get('source_database')

        if not source_database:
            # Not an import link - sync not supported
            return jsonify({
                'status': 'success',
                'sync_supported': False
            }), 200

        # This is an import link - get sync status
        last_synced_at = link.get('last_synced_at')

        # Query source database for current count
        source_label = link.get('source_label')
        target_label = link.get('target_label')
        rel_type = link.get('relationship_type')

        try:
            # Query source database for current count
            source_client = get_neo4j_client_for_profile(source_database)
            if not source_client:
                return jsonify({
                    'status': 'error',
                    'error': f'Source database "{source_database}" not found'
                }), 404

            source_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
            RETURN count(r) as current_count
            """
            source_results = source_client.execute_read(source_query)
            current_source_count = source_results[0]['current_count'] if source_results else 0

            source_client.close()

            # Query primary database for actual count
            primary_client = get_neo4j_client()
            primary_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
            RETURN count(r) as primary_count
            """
            primary_results = primary_client.execute_read(primary_query)
            primary_count = primary_results[0]['primary_count'] if primary_results else 0

        except Exception as e:
            logger.exception(f"Failed to query databases")
            return jsonify({
                'status': 'error',
                'error': f'Failed to query databases: {str(e)}'
            }), 500

        # Calculate new relationships since last sync
        new_since_sync = max(0, current_source_count - primary_count)

        # Format last_synced_at as ISO string
        last_synced_at_str = None
        if last_synced_at:
            try:
                dt = datetime.fromtimestamp(last_synced_at)
                last_synced_at_str = dt.isoformat()
            except Exception:
                last_synced_at_str = None

        return jsonify({
            'status': 'success',
            'sync_supported': True,
            'primary_count': primary_count,
            'last_synced_at': last_synced_at_str,
            'current_source_count': current_source_count,
            'new_since_sync': new_since_sync,
            'source_database': source_database
        }), 200

    except Exception as e:
        logger.exception("Failed to get link sync status")
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


@bp.route('/links/<link_id>/index', methods=['GET'])
def get_relationship_index(link_id):
    """
    Get paginated index of relationships for a link definition.

    Query params:
    - page: Page number (default 1)
    - page_size: Number of results per page (default 50)

    For links with link_def_id, reads from match_config.
    For discovered relationships (no link_def_id), accepts:
    - source_label
    - rel_type
    - target_label
    - source_database

    Returns:
    {
        "status": "success",
        "total": 526291,
        "page": 1,
        "page_size": 50,
        "rows": [
            {
                "source_uid": "D.IMG-001",
                "rel_props": {"weight": 0.8},
                "target_uid": "19-194_liver"
            }
        ]
    }
    """
    try:
        from ...services.neo4j_client import get_neo4j_client, get_neo4j_client_for_profile

        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 50))
        skip = (page - 1) * page_size

        service = _get_link_service()
        link = service.get_link_definition(link_id)

        # Determine if this is a discovered relationship or a defined link
        if link:
            # Get config from link definition
            match_config = json.loads(link.get('match_config', '{}')) if isinstance(link.get('match_config'), str) else link.get('match_config', {})

            # Try match_config first, fall back to top-level fields
            # This handles wizard-defined links auto-promoted from primary scan (no match_config)
            source_label = match_config.get('source_label') or link.get('source_label')
            target_label = match_config.get('target_label') or link.get('target_label')
            rel_type = match_config.get('rel_type') or link.get('relationship_type')
            # Fall back to elementId when UID properties are not configured
            source_uid_property = match_config.get('source_uid_property') or 'elementId'
            target_uid_property = match_config.get('target_uid_property') or 'elementId'
            # For Active links with no source_database, query primary
            source_database = match_config.get('source_database')  # None for native links

            # For Active links with no source_database, query primary directly
            # (relationships are already there from wizard-defined links)
            # For Pending/Available, query source database
            if link.get('status') == 'active' and not source_database:
                database = 'PRIMARY'
            else:
                database = source_database or 'PRIMARY'
        else:
            # Discovered relationship - get params from query string
            source_label = request.args.get('source_label')
            target_label = request.args.get('target_label')
            rel_type = request.args.get('rel_type')
            source_database = request.args.get('source_database')
            source_uid_property = request.args.get('source_uid_property') or 'elementId'
            target_uid_property = request.args.get('target_uid_property') or 'elementId'
            database = source_database or 'PRIMARY'

        if not all([source_label, target_label, rel_type]):
            return jsonify({
                'status': 'error',
                'error': 'Missing required parameters: source_label, target_label, rel_type'
            }), 400

        # Get appropriate Neo4j client
        if database == 'PRIMARY':
            client = get_neo4j_client()
            close_client = False
        else:
            client = get_neo4j_client_for_profile(database)
            close_client = True
            if not client:
                return jsonify({
                    'status': 'error',
                    'error': f'Database "{database}" not found'
                }), 404

        try:
            # Count query
            count_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
            RETURN count(r) as total
            """
            count_results = client.execute_read(count_query)
            total = count_results[0]['total'] if count_results else 0

            # Build property access with fallback to elementId
            if source_uid_property == 'elementId':
                source_return = 'elementId(a) as source_uid'
            else:
                source_return = f'a.{source_uid_property} as source_uid'

            if target_uid_property == 'elementId':
                target_return = 'elementId(b) as target_uid'
            else:
                target_return = f'b.{target_uid_property} as target_uid'

            # Data query with pagination
            data_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
            RETURN {source_return},
                   properties(r) as rel_props,
                   {target_return}
            ORDER BY source_uid, target_uid
            SKIP {skip} LIMIT {page_size}
            """
            data_results = client.execute_read(data_query)

            rows = []
            for record in data_results:
                rows.append({
                    'source_uid': record.get('source_uid'),
                    'rel_props': dict(record.get('rel_props', {})),
                    'target_uid': record.get('target_uid')
                })

            return jsonify({
                'status': 'success',
                'total': total,
                'page': page,
                'page_size': page_size,
                'rows': rows
            }), 200

        finally:
            if close_client:
                client.close()

    except Exception as e:
        logger.exception("Failed to get relationship index")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
