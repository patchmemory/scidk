"""
API routes for Link execution (LinkRegistry pattern).

This is the new Links API that works with LinkRegistry and link scripts
in scripts/links/. It is separate from the deprecated api_links.py which
handles the old wizard-based link_definitions system.

Endpoints:
- GET /api/v2/links - List all registered links
- POST /api/v2/links/<id>/run - Execute a link
- POST /api/v2/links/reload - Reload registry from disk
"""

from flask import Blueprint, jsonify, request, current_app
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('links_v2', __name__, url_prefix='/api/v2')


def _get_link_service():
    """Get or create LinkExecutionService instance."""
    from ...services.link_service_v2 import get_link_service
    return get_link_service(current_app)


@bp.route('/links', methods=['GET'])
def list_links():
    """
    Get all registered links from both LinkRegistry (scripts) and link_definitions (wizard).

    Returns unified list with source field to distinguish them.

    Returns:
    {
        "status": "success",
        "links": [
            {
                "id": "sample_to_imagingdataset",
                "name": "Sample → ImagingDataset by path matching",
                "format": "cypher",
                "source": "script",
                "from_label": "Sample",
                "to_label": "ImagingDataset",
                "relationship_type": "SUBJECT_OF",
                "matching_strategy": "exact",
                "description": "...",
                "created_at": 1234567890.123,
                "updated_at": 1234567890.123
            }
        ],
        "count": 1
    }
    """
    try:
        service = _get_link_service()

        # Get script-based links from LinkRegistry
        script_links = service.list_links()

        # Get wizard links from database
        wizard_links = _get_wizard_links()

        # Merge and mark source
        all_links = []

        for link in script_links:
            link['source'] = 'script'
            all_links.append(link)

        for link in wizard_links:
            link['source'] = 'wizard'
            all_links.append(link)

        # Sort by updated_at desc
        all_links.sort(key=lambda x: x.get('updated_at', 0), reverse=True)

        return jsonify({
            'status': 'success',
            'links': all_links,
            'count': len(all_links)
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
    Get a specific link by ID.

    Returns:
    {
        "status": "success",
        "link": {...}
    }
    """
    try:
        from ...schema.link_registry import LinkRegistry

        LinkRegistry._ensure_loaded()
        link_def = LinkRegistry.get(link_id)

        if not link_def:
            return jsonify({
                'status': 'error',
                'error': f'Link "{link_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'link': {
                'id': link_def.id,
                'name': link_def.name,
                'format': link_def.format,
                'from_label': link_def.from_label,
                'to_label': link_def.to_label,
                'relationship_type': link_def.relationship_type,
                'matching_strategy': link_def.matching_strategy,
                'description': link_def.description,
                'created_at': link_def.created_at,
                'updated_at': link_def.updated_at,
                'source_path': link_def.source_path
            }
        }), 200

    except Exception as e:
        logger.exception(f"Failed to get link {link_id}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/links/<link_id>/run', methods=['POST'])
def run_link(link_id):
    """
    Execute a link script against Neo4j.

    Request body (optional):
    {
        "params": {
            "threshold": 0.85,
            "limit": 100
        }
    }

    Returns:
    {
        "status": "success",
        "relationships_created": 42,
        "execution_time_ms": 1234,
        "details": {
            "link_id": "sample_to_imagingdataset",
            "format": "cypher",
            "from_label": "Sample",
            "to_label": "ImagingDataset",
            "relationship_type": "SUBJECT_OF",
            ...
        }
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        params = data.get('params', {})

        service = _get_link_service()
        result = service.run_link(link_id, params)

        status_code = 200 if result['status'] == 'success' else 500
        return jsonify(result), status_code

    except Exception as e:
        logger.exception(f"Failed to run link {link_id}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'relationships_created': 0
        }), 500


@bp.route('/links/reload', methods=['POST'])
def reload_links():
    """
    Reload LinkRegistry from disk.

    Scans scripts/links/ directory and reloads all link definitions.

    Returns:
    {
        "status": "success",
        "links_loaded": 3
    }
    """
    try:
        service = _get_link_service()
        result = service.reload_registry()

        status_code = 200 if result['status'] == 'success' else 500
        return jsonify(result), status_code

    except Exception as e:
        logger.exception("Failed to reload links")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _get_wizard_links():
    """
    Get wizard links from link_definitions table and normalize format.

    Returns:
        List of wizard link dicts with same structure as script links
    """
    from ...core import path_index_sqlite as pix

    conn = pix.connect()
    try:
        cur = conn.cursor()

        # Check if table exists first
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_definitions'"
        )
        if not cur.fetchone():
            # Table doesn't exist yet (migrations not run)
            return []

        cur.execute(
            """
            SELECT id, name, source_label, target_label,
                   relationship_type, match_strategy, created_at, updated_at
            FROM link_definitions
            ORDER BY updated_at DESC
            """
        )
        rows = cur.fetchall()

        links = []
        for row in rows:
            (id, name, source_label, target_label, rel_type,
             match_strategy, created_at, updated_at) = row

            links.append({
                'id': id,
                'name': name,
                'format': 'wizard',  # Distinguish wizard links
                'from_label': source_label or '',
                'to_label': target_label or '',
                'relationship_type': rel_type or '',
                'matching_strategy': match_strategy or '',
                'description': '',  # Wizards don't have descriptions
                'created_at': created_at or 0,
                'updated_at': updated_at or 0
            })

        return links

    except Exception as e:
        logger.warning(f"Failed to load wizard links: {e}")
        return []
    finally:
        conn.close()
