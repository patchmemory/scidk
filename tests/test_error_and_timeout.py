import time
import pytest
from pathlib import Path

from scidk.core.filesystem import FilesystemManager
from scidk.core.graph import InMemoryGraph
from scidk.core.registry import InterpreterRegistry
from scidk.core.security import SecureInterpreterExecutor, TimeoutException
from scidk.interpreters.python_code import PythonCodeInterpreter


def test_python_interpreter_syntax_error_scan(tmp_path: Path, bad_py_file: Path):
    # Arrange
    graph = InMemoryGraph()
    reg = InterpreterRegistry()
    reg.register_extension('.py', PythonCodeInterpreter())
    fs = FilesystemManager(graph=graph, registry=reg)

    # Act
    count = fs.scan_directory(tmp_path, recursive=False)

    # Assert: 1 file scanned and interpreted with error
    assert count == 1
    datasets = graph.list_datasets()
    assert len(datasets) == 1
    ds = datasets[0]
    assert ds['filename'] == 'bad.py'
    interp = ds['interpretations'].get('python_code')
    assert interp is not None
    assert interp['status'] == 'error'
    assert interp['data'].get('error_type') == 'SYNTAX_ERROR'


def test_secure_executor_python_timeout():
    execu = SecureInterpreterExecutor(default_timeout=1)

    def sleepy():
        time.sleep(2)
        return 'done'

    with pytest.raises(TimeoutException):
        execu.run_python_inline(sleepy)


def test_secure_executor_bash_timeout(tmp_path: Path):
    execu = SecureInterpreterExecutor(default_timeout=1)
    result = execu.run_bash('sleep 2', cwd=tmp_path, timeout=1)
    assert isinstance(result, dict)
    assert result.get('returncode') == -1
    assert result.get('stderr') == 'timeout'
