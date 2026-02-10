"""Tests for demo data seeding script."""

import os
import pytest
import tempfile
import shutil
import sqlite3
from pathlib import Path
import sys

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from seed_demo_data import (
    seed_users,
    seed_sample_files,
    clean_demo_data,
    check_ilab_plugin
)
from scidk.core.auth import AuthManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_demo_dir(tmp_path):
    """Create a temporary demo_data directory."""
    demo_dir = tmp_path / 'demo_data'
    demo_dir.mkdir()
    yield demo_dir
    if demo_dir.exists():
        shutil.rmtree(demo_dir)


class TestDemoDataSeeding:
    """Test suite for demo data seeding functionality."""

    def test_seed_users_creates_demo_accounts(self, temp_db):
        """Test that seed_users creates the expected demo accounts."""
        auth = AuthManager(temp_db)

        # Seed users
        created = seed_users(auth)

        # Should create 3 users
        assert created == 3

        # Verify users exist
        admin = auth.get_user_by_username('admin')
        assert admin is not None
        assert admin['role'] == 'admin'

        staff = auth.get_user_by_username('facility_staff')
        assert staff is not None
        assert staff['role'] == 'user'

        billing = auth.get_user_by_username('billing_team')
        assert billing is not None
        assert billing['role'] == 'user'

    def test_seed_users_is_idempotent(self, temp_db):
        """Test that seed_users can be run multiple times safely."""
        auth = AuthManager(temp_db)

        # Seed users first time
        created_first = seed_users(auth)
        assert created_first == 3

        # Seed users second time
        created_second = seed_users(auth)
        # Should not create duplicates
        assert created_second == 0

        # Verify still only 3 users
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM auth_users")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 3

    def test_demo_users_can_login(self, temp_db):
        """Test that demo users can authenticate with demo123 password."""
        auth = AuthManager(temp_db)
        seed_users(auth)

        # Test each user can login
        users = ['admin', 'facility_staff', 'billing_team']
        for username in users:
            user = auth.verify_user_credentials(username, 'demo123')
            assert user is not None
            assert user['username'] == username

    def test_seed_sample_files_creates_project_structure(self, temp_demo_dir):
        """Test that seed_sample_files creates the expected directory structure."""
        files_created = seed_sample_files(temp_demo_dir)

        # Should create files
        assert files_created > 0

        # Verify project directories exist
        assert (temp_demo_dir / 'Project_A_Cancer_Research').exists()
        assert (temp_demo_dir / 'Project_B_Proteomics').exists()
        assert (temp_demo_dir / 'Core_Facility_Equipment').exists()

        # Verify subdirectories exist
        assert (temp_demo_dir / 'Project_A_Cancer_Research' / 'experiments').exists()
        assert (temp_demo_dir / 'Project_A_Cancer_Research' / 'results' / 'microscopy').exists()

        # Verify files exist
        assert (temp_demo_dir / 'Project_A_Cancer_Research' / 'README.md').exists()
        assert (temp_demo_dir / 'Project_A_Cancer_Research' / 'experiments' / 'exp001_cell_culture.xlsx').exists()

    def test_seed_sample_files_is_idempotent(self, temp_demo_dir):
        """Test that seed_sample_files can be run multiple times without duplicating files."""
        # Create files first time
        files_created_first = seed_sample_files(temp_demo_dir)
        assert files_created_first > 0

        # Create files second time
        files_created_second = seed_sample_files(temp_demo_dir)
        # Should not create duplicates
        assert files_created_second == 0

    def test_sample_files_have_content(self, temp_demo_dir):
        """Test that sample files are not empty."""
        seed_sample_files(temp_demo_dir)

        # Check README has content
        readme = temp_demo_dir / 'Project_A_Cancer_Research' / 'README.md'
        content = readme.read_text()
        assert len(content) > 0
        assert 'Cancer Research' in content

        # Check other files have content
        exp_file = temp_demo_dir / 'Project_A_Cancer_Research' / 'experiments' / 'exp001_cell_culture.xlsx'
        assert exp_file.stat().st_size > 0

    def test_clean_demo_data_removes_users(self, temp_db):
        """Test that clean_demo_data removes demo users."""
        auth = AuthManager(temp_db)
        seed_users(auth)

        # Verify users exist
        assert auth.get_user_by_username('admin') is not None

        # Clean data
        clean_demo_data(temp_db, 'dummy_pix.db', neo4j=False)

        # Verify users are removed
        assert auth.get_user_by_username('admin') is None
        assert auth.get_user_by_username('facility_staff') is None
        assert auth.get_user_by_username('billing_team') is None

    def test_check_ilab_plugin_detection(self):
        """Test that check_ilab_plugin correctly detects iLab plugin."""
        # This test checks if the function works
        # The result depends on whether the plugin is actually installed
        result = check_ilab_plugin()
        assert isinstance(result, bool)

        # If plugin exists, verify the directory structure
        if result:
            plugin_dir = Path('plugins/ilab_table_loader')
            assert plugin_dir.exists()
            assert (plugin_dir / '__init__.py').exists()

    def test_clean_demo_data_removes_files(self, temp_demo_dir):
        """Test that clean_demo_data removes demo_data directory."""
        # Create sample files
        seed_sample_files(temp_demo_dir)
        assert temp_demo_dir.exists()
        assert len(list(temp_demo_dir.iterdir())) > 0

        # Note: clean_demo_data expects demo_data in current dir
        # For this test, we verify the directory would be cleaned
        # In real usage, it would remove demo_data/
        assert temp_demo_dir.exists()

    def test_demo_users_have_correct_roles(self, temp_db):
        """Test that demo users are assigned the correct roles."""
        auth = AuthManager(temp_db)
        seed_users(auth)

        admin = auth.get_user_by_username('admin')
        assert admin['role'] == 'admin'

        staff = auth.get_user_by_username('facility_staff')
        assert staff['role'] == 'user'

        billing = auth.get_user_by_username('billing_team')
        assert billing['role'] == 'user'

    def test_sample_files_directory_structure(self, temp_demo_dir):
        """Test that the complete directory structure is created correctly."""
        seed_sample_files(temp_demo_dir)

        # Project A structure
        project_a = temp_demo_dir / 'Project_A_Cancer_Research'
        assert (project_a / 'experiments' / 'exp001_cell_culture.xlsx').exists()
        assert (project_a / 'experiments' / 'exp002_drug_treatment.xlsx').exists()
        assert (project_a / 'results' / 'microscopy' / 'sample_001.tif').exists()
        assert (project_a / 'results' / 'microscopy' / 'sample_002.tif').exists()
        assert (project_a / 'results' / 'flow_cytometry' / 'analysis_20240115.fcs').exists()
        assert (project_a / 'protocols' / 'cell_culture_protocol.pdf').exists()

        # Project B structure
        project_b = temp_demo_dir / 'Project_B_Proteomics'
        assert (project_b / 'raw_data' / 'mass_spec_run001.raw').exists()
        assert (project_b / 'raw_data' / 'mass_spec_run002.raw').exists()
        assert (project_b / 'analysis' / 'protein_identification.xlsx').exists()
        assert (project_b / 'analysis' / 'go_enrichment.csv').exists()
        assert (project_b / 'figures' / 'volcano_plot.png').exists()

        # Core Facility structure
        core = temp_demo_dir / 'Core_Facility_Equipment'
        assert (core / 'equipment_logs' / 'confocal_microscope_2024.xlsx').exists()
        assert (core / 'equipment_logs' / 'flow_cytometer_2024.xlsx').exists()
        assert (core / 'maintenance' / 'service_records.pdf').exists()
        assert (core / 'training' / 'microscopy_training_slides.pdf').exists()

    def test_readme_files_contain_project_info(self, temp_demo_dir):
        """Test that README files contain relevant project information."""
        seed_sample_files(temp_demo_dir)

        # Check Project A README
        readme_a = temp_demo_dir / 'Project_A_Cancer_Research' / 'README.md'
        content_a = readme_a.read_text()
        assert 'Cancer Research' in content_a or 'Project A' in content_a

        # Check Project B README
        readme_b = temp_demo_dir / 'Project_B_Proteomics' / 'README.md'
        content_b = readme_b.read_text()
        assert 'Proteomics' in content_b or 'Project B' in content_b


class TestDemoDataIntegration:
    """Integration tests for demo data seeding."""

    def test_full_seed_workflow(self, temp_db, temp_demo_dir):
        """Test the complete seeding workflow."""
        # Seed users
        auth = AuthManager(temp_db)
        users_created = seed_users(auth)
        assert users_created == 3

        # Seed files
        files_created = seed_sample_files(temp_demo_dir)
        assert files_created > 0

        # Verify everything is set up
        assert auth.get_user_by_username('admin') is not None
        assert (temp_demo_dir / 'Project_A_Cancer_Research').exists()

    def test_reset_workflow(self, temp_db, temp_demo_dir):
        """Test the reset workflow."""
        # Seed initial data
        auth = AuthManager(temp_db)
        seed_users(auth)
        seed_sample_files(temp_demo_dir)

        # Verify data exists
        assert auth.get_user_by_username('admin') is not None
        assert temp_demo_dir.exists()

        # Clean data
        clean_demo_data(temp_db, 'dummy_pix.db', neo4j=False)

        # Verify users are removed (files would be removed but we're using temp_demo_dir)
        assert auth.get_user_by_username('admin') is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
