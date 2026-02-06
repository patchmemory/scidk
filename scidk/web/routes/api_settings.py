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
