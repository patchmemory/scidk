from pathlib import Path
from scidk.core.filesystem import FilesystemManager
from scidk.core.graph import InMemoryGraph
from scidk.core.registry import InterpreterRegistry


def test_rescan_does_not_duplicate(tmp_path: Path):
    # Create 2 files
    (tmp_path / 'a.txt').write_text('hello', encoding='utf-8')
    (tmp_path / 'b.txt').write_text('world', encoding='utf-8')

    graph = InMemoryGraph()
    reg = InterpreterRegistry()
    fs = FilesystemManager(graph=graph, registry=reg)

    # First scan
    count1 = fs.scan_directory(tmp_path, recursive=False)
    assert count1 == 2
    assert len(graph.list_datasets()) == 2

    # Second scan (same path)
    count2 = fs.scan_directory(tmp_path, recursive=False)
    assert count2 == 2
    # Still only 2 datasets stored
    assert len(graph.list_datasets()) == 2
