"""API routes for Scripts page - script management and execution."""

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request, send_file

from scidk.core.scripts import (
    ScriptsManager,
    Script,
    export_to_csv,
    export_to_json,
    export_to_jupyter,
    import_from_jupyter
)
from scidk.core.builtin_scripts import get_builtin_scripts
from scidk.web.decorators import require_admin

logger = logging.getLogger(__name__)

bp = Blueprint("scripts_api", __name__, url_prefix="/api/scripts")


def _get_scripts_manager():
    """Get ScriptsManager instance."""
    return ScriptsManager()


def _get_neo4j_driver():
    """Get Neo4j driver using same connection params as Chat and Maps.

    Uses get_neo4j_params() to check Settings UI first, then environment variables.
    Returns driver only (for backward compatibility).
    """
    driver, _database = _get_neo4j_driver_and_database()
    return driver


def _get_neo4j_driver_and_database():
    """Get Neo4j driver and database name.

    Uses get_neo4j_params() to check Settings UI first, then environment variables.
    Returns tuple of (driver, database).
    """
    try:
        from scidk.services.neo4j_client import get_neo4j_params
        from neo4j import GraphDatabase

        uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)

        if not uri:
            return None, None

        # Create auth based on auth mode
        auth = None if auth_mode == 'none' else (user, pwd)

        # Create and return driver
        driver = GraphDatabase.driver(uri, auth=auth)
        return driver, database

    except Exception as e:
        logger.warning(f"Failed to create Neo4j driver: {e}")
        return None, None


def _get_neo4j_config():
    """Get Neo4j connection configuration."""
    try:
        return {
            'uri': os.environ.get('NEO4J_URI', 'bolt://localhost:7687'),
            'user': os.environ.get('NEO4J_USER', 'neo4j'),
            'password': os.environ.get('NEO4J_PASSWORD', 'password')
        }
    except Exception:
        return {}


def _get_current_user():
    """Get current username from session/auth."""
    # TODO: Integrate with auth system
    return 'system'


# Script CRUD endpoints

@bp.route("/scripts", methods=["GET"])
def list_scripts():
    """List all scripts with optional filters.

    Query Parameters:
        category (str): Filter by category (builtin, custom)
        language (str): Filter by language (cypher, python)

    Returns:
        JSON response with list of scripts
    """
    try:
        category = request.args.get("category")
        language = request.args.get("language")

        manager = _get_scripts_manager()

        # Add built-in scripts if not already in database
        if not category or category == 'builtin':
            _ensure_builtin_scripts(manager)

        scripts = manager.list_scripts(category=category, language=language)

        return jsonify({
            "status": "ok",
            "scripts": [s.to_dict() for s in scripts],
            "count": len(scripts)
        })
    except Exception as e:
        logger.exception("Error listing scripts")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/active", methods=["GET"])
def list_active_scripts():
    """List only validated + active scripts for Settings panels.

    Query Parameters:
        category (str): Filter by category (interpreters, links, plugins, api)

    Returns:
        JSON response with list of active scripts
    """
    try:
        category = request.args.get("category")

        manager = _get_scripts_manager()
        all_scripts = manager.list_scripts(category=category)

        # Filter for validated + active scripts only
        active_scripts = [
            s for s in all_scripts
            if s.validation_status == 'validated' and s.is_active
        ]

        return jsonify({
            "status": "ok",
            "scripts": [s.to_dict() for s in active_scripts],
            "count": len(active_scripts)
        })
    except Exception as e:
        logger.exception("Error listing active scripts")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/plugins/available", methods=["GET"])
def list_available_plugins():
    """List all available (validated + active) plugins for plugin palette.

    Returns lightweight metadata for plugins that can be loaded by other scripts.
    Used by the plugin palette sidebar in Scripts page.

    Returns:
        JSON response with list of available plugins (metadata only, no code)
    """
    try:
        from scidk.core.script_plugin_loader import list_available_plugins

        manager = _get_scripts_manager()
        plugins = list_available_plugins(manager)

        return jsonify({
            "status": "ok",
            "plugins": plugins,
            "count": len(plugins)
        })
    except Exception as e:
        logger.exception("Error listing available plugins")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>", methods=["GET"])
def get_script(script_id: str):
    """Get a single script by ID.

    Returns:
        JSON response with script details
    """
    try:
        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        return jsonify({
            "status": "ok",
            "script": script.to_dict()
        })
    except Exception as e:
        logger.exception(f"Error getting script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts", methods=["POST"])
@require_admin
def create_script():
    """Create a new custom script.

    Request Body:
        name (str): Script name
        description (str): Description
        language (str): cypher or python
        code (str): Script code
        parameters (list): Optional parameter definitions
        tags (list): Optional tags

    Returns:
        JSON response with created script
    """
    try:
        data = request.get_json()

        script_id = str(uuid.uuid4())
        script = Script(
            id=script_id,
            name=data['name'],
            description=data.get('description', ''),
            language=data['language'],
            category='custom',
            code=data['code'],
            parameters=data.get('parameters', []),
            tags=data.get('tags', []),
            created_by=_get_current_user()
        )

        manager = _get_scripts_manager()
        created_script = manager.create_script(script)

        return jsonify({
            "status": "ok",
            "script": created_script.to_dict()
        }), 201
    except KeyError as e:
        return jsonify({"status": "error", "message": f"Missing required field: {e}"}), 400
    except Exception as e:
        logger.exception("Error creating script")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>", methods=["PUT"])
@require_admin
def update_script(script_id: str):
    """Update an existing custom script.

    Request Body:
        name (str): Script name
        description (str): Description
        code (str): Script code
        parameters (list): Parameter definitions
        tags (list): Tags

    Returns:
        JSON response with updated script
    """
    try:
        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        data = request.get_json()

        # Check if code is being changed
        code_changed = 'code' in data and data['code'] != script.code

        # Update fields
        script.name = data.get('name', script.name)
        script.description = data.get('description', script.description)
        script.code = data.get('code', script.code)
        script.parameters = data.get('parameters', script.parameters)
        script.tags = data.get('tags', script.tags)

        # If code changed, mark as edited (resets validation and clears dependencies)
        if code_changed:
            script.mark_as_edited()
            manager.clear_dependencies(script.id)

            # If this is a built-in script, mark it as modified
            if script.source == 'built-in':
                script.modified = True
                script.validation_status = 'queued'  # Queue for revalidation

        updated_script = manager.update_script(script)

        return jsonify({
            "status": "ok",
            "script": updated_script.to_dict()
        })
    except Exception as e:
        logger.exception(f"Error updating script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>", methods=["DELETE"])
@require_admin
def delete_script(script_id: str):
    """Delete a custom script.

    Returns:
        JSON response confirming deletion
    """
    try:
        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        if script.category == 'builtin':
            return jsonify({"status": "error", "message": "Cannot delete built-in scripts"}), 403

        manager.delete_script(script_id)

        return jsonify({
            "status": "ok",
            "message": "Script deleted"
        })
    except Exception as e:
        logger.exception(f"Error deleting script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Script execution

@bp.route("/scripts/<script_id>/run", methods=["POST"])
def run_script(script_id: str):
    """Execute a script.

    Request Body:
        parameters (dict): Optional parameters for the script

    Returns:
        JSON response with execution result
    """
    try:
        data = request.get_json() or {}
        parameters = data.get('parameters', {})

        manager = _get_scripts_manager()
        neo4j_driver, neo4j_database = _get_neo4j_driver_and_database()

        result = manager.execute_script(
            script_id=script_id,
            parameters=parameters,
            neo4j_driver=neo4j_driver,
            neo4j_database=neo4j_database,
            executed_by=_get_current_user()
        )

        return jsonify({
            "status": "ok",
            "result": result.to_dict()
        })
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        logger.exception(f"Error executing script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>/validate", methods=["POST"])
def validate_script(script_id: str):
    """Validate a script against its category contract.

    Runs contract tests in sandbox to ensure script meets requirements
    for its category (interpreter, link, plugin, etc.).

    Returns:
        JSON response with validation result including:
        - passed: bool
        - errors: list of error messages
        - test_results: dict of test name -> pass/fail
        - warnings: list of warnings
    """
    try:
        from scidk.core.script_testing import ScriptTestRunner
        from scidk.core.script_validators import get_validator_for_category, extract_plugin_dependencies

        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        # Get appropriate validator for category
        validator = get_validator_for_category(script.category)

        # Run validation tests in sandbox
        runner = ScriptTestRunner(timeout=10)
        result = runner.run_tests(script, validator)

        # Update script with validation results
        script.validation_status = 'validated' if result.passed else 'failed'
        script.validation_errors = result.errors
        import time
        script.validation_timestamp = time.time()

        # Save updated script
        manager.update_script(script)

        # Track dependencies if validation passed
        if result.passed and script.language == 'python':
            dependencies = extract_plugin_dependencies(script.code)
            manager.write_dependencies(
                script.id,
                script.category,  # 'interpreter', 'link', 'plugin'
                dependencies
            )
        else:
            # Clear dependencies if validation failed or not Python
            manager.clear_dependencies(script.id)

        return jsonify({
            "status": "ok",
            "validation": result.to_dict(),
            "script": {
                "id": script.id,
                "validation_status": script.validation_status,
                "validation_timestamp": script.validation_timestamp
            }
        })

    except Exception as e:
        logger.exception(f"Error validating script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>/activate", methods=["POST"])
@require_admin
def activate_script(script_id: str):
    """Activate a validated script (admin only).

    Only validated scripts can be activated. Activated scripts appear in
    Settings dropdowns and are available for use.

    Security: Requires admin role because activated scripts have full
    system access (filesystem, database, etc.).

    Returns:
        JSON response with activation status
    """
    try:
        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        if script.validation_status != 'validated':
            return jsonify({
                "status": "error",
                "message": "Script must be validated before activation"
            }), 400

        script.is_active = True
        manager.update_script(script)

        return jsonify({
            "status": "ok",
            "message": "Script activated successfully",
            "script": script.to_dict()
        })

    except Exception as e:
        logger.exception(f"Error activating script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/scripts/<script_id>/deactivate", methods=["POST"])
@require_admin
def deactivate_script(script_id: str):
    """Deactivate an active script (admin only).

    Deactivated scripts are removed from Settings dropdowns but remain
    in the Scripts library.

    Returns:
        JSON response with deactivation status
    """
    try:
        manager = _get_scripts_manager()
        script = manager.get_script(script_id)

        if not script:
            return jsonify({"status": "error", "message": "Script not found"}), 404

        script.is_active = False
        manager.update_script(script)

        return jsonify({
            "status": "ok",
            "message": "Script deactivated successfully",
            "script": script.to_dict()
        })

    except Exception as e:
        logger.exception(f"Error deactivating script {script_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Results endpoints

@bp.route("/results", methods=["GET"])
def list_results():
    """List execution results with optional filters.

    Query Parameters:
        script_id (str): Filter by script
        limit (int): Max results (default: 50)

    Returns:
        JSON response with list of results
    """
    try:
        script_id = request.args.get("script_id")
        limit = int(request.args.get("limit", 50))

        manager = _get_scripts_manager()
        results = manager.list_results(script_id=script_id, limit=limit)

        return jsonify({
            "status": "ok",
            "results": [r.to_dict() for r in results],
            "count": len(results)
        })
    except Exception as e:
        logger.exception("Error listing results")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/results/<result_id>", methods=["GET"])
def get_result(result_id: str):
    """Get a single result by ID.

    Returns:
        JSON response with result details
    """
    try:
        manager = _get_scripts_manager()
        result = manager.get_result(result_id)

        if not result:
            return jsonify({"status": "error", "message": "Result not found"}), 404

        return jsonify({
            "status": "ok",
            "result": result.to_dict()
        })
    except Exception as e:
        logger.exception(f"Error getting result {result_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/results/<result_id>", methods=["DELETE"])
def delete_result(result_id: str):
    """Delete a result.

    Returns:
        JSON response confirming deletion
    """
    try:
        manager = _get_scripts_manager()

        if not manager.delete_result(result_id):
            return jsonify({"status": "error", "message": "Result not found"}), 404

        return jsonify({
            "status": "ok",
            "message": "Result deleted"
        })
    except Exception as e:
        logger.exception(f"Error deleting result {result_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Export endpoints

@bp.route("/results/<result_id>/export", methods=["GET"])
def export_result(result_id: str):
    """Export a result in various formats.

    Query Parameters:
        format (str): csv, json, or jupyter (default: csv)

    Returns:
        File download or JSON response
    """
    try:
        format_type = request.args.get("format", "csv").lower()

        manager = _get_scripts_manager()
        result = manager.get_result(result_id)

        if not result:
            return jsonify({"status": "error", "message": "Result not found"}), 404

        if format_type == "csv":
            csv_data = export_to_csv(result.results)

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
                f.write(csv_data)
                temp_path = f.name

            return send_file(
                temp_path,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'script_{result_id}.csv'
            )

        elif format_type == "json":
            json_data = export_to_json(result.results)

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                f.write(json_data)
                temp_path = f.name

            return send_file(
                temp_path,
                mimetype='application/json',
                as_attachment=True,
                download_name=f'script_{result_id}.json'
            )

        elif format_type == "jupyter":
            script = manager.get_script(result.script_id)
            if not script:
                return jsonify({"status": "error", "message": "Script not found"}), 404

            neo4j_config = _get_neo4j_config()
            notebook = export_to_jupyter(script, result, neo4j_config)

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ipynb') as f:
                json.dump(notebook, f, indent=2)
                temp_path = f.name

            return send_file(
                temp_path,
                mimetype='application/x-ipynb+json',
                as_attachment=True,
                download_name=f'{script.name.replace(" ", "_")}.ipynb'
            )

        else:
            return jsonify({"status": "error", "message": f"Unsupported format: {format_type}"}), 400

    except Exception as e:
        logger.exception(f"Error exporting result {result_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Import endpoint

@bp.route("/import-notebook", methods=["POST"])
def import_notebook():
    """Import scripts from a Jupyter notebook.

    Request: multipart/form-data with 'file' field

    Returns:
        JSON response with imported scripts
    """
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400

        file = request.files['file']

        if not file.filename.endswith('.ipynb'):
            return jsonify({"status": "error", "message": "File must be a .ipynb notebook"}), 400

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.ipynb') as f:
            file.save(f.name)
            temp_path = Path(f.name)

        # Import scripts
        scripts = import_from_jupyter(temp_path)

        # Save to database
        manager = _get_scripts_manager()
        saved_scripts = []
        for script in scripts:
            script.created_by = _get_current_user()
            saved_script = manager.create_script(script)
            saved_scripts.append(saved_script)

        # Cleanup
        temp_path.unlink()

        return jsonify({
            "status": "ok",
            "scripts": [s.to_dict() for s in saved_scripts],
            "count": len(saved_scripts)
        }), 201

    except Exception as e:
        logger.exception("Error importing notebook")
        return jsonify({"status": "error", "message": str(e)}), 500


# Helper functions

def _ensure_builtin_scripts(manager: ScriptsManager):
    """Ensure built-in scripts are in the database.

    Creates builtin scripts if they don't exist. Does not update existing builtins
    to avoid conflicts with database state.
    """
    try:
        all_scripts = manager.list_scripts()
        existing_ids = {s.id for s in all_scripts if s.id.startswith('builtin-')}

        for script in get_builtin_scripts():
            if script.id not in existing_ids:
                manager.create_script(script)
                logger.debug(f"Created builtin script: {script.id}")
    except Exception:
        # Don't fail if we can't add built-in scripts
        logger.warning("Failed to ensure built-in scripts", exc_info=True)
