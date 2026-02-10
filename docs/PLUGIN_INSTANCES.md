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
        'graph_behavior': {
            'can_create_label': True,
            'label_source': 'table_columns',
            'sync_strategy': 'on_demand',
            'supports_preview': True
        },
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

## Plugin Categories

Plugin templates must specify a `category` field that determines how they interact with the graph layer. Valid categories:

### data_import
- **Purpose**: Import tabular data to SQLite, can publish schemas as Labels
- **Graph Behavior**: Creates label definitions from table schemas
- **Examples**: table_loader, csv_importer, api_fetcher
- **Required Config**: `graph_behavior` block with:
  - `can_create_label`: Boolean (true for most data importers)
  - `label_source`: String ('table_columns' for table-based imports)
  - `sync_strategy`: 'on_demand' or 'automatic'
  - `supports_preview`: Boolean (true if preview supported)

### graph_inject
- **Purpose**: Directly create nodes + relationships in Neo4j
- **Graph Behavior**: Bypasses SQLite, writes directly to graph
- **Examples**: ontology_loader, knowledge_base_importer
- **Use Case**: Pre-structured graph data (OWL, RDF, knowledge bases)

### enrichment
- **Purpose**: Add properties to existing nodes without creating new labels
- **Graph Behavior**: Updates existing nodes, no schema changes
- **Examples**: metadata_enricher, annotation_engine
- **Use Case**: Add computed properties, external metadata

### exporter
- **Purpose**: Read from graph/database, no graph writes (default)
- **Graph Behavior**: None (read-only)
- **Examples**: report_generator, backup_exporter
- **Use Case**: Export data, generate reports

**Default**: If no category specified, defaults to `exporter` for backward compatibility.

**Validation**: PluginTemplateRegistry validates categories on registration and logs warnings for data_import plugins missing recommended `graph_behavior` config.

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

## Graph Integration

### Plugin → Label → Integration Architecture

Plugin instances can publish their data schemas to the **Labels page**, creating a clean path from data import to graph relationships:

```
Plugin Instance → Publishes Schema → Label Definition → Used in Integrations
```

### Publishing Labels from Plugin Instances

**For `data_import` category plugins** (e.g., table_loader):

1. **During Instance Creation**: Optionally configure graph integration in wizard
   - Enable "Create Label from this data"
   - Specify label name (auto-generated from table name)
   - Select primary key column
   - Choose sync strategy (on-demand or automatic)

2. **Label Registration**: Instance publishes schema to Labels page
   ```bash
   POST /api/plugins/instances/{id}/publish-label
   {
     "label_name": "LabEquipment",
     "primary_key": "serial_number",
     "sync_strategy": "on_demand"
   }
   ```

3. **Schema Auto-Detection**: Properties inferred from SQLite table structure
   - Column names → property names
   - Column types → property types (string, integer, boolean, etc.)
   - NOT NULL constraints → required properties

4. **Label Appears**: Labels page shows new label with plugin source badge:
   - 📦 Plugin: iLab Equipment 2024
   - 45 rows in SQLite, 0 nodes in graph

5. **Sync to Neo4j**: User clicks [Sync to Neo4j] button
   - Reads data from SQLite table
   - Creates/updates nodes in Neo4j
   - Records sync timestamp and node count

6. **Available in Integrations**: Label automatically discovered by Integrations page
   - Can create relationships with other labels
   - Example: LabEquipment → USED_BY → Researcher

### Plugin Categories

**data_import**: Imports tabular data, can publish labels
- Examples: table_loader, csv_importer, api_fetcher
- Graph behavior: Creates label from table schema

**graph_inject**: Directly injects graph (nodes + relationships)
- Examples: ontology_loader, knowledge_base_importer
- Graph behavior: Registers labels it creates (read-only)

**enrichment**: Adds properties to existing nodes
- Examples: metadata_enricher, annotation_engine
- Graph behavior: No new labels

**exporter**: Reads data, no graph writes
- Examples: report_generator, backup_exporter
- Graph behavior: None

### Example: Table Loader with Graph Integration

```python
# 1. Create instance with graph config
instance_config = {
    "template_id": "table_loader",
    "name": "iLab Equipment 2024",
    "config": {
        "file_path": "/data/equipment.xlsx",
        "table_name": "ilab_equipment_2024"
    },
    "graph_config": {
        "create_label": True,
        "label_name": "LabEquipment",
        "primary_key": "serial_number",
        "sync_strategy": "on_demand"
    }
}

# 2. Instance automatically publishes label
# Label "LabEquipment" now appears on Labels page

# 3. User syncs to Neo4j
POST /api/labels/LabEquipment/sync
# → Creates 45 nodes in Neo4j

# 4. User creates integration
Integration:
  Source: LabEquipment
  Target: Researcher
  Relationship: USED_BY
  Match: equipment.user_id = researcher.id
```

### Database Schema

**label_definitions** (extended):
```sql
CREATE TABLE label_definitions (
  name TEXT PRIMARY KEY,
  properties TEXT,  -- JSON: property schema
  source_type TEXT DEFAULT 'manual',  -- 'manual', 'plugin_instance', 'system'
  source_id TEXT,  -- Plugin instance ID if source_type='plugin_instance'
  sync_config TEXT,  -- JSON: {primary_key, sync_strategy, last_sync_at, last_sync_count}
  created_at REAL,
  updated_at REAL
);
```

**plugin_instances** (extended):
```sql
ALTER TABLE plugin_instances ADD COLUMN published_label TEXT;
ALTER TABLE plugin_instances ADD COLUMN graph_config TEXT;
```

### API Endpoints

- `POST /api/plugins/instances/{id}/publish-label` - Publish label schema
- `GET /api/labels/list` - List all labels (system + plugin + manual)
- `POST /api/labels/{name}/sync` - Sync label data to Neo4j
- `GET /api/labels/{name}/preview` - Preview data (first 10 rows)

### UI Workflows

**Workflow 1: Create Plugin Instance → Label → Integration**
1. Settings > Plugins > "+ New Plugin Instance"
2. Select "Table Loader"
3. Configure file + table
4. Enable "Graph Integration"
5. Label name: "LabEquipment", Primary key: "serial_number"
6. Create instance
7. Navigate to Labels page → See "LabEquipment (📦 Plugin)"
8. Click [Sync to Neo4j] → 45 nodes created
9. Navigate to Integrations → Create "LabEquipment → STORED_IN → Folder"

**Workflow 2: Update Plugin Data → Re-sync**
1. Update Excel file with new equipment
2. Navigate to Settings > Plugins
3. Click [Sync Now] on instance card
4. Navigate to Labels page
5. Click [Sync to Neo4j]
6. Updated nodes reflected in graph

### Related Documentation

- **Feature Design**: `dev/features/plugins/feature-plugin-label-integration.md`
- **Task List**: See `feature-plugin-label-integration.md` for implementation tasks
- **Architecture**: `docs/ARCHITECTURE.md` - Plugin system overview

## Future Enhancements

- **Scheduling**: Cron-based auto-execution of instances
- **Webhooks**: Trigger instances via webhook URLs
- **Dependencies**: Instance A depends on Instance B
- **Notifications**: Email/Slack alerts on execution completion/errors
- **Versioning**: Track instance config changes over time
- **Rollback**: Revert to previous instance configuration
- **Multi-Label Plugins**: graph_inject plugins publish multiple labels
- **Schema Migrations**: Handle schema changes in plugin data
- **Automatic Sync**: Trigger sync on plugin execution completion

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
