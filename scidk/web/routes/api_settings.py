"""
Blueprint for Settings API routes.

Provides REST endpoints for:
- API endpoint registry CRUD
- Endpoint connection testing
- Settings persistence
"""
from flask import Blueprint, jsonify, request, current_app
import requests
from jsonpath_ng import parse as jsonpath_parse

bp = Blueprint('settings', __name__, url_prefix='/api')


def _get_endpoint_registry():
    """Get or create APIEndpointRegistry instance."""
    from ...core.api_endpoint_registry import APIEndpointRegistry, get_encryption_key

    if 'api_endpoint_registry' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        encryption_key = get_encryption_key()

        current_app.extensions['scidk']['api_endpoint_registry'] = APIEndpointRegistry(
            db_path=settings_db,
            encryption_key=encryption_key
        )

    return current_app.extensions['scidk']['api_endpoint_registry']


@bp.route('/settings/api-endpoints', methods=['GET'])
def list_api_endpoints():
    """
    Get all registered API endpoints.

    Returns:
    {
        "status": "success",
        "endpoints": [
            {
                "id": "uuid",
                "name": "Users API",
                "url": "https://api.example.com/users",
                "auth_method": "bearer",
                "json_path": "$.data[*]",
                "target_label": "User",
                "field_mappings": {"email": "email", "name": "fullName"},
                "created_at": 1234567890.123,
                "updated_at": 1234567890.123
            }
        ]
    }
    """
    try:
        registry = _get_endpoint_registry()
        endpoints = registry.list_endpoints()
        return jsonify({
            'status': 'success',
            'endpoints': endpoints
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/api-endpoints/<endpoint_id>', methods=['GET'])
def get_api_endpoint(endpoint_id):
    """
    Get a specific API endpoint by ID.

    Returns:
    {
        "status": "success",
        "endpoint": {...}
    }
    """
    try:
        registry = _get_endpoint_registry()
        endpoint = registry.get_endpoint(endpoint_id)

        if not endpoint:
            return jsonify({
                'status': 'error',
                'error': f'Endpoint "{endpoint_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'endpoint': endpoint
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/api-endpoints', methods=['POST'])
def create_api_endpoint():
    """
    Create a new API endpoint configuration.

    Request body:
    {
        "name": "Users API",
        "url": "https://api.example.com/users",
        "auth_method": "bearer",  // "none", "bearer", or "api_key"
        "auth_value": "token123",  // optional
        "json_path": "$.data[*]",  // optional
        "target_label": "User",  // optional
        "field_mappings": {  // optional
            "email": "email",
            "name": "fullName"
        }
    }

    Returns:
    {
        "status": "success",
        "endpoint": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        registry = _get_endpoint_registry()
        endpoint = registry.create_endpoint(data)

        return jsonify({
            'status': 'success',
            'endpoint': endpoint
        }), 201
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


@bp.route('/settings/api-endpoints/<endpoint_id>', methods=['PUT', 'PATCH'])
def update_api_endpoint(endpoint_id):
    """
    Update an existing API endpoint.

    Request body: Same as create, but all fields optional

    Returns:
    {
        "status": "success",
        "endpoint": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        registry = _get_endpoint_registry()
        endpoint = registry.update_endpoint(endpoint_id, data)

        return jsonify({
            'status': 'success',
            'endpoint': endpoint
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


@bp.route('/settings/api-endpoints/<endpoint_id>', methods=['DELETE'])
def delete_api_endpoint(endpoint_id):
    """
    Delete an API endpoint.

    Returns:
    {
        "status": "success"
    }
    """
    try:
        registry = _get_endpoint_registry()
        deleted = registry.delete_endpoint(endpoint_id)

        if not deleted:
            return jsonify({
                'status': 'error',
                'error': f'Endpoint "{endpoint_id}" not found'
            }), 404

        return jsonify({
            'status': 'success'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/api-endpoints/<endpoint_id>/test', methods=['POST'])
def test_api_endpoint(endpoint_id):
    """
    Test an API endpoint connection and return sample data.

    Returns:
    {
        "status": "success",
        "test_result": {
            "success": true,
            "status_code": 200,
            "sample_data": [...],  // First 5 records after JSONPath extraction
            "total_records": 100,  // Total records found
            "error": null
        }
    }
    """
    try:
        registry = _get_endpoint_registry()
        endpoint = registry.get_endpoint(endpoint_id)

        if not endpoint:
            return jsonify({
                'status': 'error',
                'error': f'Endpoint "{endpoint_id}" not found'
            }), 404

        # Get decrypted auth value
        auth_value = registry.get_decrypted_auth(endpoint_id)

        # Build request headers
        headers = {}
        if endpoint['auth_method'] == 'bearer' and auth_value:
            headers['Authorization'] = f'Bearer {auth_value}'
        elif endpoint['auth_method'] == 'api_key' and auth_value:
            headers['X-API-Key'] = auth_value

        # Make request
        try:
            response = requests.get(endpoint['url'], headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            return jsonify({
                'status': 'success',
                'test_result': {
                    'success': False,
                    'error': 'Request timed out after 10 seconds'
                }
            }), 200
        except requests.exceptions.RequestException as e:
            return jsonify({
                'status': 'success',
                'test_result': {
                    'success': False,
                    'error': str(e)
                }
            }), 200

        # Parse JSON response
        try:
            data = response.json()
        except Exception:
            return jsonify({
                'status': 'success',
                'test_result': {
                    'success': False,
                    'error': 'Response is not valid JSON'
                }
            }), 200

        # Apply JSONPath if specified
        records = data
        if endpoint.get('json_path'):
            try:
                jsonpath_expr = jsonpath_parse(endpoint['json_path'])
                matches = [match.value for match in jsonpath_expr.find(data)]
                records = matches
            except Exception as e:
                return jsonify({
                    'status': 'success',
                    'test_result': {
                        'success': False,
                        'error': f'JSONPath error: {str(e)}'
                    }
                }), 200

        # Ensure records is a list
        if not isinstance(records, list):
            records = [records]

        # Return sample
        return jsonify({
            'status': 'success',
            'test_result': {
                'success': True,
                'status_code': response.status_code,
                'sample_data': records[:5],  # First 5 records
                'total_records': len(records),
                'error': None
            }
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _get_table_format_registry():
    """Get or create TableFormatRegistry instance."""
    from ...core.table_format_registry import TableFormatRegistry

    if 'table_format_registry' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')

        current_app.extensions['scidk']['table_format_registry'] = TableFormatRegistry(
            db_path=settings_db
        )

    return current_app.extensions['scidk']['table_format_registry']


@bp.route('/settings/table-formats', methods=['GET'])
def list_table_formats():
    """
    Get all registered table format configurations.

    Query params:
        - include_preprogrammed: Include pre-programmed formats (default: true)

    Returns:
    {
        "status": "success",
        "formats": [...]
    }
    """
    try:
        include_preprogrammed = request.args.get('include_preprogrammed', 'true').lower() == 'true'
        registry = _get_table_format_registry()
        formats = registry.list_formats(include_preprogrammed=include_preprogrammed)
        return jsonify({
            'status': 'success',
            'formats': formats
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/table-formats/<format_id>', methods=['GET'])
def get_table_format(format_id):
    """Get a specific table format by ID."""
    try:
        registry = _get_table_format_registry()
        format_config = registry.get_format(format_id)

        if not format_config:
            return jsonify({
                'status': 'error',
                'error': f'Format "{format_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'format': format_config
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/table-formats', methods=['POST'])
def create_table_format():
    """Create a new table format configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        registry = _get_table_format_registry()
        format_config = registry.create_format(data)

        return jsonify({
            'status': 'success',
            'format': format_config
        }), 201
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


@bp.route('/settings/table-formats/<format_id>', methods=['PUT', 'PATCH'])
def update_table_format(format_id):
    """Update an existing table format."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        registry = _get_table_format_registry()
        format_config = registry.update_format(format_id, data)

        return jsonify({
            'status': 'success',
            'format': format_config
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


@bp.route('/settings/table-formats/<format_id>', methods=['DELETE'])
def delete_table_format(format_id):
    """Delete a table format."""
    try:
        registry = _get_table_format_registry()
        deleted = registry.delete_format(format_id)

        if not deleted:
            return jsonify({
                'status': 'error',
                'error': f'Format "{format_id}" not found'
            }), 404

        return jsonify({
            'status': 'success'
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


@bp.route('/settings/table-formats/detect', methods=['POST'])
def detect_table_format():
    """Auto-detect table format from uploaded file."""
    try:
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'error': 'No file provided'
            }), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({
                'status': 'error',
                'error': 'Invalid file'
            }), 400

        file_content = file.read()
        registry = _get_table_format_registry()
        detected = registry.detect_format(file_content, filename=file.filename)

        if 'error' in detected:
            return jsonify({
                'status': 'error',
                'error': detected['error']
            }), 400

        return jsonify({
            'status': 'success',
            'detected': detected
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/table-formats/<format_id>/preview', methods=['POST'])
def preview_table_data(format_id):
    """Preview table data using a format configuration."""
    try:
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'error': 'No file provided'
            }), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({
                'status': 'error',
                'error': 'Invalid file'
            }), 400

        file_content = file.read()
        num_rows = int(request.args.get('num_rows', 5))

        registry = _get_table_format_registry()
        preview = registry.preview_data(file_content, format_id, num_rows=num_rows)

        if 'error' in preview:
            return jsonify({
                'status': 'error',
                'error': preview['error']
            }), 400

        return jsonify({
            'status': 'success',
            'preview': preview
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _get_fuzzy_matching_service():
    """Get or create FuzzyMatchingService instance."""
    from ...core.fuzzy_matching import FuzzyMatchingService

    if 'fuzzy_matching_service' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')

        current_app.extensions['scidk']['fuzzy_matching_service'] = FuzzyMatchingService(
            db_path=settings_db
        )

    return current_app.extensions['scidk']['fuzzy_matching_service']


@bp.route('/settings/fuzzy-matching', methods=['GET'])
def get_fuzzy_matching_settings():
    """
    Get global fuzzy matching settings.

    Returns:
    {
        "status": "success",
        "settings": {
            "algorithm": "levenshtein",
            "threshold": 0.80,
            "case_sensitive": false,
            ...
        }
    }
    """
    try:
        service = _get_fuzzy_matching_service()
        settings = service.get_global_settings()

        return jsonify({
            'status': 'success',
            'settings': settings.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/fuzzy-matching', methods=['POST', 'PUT'])
def update_fuzzy_matching_settings():
    """
    Update global fuzzy matching settings.

    Request body:
    {
        "algorithm": "levenshtein",
        "threshold": 0.75,
        "case_sensitive": false,
        "normalize_whitespace": true,
        "strip_punctuation": true,
        "phonetic_enabled": false,
        "phonetic_algorithm": "metaphone",
        "min_string_length": 3,
        "max_comparisons": 10000,
        "show_confidence_scores": true
    }

    Returns:
    {
        "status": "success",
        "settings": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        service = _get_fuzzy_matching_service()
        settings = service.update_global_settings(data)

        return jsonify({
            'status': 'success',
            'settings': settings.to_dict()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/fuzzy-matching/preview', methods=['POST'])
def preview_fuzzy_matching():
    """
    Preview fuzzy matching results for external data.

    Request body:
    {
        "external_records": [
            {"name": "Jon Smith", "email": "jon@example.com"},
            ...
        ],
        "existing_nodes": [
            {"name": "John Smith", "email": "john@example.com"},
            ...
        ],
        "match_key": "name",
        "settings": {  // Optional override
            "algorithm": "levenshtein",
            "threshold": 0.75
        }
    }

    Returns:
    {
        "status": "success",
        "matches": [
            {
                "external_record": {...},
                "matched_node": {...} or null,
                "confidence": 0.85,
                "is_match": true
            }
        ]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        external_records = data.get('external_records', [])
        existing_nodes = data.get('existing_nodes', [])
        match_key = data.get('match_key')

        if not match_key:
            return jsonify({
                'status': 'error',
                'error': 'match_key is required'
            }), 400

        service = _get_fuzzy_matching_service()

        # Parse settings override if provided
        settings = None
        if 'settings' in data and data['settings']:
            from ...core.fuzzy_matching import FuzzyMatchSettings
            settings = FuzzyMatchSettings.from_dict(data['settings'])

        matches = service.match_external_data(
            external_records,
            existing_nodes,
            match_key,
            settings
        )

        return jsonify({
            'status': 'success',
            'matches': matches,
            'total_external': len(external_records),
            'total_matched': sum(1 for m in matches if m['is_match'])
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _get_auth_manager():
    """Get or create AuthManager instance."""
    from ...core.auth import get_auth_manager

    if 'auth_manager' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        current_app.extensions['scidk']['auth_manager'] = get_auth_manager(db_path=settings_db)

    return current_app.extensions['scidk']['auth_manager']


@bp.route('/settings/security/auth', methods=['GET'])
def get_security_auth_config():
    """
    Get current authentication configuration.

    Returns:
    {
        "status": "success",
        "config": {
            "enabled": true,
            "username": "admin",
            "has_password": true
        }
    }
    """
    try:
        auth = _get_auth_manager()
        config = auth.get_config()

        return jsonify({
            'status': 'success',
            'config': config
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/security/auth', methods=['POST', 'PUT'])
def update_security_auth_config():
    """
    Update authentication configuration.

    Request body:
    {
        "enabled": true,
        "username": "admin",
        "password": "password123"  // optional if keeping existing
    }

    Returns:
    {
        "status": "success",
        "config": {
            "enabled": true,
            "username": "admin",
            "has_password": true
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must be JSON'
            }), 400

        enabled = data.get('enabled', False)
        username = data.get('username')
        password = data.get('password')

        # Validation
        if enabled and not username:
            return jsonify({
                'status': 'error',
                'error': 'Username is required when enabling authentication'
            }), 400

        # Check if password is required
        auth = _get_auth_manager()
        existing_users = auth.list_users(include_disabled=True)
        existing_config = auth.get_config()

        # If there are no users yet, this is the first user - must be admin
        if enabled and len(existing_users) == 0:
            if not password:
                return jsonify({
                    'status': 'error',
                    'error': 'Password is required when enabling authentication for the first time'
                }), 400

            # Create first user as admin
            user_id = auth.create_user(username, password, role='admin', created_by='system')
            if not user_id:
                return jsonify({
                    'status': 'error',
                    'error': 'Failed to create admin user'
                }), 500

            # Log audit event
            auth.log_audit(username, 'first_user_created', 'First admin user created during auth setup', request.remote_addr)
        else:
            # Use legacy set_config for backward compatibility with existing setups
            if enabled and not password and not existing_config.get('has_password'):
                return jsonify({
                    'status': 'error',
                    'error': 'Password is required when enabling authentication for the first time'
                }), 400

            success = auth.set_config(enabled=enabled, username=username, password=password)
            if not success:
                return jsonify({
                    'status': 'error',
                    'error': 'Failed to update authentication configuration'
                }), 500

        # Return updated config
        config = auth.get_config()

        return jsonify({
            'status': 'success',
            'config': config
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


def _get_config_manager():
    """Get or create ConfigManager instance."""
    from ...core.config_manager import ConfigManager
    from ...core.api_endpoint_registry import get_encryption_key

    if 'config_manager' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        encryption_key = get_encryption_key()

        current_app.extensions['scidk']['config_manager'] = ConfigManager(
            db_path=settings_db,
            encryption_key=encryption_key
        )

    return current_app.extensions['scidk']['config_manager']


@bp.route('/settings/export', methods=['GET'])
def export_configuration():
    """
    Export complete configuration as JSON.

    Query params:
        - include_sensitive: Include passwords/API keys (default: false)
        - sections: Comma-separated list of sections to export (default: all)

    Returns:
    {
        "status": "success",
        "config": {...},
        "filename": "scidk-config-2026-02-08.json"
    }
    """
    try:
        include_sensitive = request.args.get('include_sensitive', 'false').lower() == 'true'
        sections_param = request.args.get('sections', '')
        sections = [s.strip() for s in sections_param.split(',') if s.strip()] if sections_param else None

        config_manager = _get_config_manager()
        config = config_manager.export_config(include_sensitive=include_sensitive, sections=sections)

        # Generate filename with timestamp
        from datetime import datetime
        filename = f"scidk-config-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.json"

        return jsonify({
            'status': 'success',
            'config': config,
            'filename': filename
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/import/preview', methods=['POST'])
def preview_import():
    """
    Preview changes that would be made by importing config.

    Request body:
    {
        "config": {...}  // Config data from export
    }

    Returns:
    {
        "status": "success",
        "diff": {
            "sections": {
                "neo4j": {
                    "changed": [{"key": "uri", "old_value": "...", "new_value": "..."}],
                    "added": [...],
                    "removed": [...]
                }
            }
        }
    }
    """
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must include "config" field'
            }), 400

        config_manager = _get_config_manager()
        diff = config_manager.preview_import_diff(data['config'])

        return jsonify({
            'status': 'success',
            'diff': diff
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/import', methods=['POST'])
def import_configuration():
    """
    Import configuration from uploaded JSON.

    Request body:
    {
        "config": {...},
        "create_backup": true,  // optional, default: true
        "sections": ["neo4j", "chat"],  // optional, default: all
        "created_by": "username"  // optional, default: "system"
    }

    Returns:
    {
        "status": "success",
        "report": {
            "success": true,
            "backup_id": "uuid",
            "sections_imported": ["neo4j", "chat"],
            "sections_failed": [],
            "errors": []
        }
    }
    """
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Request body must include "config" field'
            }), 400

        create_backup = data.get('create_backup', True)
        sections = data.get('sections')
        created_by = data.get('created_by', 'system')

        config_manager = _get_config_manager()
        report = config_manager.import_config(
            data['config'],
            create_backup=create_backup,
            sections=sections,
            created_by=created_by
        )

        status_code = 200 if report['success'] else 400

        return jsonify({
            'status': 'success' if report['success'] else 'error',
            'report': report
        }), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/backups', methods=['GET'])
def list_backups():
    """
    List configuration backups.

    Query params:
        - limit: Maximum number of backups to return (default: 50)

    Returns:
    {
        "status": "success",
        "backups": [
            {
                "id": "uuid",
                "timestamp": 1234567890.123,
                "timestamp_iso": "2026-02-08T10:30:00+00:00",
                "reason": "pre_import",
                "created_by": "admin",
                "notes": ""
            }
        ]
    }
    """
    try:
        limit = int(request.args.get('limit', 50))

        config_manager = _get_config_manager()
        backups = config_manager.list_backups(limit=limit)

        return jsonify({
            'status': 'success',
            'backups': backups
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/backups/<backup_id>', methods=['GET'])
def get_backup(backup_id):
    """
    Get a specific backup by ID.

    Returns:
    {
        "status": "success",
        "backup": {
            "id": "uuid",
            "timestamp": 1234567890.123,
            "timestamp_iso": "2026-02-08T10:30:00+00:00",
            "config": {...},
            "reason": "pre_import",
            "created_by": "admin",
            "notes": ""
        }
    }
    """
    try:
        config_manager = _get_config_manager()
        backup = config_manager.get_backup(backup_id)

        if not backup:
            return jsonify({
                'status': 'error',
                'error': f'Backup {backup_id} not found'
            }), 404

        return jsonify({
            'status': 'success',
            'backup': backup
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/backups', methods=['POST'])
def create_backup():
    """
    Create a manual backup of current configuration.

    Request body:
    {
        "reason": "manual",  // optional, default: "manual"
        "created_by": "username",  // optional, default: "system"
        "notes": "Before major changes"  // optional
    }

    Returns:
    {
        "status": "success",
        "backup_id": "uuid"
    }
    """
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'manual')
        created_by = data.get('created_by', 'system')
        notes = data.get('notes', '')

        config_manager = _get_config_manager()
        backup_id = config_manager.create_backup(
            reason=reason,
            created_by=created_by,
            notes=notes
        )

        return jsonify({
            'status': 'success',
            'backup_id': backup_id
        }), 201
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/backups/<backup_id>/restore', methods=['POST'])
def restore_backup(backup_id):
    """
    Restore configuration from a backup.

    Request body:
    {
        "created_by": "username"  // optional, default: "system"
    }

    Returns:
    {
        "status": "success",
        "report": {...}  // Same as import report
    }
    """
    try:
        data = request.get_json() or {}
        created_by = data.get('created_by', 'system')

        config_manager = _get_config_manager()
        report = config_manager.restore_backup(backup_id, created_by=created_by)

        status_code = 200 if report['success'] else 400

        return jsonify({
            'status': 'success' if report['success'] else 'error',
            'report': report
        }), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/backups/<backup_id>', methods=['DELETE'])
def delete_backup(backup_id):
    """
    Delete a backup.

    Returns:
    {
        "status": "success"
    }
    """
    try:
        config_manager = _get_config_manager()
        deleted = config_manager.delete_backup(backup_id)

        if not deleted:
            return jsonify({
                'status': 'error',
                'error': f'Backup {backup_id} not found'
            }), 404

        return jsonify({
            'status': 'success'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
