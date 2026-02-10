"""Tests for plugin loader functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
from scidk.core.plugin_loader import PluginLoader


def test_plugin_loader_init():
    """Test plugin loader initialization."""
    loader = PluginLoader()
    assert loader.plugins_dir == Path('plugins')
    assert loader.loaded_plugins == {}
    assert loader.failed_plugins == {}


def test_discover_plugins_empty_dir(tmp_path):
    """Test plugin discovery in empty directory."""
    loader = PluginLoader(str(tmp_path))
    plugins = loader.discover_plugins()
    assert plugins == []


def test_discover_plugins_with_valid_plugin(tmp_path):
    """Test plugin discovery with valid plugin."""
    # Create plugin directory with __init__.py
    plugin_dir = tmp_path / 'test_plugin'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('# Plugin code')

    loader = PluginLoader(str(tmp_path))
    plugins = loader.discover_plugins()
    assert plugins == ['test_plugin']


def test_discover_plugins_ignores_invalid(tmp_path):
    """Test that plugin discovery ignores invalid directories."""
    # Valid plugin
    valid_plugin = tmp_path / 'valid_plugin'
    valid_plugin.mkdir()
    (valid_plugin / '__init__.py').write_text('# Plugin code')

    # Invalid: no __init__.py
    invalid_plugin = tmp_path / 'invalid_plugin'
    invalid_plugin.mkdir()

    # Invalid: starts with underscore
    hidden_plugin = tmp_path / '_hidden'
    hidden_plugin.mkdir()
    (hidden_plugin / '__init__.py').write_text('# Hidden')

    # Invalid: not a directory
    (tmp_path / 'file.txt').write_text('Not a plugin')

    loader = PluginLoader(str(tmp_path))
    plugins = loader.discover_plugins()
    assert plugins == ['valid_plugin']


def test_load_plugin_missing_register_function(tmp_path, app):
    """Test loading plugin without register_plugin function."""
    # Create plugin without register_plugin
    plugin_dir = tmp_path / 'bad_plugin'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('# No register_plugin function')

    # Add to sys.path so we can import it
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        success = loader.load_plugin('bad_plugin', app)
        assert success is False
        assert 'bad_plugin' in loader.failed_plugins
        assert 'missing register_plugin()' in loader.failed_plugins['bad_plugin']
    finally:
        sys.path.remove(str(tmp_path))


def test_load_plugin_register_returns_non_dict(tmp_path, app):
    """Test loading plugin where register_plugin returns non-dict."""
    # Create plugin with register_plugin that returns None
    plugin_dir = tmp_path / 'bad_plugin_dict'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('def register_plugin(app):\n    return None\n')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        success = loader.load_plugin('bad_plugin_dict', app)
        assert success is False
        assert 'bad_plugin_dict' in loader.failed_plugins
        assert 'must return a dict' in loader.failed_plugins['bad_plugin_dict']
    finally:
        sys.path.remove(str(tmp_path))


def test_load_plugin_success(tmp_path, app):
    """Test successfully loading a valid plugin."""
    # Create valid plugin
    plugin_dir = tmp_path / 'good_plugin'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('''
def register_plugin(app):
    return {
        'name': 'Good Plugin',
        'version': '1.0.0',
        'author': 'Test',
        'description': 'A test plugin'
    }
''')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        success = loader.load_plugin('good_plugin', app, enabled=True)
        assert success is True
        assert 'good_plugin' in loader.loaded_plugins
        plugin_info = loader.loaded_plugins['good_plugin']
        assert plugin_info['name'] == 'Good Plugin'
        assert plugin_info['version'] == '1.0.0'
        assert plugin_info['enabled'] is True
        assert plugin_info['status'] == 'loaded'
    finally:
        sys.path.remove(str(tmp_path))


def test_load_plugin_disabled(tmp_path, app):
    """Test loading a disabled plugin."""
    # Create valid plugin
    plugin_dir = tmp_path / 'disabled_plugin'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('''
def register_plugin(app):
    return {
        'name': 'Disabled Plugin',
        'version': '1.0.0',
        'author': 'Test',
        'description': 'A disabled plugin'
    }
''')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        success = loader.load_plugin('disabled_plugin', app, enabled=False)
        assert success is True
        assert 'disabled_plugin' in loader.loaded_plugins
        plugin_info = loader.loaded_plugins['disabled_plugin']
        assert plugin_info['enabled'] is False
        assert plugin_info['status'] == 'disabled'
    finally:
        sys.path.remove(str(tmp_path))


def test_get_plugin_info(tmp_path, app):
    """Test getting plugin info."""
    # Create and load plugin
    plugin_dir = tmp_path / 'info_plugin'
    plugin_dir.mkdir()
    (plugin_dir / '__init__.py').write_text('''
def register_plugin(app):
    return {
        'name': 'Info Plugin',
        'version': '2.0.0',
        'author': 'Tester',
        'description': 'Plugin for testing info'
    }
''')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        loader.load_plugin('info_plugin', app, enabled=True)

        # Get info for loaded plugin
        info = loader.get_plugin_info('info_plugin')
        assert info is not None
        assert info['name'] == 'Info Plugin'
        assert info['version'] == '2.0.0'

        # Get info for non-existent plugin
        info = loader.get_plugin_info('nonexistent')
        assert info is None
    finally:
        sys.path.remove(str(tmp_path))


def test_list_plugins(tmp_path, app):
    """Test listing all plugins."""
    # Create two plugins
    for i in range(2):
        plugin_dir = tmp_path / f'plugin_{i}'
        plugin_dir.mkdir()
        (plugin_dir / '__init__.py').write_text(f'''
def register_plugin(app):
    return {{
        'name': 'Plugin {i}',
        'version': '1.0.{i}',
        'author': 'Test',
        'description': 'Plugin {i}'
    }}
''')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        loader.load_all_plugins(app)

        plugins = loader.list_plugins()
        assert len(plugins) == 2
        plugin_names = {p['name'] for p in plugins}
        assert 'Plugin 0' in plugin_names
        assert 'Plugin 1' in plugin_names
    finally:
        sys.path.remove(str(tmp_path))


def test_list_failed_plugins(tmp_path, app):
    """Test listing failed plugins."""
    # Create one good and one bad plugin
    good_plugin = tmp_path / 'good'
    good_plugin.mkdir()
    (good_plugin / '__init__.py').write_text('''
def register_plugin(app):
    return {'name': 'Good', 'version': '1.0.0', 'author': 'Test', 'description': 'Good'}
''')

    bad_plugin = tmp_path / 'bad'
    bad_plugin.mkdir()
    (bad_plugin / '__init__.py').write_text('# No register_plugin')

    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        loader = PluginLoader(str(tmp_path))
        loader.load_all_plugins(app)

        failed = loader.list_failed_plugins()
        assert 'bad' in failed
        assert 'missing register_plugin()' in failed['bad']
    finally:
        sys.path.remove(str(tmp_path))


@pytest.fixture
def app():
    """Create a minimal Flask app for testing."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app
