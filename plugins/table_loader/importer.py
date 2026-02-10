"""Table import logic for the Table Loader plugin.

This module handles the actual import of spreadsheet files into SQLite tables
using pandas for file reading and SQLite for storage.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class TableImporter:
    """Handles importing spreadsheet files into SQLite tables."""

    def __init__(self, db_path: str = 'scidk_settings.db'):
        """Initialize the table importer.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def _detect_file_type(self, file_path: str, file_type: str = 'auto') -> str:
        """Detect the file type from the file extension.

        Args:
            file_path: Path to the file
            file_type: Explicit file type or 'auto' for detection

        Returns:
            str: Detected file type (csv, excel, tsv)

        Raises:
            ValueError: If file type cannot be determined or is unsupported
        """
        if file_type != 'auto':
            return file_type

        # Auto-detect from extension
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in ['.csv']:
            return 'csv'
        elif ext in ['.xlsx', '.xls', '.xlsm']:
            return 'excel'
        elif ext in ['.tsv', '.tab']:
            return 'tsv'
        else:
            raise ValueError(f"Unsupported file extension: {ext}. Use .csv, .xlsx, .xls, or .tsv")

    def _read_file(self, file_path: str, file_type: str, has_header: bool = True,
                   sheet_name: Optional[str] = None) -> pd.DataFrame:
        """Read the file into a pandas DataFrame.

        Args:
            file_path: Path to the file to read
            file_type: Type of file (csv, excel, tsv)
            has_header: Whether the file has a header row
            sheet_name: For Excel files, sheet name or index

        Returns:
            pd.DataFrame: The loaded data

        Raises:
            FileNotFoundError: If the file doesn't exist
            Exception: For other read errors
        """
        # Check if file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Set header parameter for pandas
        header = 0 if has_header else None

        try:
            if file_type == 'csv':
                df = pd.read_csv(file_path, header=header)
            elif file_type == 'tsv':
                df = pd.read_csv(file_path, sep='\t', header=header)
            elif file_type == 'excel':
                # Handle sheet_name parameter
                if sheet_name:
                    # Try as integer first (index), then as string (name)
                    try:
                        sheet = int(sheet_name)
                    except ValueError:
                        sheet = sheet_name
                else:
                    sheet = 0  # Default to first sheet

                df = pd.read_excel(file_path, sheet_name=sheet, header=header)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            # If no header, generate column names
            if not has_header:
                df.columns = [f'col_{i}' for i in range(len(df.columns))]

            logger.info(f"Successfully read file: {file_path} ({len(df)} rows, {len(df.columns)} columns)")
            return df

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise

    def _sanitize_table_name(self, table_name: str) -> str:
        """Sanitize the table name to be a valid SQLite identifier.

        Args:
            table_name: The table name to sanitize

        Returns:
            str: Sanitized table name

        Raises:
            ValueError: If table name is invalid
        """
        # Basic validation
        if not table_name:
            raise ValueError("Table name cannot be empty")

        # Check for valid SQL identifier (alphanumeric + underscore, not starting with digit)
        if not table_name[0].isalpha() and table_name[0] != '_':
            raise ValueError(f"Table name must start with letter or underscore: {table_name}")

        for char in table_name:
            if not (char.isalnum() or char == '_'):
                raise ValueError(f"Table name contains invalid character: {char}")

        return table_name

    def import_table(self, config: dict) -> dict:
        """Import a spreadsheet file into a SQLite table.

        Args:
            config: Import configuration dict with keys:
                - file_path: Path to the file (required)
                - table_name: Name of the table (required)
                - file_type: File type or 'auto' (default: 'auto')
                - has_header: Whether file has header (default: True)
                - replace_existing: Replace or append (default: True)
                - sheet_name: For Excel, sheet to import (default: 0)

        Returns:
            dict: Import result with keys:
                - status: 'success' or 'error'
                - message: Status message
                - rows_imported: Number of rows imported
                - columns: List of column names
                - table_name: Name of the table
                - file_path: Path to the imported file

        Raises:
            ValueError: If required configuration is missing or invalid
        """
        # Validate required fields
        if 'file_path' not in config:
            raise ValueError("Missing required field: file_path")
        if 'table_name' not in config:
            raise ValueError("Missing required field: table_name")

        file_path = config['file_path']
        file_type = config.get('file_type', 'auto')
        has_header = config.get('has_header', True)
        replace_existing = config.get('replace_existing', True)
        sheet_name = config.get('sheet_name', '0')

        try:
            # Sanitize table name (may raise ValueError)
            table_name = self._sanitize_table_name(config['table_name'])
            # Detect file type
            detected_type = self._detect_file_type(file_path, file_type)
            logger.info(f"Importing {detected_type} file: {file_path} -> table: {table_name}")

            # Read the file
            df = self._read_file(file_path, detected_type, has_header, sheet_name)

            # Get database connection
            conn = self._get_connection()

            # Determine if_exists behavior
            if_exists = 'replace' if replace_existing else 'append'

            # Write to SQLite
            df.to_sql(table_name, conn, if_exists=if_exists, index=False)

            conn.close()

            result = {
                'status': 'success',
                'message': f'Successfully imported {len(df)} rows into table {table_name}',
                'rows_imported': len(df),
                'columns': list(df.columns),
                'table_name': table_name,
                'file_path': file_path,
                'file_type': detected_type
            }

            logger.info(f"Import successful: {result['message']}")
            return result

        except FileNotFoundError as e:
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg,
                'rows_imported': 0,
                'columns': [],
                'table_name': table_name,
                'file_path': file_path,
                'error': str(e)
            }

        except ValueError as e:
            error_msg = f"Invalid configuration: {str(e)}"
            logger.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg,
                'rows_imported': 0,
                'columns': [],
                'table_name': config.get('table_name', ''),
                'file_path': file_path,
                'error': str(e)
            }

        except Exception as e:
            error_msg = f"Import failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'status': 'error',
                'message': error_msg,
                'rows_imported': 0,
                'columns': [],
                'table_name': config.get('table_name', ''),
                'file_path': file_path,
                'error': str(e)
            }
