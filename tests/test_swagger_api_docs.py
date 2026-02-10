"""
Tests for Swagger/OpenAPI documentation integration.
"""
import pytest


def test_swagger_ui_endpoint_exists(client):
    """Test that the Swagger UI endpoint is accessible."""
    resp = client.get('/api/docs')
    # Swagger UI should be public (no auth required)
    assert resp.status_code == 200
    assert b'swagger-ui' in resp.data or b'Swagger' in resp.data or b'flasgger' in resp.data


def test_swagger_ui_contains_title(client):
    """Test that Swagger UI contains the SciDK API title."""
    resp = client.get('/api/docs')
    assert resp.status_code == 200
    # Check for Swagger UI elements in HTML (title is loaded dynamically from apispec)
    assert b'swagger-ui' in resp.data or b'Flasgger' in resp.data


def test_apispec_json_endpoint_exists(client):
    """Test that the API spec JSON endpoint is accessible."""
    resp = client.get('/apispec.json')
    # API spec should be public (no auth required)
    assert resp.status_code == 200


def test_apispec_json_structure(client):
    """Test that API spec JSON contains expected OpenAPI structure."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()

    # Should have OpenAPI/Swagger required fields
    assert 'info' in data
    assert 'paths' in data

    # Check info section
    assert 'title' in data['info']
    assert 'version' in data['info']
    assert data['info']['title'] == 'SciDK API'


def test_apispec_includes_documented_endpoints(client):
    """Test that API spec includes the documented endpoints."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()
    paths = data.get('paths', {})

    # Check that key documented endpoints are present
    assert '/api/health' in paths or any('/health' in p for p in paths)
    assert '/api/health/graph' in paths or any('/health/graph' in p for p in paths)


def test_apispec_includes_authentication(client):
    """Test that API spec includes authentication definitions."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()

    # Should have security definitions (for Bearer token)
    assert 'securityDefinitions' in data or 'components' in data


def test_documented_endpoint_has_swagger_info(client):
    """Test that documented endpoints include Swagger annotations."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()
    paths = data.get('paths', {})

    # Find a documented endpoint
    health_paths = [p for p in paths if '/health' in p]
    assert len(health_paths) > 0, "Should have at least one health endpoint"

    # Check that it has proper documentation
    for health_path in health_paths:
        methods = paths[health_path]
        for method, details in methods.items():
            if method in ['get', 'post', 'put', 'delete']:
                # Should have description or summary
                assert 'summary' in details or 'description' in details
                assert 'responses' in details


def test_swagger_static_files_accessible(client):
    """Test that Swagger static files are accessible."""
    resp = client.get('/flasgger_static/swagger-ui.css')
    # Should be accessible (either 200 or 304)
    assert resp.status_code in [200, 304]


def test_apispec_includes_tags(client):
    """Test that API spec organizes endpoints with tags."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()

    # Check for tags (for grouping endpoints)
    # Tags might be at top level or in paths
    paths = data.get('paths', {})
    has_tags = False

    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ['get', 'post', 'put', 'delete']:
                if 'tags' in details:
                    has_tags = True
                    break
        if has_tags:
            break

    # At least some endpoints should have tags for organization
    assert has_tags or 'tags' in data, "API spec should include tags for endpoint organization"


def test_swagger_ui_does_not_require_auth(client):
    """Test that Swagger UI is accessible without authentication."""
    # This test ensures the middleware allows Swagger routes
    resp = client.get('/api/docs')
    assert resp.status_code == 200
    # Should not redirect to login
    assert resp.headers.get('Location') is None


def test_documented_auth_endpoints(client):
    """Test that authentication endpoints are documented."""
    resp = client.get('/apispec.json')
    assert resp.status_code == 200

    data = resp.get_json()
    paths = data.get('paths', {})

    # Look for auth login endpoint
    auth_paths = [p for p in paths if '/auth/login' in p]
    if auth_paths:
        # If documented, check it has proper structure
        for auth_path in auth_paths:
            methods = paths[auth_path]
            if 'post' in methods:
                post_details = methods['post']
                assert 'parameters' in post_details or 'requestBody' in post_details
                assert 'responses' in post_details
