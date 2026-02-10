# iLab Data Importer Plugin

## Overview

The **iLab Data Importer** is a specialized plugin for importing iLab core facility data into SciDK. It provides a branded user experience with preset configurations for common iLab export types, column hints, and suggested label mappings.

## Features

- **🧪 Branded UI**: Distinctive visual styling with iLab icon and color scheme
- **Preset Configurations**: Pre-configured templates for:
  - Equipment inventory
  - Services catalog
  - PI Directory
- **Column Hints**: Helpful mappings showing how iLab columns map to SciDK properties
- **Suggested Labels**: Recommended label types for graph integration
- **Auto-fill Table Names**: Smart defaults with year insertion (e.g., `ilab_equipment_2024`)

## Installation

The iLab Data Importer plugin is included with SciDK and located in `plugins/ilab_table_loader/`.

No additional installation steps are required - the plugin is automatically discovered on startup.

## Usage

### Creating an iLab Import Instance

1. Navigate to **Settings > Plugins**
2. Scroll to the **Plugin Instances** section
3. Click **"+ New Plugin Instance"**
4. Select **"iLab Data Importer"** (identified by the 🧪 icon)
5. Choose a preset or select "Custom" for manual configuration
6. Upload your iLab export file (CSV or Excel format)
7. Configure graph integration (optional)
8. Click **"Create Instance"**

### Available Presets

#### Equipment Preset

**Use for**: iLab equipment inventory exports

**Expected columns**:
- Service Name → `name`
- Core → `core_facility`
- PI → `principal_investigator`
- Location → `location`
- Equipment ID → `equipment_id`
- Description → `description`

**Suggested labels**: `Equipment`, `LabResource`

**Table name hint**: `ilab_equipment_YYYY` (YYYY = current year)

#### Services Preset

**Use for**: iLab services catalog exports

**Expected columns**:
- Service Name → `name`
- Core → `core_facility`
- Rate Per Hour → `hourly_rate`
- Service ID → `service_id`
- Active → `is_active`

**Suggested labels**: `iLabService`

**Table name hint**: `ilab_services_YYYY`

#### PI Directory Preset

**Use for**: Principal Investigator directory exports

**Expected columns**:
- PI Name → `name`
- Email → `email`
- Department → `department`
- Lab → `lab_name`
- Phone → `phone`
- Office → `office_location`

**Suggested labels**: `PrincipalInvestigator`, `Researcher`

**Table name hint**: `ilab_pi_directory`

## Example Workflow

### Step 1: Export Data from iLab

Export your data from iLab in CSV or Excel format. The iLab Data Importer supports standard iLab export formats.

### Step 2: Create Plugin Instance

```
Settings > Plugins > "+ New Plugin Instance" > iLab Data Importer
```

Select the **Equipment** preset for equipment data.

### Step 3: Upload File

Browse to your iLab export file (e.g., `equipment_export_2024.xlsx`)

The table name will auto-fill to `ilab_equipment_2024`

### Step 4: Configure Graph Integration (Optional)

Enable **"Create Label from this data"** to sync equipment to Neo4j:
- Label Name: `LabEquipment`
- Primary Key: `equipment_id` (or appropriate unique column)
- Sync Strategy: On-demand or Automatic

### Step 5: Import and Sync

Click **"Create Instance"** to import the data.

If graph integration is enabled, data will be synced to Neo4j as nodes with the specified label.

## File Format Requirements

### Supported File Types
- CSV (`.csv`)
- Excel (`.xlsx`, `.xls`)
- TSV (`.tsv`)

### Requirements
- Files must have a header row with column names
- Column names should match iLab export format (or use Custom preset)
- No special characters in table names (alphanumeric and underscores only)

## Graph Integration

The iLab Data Importer integrates with SciDK's knowledge graph system:

1. **Label Creation**: Data is imported into a SQLite table
2. **Label Registration**: A Label schema is created linking to the table
3. **Neo4j Sync**: Rows are synced to Neo4j as nodes
4. **Relationship Support**: Link equipment/services to projects, samples, or other entities

### Recommended Label Mappings

| iLab Export Type | Recommended Label | Primary Key Column |
|------------------|-------------------|-------------------|
| Equipment | `Equipment` or `LabResource` | `Equipment ID` |
| Services | `iLabService` | `Service ID` |
| PI Directory | `PrincipalInvestigator` | `Email` |

## Configuration Options

### Instance Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instance_name` | string | Yes | Friendly name for this import |
| `preset` | enum | No | One of: equipment, services, pi_directory, custom |
| `file_path` | string | Yes | Path to iLab export file |
| `table_name` | string | No | SQLite table name (auto-filled from preset) |
| `file_type` | enum | No | csv, excel, tsv, or auto (default: auto) |
| `has_header` | boolean | No | Whether file has header row (default: true) |
| `replace_existing` | boolean | No | Replace existing table data (default: true) |

### Graph Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label_name` | string | Yes* | Label name for Neo4j nodes |
| `primary_key` | string | Yes* | Column to use as unique identifier |
| `sync_strategy` | enum | No | on_demand or automatic (default: on_demand) |

*Required if graph integration is enabled

## Sample Data

Sample iLab export files are available in `tests/fixtures/`:
- `ilab_equipment_sample.xlsx` - Equipment inventory sample
- `ilab_services_sample.xlsx` - Services catalog sample
- `ilab_pi_directory_sample.xlsx` - PI directory sample

Use these files for testing or as templates for your iLab exports.

## Troubleshooting

### Problem: Plugin doesn't appear in template list

**Solution**:
1. Check that the plugin is in `plugins/ilab_table_loader/`
2. Restart the SciDK application
3. Check logs for plugin loading errors

### Problem: Column names don't match hints

**Solution**: Use the **Custom** preset and manually configure column mappings, or rename columns in your iLab export to match expected names.

### Problem: Table name is invalid

**Solution**: Table names must start with a letter or underscore and contain only alphanumeric characters and underscores. The plugin validates this automatically.

### Problem: Import fails with file error

**Solution**:
1. Verify file path is correct
2. Check file format is CSV or Excel
3. Ensure file has a header row
4. Check for special characters or encoding issues

## API Reference

### Handler Function

```python
handle_ilab_import(instance_config: dict) -> dict
```

**Parameters**:
- `instance_config`: Configuration dictionary with preset, file_path, table_name, etc.

**Returns**:
- `dict` with keys:
  - `status`: 'success' or 'error'
  - `plugin`: 'ilab_importer'
  - `preset`: Preset ID (if used)
  - `preset_name`: Human-readable preset name
  - `table_name`: SQLite table name
  - `row_count`: Number of rows imported
  - `columns`: List of column names

### Plugin Registration

```python
register_plugin(app) -> dict
```

Registers the iLab Data Importer template with the plugin system.

**Returns**: Plugin metadata dictionary

## Development

### Running Tests

```bash
pytest tests/test_ilab_plugin.py -v
```

### Adding New Presets

Edit `plugins/ilab_table_loader/__init__.py` and add to `_get_preset_configs()`:

```python
'my_preset': {
    'name': 'My Custom Preset',
    'table_name_hint': 'my_table_YYYY',
    'column_hints': {
        'iLab Column': 'scidk_property'
    },
    'suggested_labels': ['MyLabel']
}
```

## See Also

- [Plugin System Documentation](../PLUGINS.md)
- [Table Loader Plugin](./TABLE_LOADER.md)
- [Label System Documentation](../LABELS.md)
- [Graph Integration Guide](../GRAPH_INTEGRATION.md)

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review [SciDK Documentation](../../README.md)
- File an issue on the project repository
