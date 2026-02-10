# SciDK Plugin System

The SciDK plugin system allows you to extend the application with custom functionality, routes, labels, and integrations without modifying the core codebase.

## Overview

Plugins are Python packages placed in the `plugins/` directory that are automatically discovered and loaded at application startup. Each plugin can:

- Add custom API routes and endpoints
- Register new label definitions
- Define custom settings
- Integrate with external services
- Extend existing functionality

## Plugin Structure

A minimal plugin consists of a directory with an `__init__.py` file:

```
plugins/
  my_plugin/
    __init__.py       # Required: Contains register_plugin(app) function
    routes.py         # Optional: Flask blueprints with routes
    labels.py         # Optional: Label definitions
    settings.html     # Optional: Settings UI template
    README.md         # Optional: Plugin documentation
    tests/            # Optional: Plugin-specific tests
```

## Creating a Plugin

### 1. Create Plugin Directory

Create a new directory under `plugins/` with a descriptive name:

```bash
mkdir plugins/my_plugin
```

### 2. Implement `register_plugin()` Function

Create `__init__.py` with a `register_plugin(app)` function that returns plugin metadata:

```python
# plugins/my_plugin/__init__.py

def register_plugin(app):
    """Register the plugin with the Flask app.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata with name, version, author, description
    """
    # Your plugin initialization code here

    return {
        'name': 'My Plugin',
        'version': '1.0.0',
        'author': 'Your Name',
        'description': 'A brief description of what this plugin does'
    }
```

### 3. Add Routes (Optional)

Create a Flask blueprint for your plugin's routes:

```python
# plugins/my_plugin/__init__.py

from flask import Blueprint, jsonify

bp = Blueprint('my_plugin', __name__, url_prefix='/api/my_plugin')

@bp.get('/status')
def status():
    """Example endpoint."""
    return jsonify({'status': 'active', 'plugin': 'my_plugin'})

def register_plugin(app):
    # Register the blueprint
    app.register_blueprint(bp)

    return {
        'name': 'My Plugin',
        'version': '1.0.0',
        'author': 'Your Name',
        'description': 'Adds /api/my_plugin/status endpoint'
    }
```

### 4. Register Labels (Optional)

Plugins can define custom label types for the graph database:

```python
# plugins/my_plugin/labels.py

def register_labels(app):
    """Register custom labels with the application."""
    # Access the graph backend
    ext = app.extensions['scidk']
    graph = ext['graph']

    # Define a new label
    graph.add_label({
        'name': 'MyCustomLabel',
        'properties': [
            {'name': 'custom_id', 'type': 'string'},
            {'name': 'value', 'type': 'float'}
        ]
    })
```

Then call it from your `register_plugin()` function:

```python
def register_plugin(app):
    from . import labels
    labels.register_labels(app)

    # ... rest of registration
```

## Plugin Management

### Web UI

Navigate to `/extensions` to view and manage plugins:

- View installed plugins with metadata
- Enable/disable plugins via toggle switches
- See plugin status and version information
- View failed plugin error messages

**Note:** Changes to plugin enabled state require an application restart to take effect.

### API Endpoints

#### List Plugins

```http
GET /api/plugins
```

Returns a list of all discovered plugins with their status and metadata.

Response:
```json
{
  "success": true,
  "plugins": [
    {
      "name": "My Plugin",
      "version": "1.0.0",
      "author": "Your Name",
      "description": "Plugin description",
      "enabled": true,
      "status": "loaded",
      "module_name": "my_plugin"
    }
  ],
  "failed": {}
}
```

#### Toggle Plugin

```http
POST /api/plugins/<plugin_name>/toggle
Content-Type: application/json

{
  "enabled": true
}
```

Enables or disables a plugin. Requires application restart for changes to take effect.

Response:
```json
{
  "success": true,
  "plugin": "my_plugin",
  "enabled": true,
  "message": "Plugin state updated. Restart required for changes to take effect."
}
```

## Plugin States

- **loaded**: Plugin successfully loaded and active
- **disabled**: Plugin disabled via Extensions page
- **not_loaded**: Plugin discovered but not loaded (usually disabled)
- **failed**: Plugin failed to load (check error message)

## Error Handling

The plugin loader handles errors gracefully:

- Plugin load failures are logged but don't crash the application
- Failed plugins appear in the "Failed Plugins" section with error messages
- Invalid plugins (missing `register_plugin()`, incorrect return type) are caught and reported

## Best Practices

### 1. Return Complete Metadata

Always return all required metadata fields:

```python
return {
    'name': 'My Plugin',          # Required
    'version': '1.0.0',           # Required
    'author': 'Your Name',        # Required
    'description': 'Description'  # Required
}
```

### 2. Use Blueprints for Routes

Organize routes in Flask blueprints to avoid naming conflicts:

```python
bp = Blueprint('my_plugin', __name__, url_prefix='/api/my_plugin')
```

### 3. Handle Errors Gracefully

Catch and log errors in your plugin code:

```python
def register_plugin(app):
    try:
        # Plugin initialization
        app.register_blueprint(bp)
    except Exception as e:
        app.logger.error(f"Failed to initialize my_plugin: {e}")
        raise

    return {...}
```

### 4. Document Your Plugin

Include a README.md with:
- Plugin purpose and features
- API endpoints and usage
- Configuration options
- Dependencies

### 5. Test Your Plugin

Create tests in `plugins/my_plugin/tests/`:

```python
# plugins/my_plugin/tests/test_my_plugin.py

def test_my_plugin_endpoint(client):
    resp = client.get('/api/my_plugin/status')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'active'
```

## Example Plugin

See `plugins/example_plugin/` for a complete working example that demonstrates:

- Plugin registration
- Blueprint creation
- Multiple endpoints
- Proper metadata
- Documentation

## Advanced Topics

### Accessing Application Services

Access core SciDK services through `app.extensions['scidk']`:

```python
def register_plugin(app):
    ext = app.extensions['scidk']

    # Access the graph backend
    graph = ext['graph']

    # Access the interpreter registry
    registry = ext['registry']

    # Access filesystem manager
    fs = ext['fs']

    # Access settings
    settings = ext['settings']

    # ... use services
```

### Database Persistence

Use the settings API for plugin configuration:

```python
from scidk.core.settings import get_setting, set_setting

def register_plugin(app):
    # Load plugin config
    api_key = get_setting('plugin.my_plugin.api_key', 'default_key')

    # Save plugin config
    set_setting('plugin.my_plugin.api_key', 'new_key')
```

### Integration with Existing Features

Plugins can extend existing features:

```python
def register_plugin(app):
    # Add custom interpreter
    registry = app.extensions['scidk']['registry']
    from .interpreters import MyCustomInterpreter
    registry.register(MyCustomInterpreter())

    # Add custom provider
    providers = app.extensions['scidk']['providers']
    from .providers import MyCustomProvider
    providers['my_provider'] = MyCustomProvider()
```

## Troubleshooting

### Plugin Not Appearing

1. Check that `__init__.py` exists in plugin directory
2. Verify `register_plugin(app)` function exists
3. Check application logs for errors
4. Ensure plugin directory name doesn't start with `_` or `.`

### Plugin Load Failures

1. Check `/extensions` page for error messages
2. Review application logs
3. Verify `register_plugin()` returns a dict
4. Check for import errors or missing dependencies

### Plugin Not Activating

1. Verify plugin is enabled in Extensions page
2. Restart the application after enabling
3. Check that blueprints are registered correctly
4. Verify routes don't conflict with existing endpoints

## Security Considerations

- Plugins run with full application privileges
- Only install plugins from trusted sources
- Review plugin code before installation
- Plugins can access all application data and services
- Use RBAC to restrict access to plugin endpoints if needed

## Future Enhancements

Planned features for the plugin system:

- Plugin marketplace
- Plugin dependencies
- Plugin permissions/sandboxing
- Hot reload (no restart required)
- Plugin versioning and updates
- Plugin configuration UI templates
