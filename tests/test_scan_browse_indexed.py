import os
import sqlite3
from pathlib import Path

import pytest

from scidk.core import path_index_sqlite as pix
from scidk.app import create_app
from tests.conftest import authenticate_test_client


def _insert_rows(conn, rows):
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO files(path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def test_scan_browse_index_listing_sort_filter_pagination(monkeypatch, tmp_path):
    # Use a temp SQLite DB
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    # Prepare data for scan "scan1" under parent "remote:bucket"
    scan_id = 'scan1'
    parent = 'remote:bucket'
    rows = [
        # folders
        (f'{parent}/zdir', parent, 'zdir', 1, 'folder', 0, None, None, None, None, None, 'remote', scan_id, None),
        (f'{parent}/adir', parent, 'adir', 1, 'folder', 0, None, None, None, None, None, 'remote', scan_id, None),
        # files
        (f'{parent}/b.txt', parent, 'b.txt', 2, 'file', 12, None, '.txt', 'text/plain', None, None, 'remote', scan_id, None),
        (f'{parent}/a.csv', parent, 'a.csv', 2, 'file', 34, None, '.csv', 'text/csv', None, None, 'remote', scan_id, None),
        (f'{parent}/c.txt', parent, 'c.txt', 2, 'file', 56, None, '.txt', 'text/plain', None, None, 'remote', scan_id, None),
    ]
    conn = pix.connect()
    try:
        pix.init_db(conn)
        _insert_rows(conn, rows)
    finally:
        conn.close()

    # Build app and seed minimal scan registry
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        app.extensions['scidk'].setdefault('scans', {})[scan_id] = {
            'id': scan_id,
            'path': parent,
        }

    client = authenticate_test_client(app.test_client(), app)

    # 1) Basic listing at parent, expect: folders (adir, zdir) then files (a.csv, b.txt, c.txt)
    r = client.get(f'/api/scans/{scan_id}/browse', query_string={'path': parent, 'page_size': 10})
    assert r.status_code == 200
    data = r.get_json()
    names = [e['name'] for e in data['entries']]
    assert names == ['adir', 'zdir', 'a.csv', 'b.txt', 'c.txt']

    # 2) Filter by extension .txt -> b.txt, c.txt (sorted by name)
    r = client.get(f'/api/scans/{scan_id}/browse', query_string={'path': parent, 'extension': '.txt'})
    assert r.status_code == 200
    data = r.get_json()
    names = [e['name'] for e in data['entries']]
    assert names == ['b.txt', 'c.txt']

    # 3) Filter by type folder -> adir, zdir
    r = client.get(f'/api/scans/{scan_id}/browse', query_string={'path': parent, 'type': 'folder'})
    assert r.status_code == 200
    data = r.get_json()
    names = [e['name'] for e in data['entries']]
    assert names == ['adir', 'zdir']

    # 4) Pagination: page_size=2 -> first page (adir, zdir), token -> second page (a.csv, b.txt)
    r1 = client.get(f'/api/scans/{scan_id}/browse', query_string={'path': parent, 'page_size': 2})
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert [e['name'] for e in d1['entries']] == ['adir', 'zdir']
    assert 'next_page_token' in d1
    r2 = client.get(f"/api/scans/{scan_id}/browse", query_string={'path': parent, 'page_size': 2, 'next_page_token': d1['next_page_token']})
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert [e['name'] for e in d2['entries']] == ['a.csv', 'b.txt']

    # 5) 404 when scan not found
    r = client.get('/api/scans/doesnotexist/browse', query_string={'path': parent})
    assert r.status_code == 404
