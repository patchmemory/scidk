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
        existing_config = auth.get_config()

        if enabled and not password and not existing_config.get('has_password'):
            return jsonify({
                'status': 'error',
                'error': 'Password is required when enabling authentication for the first time'
            }), 400

        # Update config
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
