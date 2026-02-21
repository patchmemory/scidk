"""
API routes for system state queries - designed for Chat self-awareness.

These endpoints expose system state through callable interfaces that Chat
can use to answer questions about:
- Plugin dependencies
- Active interpreters
- Script status
- File interpreter assignments

All endpoints use authentication if enabled.
"""
import logging
from flask import Blueprint, jsonify, request, current_app
# Auth decorators available if needed: require_admin, require_role

logger = logging.getLogger(__name__)

bp = Blueprint('api_system', __name__, url_prefix='/api/system')


def _get_ext():
    """Get SciDK extensions from current Flask app."""
    return current_app.extensions['scidk']


@bp.get('/plugin-dependencies/<plugin_id>')
def get_plugin_dependencies(plugin_id):
    """Get scripts that depend on a plugin.

    Args:
        plugin_id: Plugin identifier

    Returns:
        JSON response with list of dependent scripts

    Example:
        GET /api/system/plugin-dependencies/genomics_normalizer
        {
            "plugin_id": "genomics_normalizer",
            "used_by": [
                {"id": "fastq_interpreter", "name": "FASTQ Interpreter", "type": "interpreter"},
                {"id": "variant_link", "name": "Variant Caller", "type": "link"}
            ],
            "count": 2
        }
    """
    try:
        from scidk.core.scripts import ScriptsManager

        manager = ScriptsManager()
        dependents = manager.get_dependents(plugin_id)

        # Enrich with script names
        enriched = []
        for dep in dependents:
            script = manager.get_script(dep['id'])
            enriched.append({
                'id': dep['id'],
                'name': script.name if script else dep['id'],
                'type': dep['type'],
                'category': script.category if script else 'unknown'
            })

        return jsonify({
            'plugin_id': plugin_id,
            'used_by': enriched,
            'count': len(enriched)
        })

    except Exception as e:
        logger.error(f"Error getting plugin dependencies: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500


@bp.get('/active-interpreters')
def get_active_interpreters():
    """Get list of validated and active interpreter scripts.

    Returns:
        JSON response with list of active interpreters

    Example:
        GET /api/system/active-interpreters
        {
            "interpreters": [
                {
                    "id": "fastq_interpreter",
                    "name": "FASTQ Interpreter",
                    "description": "Parses sequencing files...",
                    "validation_status": "validated",
                    "is_active": true
                }
            ],
            "count": 3
        }
    """
    try:
        from scidk.core.scripts import ScriptsManager

        manager = ScriptsManager()
        all_scripts = manager.list_scripts(category='interpreters')

        # Filter to validated and active only
        active = [
            {
                'id': s.id,
                'name': s.name,
                'description': s.description or s.docstring,
                'validation_status': s.validation_status,
                'is_active': s.is_active,
                'validation_timestamp': s.validation_timestamp
            }
            for s in all_scripts
            if s.validation_status == 'validated' and s.is_active
        ]

        return jsonify({
            'interpreters': active,
            'count': len(active)
        })

    except Exception as e:
        logger.error(f"Error getting active interpreters: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500


@bp.get('/script-status/<script_id>')
def get_script_status(script_id):
    """Get validation status, dependencies, and usage for a script.

    Args:
        script_id: Script identifier

    Returns:
        JSON response with script status details

    Example:
        GET /api/system/script-status/fastq_interpreter
        {
            "id": "fastq_interpreter",
            "name": "FASTQ Interpreter",
            "validation_status": "validated",
            "is_active": true,
            "dependencies": ["genomics_normalizer"],
            "used_by_count": 0
        }
    """
    try:
        from scidk.core.scripts import ScriptsManager

        manager = ScriptsManager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({
                'error': f'Script not found: {script_id}'
            }), 404

        # Get dependencies (plugins this script uses)
        dependencies = manager.get_dependencies(script_id)

        # Get dependent scripts (scripts that use this as a plugin)
        dependents = manager.get_dependents(script_id)

        return jsonify({
            'id': script.id,
            'name': script.name,
            'category': script.category,
            'validation_status': script.validation_status,
            'is_active': script.is_active,
            'validation_timestamp': script.validation_timestamp,
            'dependencies': dependencies,
            'used_by_count': len(dependents),
            'used_by': [{'id': d['id'], 'type': d['type']} for d in dependents]
        })

    except Exception as e:
        logger.error(f"Error getting script status: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500


@bp.get('/file-interpreter/<path:file_path>')
def get_file_interpreter(file_path):
    """Get which interpreter would handle a file based on extension/rules.

    Args:
        file_path: File path (passed as URL path parameter)

    Returns:
        JSON response with interpreter assignment

    Example:
        GET /api/system/file-interpreter//home/data/sample.fastq
        {
            "file_path": "/home/data/sample.fastq",
            "extension": ".fastq",
            "interpreter": {
                "id": "fastq_interpreter",
                "name": "FASTQ Interpreter",
                "assigned_by": "extension_rule"
            }
        }
    """
    try:
        from pathlib import Path

        # Get interpreter registry
        ext = _get_ext()
        registry = ext.get('registry')

        if not registry:
            return jsonify({
                'file_path': file_path,
                'interpreter': None,
                'reason': 'No interpreter registry available'
            })

        # Get file extension
        path = Path(file_path)
        extension = path.suffix.lower()

        # Look up interpreter by extension
        interpreters = registry.by_extension.get(extension, [])

        if not interpreters:
            return jsonify({
                'file_path': file_path,
                'extension': extension,
                'interpreter': None,
                'reason': 'No interpreter assigned for this extension'
            })

        # Return first active interpreter
        active_interpreters = [i for i in interpreters if getattr(i, 'is_active', True)]

        if not active_interpreters:
            return jsonify({
                'file_path': file_path,
                'extension': extension,
                'interpreter': None,
                'reason': 'Interpreters exist but none are active'
            })

        interpreter = active_interpreters[0]

        return jsonify({
            'file_path': file_path,
            'extension': extension,
            'interpreter': {
                'id': getattr(interpreter, 'id', 'unknown'),
                'name': getattr(interpreter, 'name', 'Unknown'),
                'assigned_by': 'extension_rule'
            }
        })

    except Exception as e:
        logger.error(f"Error getting file interpreter: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500
