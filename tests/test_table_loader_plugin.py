"""Tests for the Table Loader plugin.

This test suite covers:
1. Plugin registration
2. CSV import
3. Excel import
4. TSV import
5. Table replacement vs append
6. Error handling (missing files, invalid configs)
7. Data validation after import
"""

import pytest
import sqlite3
import tempfile
import shutil
from pathlib import Path
import pandas as pd

from plugins.table_loader import register_plugin, handle_table_import
from plugins.table_loader.importer import TableImporter


class MockApp:
    """Mock Flask app for testing plugin registration."""

    def __init__(self):
        self.extensions = {
            'scidk': {
                'plugin_templates': MockRegistry()
            }
        }


class MockRegistry:
    """Mock plugin template registry for testing."""

    def __init__(self):
        self.templates = {}

    def register(self, template_config):
        """Mock register method."""
        template_id = template_config['id']
        self.templates[template_id] = template_config
        return True


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    # Create a temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()

    yield temp_db.name

    # Cleanup
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def fixtures_dir():
    """Get the path to test fixtures directory."""
    return Path(__file__).parent / 'fixtures'


@pytest.fixture
def mock_app():
    """Create a mock Flask app for testing."""
    return MockApp()


class TestPluginRegistration:
    """Test plugin registration functionality."""

    def test_register_plugin(self, mock_app):
        """Test that the plugin registers correctly."""
        metadata = register_plugin(mock_app)

        # Check metadata
        assert metadata['name'] == 'Table Loader'
        assert metadata['version'] == '1.0.0'
        assert metadata['author'] == 'SciDK Team'
        assert 'description' in metadata

        # Check that template was registered
        registry = mock_app.extensions['scidk']['plugin_templates']
        assert 'table_loader' in registry.templates

        # Check template configuration
        template = registry.templates['table_loader']
        assert template['id'] == 'table_loader'
        assert template['name'] == 'Table Loader'
        assert template['category'] == 'data_import'
        assert template['supports_multiple_instances'] is True
        assert template['icon'] == '📊'
        assert callable(template['handler'])

    def test_template_config_schema(self, mock_app):
        """Test that the template config schema is properly defined."""
        register_plugin(mock_app)
        registry = mock_app.extensions['scidk']['plugin_templates']
        template = registry.templates['table_loader']

        schema = template['config_schema']
        assert 'properties' in schema

        # Check required fields
        props = schema['properties']
        assert 'instance_name' in props
        assert 'file_path' in props
        assert 'table_name' in props
        assert 'file_type' in props
        assert 'has_header' in props
        assert 'replace_existing' in props
        assert 'sheet_name' in props

        # Check defaults
        assert props['has_header']['default'] is True
        assert props['replace_existing']['default'] is True
        assert props['file_type']['default'] == 'auto'

    def test_preset_configs(self, mock_app):
        """Test that preset configurations are defined."""
        register_plugin(mock_app)
        registry = mock_app.extensions['scidk']['plugin_templates']
        template = registry.templates['table_loader']

        presets = template['preset_configs']
        assert 'csv_import' in presets
        assert 'excel_import' in presets
        assert 'tsv_import' in presets


class TestCSVImport:
    """Test CSV file import functionality."""

    def test_import_csv_with_header(self, test_db, fixtures_dir):
        """Test importing a CSV file with headers."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        # Check result
        assert result['status'] == 'success'
        assert result['rows_imported'] == 5
        assert result['table_name'] == 'equipment'
        assert len(result['columns']) == 5
        assert 'equipment_id' in result['columns']
        assert 'name' in result['columns']

        # Verify data in database
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM equipment")
        count = cursor.fetchone()[0]
        assert count == 5

        cursor.execute("SELECT * FROM equipment WHERE equipment_id = 'EQ001'")
        row = cursor.fetchone()
        assert row is not None
        conn.close()

    def test_import_csv_auto_detect(self, test_db, fixtures_dir):
        """Test CSV import with auto file type detection."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_auto',
            'file_type': 'auto',  # Auto-detect
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        assert result['status'] == 'success'
        assert result['file_type'] == 'csv'
        assert result['rows_imported'] == 5

    def test_import_csv_replace_existing(self, test_db, fixtures_dir):
        """Test replacing existing table data."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_replace',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        # First import
        result1 = importer.import_table(config)
        assert result1['status'] == 'success'
        assert result1['rows_imported'] == 5

        # Second import (replace)
        result2 = importer.import_table(config)
        assert result2['status'] == 'success'
        assert result2['rows_imported'] == 5

        # Verify only 5 rows exist (replaced, not appended)
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM equipment_replace")
        count = cursor.fetchone()[0]
        assert count == 5
        conn.close()

    def test_import_csv_append(self, test_db, fixtures_dir):
        """Test appending to existing table data."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_append',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': False  # Append mode
        }

        # First import
        result1 = importer.import_table(config)
        assert result1['status'] == 'success'
        assert result1['rows_imported'] == 5

        # Second import (append)
        result2 = importer.import_table(config)
        assert result2['status'] == 'success'
        assert result2['rows_imported'] == 5

        # Verify 10 rows exist (appended)
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM equipment_append")
        count = cursor.fetchone()[0]
        assert count == 10
        conn.close()


class TestExcelImport:
    """Test Excel file import functionality."""

    def test_import_excel_with_header(self, test_db, fixtures_dir):
        """Test importing an Excel file with headers."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_pi_directory.xlsx'),
            'table_name': 'pi_directory',
            'file_type': 'excel',
            'has_header': True,
            'replace_existing': True,
            'sheet_name': '0'
        }

        result = importer.import_table(config)

        # Check result
        assert result['status'] == 'success'
        assert result['rows_imported'] == 4
        assert result['table_name'] == 'pi_directory'
        assert 'pi_id' in result['columns']
        assert 'name' in result['columns']
        assert 'department' in result['columns']

        # Verify data in database
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pi_directory")
        count = cursor.fetchone()[0]
        assert count == 4

        cursor.execute("SELECT * FROM pi_directory WHERE pi_id = 'PI001'")
        row = cursor.fetchone()
        assert row is not None
        conn.close()

    def test_import_excel_auto_detect(self, test_db, fixtures_dir):
        """Test Excel import with auto file type detection."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_pi_directory.xlsx'),
            'table_name': 'pi_auto',
            'file_type': 'auto',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        assert result['status'] == 'success'
        assert result['file_type'] == 'excel'
        assert result['rows_imported'] == 4


class TestTSVImport:
    """Test TSV file import functionality."""

    def test_import_tsv_with_header(self, test_db, fixtures_dir):
        """Test importing a TSV file with headers."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_resources.tsv'),
            'table_name': 'resources',
            'file_type': 'tsv',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        # Check result
        assert result['status'] == 'success'
        assert result['rows_imported'] == 5
        assert result['table_name'] == 'resources'
        assert 'resource_id' in result['columns']
        assert 'category' in result['columns']

        # Verify data in database
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resources")
        count = cursor.fetchone()[0]
        assert count == 5
        conn.close()

    def test_import_tsv_auto_detect(self, test_db, fixtures_dir):
        """Test TSV import with auto file type detection."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_resources.tsv'),
            'table_name': 'resources_auto',
            'file_type': 'auto',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        assert result['status'] == 'success'
        assert result['file_type'] == 'tsv'
        assert result['rows_imported'] == 5


class TestErrorHandling:
    """Test error handling and validation."""

    def test_missing_file(self, test_db):
        """Test handling of missing file."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': '/nonexistent/file.csv',
            'table_name': 'test_table',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        assert result['status'] == 'error'
        assert 'not found' in result['message'].lower()
        assert result['rows_imported'] == 0

    def test_missing_required_field(self, test_db):
        """Test handling of missing required configuration fields."""
        importer = TableImporter(db_path=test_db)

        # Missing file_path
        config = {
            'table_name': 'test_table',
            'file_type': 'csv'
        }

        with pytest.raises(ValueError, match='file_path'):
            importer.import_table(config)

        # Missing table_name
        config = {
            'file_path': '/path/to/file.csv',
            'file_type': 'csv'
        }

        with pytest.raises(ValueError, match='table_name'):
            importer.import_table(config)

    def test_invalid_table_name(self, test_db, fixtures_dir):
        """Test handling of invalid table names."""
        importer = TableImporter(db_path=test_db)

        # Table name starting with digit
        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': '123invalid',
            'file_type': 'csv',
            'has_header': True
        }

        result = importer.import_table(config)
        assert result['status'] == 'error'

        # Table name with spaces
        config['table_name'] = 'invalid table name'
        result = importer.import_table(config)
        assert result['status'] == 'error'

    def test_unsupported_file_type(self, test_db):
        """Test handling of unsupported file types."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': '/path/to/file.pdf',
            'table_name': 'test_table',
            'file_type': 'auto',
            'has_header': True
        }

        result = importer.import_table(config)
        assert result['status'] == 'error'
        assert 'unsupported' in result['message'].lower()


class TestHandleTableImport:
    """Test the main handler function."""

    def test_handle_table_import(self, test_db, fixtures_dir, monkeypatch):
        """Test the handle_table_import function."""
        # Monkey-patch the TableImporter to use our test database
        def mock_init(self, db_path='scidk_settings.db'):
            self.db_path = test_db

        monkeypatch.setattr(TableImporter, '__init__', mock_init)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_handler',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        result = handle_table_import(config)

        assert result['status'] == 'success'
        assert result['rows_imported'] == 5
        assert result['table_name'] == 'equipment_handler'


class TestDataValidation:
    """Test data integrity after import."""

    def test_column_names_preserved(self, test_db, fixtures_dir):
        """Test that column names are preserved correctly."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_columns',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        # Check that all expected columns are present
        expected_columns = ['equipment_id', 'name', 'location', 'status', 'purchase_date']
        assert all(col in result['columns'] for col in expected_columns)

        # Verify in database
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(equipment_columns)")
        db_columns = [row[1] for row in cursor.fetchall()]
        assert all(col in db_columns for col in expected_columns)
        conn.close()

    def test_data_values_preserved(self, test_db, fixtures_dir):
        """Test that data values are preserved correctly."""
        importer = TableImporter(db_path=test_db)

        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'equipment_values',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }

        result = importer.import_table(config)

        # Read back from database and verify values
        conn = sqlite3.connect(test_db)
        df = pd.read_sql_query("SELECT * FROM equipment_values ORDER BY equipment_id", conn)
        conn.close()

        # Check specific values
        assert df.loc[0, 'equipment_id'] == 'EQ001'
        assert df.loc[0, 'name'] == 'Microscope Alpha'
        assert df.loc[0, 'location'] == 'Lab A'
        assert df.loc[0, 'status'] == 'operational'

        assert df.loc[4, 'equipment_id'] == 'EQ005'
        assert df.loc[4, 'status'] == 'decommissioned'

    def test_row_count_accuracy(self, test_db, fixtures_dir):
        """Test that row counts are accurate."""
        importer = TableImporter(db_path=test_db)

        # Test with CSV (5 rows)
        config = {
            'file_path': str(fixtures_dir / 'sample_equipment.csv'),
            'table_name': 'test_csv_count',
            'file_type': 'csv',
            'has_header': True,
            'replace_existing': True
        }
        result = importer.import_table(config)
        assert result['rows_imported'] == 5

        # Test with Excel (4 rows)
        config = {
            'file_path': str(fixtures_dir / 'sample_pi_directory.xlsx'),
            'table_name': 'test_excel_count',
            'file_type': 'excel',
            'has_header': True,
            'replace_existing': True
        }
        result = importer.import_table(config)
        assert result['rows_imported'] == 4

        # Test with TSV (5 rows)
        config = {
            'file_path': str(fixtures_dir / 'sample_resources.tsv'),
            'table_name': 'test_tsv_count',
            'file_type': 'tsv',
            'has_header': True,
            'replace_existing': True
        }
        result = importer.import_table(config)
        assert result['rows_imported'] == 5
