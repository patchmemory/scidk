"""FIX-1, FIX-2, FIX-3 — the flat scan listing, its field aliases, and the
error semantics of ``/api/browse``.

Companion to ``test_scan_browse_indexed.py``, which covers the hierarchical
listing these three fixes sit beside.
"""
import pytest

from scidk.core import path_index_sqlite as pix
from scidk.app import create_app
from tests.conftest import authenticate_test_client


SCAN_ID = 'scan-entries'
PARENT = 'remote:bucket'


def _seed(conn, scan_id=SCAN_ID, parent=PARENT):
    rows = [
        (f'{parent}/zdir', parent, 'zdir', 1, 'folder', 0, None, None, None, None, None, 'remote', scan_id, None),
        (f'{parent}/adir', parent, 'adir', 1, 'folder', 0, None, None, None, None, None, 'remote', scan_id, None),
        (f'{parent}/adir/nested.csv', f'{parent}/adir', 'nested.csv', 2, 'file', 78, 1700.0, '.csv', 'text/csv', None, None, 'remote', scan_id, None),
        (f'{parent}/b.txt', parent, 'b.txt', 2, 'file', 12, 1000.5, '.txt', 'text/plain', None, None, 'remote', scan_id, None),
        (f'{parent}/a.csv', parent, 'a.csv', 2, 'file', 34, 1100.0, '.csv', 'text/csv', None, None, 'remote', scan_id, None),
    ]
    conn.executemany(
        "INSERT INTO files(path, parent_path, name, depth, type, size, modified_time, file_extension,"
        " mime_type, etag, hash, remote, scan_id, extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    conn = pix.connect()
    try:
        pix.init_db(conn)
        _seed(conn)
    finally:
        conn.close()

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        app.extensions['scidk'].setdefault('scans', {})[SCAN_ID] = {'id': SCAN_ID, 'path': PARENT}
    return authenticate_test_client(app.test_client(), app)


# ── FIX-1 — /api/scans/<id>/entries ────────────────────────────────────────

def test_entries_returns_every_record_flat(client):
    """Flat: the nested file appears alongside its parent's siblings.

    That is the whole difference from /browse, which would only show the
    directory `adir` at this level.
    """
    r = client.get(f'/api/scans/{SCAN_ID}/entries', query_string={'page_size': 100})
    assert r.status_code == 200
    data = r.get_json()
    assert [e['name'] for e in data['entries']] == [
        'a.csv', 'adir', 'nested.csv', 'b.txt', 'zdir',
    ]
    assert data['scan_id'] == SCAN_ID


def test_entries_filters_and_paginates(client):
    r = client.get(f'/api/scans/{SCAN_ID}/entries', query_string={'extension': '.csv'})
    assert [e['name'] for e in r.get_json()['entries']] == ['a.csv', 'nested.csv']

    r = client.get(f'/api/scans/{SCAN_ID}/entries', query_string={'type': 'folder'})
    assert [e['name'] for e in r.get_json()['entries']] == ['adir', 'zdir']

    first = client.get(f'/api/scans/{SCAN_ID}/entries', query_string={'page_size': 2}).get_json()
    assert [e['name'] for e in first['entries']] == ['a.csv', 'adir']
    assert 'next_page_token' in first
    second = client.get(
        f'/api/scans/{SCAN_ID}/entries',
        query_string={'page_size': 2, 'next_page_token': first['next_page_token']},
    ).get_json()
    assert [e['name'] for e in second['entries']] == ['nested.csv', 'b.txt']


def test_entries_404_on_unknown_scan(client):
    assert client.get('/api/scans/doesnotexist/entries').status_code == 404


# ── FIX-2 — field aliases shared with /api/browse ──────────────────────────

@pytest.mark.parametrize('route', ['browse', 'entries'])
def test_index_listings_carry_browse_field_aliases(client, route):
    """Both index listings speak /api/browse's field names as well as their own.

    The Files page switches between live and index mode; without the aliases it
    has to guess which spelling it is holding.
    """
    qs = {'path': PARENT} if route == 'browse' else {}
    entries = client.get(f'/api/scans/{SCAN_ID}/{route}', query_string=qs).get_json()['entries']
    by_name = {e['name']: e for e in entries}

    txt = by_name['b.txt']
    assert txt['id'] == txt['path'] == f'{PARENT}/b.txt'
    assert txt['mtime'] == txt['modified'] == 1000.5
    assert txt['size'] == txt['size_bytes'] == 12


# ── FIX-3 — /api/browse error semantics ────────────────────────────────────

def test_browse_missing_path_is_404(client, tmp_path):
    r = client.get('/api/browse', query_string={
        'provider_id': 'local_fs',
        'root_id': str(tmp_path),
        'path': str(tmp_path / 'no-such-directory'),
    })
    assert r.status_code == 404
    body = r.get_json()
    assert body['code'] == 'browse_not_found'
    assert body['entries'] == []


def test_browse_unreadable_path_is_403(client, tmp_path, monkeypatch):
    """A directory the process cannot read is the caller's answer, not a 500.

    PermissionError is injected rather than produced with chmod: the test suite
    may run as root, for whom no directory is unreadable.
    """
    from scidk.core.providers import LocalFSProvider

    def boom(self, root_id, path, *a, **kw):
        raise PermissionError(13, 'Permission denied', path)

    monkeypatch.setattr(LocalFSProvider, 'list', boom)
    r = client.get('/api/browse', query_string={
        'provider_id': 'local_fs', 'root_id': str(tmp_path), 'path': str(tmp_path),
    })
    assert r.status_code == 403
    body = r.get_json()
    assert body['code'] == 'browse_forbidden'
    assert body['entries'] == []


def test_browse_empty_directory_is_still_200(client, tmp_path):
    """The 404 must not swallow the ordinary empty-folder case."""
    empty = tmp_path / 'empty'
    empty.mkdir()
    r = client.get('/api/browse', query_string={
        'provider_id': 'local_fs', 'root_id': str(empty), 'path': str(empty),
    })
    assert r.status_code == 200
    assert r.get_json()['entries'] == []
