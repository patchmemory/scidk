# Plugin Instance Framework

## Overview

The Plugin Instance Framework allows users to create multiple instances of plugin templates via the UI. This separates plugin code (templates) from user configuration (instances).

**Analogy**: Plugin templates are like application classes, while plugin instances are like object instances with specific configurations.

## Architecture

### Components

1. **PluginTemplateRegistry** (`scidk/core/plugin_template_registry.py`)
   - Manages plugin templates (code-based)
   - Templates define capabilities, config schema, and execution handler
   - Examples: `table_loader`, `api_fetcher`, `file_importer`

2. **PluginInstanceManager** (`scidk/core/plugin_instance_manager.py`)
   - Manages user-created instances (stored in SQLite)
   - Each instance has: ID, name, template_id, config, status, timestamps
   - Tracks execution history and results

3. **API Endpoints** (`scidk/web/routes/api_plugins.py`)
   - `GET /api/plugins/templates` - List templates
   - `GET /api/plugins/instances` - List instances
   - `POST /api/plugins/instances` - Create instance
   - `PUT /api/plugins/instances/<id>` - Update instance
   - `DELETE /api/plugins/instances/<id>` - Delete instance
   - `POST /api/plugins/instances/<id>/execute` - Execute instance

## Template Registration

Plugin templates register themselves during plugin loading:

```python
# plugins/table_loader/__init__.py
def register_plugin(app):
    """Register table loader template."""

    registry = app.extensions['scidk']['plugin_templates']

    registry.register({
        'id': 'table_loader',
        'name': 'Table Loader',
        'description': 'Import spreadsheets into SQLite tables',
        'category': 'data_import',
        'supports_multiple_instances': True,  # Users can create many instances
        'config_schema': {
            'type': 'object',
            'properties': {
                'instance_name': {'type': 'string', 'required': True},
                'file_path': {'type': 'string'},
                'table_name': {'type': 'string', 'required': True},
            }
        },
        'handler': handle_table_import  # Function to execute
    })

    return {
        'name': 'Table Loader',
        'version': '1.0.0'
    }

def handle_table_import(instance_config):
    """Execute the template logic with instance config."""
    file_path = instance_config['file_path']
    table_name = instance_config['table_name']

    # Import logic here
    # ...

    return {
        'status': 'success',
        'rows_imported': 45,
        'columns': ['name', 'location']
    }
```

## Instance Management

### Creating an Instance via API

```bash
curl -X POST http://localhost:5000/api/plugins/instances \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "table_loader",
    "name": "iLab Equipment 2024",
    "config": {
      "file_path": "/data/equipment.xlsx",
      "table_name": "ilab_equipment_2024"
    }
  }'
```

### Executing an Instance

```bash
curl -X POST http://localhost:5000/api/plugins/instances/<instance_id>/execute
```

This calls the template's handler function with the instance configuration and records the result.

## Database Schema

```sql
CREATE TABLE plugin_instances (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    config TEXT NOT NULL,  -- JSON
    enabled INTEGER DEFAULT 1,
    status TEXT,  -- 'pending', 'active', 'inactive', 'error'
    last_run REAL,
    last_result TEXT,  -- JSON
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
```

## Use Cases

### Use Case 1: Multiple Data Imports

A lab admin wants to track multiple data sources:
- Instance 1: "iLab Equipment 2024" (table_loader template)
- Instance 2: "PI Directory" (table_loader template)
- Instance 3: "Lab Resources Q1" (table_loader template)

Each instance has its own file, table name, and sync schedule.

### Use Case 2: API Integrations

Researcher wants to pull data from multiple APIs:
- Instance 1: "PubMed Latest Papers" (api_fetcher template)
- Instance 2: "GitHub Repositories" (api_fetcher template)
- Instance 3: "Slack Notifications" (api_fetcher template)

Each instance has different API credentials, endpoints, and sync intervals.

## Template Categories

- **data_import**: Import data from files (CSV, Excel, EDA, BioPAX)
- **api_fetcher**: Fetch data from external APIs
- **file_importer**: Import from specialized file formats
- **exporter**: Export data to external systems
- **transformer**: Transform/process existing data

## Best Practices

### For Template Developers

1. **Idempotent handlers**: Handlers should be safe to re-execute
2. **Clear error messages**: Return descriptive errors in results
3. **Config validation**: Validate config before execution
4. **Progress tracking**: Return row counts, statistics in results
5. **Resource cleanup**: Clean up temp files, connections

### For Instance Configurations

1. **Descriptive names**: "iLab Equipment 2024" not "Import 1"
2. **Version in name**: Include year/quarter for time-series data
3. **Enable/disable**: Use enabled flag instead of deleting instances
4. **Test before production**: Test with small datasets first

## Future Enhancements

- **Scheduling**: Cron-based auto-execution of instances
- **Webhooks**: Trigger instances via webhook URLs
- **Dependencies**: Instance A depends on Instance B
- **Notifications**: Email/Slack alerts on execution completion/errors
- **Versioning**: Track instance config changes over time
- **Rollback**: Revert to previous instance configuration

## Migration from Code-based Plugins

Existing plugins can be gradually migrated to use templates:

**Before** (single-instance plugin):
```python
def register_plugin(app):
    # Hard-coded configuration
    api_url = "https://api.example.com"

    @app.route('/my-plugin/sync')
    def sync():
        # ... sync logic ...
        pass
```

**After** (multi-instance template):
```python
def register_plugin(app):
    registry = app.extensions['scidk']['plugin_templates']

    registry.register({
        'id': 'my_plugin',
        'name': 'My Plugin',
        'supports_multiple_instances': True,
        'config_schema': {
            'properties': {
                'api_url': {'type': 'string'}
            }
        },
        'handler': sync_handler
    })

def sync_handler(instance_config):
    api_url = instance_config['api_url']
    # ... sync logic using api_url from instance ...
```

Now users can create multiple instances with different API URLs!
