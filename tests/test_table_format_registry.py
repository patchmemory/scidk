"""
Tests for Table Format Registry.

Tests CRUD operations, format detection, and data preview.
"""
import pytest
import tempfile
import os
import io
import csv
from scidk.core.table_format_registry import TableFormatRegistry


@pytest.fixture
def registry():
    """Create a temporary registry for testing."""
    # Use temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    reg = TableFormatRegistry(db_path=db_path)

    yield reg

    # Cleanup
    reg.db.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_preprogrammed_formats_seeded(registry):
    """Test that preprogrammed formats are seeded on initialization."""
    formats = registry.list_formats(include_preprogrammed=True)

    # Should have at least the 4 preprogrammed formats
    preprogrammed = [f for f in formats if f['is_preprogrammed']]
    assert len(preprogrammed) == 4

    names = {f['name'] for f in preprogrammed}
    assert 'CSV (Standard)' in names
    assert 'TSV (Standard)' in names
    assert 'Excel (Standard)' in names
    assert 'Parquet (Standard)' in names


def test_create_format(registry):
    """Test creating a new table format."""
    format_data = {
        'name': 'My CSV Format',
        'file_type': 'csv',
        'delimiter': ';',
        'encoding': 'utf-8',
        'has_header': True,
        'header_row': 0,
        'target_label': 'Person',
        'description': 'Custom semicolon-separated format'
    }

    format_config = registry.create_format(format_data)

    assert format_config['id'] is not None
    assert format_config['name'] == 'My CSV Format'
    assert format_config['file_type'] == 'csv'
    assert format_config['delimiter'] == ';'
    assert format_config['encoding'] == 'utf-8'
    assert format_config['has_header'] is True
    assert format_config['header_row'] == 0
    assert format_config['target_label'] == 'Person'
    assert format_config['description'] == 'Custom semicolon-separated format'
    assert format_config['is_preprogrammed'] is False


def test_create_format_validation(registry):
    """Test format creation validation."""
    # Missing name
    with pytest.raises(ValueError, match="Format name is required"):
        registry.create_format({'file_type': 'csv'})

    # Missing file_type
    with pytest.raises(ValueError, match="File type is required"):
        registry.create_format({'name': 'Test'})

    # Invalid file_type
    with pytest.raises(ValueError, match="File type must be one of"):
        registry.create_format({'name': 'Test', 'file_type': 'invalid'})


def test_create_duplicate_name(registry):
    """Test that duplicate names are rejected."""
    data = {
        'name': 'Duplicate Format',
        'file_type': 'csv'
    }

    # First creation should succeed
    registry.create_format(data)

    # Second creation with same name should fail
    with pytest.raises(ValueError, match="already exists"):
        registry.create_format(data)


def test_get_format(registry):
    """Test retrieving a format by ID."""
    data = {
        'name': 'Get Test Format',
        'file_type': 'tsv',
        'delimiter': '\t'
    }

    created = registry.create_format(data)
    format_id = created['id']

    retrieved = registry.get_format(format_id)

    assert retrieved is not None
    assert retrieved['id'] == format_id
    assert retrieved['name'] == 'Get Test Format'
    assert retrieved['file_type'] == 'tsv'


def test_get_nonexistent_format(registry):
    """Test retrieving a format that doesn't exist."""
    result = registry.get_format('nonexistent-id')
    assert result is None


def test_list_formats(registry):
    """Test listing all formats."""
    # Create custom formats
    registry.create_format({'name': 'Custom CSV', 'file_type': 'csv'})
    registry.create_format({'name': 'Custom TSV', 'file_type': 'tsv'})

    # List all formats
    all_formats = registry.list_formats(include_preprogrammed=True)
    assert len(all_formats) >= 6  # 4 preprogrammed + 2 custom

    # List only custom formats
    custom_formats = registry.list_formats(include_preprogrammed=False)
    assert len(custom_formats) == 2
    assert all(not f['is_preprogrammed'] for f in custom_formats)


def test_update_format(registry):
    """Test updating an existing format."""
    # Create format
    data = {
        'name': 'Update Test',
        'file_type': 'csv',
        'delimiter': ','
    }
    created = registry.create_format(data)
    format_id = created['id']

    # Update format
    updates = {
        'name': 'Updated Name',
        'delimiter': ';',
        'target_label': 'NewLabel'
    }
    updated = registry.update_format(format_id, updates)

    assert updated['name'] == 'Updated Name'
    assert updated['delimiter'] == ';'
    assert updated['target_label'] == 'NewLabel'
    assert updated['file_type'] == 'csv'  # Unchanged


def test_update_nonexistent_format(registry):
    """Test updating a format that doesn't exist."""
    with pytest.raises(ValueError, match="not found"):
        registry.update_format('nonexistent-id', {'name': 'New Name'})


def test_update_preprogrammed_format(registry):
    """Test that preprogrammed formats cannot be updated."""
    formats = registry.list_formats(include_preprogrammed=True)
    preprogrammed = [f for f in formats if f['is_preprogrammed']][0]

    with pytest.raises(ValueError, match="Cannot modify preprogrammed"):
        registry.update_format(preprogrammed['id'], {'name': 'New Name'})


def test_delete_format(registry):
    """Test deleting a format."""
    # Create format
    data = {'name': 'Delete Test', 'file_type': 'csv'}
    created = registry.create_format(data)
    format_id = created['id']

    # Delete format
    deleted = registry.delete_format(format_id)
    assert deleted is True

    # Verify deleted
    retrieved = registry.get_format(format_id)
    assert retrieved is None


def test_delete_nonexistent_format(registry):
    """Test deleting a format that doesn't exist."""
    deleted = registry.delete_format('nonexistent-id')
    assert deleted is False


def test_delete_preprogrammed_format(registry):
    """Test that preprogrammed formats cannot be deleted."""
    formats = registry.list_formats(include_preprogrammed=True)
    preprogrammed = [f for f in formats if f['is_preprogrammed']][0]

    with pytest.raises(ValueError, match="Cannot delete preprogrammed"):
        registry.delete_format(preprogrammed['id'])


def test_detect_format_csv(registry):
    """Test auto-detecting CSV format."""
    # Create sample CSV content
    csv_content = "Name,Email,Age\nJohn,john@example.com,30\nJane,jane@example.com,25"
    file_bytes = csv_content.encode('utf-8')

    detected = registry.detect_format(file_bytes, filename='test.csv')

    assert detected['file_type'] == 'csv'
    assert detected['delimiter'] == ','
    assert detected['encoding'] == 'utf-8'
    assert detected['has_header'] is True
    assert detected['sample_columns'] == ['Name', 'Email', 'Age']


def test_detect_format_tsv(registry):
    """Test auto-detecting TSV format."""
    # Create sample TSV content
    tsv_content = "Name\tEmail\tAge\nJohn\tjohn@example.com\t30\nJane\tjane@example.com\t25"
    file_bytes = tsv_content.encode('utf-8')

    detected = registry.detect_format(file_bytes, filename='test.tsv')

    assert detected['file_type'] == 'tsv'
    assert detected['delimiter'] == '\t'
    assert detected['encoding'] == 'utf-8'
    assert detected['has_header'] is True
    assert detected['sample_columns'] == ['Name', 'Email', 'Age']


def test_detect_format_fallback_encoding(registry):
    """Test detecting format with non-UTF-8 encoding falls back to latin-1."""
    # Create binary data that's not valid UTF-8 but valid latin-1
    invalid_utf8_bytes = bytes([0xFF, 0xFE, 0xFD])

    detected = registry.detect_format(invalid_utf8_bytes, filename='test.csv')

    # Should fall back to latin-1 encoding
    assert detected['encoding'] in ['latin-1', 'utf-16']  # Could detect either
    assert detected['file_type'] == 'csv'


def test_preview_data_csv(registry):
    """Test previewing CSV data."""
    # Create CSV format
    format_data = {
        'name': 'Preview Test CSV',
        'file_type': 'csv',
        'delimiter': ',',
        'encoding': 'utf-8',
        'has_header': True,
        'header_row': 0
    }
    format_config = registry.create_format(format_data)
    format_id = format_config['id']

    # Create sample CSV content
    csv_content = "Name,Email,Age\nJohn,john@example.com,30\nJane,jane@example.com,25\nBob,bob@example.com,35"
    file_bytes = csv_content.encode('utf-8')

    preview = registry.preview_data(file_bytes, format_id, num_rows=2)

    assert 'error' not in preview
    assert preview['columns'] == ['Name', 'Email', 'Age']
    assert len(preview['rows']) == 2
    assert preview['rows'][0]['Name'] == 'John'
    assert preview['rows'][1]['Name'] == 'Jane'
    assert preview['total_rows'] == 3


def test_preview_data_invalid_format(registry):
    """Test previewing data with non-existent format."""
    file_bytes = b"test"
    preview = registry.preview_data(file_bytes, 'nonexistent-id')

    assert 'error' in preview
    assert 'not found' in preview['error']


def test_column_mappings(registry):
    """Test creating format with column mappings."""
    format_data = {
        'name': 'Mapped Format',
        'file_type': 'csv',
        'column_mappings': {
            'Name': {
                'label_property': 'full_name',
                'type_hint': 'string',
                'ignore': False
            },
            'Age': {
                'label_property': 'age_years',
                'type_hint': 'number',
                'ignore': False
            }
        }
    }

    format_config = registry.create_format(format_data)

    assert 'column_mappings' in format_config
    assert 'Name' in format_config['column_mappings']
    assert format_config['column_mappings']['Name']['label_property'] == 'full_name'
    assert format_config['column_mappings']['Age']['type_hint'] == 'number'


def test_format_with_sheet_name(registry):
    """Test creating Excel format with sheet name."""
    format_data = {
        'name': 'Excel with Sheet',
        'file_type': 'excel',
        'sheet_name': 'Data'
    }

    format_config = registry.create_format(format_data)

    assert format_config['sheet_name'] == 'Data'
    assert format_config['file_type'] == 'excel'
