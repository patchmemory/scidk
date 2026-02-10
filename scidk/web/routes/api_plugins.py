"""API routes for plugin management.

Provides endpoints to:
- List plugins
- Get plugin details
- Enable/disable plugins
- Get/update plugin settings
"""

import logging
from flask import Blueprint, jsonify, request, current_app
from ...core.plugin_loader import set_plugin_enabled_state, get_plugin_enabled_state
from ...core.plugin_settings import (
    get_all_plugin_settings,
    set_plugin_setting,
    validate_settings_against_schema,
    apply_schema_defaults
)

logger = logging.getLogger(__name__)

bp = Blueprint('api_plugins', __name__, url_prefix='/api/plugins')


def _get_ext():
    """Get SciDK extensions from current Flask app."""
    return current_app.extensions['scidk']


@bp.get('')
def list_plugins():
    """List all plugins (loaded and discovered).

    Returns:
        JSON response with list of plugins
    """
    ext = _get_ext()
    plugins_info = ext.get('plugins', {})

    # Get loaded plugins
    loaded = plugins_info.get('loaded', [])

    # Get plugin loader to discover all available plugins
    loader = plugins_info.get('loader')
    if loader:
        all_discovered = loader.discover_plugins()

        # Add discovered but not loaded plugins to the list
        loaded_names = {p.get('module_name') or p.get('name') for p in loaded}
        for plugin_name in all_discovered:
            if plugin_name not in loaded_names:
                # Plugin discovered but not loaded (probably disabled)
                loaded.append({
                    'name': plugin_name,
                    'module_name': plugin_name,
                    'version': 'N/A',
                    'author': 'Unknown',
                    'description': 'Plugin not loaded (may be disabled)',
                    'enabled': get_plugin_enabled_state(plugin_name),
                    'status': 'not_loaded'
                })

    return jsonify({
        'success': True,
        'plugins': loaded,
        'failed': plugins_info.get('failed', {})
    })


@bp.get('/<plugin_name>')
def get_plugin(plugin_name):
    """Get details about a specific plugin.

    Args:
        plugin_name: Name of the plugin

    Returns:
        JSON response with plugin details
    """
    ext = _get_ext()
    loader = ext.get('plugins', {}).get('loader')

    if not loader:
        return jsonify({'success': False, 'error': 'Plugin loader not initialized'}), 500

    info = loader.get_plugin_info(plugin_name)
    if not info:
        return jsonify({'success': False, 'error': 'Plugin not found'}), 404

    return jsonify({
        'success': True,
        'plugin': info
    })


@bp.post('/<plugin_name>/toggle')
def toggle_plugin(plugin_name):
    """Enable or disable a plugin.

    Args:
        plugin_name: Name of the plugin

    Request body:
        {
            "enabled": true/false
        }

    Returns:
        JSON response indicating success
    """
    data = request.get_json()
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    enabled = data.get('enabled', True)

    # Save plugin state to database
    success = set_plugin_enabled_state(plugin_name, enabled)

    if not success:
        return jsonify({
            'success': False,
            'error': 'Failed to update plugin state'
        }), 500

    return jsonify({
        'success': True,
        'plugin': plugin_name,
        'enabled': enabled,
        'message': 'Plugin state updated. Restart required for changes to take effect.'
    })


@bp.get('/<plugin_name>/settings')
def get_plugin_settings(plugin_name):
    """Get plugin configuration settings.

    Args:
        plugin_name: Name of the plugin

    Returns:
        JSON response with plugin settings and schema
    """
    ext = _get_ext()
    loader = ext.get('plugins', {}).get('loader')

    if not loader:
        return jsonify({'success': False, 'error': 'Plugin loader not initialized'}), 500

    # Check if plugin exists
    plugin_info = loader.get_plugin_info(plugin_name)
    if not plugin_info:
        # Check if plugin is discovered but not loaded
        discovered = loader.discover_plugins()
        if plugin_name not in discovered:
            return jsonify({'success': False, 'error': 'Plugin not found'}), 404

    # Get current settings
    settings = get_all_plugin_settings(plugin_name)

    # Try to get schema from plugin
    schema = None
    try:
        import importlib
        try:
            module = importlib.import_module(f'plugins.{plugin_name}')
        except ModuleNotFoundError:
            module = importlib.import_module(plugin_name)

        if hasattr(module, 'get_settings_schema'):
            schema = module.get_settings_schema()
            # Apply defaults from schema
            settings = apply_schema_defaults(settings, schema)
    except Exception as e:
        logger.warning(f"Could not get settings schema for plugin {plugin_name}: {e}")

    return jsonify({
        'success': True,
        'plugin': plugin_name,
        'settings': settings,
        'schema': schema
    })


@bp.post('/<plugin_name>/settings')
def update_plugin_settings(plugin_name):
    """Update plugin configuration settings.

    Args:
        plugin_name: Name of the plugin

    Request body:
        {
            "settings": {
                "key1": "value1",
                "key2": "value2"
            }
        }

    Returns:
        JSON response indicating success
    """
    ext = _get_ext()
    loader = ext.get('plugins', {}).get('loader')

    if not loader:
        return jsonify({'success': False, 'error': 'Plugin loader not initialized'}), 500

    # Check if plugin exists
    discovered = loader.discover_plugins()
    if plugin_name not in discovered:
        return jsonify({'success': False, 'error': 'Plugin not found'}), 404

    data = request.get_json()
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    new_settings = data.get('settings', {})
    if not isinstance(new_settings, dict):
        return jsonify({'success': False, 'error': 'Settings must be a dictionary'}), 400

    # Try to get and validate against schema
    schema = None
    try:
        import importlib
        try:
            module = importlib.import_module(f'plugins.{plugin_name}')
        except ModuleNotFoundError:
            module = importlib.import_module(plugin_name)

        if hasattr(module, 'get_settings_schema'):
            schema = module.get_settings_schema()
            is_valid, errors = validate_settings_against_schema(new_settings, schema)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'error': 'Settings validation failed',
                    'errors': errors
                }), 400
    except Exception as e:
        logger.warning(f"Could not validate settings for plugin {plugin_name}: {e}")

    # Save settings
    try:
        for key, value in new_settings.items():
            # Determine if field should be encrypted
            encrypted = False
            if schema and key in schema:
                field_type = schema[key].get('type', 'text')
                encrypted = (field_type == 'password')

            set_plugin_setting(plugin_name, key, value, encrypted=encrypted)

        return jsonify({
            'success': True,
            'plugin': plugin_name,
            'message': 'Plugin settings updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating plugin settings: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to update settings: {str(e)}'
        }), 500


@bp.get('/<plugin_name>/settings/schema')
def get_plugin_settings_schema(plugin_name):
    """Get plugin settings schema definition.

    Args:
        plugin_name: Name of the plugin

    Returns:
        JSON response with schema definition
    """
    try:
        import importlib
        try:
            module = importlib.import_module(f'plugins.{plugin_name}')
        except ModuleNotFoundError:
            module = importlib.import_module(plugin_name)

        if not hasattr(module, 'get_settings_schema'):
            return jsonify({
                'success': True,
                'plugin': plugin_name,
                'schema': None,
                'message': 'Plugin does not define a settings schema'
            })

        schema = module.get_settings_schema()

        return jsonify({
            'success': True,
            'plugin': plugin_name,
            'schema': schema
        })

    except Exception as e:
        logger.error(f"Error getting plugin settings schema: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to get settings schema: {str(e)}'
        }), 500
