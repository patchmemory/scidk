"""Tests for scripts module."""
import json
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scidk.core.scripts import (
    ScriptsManager,
    ScriptExecution,
    Script,
    export_to_csv,
    export_to_json,
    export_to_jupyter,
    import_from_jupyter,
)
from scidk.core.builtin_scripts import get_builtin_scripts


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)

    # Create schema (with v17 columns)
    conn.execute("""
        CREATE TABLE scripts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            language TEXT NOT NULL,
            category TEXT NOT NULL,
            code TEXT NOT NULL,
            parameters TEXT,
            tags TEXT,
            created_at REAL NOT NULL,
            created_by TEXT,
            updated_at REAL NOT NULL,
            file_path TEXT,
            is_file_based INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE script_executions (
            id TEXT PRIMARY KEY,
            script_id TEXT NOT NULL,
            executed_at REAL NOT NULL,
            executed_by TEXT,
            parameters TEXT,
            results TEXT,
            execution_time_ms INTEGER,
            status TEXT NOT NULL,
            error TEXT
        )
    """)

    conn.commit()

    yield conn

    conn.close()
    Path(db_path).unlink()


def test_script_creation():
    """Test creating a Script."""
    script = Script(
        id='test-1',
        name='Test Script',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN n',
        description='A test script',
        parameters=[{'name': 'limit', 'type': 'integer', 'default': 10}],
        tags=['test', 'demo']
    )

    assert script.id == 'test-1'
    assert script.name == 'Test Script'
    assert script.language == 'cypher'
    assert script.category == 'custom'
    assert len(script.parameters) == 1
    assert len(script.tags) == 2


def test_script_to_dict():
    """Test converting Script to dictionary."""
    script = Script(
        id='test-1',
        name='Test Script',
        language='python',
        category='builtin',
        code='print("hello")',
    )

    data = script.to_dict()

    assert data['id'] == 'test-1'
    assert data['name'] == 'Test Script'
    assert data['language'] == 'python'
    assert data['category'] == 'builtin'
    assert data['code'] == 'print("hello")'


def test_script_from_dict():
    """Test creating Script from dictionary."""
    data = {
        'id': 'test-1',
        'name': 'Test Script',
        'language': 'cypher',
        'category': 'custom',
        'code': 'MATCH (n) RETURN n',
        'description': 'Test',
        'parameters': [],
        'tags': ['test']
    }

    script = Script.from_dict(data)

    assert script.id == 'test-1'
    assert script.name == 'Test Script'
    assert script.language == 'cypher'


def test_create_script(temp_db):
    """Test creating a script in the database."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Test Script',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN n'
    )

    created = manager.create_script(script)

    assert created.id == script.id
    assert created.name == script.name


def test_get_script(temp_db):
    """Test retrieving a script by ID."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Test Script',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN n'
    )

    manager.create_script(script)
    retrieved = manager.get_script('test-1')

    assert retrieved is not None
    assert retrieved.id == 'test-1'
    assert retrieved.name == 'Test Script'


def test_get_nonexistent_script(temp_db):
    """Test getting a script that doesn't exist."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)
    result = manager.get_script('nonexistent')

    assert result is None


def test_list_scripts(temp_db):
    """Test listing all scripts."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script1 = Script(
        id='test-1',
        name='Script 1',
        language='cypher',
        category='builtin',
        code='MATCH (n) RETURN n'
    )

    script2 = Script(
        id='test-2',
        name='Script 2',
        language='python',
        category='custom',
        code='print("hello")'
    )

    manager.create_script(script1)
    manager.create_script(script2)

    scripts = manager.list_scripts()

    assert len(scripts) == 2


def test_list_scripts_by_category(temp_db):
    """Test filtering scripts by category."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script1 = Script(
        id='test-1',
        name='Script 1',
        language='cypher',
        category='builtin',
        code='MATCH (n) RETURN n'
    )

    script2 = Script(
        id='test-2',
        name='Script 2',
        language='python',
        category='custom',
        code='print("hello")'
    )

    manager.create_script(script1)
    manager.create_script(script2)

    builtin_scripts = manager.list_scripts(category='builtin')
    custom_scripts = manager.list_scripts(category='custom')

    assert len(builtin_scripts) == 1
    assert len(custom_scripts) == 1
    assert builtin_scripts[0].id == 'test-1'
    assert custom_scripts[0].id == 'test-2'


def test_update_script(temp_db):
    """Test updating an existing script."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Original Name',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN n'
    )

    manager.create_script(script)

    script.name = 'Updated Name'
    script.code = 'MATCH (f:File) RETURN f'

    updated = manager.update_script(script)

    assert updated.name == 'Updated Name'
    assert updated.code == 'MATCH (f:File) RETURN f'

    # Verify in database
    retrieved = manager.get_script('test-1')
    assert retrieved.name == 'Updated Name'


def test_delete_script(temp_db):
    """Test deleting a script."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Test Script',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN n'
    )

    manager.create_script(script)
    assert manager.get_script('test-1') is not None

    deleted = manager.delete_script('test-1')
    assert deleted is True

    assert manager.get_script('test-1') is None


def test_execute_cypher_script(temp_db):
    """Test executing a Cypher script."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Count Nodes',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN count(n) as count'
    )

    manager.create_script(script)

    # Mock Neo4j driver
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_record = {'count': 42}
    mock_result.__iter__ = lambda self: iter([mock_record])

    mock_session.run.return_value = mock_result
    mock_driver.session.return_value.__enter__.return_value = mock_session

    result = manager.execute_script('test-1', neo4j_driver=mock_driver)

    assert result.status == 'success'
    assert len(result.results) == 1
    assert result.results[0]['count'] == 42
    assert result.execution_time_ms >= 0  # Can be 0ms for very fast queries


def test_execute_python_script(temp_db):
    """Test executing a Python script."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Python Test',
        language='python',
        category='custom',
        code='''
results = [
    {'name': 'Alice', 'age': 30},
    {'name': 'Bob', 'age': 25}
]
'''
    )

    manager.create_script(script)

    result = manager.execute_script('test-1')

    assert result.status == 'success'
    assert len(result.results) == 2
    assert result.results[0]['name'] == 'Alice'


def test_execute_script_error(temp_db):
    """Test handling errors during script execution."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    script = Script(
        id='test-1',
        name='Bad Script',
        language='python',
        category='custom',
        code='raise ValueError("Test error")'
    )

    manager.create_script(script)

    result = manager.execute_script('test-1')

    assert result.status == 'error'
    assert result.error is not None
    assert 'Test error' in result.error


def test_save_and_retrieve_result(temp_db):
    """Test saving and retrieving execution results."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    result = ScriptExecution(
        id='result-1',
        script_id='script-1',
        executed_at=time.time(),
        status='success',
        results=[{'count': 42}],
        execution_time_ms=100
    )

    manager.save_result(result)

    retrieved = manager.get_result('result-1')

    assert retrieved is not None
    assert retrieved.id == 'result-1'
    assert retrieved.status == 'success'
    assert len(retrieved.results) == 1


def test_list_results(temp_db):
    """Test listing execution results."""
    manager = ScriptsManager(conn=temp_db, use_file_registry=False)

    result1 = ScriptExecution(
        id='result-1',
        script_id='script-1',
        executed_at=time.time(),
        status='success',
        results=[{'count': 1}],
        execution_time_ms=100
    )

    result2 = ScriptExecution(
        id='result-2',
        script_id='script-1',
        executed_at=time.time() + 1,
        status='success',
        results=[{'count': 2}],
        execution_time_ms=150
    )

    manager.save_result(result1)
    manager.save_result(result2)

    results = manager.list_results(script_id='script-1')

    assert len(results) == 2
    # Should be ordered by executed_at DESC
    assert results[0].id == 'result-2'
    assert results[1].id == 'result-1'


def test_export_to_csv():
    """Test exporting results to CSV."""
    results = [
        {'name': 'Alice', 'age': 30},
        {'name': 'Bob', 'age': 25}
    ]

    csv_data = export_to_csv(results)

    assert 'name,age' in csv_data
    assert 'Alice,30' in csv_data
    assert 'Bob,25' in csv_data


def test_export_to_json():
    """Test exporting results to JSON."""
    results = [
        {'name': 'Alice', 'age': 30},
        {'name': 'Bob', 'age': 25}
    ]

    json_data = export_to_json(results)
    parsed = json.loads(json_data)

    assert len(parsed) == 2
    assert parsed[0]['name'] == 'Alice'
    assert parsed[1]['name'] == 'Bob'


def test_export_to_jupyter():
    """Test generating Jupyter notebook."""
    script = Script(
        id='test-1',
        name='Test Script',
        language='cypher',
        category='custom',
        code='MATCH (n) RETURN count(n) as count',
        description='Count all nodes'
    )

    result = ScriptExecution(
        id='result-1',
        script_id='test-1',
        executed_at=time.time(),
        status='success',
        results=[{'count': 42}],
        execution_time_ms=100
    )

    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'test'
    }

    notebook = export_to_jupyter(script, result, neo4j_config)

    assert notebook['nbformat'] == 4
    assert len(notebook['cells']) > 0
    assert any('Test Script' in str(cell.get('source', '')) for cell in notebook['cells'])


def test_import_from_jupyter(tmp_path):
    """Test importing scripts from a Jupyter notebook."""
    notebook_content = {
        'cells': [
            {
                'cell_type': 'markdown',
                'source': ['# Test Notebook']
            },
            {
                'cell_type': 'code',
                'source': ['MATCH (n) RETURN count(n) as count']
            },
            {
                'cell_type': 'code',
                'source': ['print("hello world")']
            }
        ],
        'metadata': {},
        'nbformat': 4,
        'nbformat_minor': 4
    }

    notebook_path = tmp_path / 'test.ipynb'
    with open(notebook_path, 'w') as f:
        json.dump(notebook_content, f)

    scripts = import_from_jupyter(notebook_path)

    assert len(scripts) == 2
    assert any(s.language == 'cypher' for s in scripts)
    assert any(s.language == 'python' for s in scripts)


def test_builtin_scripts():
    """Test that built-in scripts are properly defined."""
    scripts = get_builtin_scripts()

    assert len(scripts) == 7

    # Check all scripts have required fields
    for script in scripts:
        assert script.id.startswith('builtin-')
        assert script.name
        assert script.language in ['cypher', 'python']
        assert script.category == 'analyses/builtin'
        assert script.code
        assert isinstance(script.tags, list)


def test_builtin_file_distribution_script():
    """Test the file distribution built-in script."""
    scripts = get_builtin_scripts()
    file_dist = next(s for s in scripts if s.id == 'builtin-file-distribution')

    assert file_dist.name == 'File Distribution by Extension'
    assert file_dist.language == 'cypher'
    assert 'MATCH (f:File)' in file_dist.code
    assert len(file_dist.parameters) == 1
    assert file_dist.parameters[0]['name'] == 'limit'


def test_builtin_largest_files_script():
    """Test the largest files built-in script."""
    scripts = get_builtin_scripts()
    largest = next(s for s in scripts if s.id == 'builtin-largest-files')

    assert largest.name == 'Largest Files'
    assert largest.language == 'cypher'
    assert 'ORDER BY f.size DESC' in largest.code
