"""Example SciDK Plugin.

This plugin demonstrates the basic structure and registration pattern for SciDK plugins.

To create your own plugin:
1. Create a directory under plugins/
2. Add __init__.py with a register_plugin(app) function
3. Optionally add routes.py, labels.py, etc.
4. Return plugin metadata from register_plugin()
"""

from flask import Blueprint, jsonify

# Create a blueprint for this plugin's routes
bp = Blueprint('example_plugin', __name__, url_prefix='/api/example')


@bp.get('/hello')
def hello():
    """Example API endpoint."""
    return jsonify({
        'message': 'Hello from Example Plugin!',
        'plugin': 'example_plugin',
        'version': '1.0.0'
    })


@bp.get('/status')
def status():
    """Example status endpoint."""
    return jsonify({
        'status': 'active',
        'plugin': 'example_plugin',
        'endpoints': [
            '/api/example/hello',
            '/api/example/status'
        ]
    })


def get_settings_schema():
    """Define the settings schema for this plugin.

    Returns:
        dict: Settings schema defining configurable options
    """
    return {
        'api_key': {
            'type': 'password',
            'required': False,
            'description': 'Example API key (encrypted when saved)',
            'default': ''
        },
        'endpoint_url': {
            'type': 'text',
            'required': False,
            'description': 'Example endpoint URL',
            'default': 'https://api.example.com'
        },
        'enabled_features': {
            'type': 'text',
            'required': False,
            'description': 'Comma-separated list of enabled features',
            'default': 'feature1,feature2'
        },
        'max_retries': {
            'type': 'number',
            'required': False,
            'description': 'Maximum number of retry attempts',
            'default': 3
        },
        'debug_mode': {
            'type': 'boolean',
            'required': False,
            'description': 'Enable debug logging',
            'default': False
        }
    }


def register_plugin(app):
    """Register the example plugin with the Flask app.

    This function is called by the plugin loader during application startup.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata with name, version, author, description
    """
    # Register the blueprint with the app
    app.register_blueprint(bp)

    # Return plugin metadata
    return {
        'name': 'Example Plugin',
        'version': '1.0.0',
        'author': 'SciDK Team',
        'description': 'A simple example plugin demonstrating the plugin system. '
                      'Adds /api/example/hello and /api/example/status endpoints.'
    }
