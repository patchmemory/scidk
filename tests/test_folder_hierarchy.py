import pytest

from scidk.core.folder_hierarchy import build_complete_folder_hierarchy


def as_edges(folder_rows):
    edges = set()
    for fr in folder_rows:
        p = fr.get('parent') or ''
        c = fr.get('path') or ''
        if p and c and p != c:
            edges.add((p, c))
    return edges


def test_simple_two_level_local():
    scan = {'path': '/base'}
    rows = [
        {
            'path': '/base/folder1/file1.txt',
            'folder': '/base/folder1',
            'filename': 'file1.txt',
        }
    ]
    folder_rows = [
        {'path': '/base/folder1', 'name': 'folder1', 'parent': '/base', 'parent_name': 'base'}
    ]
    out = build_complete_folder_hierarchy(rows, folder_rows, scan)
    paths = {fr['path'] for fr in out}
    assert '/base' in paths
    assert '/base/folder1' in paths
    edges = as_edges(out)
    assert ('/base', '/base/folder1') in edges


def test_deep_nested_local():
    scan = {'path': '/base'}
    rows = [
        {
            'path': '/base/f1/s1/d1/file1.txt',
            'folder': '/base/f1/s1/d1',
            'filename': 'file1.txt',
        }
    ]
    folder_rows = []
    out = build_complete_folder_hierarchy(rows, folder_rows, scan)
    edges = as_edges(out)
    expected_chain = [
        ('/base', '/base/f1'),
        ('/base/f1', '/base/f1/s1'),
        ('/base/f1/s1', '/base/f1/s1/d1'),
    ]
    for e in expected_chain:
        assert e in edges


def test_remote_rclone_paths():
    # rclone style: remote:path/to/folder
    scan = {'path': 'remote:root'}
    rows = [
        {
            'path': 'remote:root/f1/s1/d1/file.txt',
            'folder': 'remote:root/f1/s1/d1',
            'filename': 'file.txt',
        }
    ]
    out = build_complete_folder_hierarchy(rows, [], scan)
    edges = as_edges(out)
    # Ensure ancestors are built correctly
    assert ('remote:root', 'remote:root/f1') in edges
    assert ('remote:root/f1', 'remote:root/f1/s1') in edges
    assert ('remote:root/f1/s1', 'remote:root/f1/s1/d1') in edges


def test_no_orphan_folders_except_root():
    scan = {'path': '/base'}
    rows = [
        {'path': '/base/a/b/c/file.txt', 'folder': '/base/a/b/c', 'filename': 'file.txt'}
    ]
    out = build_complete_folder_hierarchy(rows, [], scan)
    parents = {fr['parent'] for fr in out}
    paths = {fr['path'] for fr in out}
    # every folder except scan base should appear as a child in some edge
    edges = as_edges(out)
    children_with_parent = {c for (_, c) in edges}
    for p in paths:
        if p == '/base':
            continue
        assert p in children_with_parent
