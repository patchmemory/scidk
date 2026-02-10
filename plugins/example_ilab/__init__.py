"""Example iLab plugin demonstrating label endpoint registration.

This plugin shows how to register API endpoints that map to Label types
in the SciDK integration system.
"""


def register_plugin(app):
    """Register the iLab plugin with the Flask app.

    This function is called during app initialization when the plugin is loaded.
    It registers label endpoints that will appear in Settings > Integrations.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata
    """
    # Get the label endpoint registry from app extensions
    registry = app.extensions['scidk']['label_endpoints']

    # Register iLab Services endpoint
    registry.register({
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab/services',
        'label_type': 'iLabService',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'example_ilab',
        'description': 'Integration with iLab service management system for lab services'
    })

    # Register iLab Equipment endpoint
    registry.register({
        'name': 'iLab Equipment',
        'endpoint': '/api/integrations/ilab/equipment',
        'label_type': 'Equipment',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'example_ilab',
        'description': 'Integration with iLab equipment inventory'
    })

    # Return plugin metadata
    return {
        'name': 'iLab Integration (Example)',
        'version': '1.0.0',
        'author': 'SciDK Team',
        'description': 'Example plugin demonstrating label endpoint registration for iLab services'
    }
