"""Tests for iLab Data Importer plugin."""

import os
import tempfile
import pytest
import pandas as pd
from plugins.ilab_table_loader import handle_ilab_import, _get_preset_configs


@pytest.fixture
def sample_equipment_csv(tmp_path):
    """Create a sample iLab equipment CSV file."""
    csv_file = tmp_path / "ilab_equipment.csv"
    data = {
        'Service Name': ['Confocal Microscope', 'Flow Cytometer', 'Mass Spectrometer'],
        'Core': ['Microscopy Core', 'Flow Cytometry Core', 'Proteomics Core'],
        'PI': ['Dr. Smith', 'Dr. Jones', 'Dr. Williams'],
        'Location': ['Building A, Room 101', 'Building B, Room 202', 'Building C, Room 303'],
        'Equipment ID': ['EQ-001', 'EQ-002', 'EQ-003'],
        'Description': ['Advanced confocal imaging', 'Cell sorting and analysis', 'Protein analysis']
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def sample_services_csv(tmp_path):
    """Create a sample iLab services CSV file."""
    csv_file = tmp_path / "ilab_services.csv"
    data = {
        'Service Name': ['Microscopy Training', 'Flow Cytometry Analysis', 'Mass Spec Run'],
        'Core': ['Microscopy Core', 'Flow Cytometry Core', 'Proteomics Core'],
        'Rate Per Hour': [50, 75, 100],
        'Service ID': ['SVC-001', 'SVC-002', 'SVC-003'],
        'Active': ['Yes', 'Yes', 'No']
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def sample_pi_csv(tmp_path):
    """Create a sample PI directory CSV file."""
    csv_file = tmp_path / "ilab_pi_directory.csv"
    data = {
        'PI Name': ['Dr. Alice Smith', 'Dr. Bob Jones', 'Dr. Carol Williams'],
        'Email': ['alice.smith@example.edu', 'bob.jones@example.edu', 'carol.williams@example.edu'],
        'Department': ['Biology', 'Chemistry', 'Physics'],
        'Lab': ['Smith Lab', 'Jones Lab', 'Williams Lab'],
        'Phone': ['555-0101', '555-0102', '555-0103'],
        'Office': ['Bio 101', 'Chem 202', 'Physics 303']
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    return str(csv_file)


class TestIlabPlugin:
    """Test suite for iLab Data Importer plugin."""

    def test_preset_configs_exist(self):
        """Test that all expected presets are defined."""
        presets = _get_preset_configs()
        assert 'equipment' in presets
        assert 'services' in presets
        assert 'pi_directory' in presets

    def test_equipment_preset_has_column_hints(self):
        """Test that equipment preset has proper column hints."""
        presets = _get_preset_configs()
        equipment = presets['equipment']
        assert equipment['name'] == 'iLab Equipment'
        assert 'column_hints' in equipment
        assert 'Service Name' in equipment['column_hints']
        assert equipment['column_hints']['Service Name'] == 'name'

    def test_services_preset_has_suggested_labels(self):
        """Test that services preset has suggested labels."""
        presets = _get_preset_configs()
        services = presets['services']
        assert 'suggested_labels' in services
        assert 'iLabService' in services['suggested_labels']

    def test_pi_directory_preset_configuration(self):
        """Test PI directory preset configuration."""
        presets = _get_preset_configs()
        pi_dir = presets['pi_directory']
        assert pi_dir['name'] == 'PI Directory'
        assert pi_dir['table_name_hint'] == 'ilab_pi_directory'
        assert 'PrincipalInvestigator' in pi_dir['suggested_labels']
        assert 'Researcher' in pi_dir['suggested_labels']

    def test_import_equipment_with_preset(self, sample_equipment_csv, tmp_path):
        """Test importing equipment data with equipment preset."""
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'equipment',
            'file_path': sample_equipment_csv,
            'table_name': 'ilab_equipment_2024',
            'db_path': str(db_path)
        }

        result = handle_ilab_import(config)

        assert result['status'] == 'success'
        assert result['plugin'] == 'ilab_importer'
        assert result['preset'] == 'equipment'
        assert result['preset_name'] == 'iLab Equipment'
        assert result['rows_imported'] == 3
        assert 'Service Name' in result['columns']

    def test_import_services_with_preset(self, sample_services_csv, tmp_path):
        """Test importing services data with services preset."""
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'services',
            'file_path': sample_services_csv,
            'table_name': 'ilab_services_2024',
            'db_path': str(db_path)
        }

        result = handle_ilab_import(config)

        assert result['status'] == 'success'
        assert result['preset'] == 'services'
        assert result['rows_imported'] == 3

    def test_import_pi_directory_with_preset(self, sample_pi_csv, tmp_path):
        """Test importing PI directory with preset."""
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'pi_directory',
            'file_path': sample_pi_csv,
            'table_name': 'ilab_pi_directory',
            'db_path': str(db_path)
        }

        result = handle_ilab_import(config)

        assert result['status'] == 'success'
        assert result['preset'] == 'pi_directory'
        assert result['rows_imported'] == 3
        assert 'PI Name' in result['columns']

    def test_import_without_preset(self, sample_equipment_csv, tmp_path):
        """Test importing without specifying a preset (custom mode)."""
        db_path = tmp_path / "test.db"
        config = {
            'file_path': sample_equipment_csv,
            'table_name': 'custom_table',
            'db_path': str(db_path)
        }

        result = handle_ilab_import(config)

        assert result['status'] == 'success'
        assert result['plugin'] == 'ilab_importer'
        assert 'preset' not in result
        assert result['rows_imported'] == 3

    def test_table_name_auto_fill_with_preset(self, sample_equipment_csv, tmp_path):
        """Test that table name is auto-filled from preset hint."""
        from datetime import datetime
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'equipment',
            'file_path': sample_equipment_csv,
            'db_path': str(db_path)
            # Note: no table_name provided
        }

        result = handle_ilab_import(config)

        assert result['status'] == 'success'
        # Table name should be auto-filled with current year
        current_year = datetime.now().year
        expected_table = f'ilab_equipment_{current_year}'
        assert result['table_name'] == expected_table

    def test_column_hints_stored_in_config(self, sample_equipment_csv, tmp_path):
        """Test that column hints are stored in instance config."""
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'equipment',
            'file_path': sample_equipment_csv,
            'table_name': 'test_table',
            'db_path': str(db_path)
        }

        handle_ilab_import(config)

        # Column hints should be added to config
        assert '_column_hints' in config
        assert config['_column_hints']['Service Name'] == 'name'
        assert config['_column_hints']['Core'] == 'core_facility'

    def test_suggested_labels_stored_in_config(self, sample_services_csv, tmp_path):
        """Test that suggested labels are stored in instance config."""
        db_path = tmp_path / "test.db"
        config = {
            'preset': 'services',
            'file_path': sample_services_csv,
            'table_name': 'test_table',
            'db_path': str(db_path)
        }

        handle_ilab_import(config)

        # Suggested labels should be added to config
        assert '_suggested_labels' in config
        assert 'iLabService' in config['_suggested_labels']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
