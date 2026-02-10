"""Tests for plugins API endpoints."""

import pytest


def test_list_plugins_endpoint(client):
    """Test GET /api/plugins endpoint."""
    resp = client.get('/api/plugins')
    assert resp.status_code == 200

    data = resp.get_json()
    assert 'success' in data
    assert data['success'] is True
    assert 'plugins' in data
    assert isinstance(data['plugins'], list)


def test_list_plugins_includes_example_plugin(client):
    """Test that example_plugin is in the plugins list."""
    resp = client.get('/api/plugins')
    data = resp.get_json()

    # Find example plugin
    example_plugin = None
    for plugin in data['plugins']:
        if plugin.get('module_name') == 'example_plugin' or plugin.get('name') == 'Example Plugin':
            example_plugin = plugin
            break

    assert example_plugin is not None, "Example plugin should be discoverable"
    # Check if it has expected metadata (if loaded)
    if example_plugin.get('status') == 'loaded':
        assert example_plugin['name'] == 'Example Plugin'
        assert example_plugin['version'] == '1.0.0'


def test_toggle_plugin_endpoint(client):
    """Test POST /api/plugins/<name>/toggle endpoint."""
    # Try to disable example_plugin
    resp = client.post(
        '/api/plugins/example_plugin/toggle',
        json={'enabled': False}
    )
    assert resp.status_code == 200

    data = resp.get_json()
    assert data['success'] is True
    assert data['plugin'] == 'example_plugin'
    assert data['enabled'] is False

    # Enable it again
    resp = client.post(
        '/api/plugins/example_plugin/toggle',
        json={'enabled': True}
    )
    assert resp.status_code == 200

    data = resp.get_json()
    assert data['success'] is True
    assert data['enabled'] is True


def test_toggle_plugin_invalid_json(client):
    """Test toggle with invalid JSON."""
    resp = client.post(
        '/api/plugins/example_plugin/toggle',
        data='not json',
        content_type='application/json'
    )
    assert resp.status_code == 400

    # When JSON parsing fails, Flask returns None for get_json()
    # So we check the response directly or use force=True
    try:
        data = resp.get_json(force=True)
    except:
        data = None

    if data is None:
        # JSON parsing failed as expected, which triggers a 400
        assert True
    else:
        assert data.get('success') is False
        assert 'error' in data


def test_example_plugin_endpoints(client):
    """Test that example plugin endpoints work when loaded."""
    # Check if example plugin is loaded
    resp = client.get('/api/plugins')
    plugins = resp.get_json()['plugins']

    example_plugin = next(
        (p for p in plugins if p.get('module_name') == 'example_plugin' and p.get('status') == 'loaded'),
        None
    )

    if example_plugin:
        # Test hello endpoint
        resp = client.get('/api/example/hello')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['message'] == 'Hello from Example Plugin!'
        assert data['plugin'] == 'example_plugin'

        # Test status endpoint
        resp = client.get('/api/example/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'active'
        assert data['plugin'] == 'example_plugin'
        assert isinstance(data['endpoints'], list)
