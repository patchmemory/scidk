"""Table Loader Plugin for SciDK.

This plugin template enables importing spreadsheet files (CSV, Excel, TSV) into SQLite tables.
Users can create multiple instances of this plugin for different data sources.

Example instances:
    - "iLab Equipment 2024": Loads equipment.xlsx into ilab_equipment_2024 table
    - "PI Directory": Loads pi_directory.csv into pi_directory table
    - "Lab Resources Q1": Loads resources.tsv into lab_resources_q1 table
"""

import logging
from .importer import TableImporter

logger = logging.getLogger(__name__)


def handle_table_import(instance_config: dict) -> dict:
    """Execute the table import based on instance configuration.

    Args:
        instance_config: Instance configuration containing:
            - file_path: Path to the file to import
            - table_name: Name of the SQLite table to create/update
            - file_type: Type of file (csv, excel, tsv) - optional, auto-detected if not provided
            - has_header: Whether the file has a header row (default: True)
            - replace_existing: Whether to replace existing table data (default: True)
            - sheet_name: For Excel files, which sheet to import (default: 0)

    Returns:
        dict: Import result with status, row count, columns, and table name

    Raises:
        ValueError: If required configuration is missing or invalid
        FileNotFoundError: If the file doesn't exist
        Exception: For other import errors
    """
    importer = TableImporter()
    return importer.import_table(instance_config)


def register_plugin(app):
    """Register the table loader plugin template with SciDK.

    This plugin registers a template that can be instantiated multiple times
    by users to import different spreadsheet files into SQLite tables.

    Args:
        app: Flask application instance

    Returns:
        dict: Plugin metadata
    """
    # Get the plugin template registry from app extensions
    registry = app.extensions['scidk']['plugin_templates']

    # Register the table loader template
    success = registry.register({
        'id': 'table_loader',
        'name': 'Table Loader',
        'description': 'Import spreadsheets (CSV, Excel, TSV) into SQLite tables for querying and analysis',
        'category': 'data_import',
        'icon': '📊',
        'supports_multiple_instances': True,
        'version': '1.0.0',
        'config_schema': {
            'type': 'object',
            'properties': {
                'instance_name': {
                    'type': 'string',
                    'description': 'Friendly name for this import configuration',
                    'required': True
                },
                'file_path': {
                    'type': 'string',
                    'description': 'Path to the spreadsheet file to import',
                    'required': True
                },
                'table_name': {
                    'type': 'string',
                    'description': 'Name of the SQLite table to create/update',
                    'required': True,
                    'pattern': '^[a-zA-Z_][a-zA-Z0-9_]*$'  # Valid SQL identifier
                },
                'file_type': {
                    'type': 'string',
                    'enum': ['csv', 'excel', 'tsv', 'auto'],
                    'default': 'auto',
                    'description': 'File type (auto-detected from extension if not specified)'
                },
                'has_header': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Whether the file has a header row with column names'
                },
                'replace_existing': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Replace existing table data (True) or append (False)'
                },
                'sheet_name': {
                    'type': 'string',
                    'default': '0',
                    'description': 'For Excel files: sheet name or index (0-based)'
                }
            }
        },
        'handler': handle_table_import,
        'preset_configs': {
            'csv_import': {
                'name': 'CSV Import',
                'description': 'Import a CSV file with headers',
                'config': {
                    'file_type': 'csv',
                    'has_header': True,
                    'replace_existing': True
                }
            },
            'excel_import': {
                'name': 'Excel Import',
                'description': 'Import an Excel spreadsheet',
                'config': {
                    'file_type': 'excel',
                    'has_header': True,
                    'replace_existing': True,
                    'sheet_name': '0'
                }
            },
            'tsv_import': {
                'name': 'TSV Import',
                'description': 'Import a tab-separated values file',
                'config': {
                    'file_type': 'tsv',
                    'has_header': True,
                    'replace_existing': True
                }
            }
        }
    })

    if success:
        logger.info("Table Loader plugin template registered successfully")
    else:
        logger.error("Failed to register Table Loader plugin template")

    # Return plugin metadata
    return {
        'name': 'Table Loader',
        'version': '1.0.0',
        'author': 'SciDK Team',
        'description': 'Generic spreadsheet importer for CSV, Excel, and TSV files. '
                      'Creates SQLite tables that can be queried and linked to the knowledge graph.'
    }
