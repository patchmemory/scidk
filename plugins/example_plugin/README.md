# Example Plugin

A simple demonstration plugin for SciDK that shows how to create and register plugins.

## Features

- Example API endpoints
- Blueprint registration
- Plugin metadata

## API Endpoints

### GET /api/example/hello

Returns a hello message from the plugin.

**Response:**
```json
{
  "message": "Hello from Example Plugin!",
  "plugin": "example_plugin",
  "version": "1.0.0"
}
```

### GET /api/example/status

Returns the plugin status and available endpoints.

**Response:**
```json
{
  "status": "active",
  "plugin": "example_plugin",
  "endpoints": [
    "/api/example/hello",
    "/api/example/status"
  ]
}
```

## Creating Your Own Plugin

1. Create a directory under `plugins/` with your plugin name
2. Add `__init__.py` with a `register_plugin(app)` function
3. Optionally add additional modules (routes.py, labels.py, etc.)
4. Return plugin metadata from `register_plugin()`

Example structure:
```
plugins/
  my_plugin/
    __init__.py       # Contains register_plugin(app)
    routes.py         # Optional: Flask blueprint with routes
    labels.py         # Optional: Label definitions
    settings.html     # Optional: Settings UI template
    README.md         # Plugin documentation
```

## Plugin Registration Pattern

```python
def register_plugin(app):
    '''Register plugin with the Flask app.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata with name, version, author, description
    '''
    # Register routes, labels, etc.
    from . import routes
    app.register_blueprint(routes.bp)

    return {
        'name': 'My Plugin',
        'version': '1.0.0',
        'author': 'Author Name',
        'description': 'Plugin description'
    }
```

## Enable/Disable

Plugins can be enabled or disabled through the Extensions page (`/extensions`) without modifying code. The plugin state is persisted in the database and takes effect after restarting the application.
