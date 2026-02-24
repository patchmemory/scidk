"""Test data fixtures for transparency layers testing.

This module provides reusable fixtures for creating test scripts (plugins, interpreters, links)
with proper validation status and dependency relationships.
"""
import pytest
import tempfile
import time
from pathlib import Path
from scidk.core.scripts import ScriptsManager, Script
from scidk.core.script_validators import BaseValidator, InterpreterValidator, LinkValidator, extract_plugin_dependencies


@pytest.fixture(scope="function")
def scripts_manager():
    """Create ScriptsManager instance using shared test database.

    Uses pix.connect() which reads SCIDK_DB_PATH from conftest,
    ensuring scripts are visible to Flask app routes.

    Function-scoped to ensure clean state for each test.
    Cleanup happens BEFORE each test to remove artifacts from previous test.
    """
    import os
    import sqlite3
    from scidk.core.migrations import migrate
    from scidk.core import path_index_sqlite as pix

    # Use pix.connect() to get the same database as API routes
    conn = pix.connect()
    migrate(conn)

    manager = ScriptsManager(conn=conn, use_file_registry=False)

    # Cleanup BEFORE test to ensure clean state
    # This removes scripts AND their dependencies from previous tests
    test_script_ids = [
        'test_plugin_alpha', 'test_plugin_beta',
        'test_interpreter_alpha', 'test_interpreter_multi',
        'test_interpreter_draft', 'test_interpreter_failing',
        'test_link_alpha', 'draft_interpreter'  # Used by test_no_dependencies_for_unvalidated_script
    ]

    # Delete dependencies first, then scripts
    # Note: script_dependencies uses 'dependent_id' and 'dependency_id', not 'script_id'
    cur = conn.cursor()
    for script_id in test_script_ids:
        try:
            # Delete where script is dependent (uses other scripts/plugins)
            cur.execute("DELETE FROM script_dependencies WHERE dependent_id = ?", (script_id,))
            # Delete where script is a dependency (other scripts use it)
            cur.execute("DELETE FROM script_dependencies WHERE dependency_id = ?", (script_id,))
            # Now delete the script itself
            cur.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
        except Exception as e:
            pass  # Ignore errors during cleanup
    conn.commit()

    yield manager

    # Do NOT cleanup after - let next test's before-cleanup handle it
    # This ensures fixtures created during the test remain available
    # for the entire test duration


@pytest.fixture
def test_plugin(scripts_manager):
    """Create a validated and active test plugin.

    Returns:
        Script: Plugin script object with id 'test_plugin_alpha'
    """
    # Check if already exists (fixture may be reused in test)
    existing = scripts_manager.get_script('test_plugin_alpha')
    if existing:
        return existing

    plugin_code = '''
def run(context):
    """Test plugin that returns sample data."""
    return {
        'result': 'success',
        'data': [1, 2, 3],
        'message': 'Test plugin executed successfully'
    }
'''

    plugin = Script(
        id='test_plugin_alpha',
        name='Test Plugin Alpha',
        description='Test plugin for transparency layer testing',
        code=plugin_code,
        category='plugins',
        language='python',
        validation_status='validated',  # Set directly without validation
        validation_timestamp=time.time(),
        is_active=True
    )

    scripts_manager.create_script(plugin)
    return plugin


@pytest.fixture
def test_interpreter_with_plugin(scripts_manager, test_plugin):
    """Create interpreter that depends on test_plugin_alpha.

    This interpreter uses load_plugin() to call the test plugin,
    creating a dependency relationship.

    Returns:
        Script: Interpreter script object with id 'test_interpreter_alpha'
    """
    # Check if already exists
    existing = scripts_manager.get_script('test_interpreter_alpha')
    if existing:
        return existing

    interpreter_code = '''
def interpret(file_path, manager=None, context=None):
    """Test interpreter that uses a plugin."""
    # Load the plugin - this creates a dependency
    plugin_result = load_plugin('test_plugin_alpha', manager, context)

    # Use plugin result to build file metadata
    return {
        'status': 'success',
        'entity_type': 'TestFile',
        'metadata': {
            'file_path': str(file_path),
            'plugin_used': True,
            'plugin_result': plugin_result
        }
    }
'''

    interpreter = Script(
        id='test_interpreter_alpha',
        name='Test Interpreter Alpha',
        description='Test interpreter for transparency layer testing',
        code=interpreter_code,
        category='interpreters',
        language='python',
        validation_status='validated',  # Set directly
        validation_timestamp=time.time(),
        is_active=True
    )

    scripts_manager.create_script(interpreter)

    # Extract and save dependencies (the key part being tested)
    dependencies = extract_plugin_dependencies(interpreter_code)
    scripts_manager.write_dependencies(interpreter.id, 'interpreter', dependencies)

    return interpreter


@pytest.fixture
def test_plugin_beta(scripts_manager):
    """Create a second test plugin (inactive).

    Returns:
        Script: Plugin script object with id 'test_plugin_beta'
    """
    # Check if already exists
    existing = scripts_manager.get_script('test_plugin_beta')
    if existing:
        return existing

    plugin_code = '''
def run(context):
    """Second test plugin."""
    return {'result': 'beta', 'data': [4, 5, 6]}
'''

    plugin = Script(
        id='test_plugin_beta',
        name='Test Plugin Beta',
        description='Second test plugin (inactive)',
        code=plugin_code,
        category='plugins',
        language='python',
        validation_status='validated',
        validation_timestamp=time.time(),
        is_active=False  # Keep inactive
    )

    scripts_manager.create_script(plugin)
    return plugin


@pytest.fixture
def test_interpreter_multi_plugin(scripts_manager, test_plugin, test_plugin_beta):
    """Create interpreter that depends on multiple plugins.

    Returns:
        Script: Interpreter with dependencies on both test plugins
    """
    # Check if already exists
    existing = scripts_manager.get_script('test_interpreter_multi')
    if existing:
        return existing

    interpreter_code = '''
def interpret(file_path, manager=None, context=None):
    """Test interpreter using multiple plugins."""
    alpha = load_plugin('test_plugin_alpha', manager, context)
    beta = load_plugin('test_plugin_beta', manager, context)

    return {
        'status': 'success',
        'entity_type': 'MultiPluginFile',
        'metadata': {
            'alpha_result': alpha,
            'beta_result': beta
        }
    }
'''

    interpreter = Script(
        id='test_interpreter_multi',
        name='Test Interpreter Multi Plugin',
        description='Interpreter using multiple plugins',
        code=interpreter_code,
        category='interpreters',
        language='python',
        validation_status='validated',
        validation_timestamp=time.time(),
        is_active=True
    )

    scripts_manager.create_script(interpreter)

    # Extract and save dependencies
    dependencies = extract_plugin_dependencies(interpreter_code)
    scripts_manager.write_dependencies(interpreter.id, 'interpreter', dependencies)

    return interpreter


@pytest.fixture
def test_link_script(scripts_manager):
    """Create a validated link script.

    Returns:
        Script: Link script object with id 'test_link_alpha'
    """
    link_code = '''
def create_links(source_nodes, target_nodes, context=None):
    """Test link script."""
    links = []
    for source in source_nodes:
        for target in target_nodes:
            links.append({
                'source_id': source['id'],
                'target_id': target['id'],
                'relationship_type': 'TEST_LINK'
            })
    return links
'''

    link = Script(
        id='test_link_alpha',
        name='Test Link Alpha',
        description='Test link script',
        code=link_code,
        category='links',
        language='python',
        validation_status='validated',
        validation_timestamp=time.time(),
        is_active=True
    )

    scripts_manager.create_script(link)
    return link


@pytest.fixture
def test_file(tmp_path):
    """Create a temporary test file.

    Returns:
        Path: Path to test file
    """
    test_file = tmp_path / "test_sample.txt"
    test_file.write_text("This is test file content for transparency layer testing.")
    return test_file


@pytest.fixture
def unvalidated_interpreter(scripts_manager):
    """Create an unvalidated interpreter (draft status).

    Returns:
        Script: Draft interpreter script
    """
    interpreter_code = '''
def interpret(file_path, manager=None, context=None):
    """Unvalidated test interpreter."""
    return {'status': 'success', 'entity_type': 'DraftFile', 'metadata': {}}
'''

    interpreter = Script(
        id='test_interpreter_draft',
        name='Test Interpreter Draft',
        description='Unvalidated interpreter for testing',
        code=interpreter_code,
        category='interpreters',
        language='python',
        validation_status='draft'  # Stays draft
    )

    scripts_manager.create_script(interpreter)
    # Do NOT validate - leave in draft status

    return interpreter


@pytest.fixture
def failing_interpreter(scripts_manager):
    """Create an interpreter that fails validation.

    Returns:
        Script: Interpreter script that will fail validation
    """
    # Invalid code (syntax error)
    interpreter_code = '''
def interpret(file_path, manager=None, context=None)
    # Missing colon - syntax error
    return {'status': 'error', 'entity_type': 'BadFile'}
'''

    interpreter = Script(
        id='test_interpreter_failing',
        name='Test Interpreter Failing',
        description='Interpreter with syntax error',
        code=interpreter_code,
        category='interpreters',
        language='python',
        validation_status='draft'
    )

    scripts_manager.create_script(interpreter)
    # Validation will fail due to syntax error

    return interpreter
