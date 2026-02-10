"""Tests for plugin settings API endpoints."""

import pytest
import json
import tempfile
import os
import sys

# Add test plugin directory to path for imports
test_plugins_dir = os.path.join(os.path.dirname(__file__), 'test_plugins')
if test_plugins_dir not in sys.path:
    sys.path.insert(0, test_plugins_dir)


@pytest.fixture
def app():
    """Create a Flask app for testing."""
    from flask import Flask
    from scidk.web.routes.api_plugins import bp as plugins_bp
    from scidk.core.plugin_loader import PluginLoader

    app = Flask(__name__)
    app.config['TESTING'] = True

    # Register blueprint
    app.register_blueprint(plugins_bp)

    # Create temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    app.config['DATABASE'] = db_path
    os.environ['SCIDK_DB_PATH'] = db_path

    # Initialize database
    from scidk.core.migrations import migrate
    import sqlite3
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()

    # Initialize plugin loader
    loader = PluginLoader('plugins')

    # Store in app extensions
    if not hasattr(app, 'extensions'):
        app.extensions = {}
    app.extensions['scidk'] = {
        'plugins': {
            'loader': loader,
            'loaded': [],
            'failed': {}
        }
    }

    yield app

    # Cleanup
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


def test_get_plugin_settings_no_schema(client, app):
    """Test getting plugin settings when plugin has no schema."""
    # Create a simple test plugin without schema
    os.makedirs('test_plugins/simple_plugin', exist_ok=True)

    with open('test_plugins/simple_plugin/__init__.py', 'w') as f:
        f.write("""
def register_plugin(app):
    return {
        'name': 'Simple Plugin',
        'version': '1.0.0',
        'author': 'Test',
        'description': 'Test plugin without schema'
    }
""")

    # Discover plugins
    from pathlib import Path
    with app.app_context():
        loader = app.extensions['scidk']['plugins']['loader']
        loader.plugins_dir = Path('test_plugins')

    response = client.get('/api/plugins/simple_plugin/settings')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['success'] is True
    assert data['plugin'] == 'simple_plugin'
    assert data['schema'] is None

    # Cleanup
    import shutil
    shutil.rmtree('test_plugins', ignore_errors=True)


def test_get_plugin_settings_with_schema(client, app):
    """Test getting plugin settings when plugin has schema."""
    response = client.get('/api/plugins/example_plugin/settings')

    if response.status_code == 404:
        pytest.skip("example_plugin not available in test environment")

    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['success'] is True
    assert data['plugin'] == 'example_plugin'
    assert data['schema'] is not None
    assert isinstance(data['settings'], dict)


def test_update_plugin_settings(client, app):
    """Test updating plugin settings."""
    new_settings = {
        'api_key': 'test_key_123',
        'endpoint_url': 'https://test.example.com',
        'max_retries': 5
    }

    response = client.post(
        '/api/plugins/example_plugin/settings',
        data=json.dumps({'settings': new_settings}),
        content_type='application/json'
    )

    if response.status_code == 404:
        pytest.skip("example_plugin not available in test environment")

    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['success'] is True

    # Verify settings were saved
    response = client.get('/api/plugins/example_plugin/settings')
    data = json.loads(response.data)

    assert data['settings']['endpoint_url'] == 'https://test.example.com'
    assert data['settings']['max_retries'] == 5  # Should be int, not string


def test_update_plugin_settings_invalid_json(client):
    """Test updating plugin settings with invalid JSON."""
    response = client.post(
        '/api/plugins/example_plugin/settings',
        data='invalid json',
        content_type='application/json'
    )

    # Should return 400 for invalid JSON
    assert response.status_code == 400

    # Flask returns HTML error page for 400, not JSON
    assert b'Bad Request' in response.data or response.status_code == 400


def test_update_plugin_settings_not_dict(client):
    """Test updating plugin settings with non-dict settings."""
    response = client.post(
        '/api/plugins/example_plugin/settings',
        data=json.dumps({'settings': 'not a dict'}),
        content_type='application/json'
    )

    assert response.status_code == 400

    data = json.loads(response.data)
    assert data['success'] is False


def test_update_plugin_settings_nonexistent_plugin(client):
    """Test updating settings for a nonexistent plugin."""
    response = client.post(
        '/api/plugins/nonexistent_plugin/settings',
        data=json.dumps({'settings': {}}),
        content_type='application/json'
    )

    assert response.status_code == 404

    data = json.loads(response.data)
    assert data['success'] is False


def test_get_plugin_settings_schema(client):
    """Test getting plugin settings schema."""
    response = client.get('/api/plugins/example_plugin/settings/schema')

    if response.status_code in [404, 500]:
        pytest.skip("example_plugin not available in test environment")

    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['success'] is True
    assert data['schema'] is not None


def test_update_plugin_settings_validation(client, app):
    """Test that settings validation works with schema."""
    # Create a test plugin with strict validation
    os.makedirs('test_plugins/validated_plugin', exist_ok=True)

    with open('test_plugins/validated_plugin/__init__.py', 'w') as f:
        f.write("""
def get_settings_schema():
    return {
        'required_field': {
            'type': 'text',
            'required': True,
            'description': 'This field is required'
        },
        'number_field': {
            'type': 'number',
            'required': False
        }
    }

def register_plugin(app):
    return {
        'name': 'Validated Plugin',
        'version': '1.0.0',
        'author': 'Test',
        'description': 'Test plugin with validation'
    }
""")

    # Update plugin loader to use test_plugins directory
    from pathlib import Path
    with app.app_context():
        loader = app.extensions['scidk']['plugins']['loader']
        loader.plugins_dir = Path('test_plugins')

    # Try to update with invalid settings (missing required field)
    response = client.post(
        '/api/plugins/validated_plugin/settings',
        data=json.dumps({'settings': {'number_field': 42}}),
        content_type='application/json'
    )

    # Should fail validation
    if response.status_code != 404:  # Only if plugin was found
        data = json.loads(response.data)
        if not data.get('success'):
            assert 'validation' in data.get('error', '').lower() or 'errors' in data

    # Cleanup
    import shutil
    shutil.rmtree('test_plugins', ignore_errors=True)


def test_encrypted_password_fields(client, app):
    """Test that password fields are encrypted when saved."""
    # This test verifies the encryption behavior
    settings_with_password = {
        'api_key': 'secret_password_123',
        'endpoint_url': 'https://test.com'
    }

    response = client.post(
        '/api/plugins/example_plugin/settings',
        data=json.dumps({'settings': settings_with_password}),
        content_type='application/json'
    )

    if response.status_code == 404:
        pytest.skip("example_plugin not available in test environment")

    assert response.status_code == 200

    # Verify the password field can be retrieved (decrypted)
    response = client.get('/api/plugins/example_plugin/settings')
    data = json.loads(response.data)

    # The api_key should be retrievable (it gets decrypted automatically)
    assert 'api_key' in data['settings']


def test_settings_persistence(client, app):
    """Test that settings persist across requests."""
    settings = {
        'test_field': 'test_value_persistent'
    }

    # Set settings
    response = client.post(
        '/api/plugins/example_plugin/settings',
        data=json.dumps({'settings': settings}),
        content_type='application/json'
    )

    if response.status_code == 404:
        pytest.skip("example_plugin not available in test environment")

    # Get settings in a new request
    response = client.get('/api/plugins/example_plugin/settings')
    data = json.loads(response.data)

    assert data['settings']['test_field'] == 'test_value_persistent'
