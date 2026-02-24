"""Tests for Plugins Page transparency layer.

Tests the Plugins page backend endpoints that expose dependency relationships
and script status information.
"""
import pytest


class TestPluginsPageAPI:
    """Test Plugins transparency layer API endpoints."""

    def test_get_plugin_dependencies_with_dependents(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test getting dependencies for a plugin that has dependent scripts."""
        # test_interpreter_with_plugin depends on test_plugin_alpha
        resp = client.get('/api/system/plugin-dependencies/test_plugin_alpha')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['plugin_id'] == 'test_plugin_alpha'
        assert 'used_by' in data
        assert len(data['used_by']) == 1
        assert data['count'] == 1

        # Check dependent script details
        dependent = data['used_by'][0]
        assert dependent['id'] == 'test_interpreter_alpha'
        assert dependent['name'] == 'Test Interpreter Alpha'
        assert dependent['type'] == 'interpreter'
        assert dependent['category'] == 'interpreters'

    def test_get_plugin_dependencies_no_dependents(self, client, scripts_manager, test_plugin_beta):
        """Test getting dependencies for plugin with no dependents."""
        # test_plugin_beta is not used by any script
        resp = client.get('/api/system/plugin-dependencies/test_plugin_beta')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['plugin_id'] == 'test_plugin_beta'
        assert data['used_by'] == []
        assert data['count'] == 0

    def test_get_plugin_dependencies_multiple(self, client, scripts_manager, test_interpreter_multi_plugin):
        """Test script that depends on multiple plugins."""
        # test_interpreter_multi_plugin uses both test_plugin_alpha and test_plugin_beta

        resp = client.get('/api/system/plugin-dependencies/test_plugin_alpha')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['count'] == 1  # Only test_interpreter_multi in this test

        dependent_ids = {d['id'] for d in data['used_by']}
        assert 'test_interpreter_multi' in dependent_ids

    def test_get_plugin_dependencies_nonexistent(self, client, scripts_manager):
        """Test getting dependencies for plugin that doesn't exist."""
        resp = client.get('/api/system/plugin-dependencies/nonexistent_plugin')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['plugin_id'] == 'nonexistent_plugin'
        assert data['used_by'] == []
        assert data['count'] == 0

    def test_active_interpreters_list(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test getting list of active interpreters."""
        # Debug: Check if script exists in test's manager
        test_scripts = scripts_manager.list_scripts(category='interpreters')
        print(f"DEBUG: Test scripts_manager has {len(test_scripts)} interpreters")
        for s in test_scripts:
            print(f"  - {s.id}: {s.validation_status}, active={s.is_active}")

        # Debug: Check directly in DB
        import sqlite3
        from scidk.core import path_index_sqlite as pix
        conn = pix.connect()
        cur = conn.cursor()
        rows = cur.execute("SELECT id, category, validation_status, is_active, is_file_based FROM scripts").fetchall()
        print(f"DEBUG: Direct DB query found {len(rows)} scripts:")
        for row in rows:
            id_, cat, val_status, is_act, is_file = row
            print(f"  - id={id_}, cat={cat}, val={val_status}, active={is_act}, file={is_file}")
        conn.close()

        resp = client.get('/api/system/active-interpreters')
        assert resp.status_code == 200

        data = resp.get_json()
        print(f"DEBUG: API returned {data['count']} interpreters")
        assert 'interpreters' in data
        assert 'count' in data
        assert data['count'] >= 1

        # Find our test interpreter
        interpreter = next(
            (i for i in data['interpreters'] if i['id'] == 'test_interpreter_alpha'),
            None
        )

        assert interpreter is not None
        assert interpreter['name'] == 'Test Interpreter Alpha'
        assert interpreter['validation_status'] == 'validated'
        assert interpreter['is_active'] is True
        assert 'validation_timestamp' in interpreter

    def test_active_interpreters_excludes_inactive(self, client, scripts_manager, test_interpreter_with_plugin, unvalidated_interpreter):
        """Test that inactive/unvalidated interpreters are excluded."""
        resp = client.get('/api/system/active-interpreters')
        data = resp.get_json()

        interpreter_ids = {i['id'] for i in data['interpreters']}

        # Active interpreter should be present
        assert 'test_interpreter_alpha' in interpreter_ids

        # Unvalidated interpreter should NOT be present
        assert 'test_interpreter_draft' not in interpreter_ids

    def test_script_status_full_details(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test getting complete script status with dependencies."""
        resp = client.get('/api/system/script-status/test_interpreter_alpha')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['id'] == 'test_interpreter_alpha'
        assert data['name'] == 'Test Interpreter Alpha'
        assert data['category'] == 'interpreters'
        assert data['validation_status'] == 'validated'
        assert data['is_active'] is True

        # Check dependencies
        assert 'dependencies' in data
        assert 'test_plugin_alpha' in data['dependencies']

        # Check used_by
        assert 'used_by_count' in data
        assert 'used_by' in data

    def test_script_status_plugin_with_dependents(self, client, scripts_manager, test_interpreter_with_plugin):
        """Test script status for a plugin that has dependents."""
        resp = client.get('/api/system/script-status/test_plugin_alpha')
        assert resp.status_code == 200

        data = resp.get_json()
        assert data['id'] == 'test_plugin_alpha'
        assert data['category'] == 'plugins'

        # Plugin has 1 dependent (test_interpreter_alpha)
        assert data['used_by_count'] == 1
        assert len(data['used_by']) == 1
        assert data['used_by'][0]['id'] == 'test_interpreter_alpha'
        assert data['used_by'][0]['type'] == 'interpreter'

    def test_script_status_nonexistent(self, client, scripts_manager):
        """Test getting status for script that doesn't exist."""
        resp = client.get('/api/system/script-status/nonexistent_script')
        assert resp.status_code == 404

        data = resp.get_json()
        assert 'error' in data
        assert 'not found' in data['error'].lower()
