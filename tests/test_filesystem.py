from pathlib import Path

from scidk.core.filesystem import FilesystemManager
from scidk.core.graph import InMemoryGraph
from scidk.core.registry import InterpreterRegistry
from scidk.interpreters.python_code import PythonCodeInterpreter


def test_scan_directory_counts_and_interpretations(tmp_path: Path, sample_py_file: Path):
    # Arrange: sample_py_file is in a temp dir, add a txt file too
    txt = tmp_path / "note.txt"
    txt.write_text("hello", encoding="utf-8")

    graph = InMemoryGraph()
    reg = InterpreterRegistry()
    reg.register_extension('.py', PythonCodeInterpreter())
    fs = FilesystemManager(graph=graph, registry=reg)

    # Act
    count = fs.scan_directory(tmp_path, recursive=False)

    # Assert: 2 files scanned
    assert count == 2
    datasets = graph.list_datasets()
    assert len(datasets) == 2

    # The .py file should have an interpretation for python_code
    py_ds = next(d for d in datasets if d['extension'] == '.py')
    assert 'python_code' in py_ds['interpretations']
    assert py_ds['interpretations']['python_code']['status'] == 'success'


def test_checksum_stability(tmp_path: Path):
    f1 = tmp_path / 'a.bin'
    f1.write_bytes(b'123456')
    f2 = tmp_path / 'b.bin'
    f2.write_bytes(b'123456')

    graph = InMemoryGraph()
    reg = InterpreterRegistry()
    fs = FilesystemManager(graph=graph, registry=reg)

    c1 = fs.calculate_checksum(f1)
    c2 = fs.calculate_checksum(f2)
    assert c1 == c2


def test_rescan_idempotency(tmp_path: Path, sample_py_file: Path):
    # Add an extra non-py file
    (tmp_path / 'readme.txt').write_text('hello', encoding='utf-8')

    graph = InMemoryGraph()
    reg = InterpreterRegistry()
    # Register python interpreter so interpretations are attempted
    reg.register_extension('.py', PythonCodeInterpreter())
    fs = FilesystemManager(graph=graph, registry=reg)

    # First scan
    count1 = fs.scan_directory(tmp_path, recursive=False)
    datasets1 = graph.list_datasets()
    assert count1 == 2  # sample_py_file + readme.txt
    assert len(datasets1) == 2

    # Second scan of the same directory should not create duplicates
    count2 = fs.scan_directory(tmp_path, recursive=False)
    datasets2 = graph.list_datasets()
    # Count of scanned files remains the same per run
    assert count2 == 2
    # Graph should still contain only 2 unique datasets (by checksum)
    assert len(datasets2) == 2
