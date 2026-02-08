"""
Table Format Registry for Links integration.

Manages persistent storage of table format configurations (CSV, TSV, Excel, Parquet)
for importing tabular data as Link source instances in the Links wizard.
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
import io


class TableFormatRegistry:
    """
    Registry for table format configurations.

    Stores format metadata including:
    - File type (CSV, TSV, Excel, Parquet)
    - Delimiter, encoding, header configuration
    - Column mappings to Label properties
    - Target label for data import
    """

    # Pre-programmed formats
    PREPROGRAMMED_FORMATS = {
        'csv_standard': {
            'name': 'CSV (Standard)',
            'file_type': 'csv',
            'delimiter': ',',
            'encoding': 'utf-8',
            'has_header': True,
            'header_row': 0,
            'description': 'Standard comma-separated values with UTF-8 encoding'
        },
        'tsv_standard': {
            'name': 'TSV (Standard)',
            'file_type': 'tsv',
            'delimiter': '\t',
            'encoding': 'utf-8',
            'has_header': True,
            'header_row': 0,
            'description': 'Tab-separated values with UTF-8 encoding'
        },
        'excel_standard': {
            'name': 'Excel (Standard)',
            'file_type': 'excel',
            'delimiter': None,
            'encoding': 'utf-8',
            'has_header': True,
            'header_row': 0,
            'description': 'Microsoft Excel (.xlsx) with first sheet'
        },
        'parquet_standard': {
            'name': 'Parquet (Standard)',
            'file_type': 'parquet',
            'delimiter': None,
            'encoding': 'utf-8',
            'has_header': True,
            'header_row': 0,
            'description': 'Apache Parquet columnar format with auto-detected schema'
        }
    }

    def __init__(self, db_path: str):
        """
        Initialize registry with SQLite database.

        Args:
            db_path: Path to settings database
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.db.row_factory = sqlite3.Row
        self.init_tables()

    def init_tables(self):
        """Create tables if they don't exist."""
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS table_formats (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                file_type TEXT NOT NULL,
                delimiter TEXT,
                encoding TEXT NOT NULL DEFAULT 'utf-8',
                has_header INTEGER NOT NULL DEFAULT 1,
                header_row INTEGER NOT NULL DEFAULT 0,
                sheet_name TEXT,
                target_label TEXT,
                column_mappings TEXT,
                description TEXT,
                is_preprogrammed INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.db.commit()

        # Seed preprogrammed formats if they don't exist
        self._seed_preprogrammed_formats()

    def _seed_preprogrammed_formats(self):
        """Insert preprogrammed formats if they don't exist."""
        for format_id, format_data in self.PREPROGRAMMED_FORMATS.items():
            existing = self._get_format_by_name_internal(format_data['name'])
            if not existing:
                now = datetime.now(timezone.utc).timestamp()
                self.db.execute(
                    """
                    INSERT INTO table_formats
                    (id, name, file_type, delimiter, encoding, has_header, header_row,
                     description, is_preprogrammed, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        format_id,
                        format_data['name'],
                        format_data['file_type'],
                        format_data['delimiter'],
                        format_data['encoding'],
                        1 if format_data['has_header'] else 0,
                        format_data['header_row'],
                        format_data['description'],
                        now,
                        now
                    )
                )
                self.db.commit()

    def _get_format_by_name_internal(self, name: str) -> Optional[Dict[str, Any]]:
        """Internal method to get format by name without full serialization."""
        cursor = self.db.execute(
            "SELECT * FROM table_formats WHERE name = ?",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def list_formats(self, include_preprogrammed: bool = True) -> List[Dict[str, Any]]:
        """
        Get all table format configurations.

        Args:
            include_preprogrammed: Whether to include pre-programmed formats

        Returns:
            List of format dicts
        """
        cursor = self.db.execute(
            """
            SELECT id, name, file_type, delimiter, encoding, has_header, header_row,
                   sheet_name, target_label, column_mappings, description,
                   is_preprogrammed, created_at, updated_at
            FROM table_formats
            ORDER BY is_preprogrammed DESC, name ASC
            """
        )
        rows = cursor.fetchall()

        formats = []
        for row in rows:
            if not include_preprogrammed and row['is_preprogrammed']:
                continue

            formats.append({
                'id': row['id'],
                'name': row['name'],
                'file_type': row['file_type'],
                'delimiter': row['delimiter'],
                'encoding': row['encoding'],
                'has_header': bool(row['has_header']),
                'header_row': row['header_row'],
                'sheet_name': row['sheet_name'],
                'target_label': row['target_label'],
                'column_mappings': json.loads(row['column_mappings']) if row['column_mappings'] else {},
                'description': row['description'],
                'is_preprogrammed': bool(row['is_preprogrammed']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })

        return formats

    def get_format(self, format_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific table format by ID.

        Args:
            format_id: Format ID

        Returns:
            Format dict or None if not found
        """
        cursor = self.db.execute(
            """
            SELECT id, name, file_type, delimiter, encoding, has_header, header_row,
                   sheet_name, target_label, column_mappings, description,
                   is_preprogrammed, created_at, updated_at
            FROM table_formats
            WHERE id = ?
            """,
            (format_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return {
            'id': row['id'],
            'name': row['name'],
            'file_type': row['file_type'],
            'delimiter': row['delimiter'],
            'encoding': row['encoding'],
            'has_header': bool(row['has_header']),
            'header_row': row['header_row'],
            'sheet_name': row['sheet_name'],
            'target_label': row['target_label'],
            'column_mappings': json.loads(row['column_mappings']) if row['column_mappings'] else {},
            'description': row['description'],
            'is_preprogrammed': bool(row['is_preprogrammed']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }

    def create_format(self, format_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new table format configuration.

        Args:
            format_data: Dict with keys:
                - name: Format name (required)
                - file_type: "csv", "tsv", "excel", "parquet" (required)
                - delimiter: Column delimiter (optional, for CSV/TSV)
                - encoding: File encoding (default: "utf-8")
                - has_header: Whether file has header row (default: True)
                - header_row: Row index of header (default: 0)
                - sheet_name: Sheet name for Excel files (optional)
                - target_label: Target Label name (optional)
                - column_mappings: Dict {table_column: {label_property, type_hint, ignore}} (optional)
                - description: Format description (optional)

        Returns:
            Created format dict with id

        Raises:
            ValueError: If required fields missing or format name exists
        """
        # Validation
        if not format_data.get('name'):
            raise ValueError("Format name is required")
        if not format_data.get('file_type'):
            raise ValueError("File type is required")

        valid_types = ['csv', 'tsv', 'excel', 'parquet']
        if format_data['file_type'] not in valid_types:
            raise ValueError(f"File type must be one of: {', '.join(valid_types)}")

        # Check for duplicate name
        existing = self._get_format_by_name_internal(format_data['name'])
        if existing:
            raise ValueError(f"Format with name '{format_data['name']}' already exists")

        # Generate ID and timestamps
        format_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).timestamp()

        # Extract fields with defaults
        name = format_data['name']
        file_type = format_data['file_type']
        delimiter = format_data.get('delimiter')
        encoding = format_data.get('encoding', 'utf-8')
        has_header = format_data.get('has_header', True)
        header_row = format_data.get('header_row', 0)
        sheet_name = format_data.get('sheet_name')
        target_label = format_data.get('target_label')
        column_mappings = format_data.get('column_mappings', {})
        description = format_data.get('description')

        # Insert into database
        self.db.execute(
            """
            INSERT INTO table_formats
            (id, name, file_type, delimiter, encoding, has_header, header_row,
             sheet_name, target_label, column_mappings, description,
             is_preprogrammed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                format_id,
                name,
                file_type,
                delimiter,
                encoding,
                1 if has_header else 0,
                header_row,
                sheet_name,
                target_label,
                json.dumps(column_mappings) if column_mappings else None,
                description,
                now,
                now
            )
        )
        self.db.commit()

        return self.get_format(format_id)

    def update_format(self, format_id: str, format_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing table format.

        Args:
            format_id: Format ID
            format_data: Dict with fields to update (same as create_format)

        Returns:
            Updated format dict

        Raises:
            ValueError: If format not found or is preprogrammed
        """
        existing = self.get_format(format_id)
        if not existing:
            raise ValueError(f"Format '{format_id}' not found")

        if existing['is_preprogrammed']:
            raise ValueError("Cannot modify preprogrammed formats")

        # Check for name conflict if name is being changed
        if 'name' in format_data and format_data['name'] != existing['name']:
            name_check = self._get_format_by_name_internal(format_data['name'])
            if name_check and name_check['id'] != format_id:
                raise ValueError(f"Format with name '{format_data['name']}' already exists")

        # Build update statement dynamically
        updates = []
        params = []

        if 'name' in format_data:
            updates.append("name = ?")
            params.append(format_data['name'])
        if 'file_type' in format_data:
            valid_types = ['csv', 'tsv', 'excel', 'parquet']
            if format_data['file_type'] not in valid_types:
                raise ValueError(f"File type must be one of: {', '.join(valid_types)}")
            updates.append("file_type = ?")
            params.append(format_data['file_type'])
        if 'delimiter' in format_data:
            updates.append("delimiter = ?")
            params.append(format_data['delimiter'])
        if 'encoding' in format_data:
            updates.append("encoding = ?")
            params.append(format_data['encoding'])
        if 'has_header' in format_data:
            updates.append("has_header = ?")
            params.append(1 if format_data['has_header'] else 0)
        if 'header_row' in format_data:
            updates.append("header_row = ?")
            params.append(format_data['header_row'])
        if 'sheet_name' in format_data:
            updates.append("sheet_name = ?")
            params.append(format_data['sheet_name'])
        if 'target_label' in format_data:
            updates.append("target_label = ?")
            params.append(format_data['target_label'])
        if 'column_mappings' in format_data:
            updates.append("column_mappings = ?")
            params.append(json.dumps(format_data['column_mappings']) if format_data['column_mappings'] else None)
        if 'description' in format_data:
            updates.append("description = ?")
            params.append(format_data['description'])

        # Update timestamp
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).timestamp())

        # Add format_id to params
        params.append(format_id)

        if updates:
            sql = f"UPDATE table_formats SET {', '.join(updates)} WHERE id = ?"
            self.db.execute(sql, params)
            self.db.commit()

        return self.get_format(format_id)

    def delete_format(self, format_id: str) -> bool:
        """
        Delete a table format.

        Args:
            format_id: Format ID

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If format is preprogrammed
        """
        existing = self.get_format(format_id)
        if not existing:
            return False

        if existing['is_preprogrammed']:
            raise ValueError("Cannot delete preprogrammed formats")

        self.db.execute("DELETE FROM table_formats WHERE id = ?", (format_id,))
        self.db.commit()
        return True

    def detect_format(self, file_content: bytes, filename: str = None) -> Dict[str, Any]:
        """
        Auto-detect table format from file content.

        Args:
            file_content: Raw file bytes
            filename: Original filename (for extension hints)

        Returns:
            Dict with detected format parameters:
                - file_type: Detected type
                - delimiter: Detected delimiter (for CSV/TSV)
                - encoding: Detected encoding
                - has_header: Whether header row detected
                - sample_columns: List of detected column names
                - error: Error message if detection failed
        """
        try:
            # Try to detect encoding
            encodings = ['utf-8', 'latin-1', 'utf-16']
            detected_encoding = 'utf-8'
            decoded_content = None

            for enc in encodings:
                try:
                    decoded_content = file_content.decode(enc)
                    detected_encoding = enc
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue

            if decoded_content is None:
                return {'error': 'Unable to decode file with supported encodings'}

            # Detect file type from extension
            file_type = None
            if filename:
                ext = filename.lower().split('.')[-1]
                if ext in ['csv']:
                    file_type = 'csv'
                elif ext in ['tsv', 'txt']:
                    file_type = 'tsv'
                elif ext in ['xlsx', 'xls']:
                    file_type = 'excel'
                elif ext in ['parquet']:
                    file_type = 'parquet'

            # If no extension hint, try to detect from content
            if not file_type:
                # Try CSV sniffer
                try:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(decoded_content[:1024])
                    delimiter = dialect.delimiter
                    if delimiter == ',':
                        file_type = 'csv'
                    elif delimiter == '\t':
                        file_type = 'tsv'
                    else:
                        file_type = 'csv'  # Default to CSV
                except:
                    file_type = 'csv'  # Default fallback

            # Detect delimiter for CSV/TSV
            delimiter = ','
            if file_type in ['csv', 'tsv']:
                try:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(decoded_content[:1024])
                    delimiter = dialect.delimiter
                except:
                    delimiter = ',' if file_type == 'csv' else '\t'

            # Try to parse first few rows to detect columns
            sample_columns = []
            try:
                if file_type in ['csv', 'tsv']:
                    df = pd.read_csv(io.StringIO(decoded_content), delimiter=delimiter, nrows=1)
                    sample_columns = df.columns.tolist()
                elif file_type == 'excel':
                    df = pd.read_excel(io.BytesIO(file_content), nrows=1)
                    sample_columns = df.columns.tolist()
                elif file_type == 'parquet':
                    df = pd.read_parquet(io.BytesIO(file_content))
                    sample_columns = df.columns.tolist()
            except Exception as e:
                return {'error': f'Failed to parse file: {str(e)}'}

            return {
                'file_type': file_type,
                'delimiter': delimiter,
                'encoding': detected_encoding,
                'has_header': len(sample_columns) > 0,
                'sample_columns': sample_columns
            }

        except Exception as e:
            return {'error': f'Format detection failed: {str(e)}'}

    def preview_data(self, file_content: bytes, format_id: str, num_rows: int = 5) -> Dict[str, Any]:
        """
        Preview table data using a format configuration.

        Args:
            file_content: Raw file bytes
            format_id: Format ID to use for parsing
            num_rows: Number of rows to preview (default: 5)

        Returns:
            Dict with preview data:
                - columns: List of column names
                - rows: List of row dicts
                - total_rows: Total row count
                - error: Error message if preview failed
        """
        format_config = self.get_format(format_id)
        if not format_config:
            return {'error': f'Format "{format_id}" not found'}

        try:
            df = None

            if format_config['file_type'] in ['csv', 'tsv']:
                # Decode content
                content_str = file_content.decode(format_config['encoding'])
                df = pd.read_csv(
                    io.StringIO(content_str),
                    delimiter=format_config['delimiter'],
                    header=format_config['header_row'] if format_config['has_header'] else None
                )

            elif format_config['file_type'] == 'excel':
                df = pd.read_excel(
                    io.BytesIO(file_content),
                    sheet_name=format_config.get('sheet_name', 0),
                    header=format_config['header_row'] if format_config['has_header'] else None
                )

            elif format_config['file_type'] == 'parquet':
                df = pd.read_parquet(io.BytesIO(file_content))

            else:
                return {'error': f'Unsupported file type: {format_config["file_type"]}'}

            # Convert to preview format
            columns = df.columns.tolist()
            rows = df.head(num_rows).to_dict(orient='records')
            total_rows = len(df)

            return {
                'columns': columns,
                'rows': rows,
                'total_rows': total_rows
            }

        except Exception as e:
            return {'error': f'Preview failed: {str(e)}'}


def get_table_format_registry(db_path: str = 'scidk_settings.db') -> TableFormatRegistry:
    """
    Get or create a TableFormatRegistry instance.

    Args:
        db_path: Path to settings database

    Returns:
        TableFormatRegistry instance
    """
    return TableFormatRegistry(db_path)
