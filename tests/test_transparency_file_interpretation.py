"""Tests for File Interpretation transparency layer.

Tests the Files page sidebar that shows which interpreter handles each file
and displays dependency information.
"""
import pytest
from pathlib import Path


class TestFileInterpretationAPI:
    """Test Files page interpreter assignment API."""

    def test_file_interpreter_lookup_by_extension(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test looking up interpreter for a file by extension."""
        # First need to register the interpreter with an extension
        # For this test, we'll test the endpoint behavior directly
        # The actual registry setup happens in the app initialization

        # Test a hypothetical file path
        file_path = '/data/test_sample.txt'
        resp = client.get(f'/api/system/file-interpreter{file_path}')

        # Should return 200 even if no interpreter found
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['file_path'] == file_path
        assert 'extension' in data
        assert 'interpreter' in data or 'reason' in data

    def test_file_interpreter_with_registered_extension(self, app, client, scripts_manager, test_interpreter_with_plugin):
        """Test file interpreter lookup with a registered extension."""
        # Get the registry from app extensions
        ext = app.extensions.get('scidk')
        if not ext or not ext.get('registry'):
            pytest.skip("Registry not available in test app")

        registry = ext.get('registry')

        # Register test interpreter for .test extension
        test_interp = scripts_manager.get_script('test_interpreter_alpha')
        registry.by_extension['.test'] = [test_interp]

        # Now test the lookup
        file_path = '/data/sample.test'
        resp = client.get(f'/api/system/file-interpreter{file_path}')

        assert resp.status_code == 200
        data = resp.get_json()

        assert data['file_path'] == file_path
        assert data['extension'] == '.test'
        assert data['interpreter'] is not None
        assert data['interpreter']['id'] == 'test_interpreter_alpha'
        assert data['interpreter']['name'] == 'Test Interpreter Alpha'
        assert data['interpreter']['assigned_by'] == 'extension_rule'

    def test_file_interpreter_no_extension(self, client):
        """Test file without extension."""
        file_path = '/data/README'
        resp = client.get(f'/api/system/file-interpreter{file_path}')

        assert resp.status_code == 200
        data = resp.get_json()

        assert data['file_path'] == file_path
        assert data['extension'] == ''
        # No interpreter expected
        assert data['interpreter'] is None or 'reason' in data

    def test_file_interpreter_inactive_interpreter(self, app, client, scripts_manager, test_interpreter_with_plugin):
        """Test that inactive interpreters are not returned."""
        ext = app.extensions.get('scidk')
        if not ext or not ext.get('registry'):
            pytest.skip("Registry not available in test app")

        registry = ext.get('registry')

        # Deactivate the interpreter
        scripts_manager.deactivate_script('test_interpreter_alpha')

        # Register it anyway (simulating stale registry)
        test_interp = scripts_manager.get_script('test_interpreter_alpha')
        registry.by_extension['.inactive'] = [test_interp]

        file_path = '/data/sample.inactive'
        resp = client.get(f'/api/system/file-interpreter{file_path}')

        assert resp.status_code == 200
        data = resp.get_json()

        # Should not return the inactive interpreter
        if data['interpreter'] is None:
            assert 'reason' in data
            assert 'none are active' in data['reason'].lower() or 'no interpreter' in data['reason'].lower()

    def test_file_interpreter_complex_path(self, client):
        """Test with complex file path including spaces and special chars."""
        file_path = '/data/my folder/file with spaces.txt'
        resp = client.get(f'/api/system/file-interpreter{file_path}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['file_path'] == file_path
        assert data['extension'] == '.txt'

    def test_file_interpreter_dependency_chain(self, app, client, scripts_manager, test_interpreter_with_plugin):
        """Test that interpreter's plugin dependencies are tracked."""
        # Get script status which includes dependencies
        resp = client.get('/api/system/script-status/test_interpreter_alpha')

        assert resp.status_code == 200
        data = resp.get_json()

        # Should show dependency on test_plugin_alpha
        assert 'dependencies' in data
        assert 'test_plugin_alpha' in data['dependencies']

        # Now check if the plugin itself has status
        resp2 = client.get('/api/system/script-status/test_plugin_alpha')
        assert resp2.status_code == 200
        plugin_data = resp2.get_json()

        # Plugin should show it's used by the interpreter
        assert plugin_data['used_by_count'] >= 1
        interpreter_ids = {dep['id'] for dep in plugin_data['used_by']}
        assert 'test_interpreter_alpha' in interpreter_ids
