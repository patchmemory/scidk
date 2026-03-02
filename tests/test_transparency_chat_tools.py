"""Tests for Chat self-awareness tools.

Tests the /api/system/* endpoints from the perspective of Chat tools
that call them to answer questions about the system state.
"""
import pytest


class TestChatSelfAwarenessTools:
    """Test system state query endpoints used by Chat."""

    def test_plugin_dependencies_endpoint(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test /api/system/plugin-dependencies/<id> returns expected format."""
        response = client.get('/api/system/plugin-dependencies/test_plugin_alpha')
        assert response.status_code == 200

        data = response.get_json()
        assert data['plugin_id'] == 'test_plugin_alpha'
        assert len(data['used_by']) == 1
        assert data['used_by'][0]['id'] == 'test_interpreter_alpha'

    def test_active_interpreters_endpoint(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test /api/system/active-interpreters returns list format."""
        response = client.get('/api/system/active-interpreters')
        assert response.status_code == 200

        data = response.get_json()
        assert 'interpreters' in data
        assert 'count' in data
        assert data['count'] >= 1

        # Find our test interpreter
        interpreter = next(
            (i for i in data['interpreters'] if i['id'] == 'test_interpreter_alpha'),
            None
        )
        assert interpreter is not None
        assert interpreter['validation_status'] == 'validated'
        assert interpreter['is_active'] is True

    def test_script_status_endpoint(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test /api/system/script-status/<id> returns full details."""
        response = client.get('/api/system/script-status/test_interpreter_alpha')
        assert response.status_code == 200

        data = response.get_json()
        assert data['id'] == 'test_interpreter_alpha'
        assert data['validation_status'] == 'validated'
        assert data['is_active'] is True
        assert 'dependencies' in data
        assert 'test_plugin_alpha' in data['dependencies']

    def test_file_interpreter_endpoint(self, client):
        """Test /api/system/file-interpreter/<path> returns structure."""
        response = client.get('/api/system/file-interpreter//tmp/test.txt', follow_redirects=True)
        assert response.status_code == 200

        data = response.get_json()
        assert 'file_path' in data
        assert 'extension' in data
        # May or may not have interpreter depending on registry state

    def test_script_status_endpoint_not_found(self, client):
        """Test endpoint returns 404 for nonexistent script."""
        response = client.get('/api/system/script-status/nonexistent_script_id')
        assert response.status_code == 404

        data = response.get_json()
        assert 'error' in data
