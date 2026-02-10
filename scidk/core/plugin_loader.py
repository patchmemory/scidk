"""Plugin loader for SciDK.

Discovers and registers plugins from the plugins/ directory.
Each plugin is a Python package that implements a register_plugin(app) function.

Plugin Structure:
    plugins/
      my_plugin/
        __init__.py       # Contains register_plugin(app) function
        routes.py         # Optional: Flask blueprint with routes
        labels.py         # Optional: Label definitions
        settings.html     # Optional: Settings UI template

Plugin Registration:
    def register_plugin(app):
        '''Register plugin with the Flask app.

        Args:
            app: Flask application instance

        Returns:
            dict: Plugin metadata with name, version, author, description
        '''
        # Register routes, labels, etc.
        return {
            'name': 'My Plugin',
            'version': '1.0.0',
            'author': 'Author Name',
            'description': 'Plugin description'
        }
"""

import importlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PluginLoader:
    """Loads and manages plugins for the SciDK application."""

    def __init__(self, plugins_dir: str = 'plugins'):
        """Initialize the plugin loader.

        Args:
            plugins_dir: Directory containing plugins (relative to project root)
        """
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: Dict[str, dict] = {}
        self.failed_plugins: Dict[str, str] = {}

    def discover_plugins(self) -> List[str]:
        """Find all plugins in the plugins/ directory.

        Returns:
            List of plugin names (directory names)
        """
        if not self.plugins_dir.exists():
            logger.info(f"Plugins directory {self.plugins_dir} does not exist")
            return []

        plugins = []
        for plugin_path in self.plugins_dir.iterdir():
            if plugin_path.is_dir() and (plugin_path / '__init__.py').exists():
                # Exclude __pycache__ and hidden directories
                if not plugin_path.name.startswith('_') and not plugin_path.name.startswith('.'):
                    plugins.append(plugin_path.name)

        logger.info(f"Discovered {len(plugins)} plugins: {plugins}")
        return plugins

    def load_plugin(self, plugin_name: str, app, enabled: bool = True) -> bool:
        """Load and register a plugin.

        Args:
            plugin_name: Name of the plugin (directory name)
            app: Flask application instance
            enabled: Whether the plugin is enabled

        Returns:
            bool: True if plugin loaded successfully, False otherwise
        """
        if not enabled:
            logger.info(f"Plugin {plugin_name} is disabled, skipping load")
            self.loaded_plugins[plugin_name] = {
                'name': plugin_name,
                'enabled': False,
                'status': 'disabled'
            }
            return True

        try:
            # Import the plugin module
            # Try to import from plugins package first, then try direct import (for testing)
            try:
                module = importlib.import_module(f'plugins.{plugin_name}')
            except ModuleNotFoundError:
                # Try direct import (for testing with custom paths in sys.path)
                module = importlib.import_module(plugin_name)

            # Check if plugin has register_plugin function
            if not hasattr(module, 'register_plugin'):
                error_msg = f"Plugin {plugin_name} missing register_plugin() function"
                logger.error(error_msg)
                self.failed_plugins[plugin_name] = error_msg
                return False

            # Call the registration function
            metadata = module.register_plugin(app)

            # Validate metadata
            if not isinstance(metadata, dict):
                error_msg = f"Plugin {plugin_name} register_plugin() must return a dict"
                logger.error(error_msg)
                self.failed_plugins[plugin_name] = error_msg
                return False

            # Store plugin info
            self.loaded_plugins[plugin_name] = {
                'name': metadata.get('name', plugin_name),
                'version': metadata.get('version', '0.0.0'),
                'author': metadata.get('author', 'Unknown'),
                'description': metadata.get('description', ''),
                'enabled': True,
                'status': 'loaded',
                'module_name': plugin_name
            }

            logger.info(f"Successfully loaded plugin: {plugin_name} v{metadata.get('version', '0.0.0')}")
            return True

        except Exception as e:
            error_msg = f"Failed to load plugin {plugin_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.failed_plugins[plugin_name] = error_msg
            return False

    def load_all_plugins(self, app, enabled_plugins: Optional[List[str]] = None):
        """Discover and load all plugins.

        Args:
            app: Flask application instance
            enabled_plugins: Optional list of enabled plugin names.
                           If None, all plugins are enabled by default.
        """
        plugins = self.discover_plugins()

        for plugin_name in plugins:
            enabled = True
            if enabled_plugins is not None:
                enabled = plugin_name in enabled_plugins

            self.load_plugin(plugin_name, app, enabled=enabled)

    def get_plugin_info(self, plugin_name: str) -> Optional[dict]:
        """Get information about a loaded plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Plugin metadata dict, or None if not loaded
        """
        return self.loaded_plugins.get(plugin_name)

    def list_plugins(self) -> List[dict]:
        """List all loaded plugins.

        Returns:
            List of plugin metadata dicts
        """
        return list(self.loaded_plugins.values())

    def list_failed_plugins(self) -> Dict[str, str]:
        """List plugins that failed to load.

        Returns:
            Dict mapping plugin name to error message
        """
        return self.failed_plugins.copy()


def get_plugin_enabled_state(plugin_name: str) -> bool:
    """Check if a plugin is enabled in the database.

    Args:
        plugin_name: Name of the plugin

    Returns:
        bool: True if enabled (default), False if disabled
    """
    try:
        from .settings import get_setting
        return get_setting(f'plugin.{plugin_name}.enabled', 'true') == 'true'
    except Exception as e:
        logger.warning(f"Failed to get plugin enabled state for {plugin_name}: {e}")
        return True  # Default to enabled


def set_plugin_enabled_state(plugin_name: str, enabled: bool) -> bool:
    """Set whether a plugin is enabled.

    Args:
        plugin_name: Name of the plugin
        enabled: Whether to enable the plugin

    Returns:
        bool: True if successful
    """
    try:
        from .settings import set_setting
        set_setting(f'plugin.{plugin_name}.enabled', 'true' if enabled else 'false')
        return True
    except Exception as e:
        logger.error(f"Failed to set plugin enabled state for {plugin_name}: {e}")
        return False


def get_all_plugin_states() -> Dict[str, bool]:
    """Get the enabled state for all plugins from database.

    Returns:
        Dict mapping plugin name to enabled state
    """
    plugin_states = {}
    try:
        from .settings import get_settings_by_prefix
        settings = get_settings_by_prefix('plugin.')

        for key, value in settings.items():
            if key.endswith('.enabled'):
                # Extract plugin name from key like "plugin.my_plugin.enabled"
                plugin_name = key[7:-8]  # Remove "plugin." and ".enabled"
                plugin_states[plugin_name] = (value == 'true')
    except Exception as e:
        logger.warning(f"Failed to get plugin states: {e}")

    return plugin_states
