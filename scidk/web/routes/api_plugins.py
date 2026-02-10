"""API routes for plugin management.

Provides endpoints to:
- List plugins
- Get plugin details
- Enable/disable plugins
"""

from flask import Blueprint, jsonify, request, current_app
from ...core.plugin_loader import set_plugin_enabled_state, get_plugin_enabled_state

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
