"""iLab Data Importer Plugin for SciDK.

This plugin provides a branded table loader specifically designed for iLab core facility data.
It includes presets for common iLab exports (Equipment, Services, PI Directory) with
column hints and suggested label mappings.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def handle_ilab_import(instance_config: dict) -> dict:
    """Execute iLab data import with preset-specific enhancements.

    Args:
        instance_config: Instance configuration containing:
            - preset: One of 'equipment', 'services', 'pi_directory', or 'custom'
            - file_path: Path to the iLab export file
            - table_name: Name of the SQLite table to create/update
            - instance_name: Friendly name for this import

    Returns:
        dict: Import result with status, row count, columns, and table name

    Raises:
        ValueError: If required configuration is missing or invalid
        FileNotFoundError: If the file doesn't exist
        Exception: For other import errors
    """
    from plugins.table_loader import handle_table_import

    # Get preset configuration if specified
    preset = instance_config.get('preset')
    preset_configs = _get_preset_configs()

    # Apply preset defaults if available
    if preset and preset in preset_configs:
        preset_config = preset_configs[preset]

        # Auto-fill table name if not provided
        if not instance_config.get('table_name'):
            table_name_hint = preset_config['table_name_hint']
            # Replace YYYY with current year
            current_year = datetime.now().year
            instance_config['table_name'] = table_name_hint.replace('YYYY', str(current_year))

        # Store column hints and suggested labels for UI display
        instance_config['_column_hints'] = preset_config.get('column_hints', {})
        instance_config['_suggested_labels'] = preset_config.get('suggested_labels', [])

    # Delegate to generic table loader for actual import
    result = handle_table_import(instance_config)

    # Add iLab-specific metadata to result
    result['plugin'] = 'ilab_importer'
    if preset:
        result['preset'] = preset
        result['preset_name'] = preset_configs[preset]['name']

    return result


def _get_preset_configs() -> dict:
    """Get preset configurations for iLab data types.

    Returns:
        dict: Preset configurations keyed by preset ID
    """
    return {
        'equipment': {
            'name': 'iLab Equipment',
            'table_name_hint': 'ilab_equipment_YYYY',
            'column_hints': {
                'Service Name': 'name',
                'Core': 'core_facility',
                'PI': 'principal_investigator',
                'Location': 'location',
                'Equipment ID': 'equipment_id',
                'Description': 'description'
            },
            'suggested_labels': ['Equipment', 'LabResource']
        },
        'services': {
            'name': 'iLab Services',
            'table_name_hint': 'ilab_services_YYYY',
            'column_hints': {
                'Service Name': 'name',
                'Core': 'core_facility',
                'Rate Per Hour': 'hourly_rate',
                'Service ID': 'service_id',
                'Active': 'is_active'
            },
            'suggested_labels': ['iLabService']
        },
        'pi_directory': {
            'name': 'PI Directory',
            'table_name_hint': 'ilab_pi_directory',
            'column_hints': {
                'PI Name': 'name',
                'Email': 'email',
                'Department': 'department',
                'Lab': 'lab_name',
                'Phone': 'phone',
                'Office': 'office_location'
            },
            'suggested_labels': ['PrincipalInvestigator', 'Researcher']
        }
    }


def register_plugin(app):
    """Register the iLab Data Importer plugin template with SciDK.

    This plugin registers a specialized table loader template for iLab core facility data
    with branded UI, presets, and helpful column hints.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata
    """
    # Get the plugin template registry from app extensions
    registry = app.extensions['scidk']['plugin_templates']

    # Register the iLab Data Importer template
    success = registry.register({
        'id': 'ilab_importer',
        'name': 'iLab Data Importer',
        'description': 'Upload iLab export spreadsheets (CSV or Excel format). Specialized importer with presets for Equipment, Services, and PI Directory.',
        'category': 'data_import',
        'icon': '🧪',
        'supports_multiple_instances': True,
        'version': '1.0.0',
        'branding': {
            'css_class': 'ilab-template',
            'color': '#0066cc'
        },
        'preset_configs': _get_preset_configs(),
        'config_schema': {
            'type': 'object',
            'properties': {
                'instance_name': {
                    'type': 'string',
                    'description': 'Friendly name for this iLab import configuration',
                    'required': True
                },
                'preset': {
                    'type': 'string',
                    'enum': ['equipment', 'services', 'pi_directory', 'custom'],
                    'default': 'equipment',
                    'description': 'iLab data type preset'
                },
                'file_path': {
                    'type': 'string',
                    'description': 'Path to the iLab export file (CSV or Excel)',
                    'required': True
                },
                'table_name': {
                    'type': 'string',
                    'description': 'SQLite table name (auto-filled from preset)',
                    'pattern': '^[a-zA-Z_][a-zA-Z0-9_]*$'
                },
                'file_type': {
                    'type': 'string',
                    'enum': ['csv', 'excel', 'auto'],
                    'default': 'auto',
                    'description': 'File type (auto-detected if not specified)'
                },
                'has_header': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Whether the file has a header row'
                },
                'replace_existing': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Replace existing table data'
                }
            }
        },
        'handler': handle_ilab_import
    })

    if success:
        logger.info("iLab Data Importer plugin template registered successfully")
    else:
        logger.error("Failed to register iLab Data Importer plugin template")

    # Return plugin metadata
    return {
        'name': 'iLab Data Importer',
        'version': '1.0.0',
        'author': 'SciDK Team',
        'description': 'Specialized importer for iLab core facility data with branded UI and helpful presets'
    }
