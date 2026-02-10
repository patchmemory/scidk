# Plugin Label Endpoint Registry

## Overview

The Label Endpoint Registry allows plugins to register API endpoints that map to Label types in the SciDK schema. This enables plugins to provide external data integrations that appear automatically in the Integrations settings page.

## Architecture

### Components

1. **LabelEndpointRegistry** (`scidk/core/label_endpoint_registry.py`)
   - Central registry for plugin-registered endpoints
   - Initialized during app startup before plugins are loaded
   - Accessible via `app.extensions['scidk']['label_endpoints']`

2. **API Endpoints** (`scidk/web/routes/api_settings.py`)
   - `GET /api/settings/plugin-endpoints` - List all plugin endpoints
   - `GET /api/settings/plugin-endpoints/<path>` - Get specific endpoint

3. **UI Integration** (`scidk/ui/templates/settings/_integrations.html`)
   - Displays plugin endpoints in Settings > Integrations page
   - Shows endpoint name, path, label type, plugin, and description
   - Read-only display (cannot be manually edited)

## Plugin Registration

### Basic Example

```python
def register_plugin(app):
    """Register the plugin with the Flask app."""

    # Get the label endpoint registry
    registry = app.extensions['scidk']['label_endpoints']

    # Register an endpoint
    registry.register({
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'ilab_plugin',
        'description': 'Integration with iLab service management system'
    })

    return {
        'name': 'iLab Plugin',
        'version': '1.0.0',
        'author': 'Your Name',
        'description': 'Plugin for iLab integration'
    }
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name shown in UI |
| `endpoint` | string | API endpoint path (must be unique) |
| `label_type` | string | Target Label type in schema |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auth_required` | boolean | `False` | Whether authentication is required |
| `test_url` | string | `None` | URL for testing connection |
| `plugin` | string | `'unknown'` | Plugin name (auto-populated) |
| `description` | string | `''` | Human-readable description |
| `config_schema` | dict | `{}` | JSON schema for configuration options |

## Usage in Integrations

Once registered, plugin endpoints:

1. **Appear in Settings > Integrations**
   - Listed in the "Plugin Endpoints" section
   - Show badge if authentication required
   - Display associated Label type

2. **Can be used in Integration workflows**
   - Select as source or target in integration definitions
   - Map to Label properties automatically
   - Leverage plugin-provided authentication

3. **Support testing**
   - If `test_url` provided, test connection button appears
   - Plugin must implement test endpoint handler

## Complete Example

See `plugins/example_ilab/` for a complete working example that demonstrates:
- Registering multiple endpoints
- Different Label types
- Authentication requirements
- Descriptive metadata

```python
# plugins/example_ilab/__init__.py
def register_plugin(app):
    registry = app.extensions['scidk']['label_endpoints']

    # Register services endpoint
    registry.register({
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab/services',
        'label_type': 'iLabService',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'example_ilab',
        'description': 'Integration with iLab service management system'
    })

    # Register equipment endpoint
    registry.register({
        'name': 'iLab Equipment',
        'endpoint': '/api/integrations/ilab/equipment',
        'label_type': 'Equipment',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'example_ilab',
        'description': 'Integration with iLab equipment inventory'
    })

    return {
        'name': 'iLab Integration',
        'version': '1.0.0',
        'author': 'SciDK Team',
        'description': 'Example plugin for iLab integration'
    }
```

## API Reference

### LabelEndpointRegistry Methods

#### `register(endpoint_config: dict) -> bool`
Register a new label endpoint.

**Returns:** `True` if successful, `False` if validation fails

#### `unregister(endpoint_path: str) -> bool`
Unregister an endpoint by path.

**Returns:** `True` if found and removed, `False` if not found

#### `get_endpoint(endpoint_path: str) -> Optional[dict]`
Get endpoint configuration by path.

**Returns:** Endpoint config dict or `None`

#### `list_endpoints() -> List[dict]`
List all registered endpoints.

**Returns:** List of endpoint config dicts

#### `list_by_plugin(plugin_name: str) -> List[dict]`
List endpoints registered by specific plugin.

**Returns:** Filtered list of endpoints

#### `list_by_label_type(label_type: str) -> List[dict]`
List endpoints that map to a specific label type.

**Returns:** Filtered list of endpoints

## Testing

The registry includes comprehensive unit tests in `tests/test_label_endpoint_registry.py`:

```bash
pytest tests/test_label_endpoint_registry.py -v
```

Tests cover:
- Basic registration and retrieval
- Field validation
- Duplicate handling
- Filtering by plugin and label type
- Edge cases and error handling

## Integration with Existing Systems

### Relationship to API Endpoint Registry

The Label Endpoint Registry is **separate** from the manual API Endpoint Registry (`api_endpoint_registry.py`):

| Feature | Manual Endpoints | Plugin Endpoints |
|---------|-----------------|------------------|
| Configuration | Settings UI | Plugin code |
| Storage | SQLite database | In-memory registry |
| Editability | User-editable | Read-only |
| Lifecycle | Persistent | Reset on restart |
| Use Case | User-configured APIs | Plugin-provided integrations |

Both types of endpoints can be used in Integration workflows.

### Relationship to Links/Integrations

Plugin endpoints appear as available sources/targets when creating integration definitions:
- Listed alongside manually configured endpoints
- Can be selected in integration wizard
- Map to Label types automatically

## Future Enhancements

Potential improvements for future iterations:

1. **Configuration UI** - Allow users to configure plugin endpoint parameters (URL, auth tokens) through UI
2. **Persistence** - Option to persist plugin endpoint configs to database
3. **Versioning** - Track endpoint schema versions for compatibility
4. **Discovery** - Auto-discover and suggest Label mappings based on data structure
5. **Monitoring** - Track endpoint usage and performance metrics

## Migration Notes

If you have existing plugins, no changes are required unless you want to register label endpoints. The registry is initialized automatically and available in all plugin `register_plugin()` calls via `app.extensions['scidk']['label_endpoints']`.
