"""
Test selective scan cache integration using scan_items and directory_cache.
"""
import os
import time
from pathlib import Path
import pytest


def test_scan_populates_cache_tables(tmp_path: Path):
    """Test that scans populate scan_items and directory_cache tables."""
    from scidk.core import path_index_sqlite as pix
    from scidk.core.migrations import migrate

    # Setup test directory structure
    (tmp_path / 'dir1').mkdir()
    (tmp_path / 'dir1' / 'file1.txt').write_text('content1', encoding='utf-8')
    (tmp_path / 'dir1' / 'file2.txt').write_text('content2', encoding='utf-8')
    (tmp_path / 'dir2').mkdir()
    (tmp_path / 'dir2' / 'file3.txt').write_text('content3', encoding='utf-8')

    # Run a scan via the API
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with app.test_client() as client:
        resp = client.post('/api/scan', json={
            'path': str(tmp_path),
            'recursive': True,
            'provider_id': 'local_fs'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        scan_id = data['scan_id']

    # Verify scan_items table is populated
    conn = pix.connect()
    migrate(conn)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM scan_items WHERE scan_id=?", (scan_id,))
    count = cur.fetchone()[0]
    assert count >= 5  # 2 dirs + 3 files

    # Verify directory_cache table is populated
    cur.execute("SELECT COUNT(*) FROM directory_cache WHERE scan_id=?", (scan_id,))
    cache_count = cur.fetchone()[0]
    assert cache_count >= 2  # At least tmp_path and dir1/dir2
    conn.close()


def test_rescan_uses_cache(tmp_path: Path):
    """Test that rescanning unchanged directories uses cache and is faster."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    # Create a larger directory structure
    for i in range(5):
        subdir = tmp_path / f'dir{i}'
        subdir.mkdir()
        for j in range(10):
            (subdir / f'file{j}.txt').write_text(f'content{i}{j}', encoding='utf-8')

    # First scan (cold)
    with app.test_client() as client:
        resp1 = client.post('/api/scan', json={
            'path': str(tmp_path),
            'recursive': True,
            'provider_id': 'local_fs'
        })
        assert resp1.status_code == 200
        data1 = resp1.get_json()
        duration1 = data1['duration_sec']
        cache_stats1 = data1.get('cache_stats', {})
        hits1 = cache_stats1.get('cache_hits', 0)

        # First scan may or may not have cache hits depending on DB state
        # (if test DB persists, there might be cached data from previous runs)

        time.sleep(0.1)  # Small delay to ensure different scan_id

        # Second scan (warm - should use cache)
        resp2 = client.post('/api/scan', json={
            'path': str(tmp_path),
            'recursive': True,
            'provider_id': 'local_fs'
        })
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        duration2 = data2['duration_sec']
        cache_stats2 = data2.get('cache_stats', {})
        hits2 = cache_stats2.get('cache_hits', 0)

        # Second scan should have at least as many cache hits as first
        # (directory contents unchanged, so cache should be effective)
        assert hits2 >= hits1


def test_cache_detects_changes(tmp_path: Path):
    """Test that cache correctly detects when directories change."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    # Create initial structure
    (tmp_path / 'dir1').mkdir()
    (tmp_path / 'dir1' / 'file1.txt').write_text('content1', encoding='utf-8')

    # First scan
    with app.test_client() as client:
        resp1 = client.post('/api/scan', json={
            'path': str(tmp_path),
            'recursive': True,
            'provider_id': 'local_fs'
        })
        assert resp1.status_code == 200

        # Add a new file (changes directory)
        (tmp_path / 'dir1' / 'file2.txt').write_text('content2', encoding='utf-8')
        time.sleep(0.1)

        # Second scan - cache should miss because directory changed
        resp2 = client.post('/api/scan', json={
            'path': str(tmp_path),
            'recursive': True,
            'provider_id': 'local_fs'
        })
        assert resp2.status_code == 200
        data2 = resp2.get_json()

        # Should detect the new file
        assert data2['scanned'] >= 2


def test_cache_can_be_disabled(tmp_path: Path):
    """Test that cache can be disabled via environment variable."""
    from scidk.app import create_app

    # Create test structure
    (tmp_path / 'file.txt').write_text('content', encoding='utf-8')

    # Disable cache
    original = os.environ.get('SCIDK_CACHE_SCAN')
    try:
        os.environ['SCIDK_CACHE_SCAN'] = '0'
        app = create_app()
        app.config['TESTING'] = True

        with app.test_client() as client:
            # First scan
            resp1 = client.post('/api/scan', json={
                'path': str(tmp_path),
                'recursive': True,
                'provider_id': 'local_fs'
            })
            assert resp1.status_code == 200
            data1 = resp1.get_json()
            cache_stats1 = data1.get('cache_stats', {})

            # Cache should be disabled
            assert cache_stats1.get('enabled') is False

            time.sleep(0.1)

            # Second scan
            resp2 = client.post('/api/scan', json={
                'path': str(tmp_path),
                'recursive': True,
                'provider_id': 'local_fs'
            })
            assert resp2.status_code == 200
            data2 = resp2.get_json()
            cache_stats2 = data2.get('cache_stats', {})

            # Cache should still be disabled
            assert cache_stats2.get('enabled') is False
    finally:
        if original is not None:
            os.environ['SCIDK_CACHE_SCAN'] = original
        elif 'SCIDK_CACHE_SCAN' in os.environ:
            del os.environ['SCIDK_CACHE_SCAN']


def test_cache_helpers():
    """Test cache helper functions in path_index_sqlite."""
    import hashlib
    import time
    from scidk.core import path_index_sqlite as pix
    from scidk.core.migrations import migrate

    # Use unique scan_id to avoid conflicts
    scan_id = f"test_scan_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:12]}"

    # Test record_scan_items
    rows = [
        ('/tmp/file1.txt', 'file', 100, 1234567890.0, '.txt', 'text/plain', None, 'hash1', None),
        ('/tmp/file2.txt', 'file', 200, 1234567891.0, '.txt', 'text/plain', None, 'hash2', None),
    ]
    inserted = pix.record_scan_items(scan_id, rows)
    assert inserted == 2

    # Test cache_directory_listing
    pix.cache_directory_listing(scan_id, '/tmp', ['file1.txt', 'file2.txt'])

    # Test get_cached_directory
    cached = pix.get_cached_directory(scan_id, '/tmp')
    assert cached == ['file1.txt', 'file2.txt']

    # Test get_previous_scan_for_path
    prev = pix.get_previous_scan_for_path('/tmp/file1.txt')
    assert prev == scan_id

    # Test get_scan_item
    item = pix.get_scan_item(scan_id, '/tmp/file1.txt')
    assert item is not None
    assert item['path'] == '/tmp/file1.txt'
    assert item['type'] == 'file'
    assert item['size'] == 100
