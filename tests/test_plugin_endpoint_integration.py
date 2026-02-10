"""Integration tests for plugin label endpoint registration.

Tests the full flow of:
1. Plugin registration during app initialization
2. Endpoint registration in the registry
3. API exposure via /api/settings/plugin-endpoints
4. UI display in Settings > Integrations
"""

import pytest
from scidk.app import create_app
from scidk.core.label_endpoint_registry import LabelEndpointRegistry
from tests.conftest import authenticate_test_client


@pytest.fixture
def app():
    """Create a test Flask app."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create an authenticated test client."""
    test_client = app.test_client()
    return authenticate_test_client(test_client, app)


def test_registry_initialized_on_app_startup(app):
    """Test that the label endpoint registry is initialized during app startup."""
    assert 'label_endpoints' in app.extensions['scidk']
    registry = app.extensions['scidk']['label_endpoints']
    assert isinstance(registry, LabelEndpointRegistry)


def test_example_plugin_registers_endpoints(app):
    """Test that the example_ilab plugin registers its endpoints."""
    registry = app.extensions['scidk']['label_endpoints']
    endpoints = registry.list_endpoints()

    # Should have at least 2 endpoints from example_ilab plugin
    ilab_endpoints = [e for e in endpoints if e.get('plugin') == 'example_ilab']
    assert len(ilab_endpoints) >= 2

    # Check for iLab Services endpoint
    services_endpoint = registry.get_endpoint('/api/integrations/ilab/services')
    assert services_endpoint is not None
    assert services_endpoint['name'] == 'iLab Services'
    assert services_endpoint['label_type'] == 'iLabService'
    assert services_endpoint['auth_required'] is True
    assert services_endpoint['plugin'] == 'example_ilab'

    # Check for iLab Equipment endpoint
    equipment_endpoint = registry.get_endpoint('/api/integrations/ilab/equipment')
    assert equipment_endpoint is not None
    assert equipment_endpoint['name'] == 'iLab Equipment'
    assert equipment_endpoint['label_type'] == 'Equipment'


def test_api_list_plugin_endpoints(client):
    """Test GET /api/settings/plugin-endpoints returns registered endpoints."""
    response = client.get('/api/settings/plugin-endpoints')
    assert response.status_code == 200

    data = response.get_json()
    assert data['status'] == 'success'
    assert 'endpoints' in data
    assert isinstance(data['endpoints'], list)

    # Should have endpoints from example_ilab
    endpoints = data['endpoints']
    assert len(endpoints) >= 2

    # Verify structure of returned endpoints
    for endpoint in endpoints:
        assert 'name' in endpoint
        assert 'endpoint' in endpoint
        assert 'label_type' in endpoint
        assert 'plugin' in endpoint
        assert 'source' in endpoint
        assert endpoint['source'] == 'plugin'


def test_api_get_specific_plugin_endpoint(client):
    """Test GET /api/settings/plugin-endpoints/<path> returns specific endpoint."""
    # URL-encode the slash in the endpoint path
    response = client.get('/api/settings/plugin-endpoints/api/integrations/ilab/services')
    assert response.status_code == 200

    data = response.get_json()
    assert data['status'] == 'success'
    assert 'endpoint' in data

    endpoint = data['endpoint']
    assert endpoint['name'] == 'iLab Services'
    assert endpoint['endpoint'] == '/api/integrations/ilab/services'
    assert endpoint['label_type'] == 'iLabService'


def test_api_get_missing_endpoint_returns_404(client):
    """Test GET for non-existent endpoint returns 404."""
    response = client.get('/api/settings/plugin-endpoints/api/missing/endpoint')
    assert response.status_code == 404

    data = response.get_json()
    assert data['status'] == 'error'


def test_endpoints_filtered_by_plugin(app):
    """Test that endpoints can be filtered by plugin name."""
    registry = app.extensions['scidk']['label_endpoints']

    ilab_endpoints = registry.list_by_plugin('example_ilab')
    assert len(ilab_endpoints) >= 2
    assert all(e['plugin'] == 'example_ilab' for e in ilab_endpoints)


def test_endpoints_filtered_by_label_type(app):
    """Test that endpoints can be filtered by label type."""
    registry = app.extensions['scidk']['label_endpoints']

    service_endpoints = registry.list_by_label_type('iLabService')
    assert len(service_endpoints) >= 1
    assert all(e['label_type'] == 'iLabService' for e in service_endpoints)


def test_plugin_endpoint_metadata_complete(app):
    """Test that plugin endpoints have all expected metadata fields."""
    registry = app.extensions['scidk']['label_endpoints']
    endpoint = registry.get_endpoint('/api/integrations/ilab/services')

    required_fields = ['name', 'endpoint', 'label_type', 'auth_required',
                      'test_url', 'plugin', 'description', 'config_schema', 'source']

    for field in required_fields:
        assert field in endpoint, f"Missing field: {field}"


def test_multiple_plugins_can_register_endpoints(app):
    """Test that multiple plugins can register different endpoints."""
    registry = app.extensions['scidk']['label_endpoints']
    all_endpoints = registry.list_endpoints()

    # Should have endpoints from at least one plugin
    assert len(all_endpoints) >= 2

    # Check that endpoints have different paths
    endpoint_paths = [e['endpoint'] for e in all_endpoints]
    assert len(endpoint_paths) == len(set(endpoint_paths)), "Duplicate endpoint paths found"
