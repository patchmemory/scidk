"""Read-only Scans browser over an external files.db (SCIDK_EXTERNAL_INDEX_DB)."""
import hashlib
import json
import os
import sqlite3

import pytest

from scidk.app import create_app

SCAN = 'scan-1'


def _build(path):
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE scans (id TEXT PRIMARY KEY, root TEXT, started REAL, completed REAL, status TEXT, extra_json TEXT);
        CREATE TABLE scan_progress (scan_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL, updated REAL, PRIMARY KEY (scan_id, metric));
        CREATE TABLE files (path TEXT NOT NULL, parent_path TEXT, name TEXT NOT NULL, depth INTEGER NOT NULL, type TEXT NOT NULL,
            size INTEGER NOT NULL, modified_time REAL, file_extension TEXT, scan_id TEXT);
        CREATE INDEX idx_files_scan_parent ON files(scan_id, parent_path, name);
        CREATE INDEX idx_files_scan_parent_name ON files(scan_id, parent_path, name);
        CREATE INDEX idx_files_path_prefix ON files(scan_id, type, path);
        CREATE TABLE object_members (object_id TEXT NOT NULL, file_path TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
            PRIMARY KEY (object_id, file_path));
        CREATE TABLE data_objects (id TEXT PRIMARY KEY, pattern_name TEXT NOT NULL, root_path TEXT NOT NULL, scan_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate', confidence REAL NOT NULL DEFAULT 1.0, file_count INTEGER, total_bytes INTEGER);
        CREATE INDEX idx_do_root ON data_objects(root_path);
    ''')
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?)", (SCAN, '/data0/core/atwai', 1.0, 2.0, 'complete', '{}'))
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?)", ('scan-2', '/mnt/old/thing', 1.0, 2.0, 'completed', json.dumps({'file_count': 7})))
    for metric, value in (('files_scanned', 12), ('bytes_scanned', 3000), ('dirs_scanned', 2)):
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (SCAN, metric, value, 0))
    for i in range(205):
        conn.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)',
                     (f'/data0/core/atwai/f{i:03}.txt', '/data0/core/atwai', f'f{i:03}.txt', 1, 'file', i, 5.0, '.txt', SCAN))
    for pattern, root in (('vevo_ultrasound', '/data0/core/atwai/huang'), ('vevo_ultrasound', '/data0/core/atwai/huang/s1'),
                          ('vevo_ultrasound', '/data0/core/atwai/huangw/s2'), ('vevo_ultrasound', '/data0/core/atwai/hu_ng/s3'),
                          ('vevo_ultrasound', '/data0/core/atwai/huXng/s4')):
        conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, file_count, total_bytes) VALUES (?,?,?,?,1,10)",
                     (root, pattern, root, SCAN))
    _build_demo(conn)
    conn.commit()
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()


D = '/data0/core/demo/s'


def _build_demo(conn):
    """Share 'demo': a latest full-root scan plus other mounts/subfolders/unfinished; share 'solo': subfolder scan only."""
    for sid, root, status, started, files in (
            ('demo-new', '/data0/core/demo', 'complete', 300.0, 1000), ('demo-old', '/net/h1/data/demo', 'completed', 100.0, 400),
            ('demo-sub', '/mnt/server/h2/demo/archive', 'committed', 200.0, 500), ('demo-run', '/data0/core/demo', 'running', 400.0, 50),
            ('solo-sub', '/mnt/server/h3/solo/Data', 'complete', 50.0, 77)):
        conn.execute('INSERT INTO scans VALUES (?,?,?,?,?,?)', (sid, root, started, started + 1, status, '{}'))
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (sid, 'files_scanned', files, 0))
    rows = [(D, 'folder', 0), (D + '/.snapshot', 'folder', 0), (D + '/.Trash-1000', 'folder', 0), (D + '/sub', 'folder', 0),
            (D + '/sub2', 'folder', 0), (D + '/._a', 'file', 1), (D + '/.DS_Store', 'file', 1), (D + '/real.txt', 'file', 5),
            (D + '/readme', 'file', 1), (D + '/notes2', 'file', 1), (D + '/sub/deep_target.txt', 'file', 1),
            (D + '/.snapshot/ghost_target.txt', 'file', 1), (D + '/sub2/._hidden_target', 'file', 1),
            (D + '/.Trash-1000/trash_target.txt', 'file', 1)]
    rows += [(D + '/img_%d.tif' % i, 'file', 100) for i in range(1, 6)] + [(D + '/x_C1_1.tif', 'file', 7)]
    for path, kind, size in rows:
        parent, name = path.rsplit('/', 1)
        conn.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)', (path, parent, name, 1, kind, size, 5.0, '', 'demo-new'))
    for oid, pattern, root, count, confidence in (
            ('d1', 'ivis_spectrum', D + '/.TemporaryItems/folders.501/seq', 2, 1.0), ('d2', 'atwai_workspace', D + '/ws', None, 0.5),
            ('d3', 'vevo_ultrasound', D + '/sub', 40, 1.0), ('d4', 'dicom_series', D + '/sub2', None, 1.0),
            ('d5', 'bruker_microct', D + '/sub3', None, 1.0), ('d6', 'ivis_spectrum', D + '/.snapshot/x', 3, 1.0)):
        conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, file_count, confidence) VALUES (?,?,?,?,?,?)",
                     (oid, pattern, root, 'demo-new', count, confidence))
    for i in range(3):
        conn.execute("INSERT INTO object_members (object_id, file_path) VALUES ('d4', ?)", ('/m/%d' % i,))


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    db = tmp_path / 'files.db'
    _build(str(db))
    monkeypatch.setenv('SCIDK_EXTERNAL_INDEX_DB', str(db))
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    from scidk.core.auth import get_auth_manager
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('alice', 'password123', role='user')
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'alice'))
    return db, client, app


def _digest(db):
    return hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns


def test_named_session_and_get_only(index):
    _, c, app = index
    anonymous = app.test_client()
    for route in ('scans', 'browse?scan_id=scan-1', 'datasets?scan_id=scan-1'):
        assert anonymous.get('/api/external-index/' + route).status_code in (401, 403)
    assert c.post('/api/external-index/scans').status_code in (403, 405)


def test_scans_totals_without_counting_files(index):
    _, c, _ = index
    scans = {s['id']: s for s in c.get('/api/external-index/scans').get_json()['scans']}
    assert scans[SCAN]['files'] == 12 and scans[SCAN]['bytes'] == 3000 and scans[SCAN]['share'] == 'atwai'
    assert scans['scan-2']['files'] == 7 and scans['scan-2']['bytes'] is None


def test_browse_pages_one_folder(index):
    _, c, _ = index
    first = c.get('/api/external-index/browse', query_string={'scan_id': SCAN}).get_json()
    assert len(first['entries']) == 200 and first['has_more'] and first['path'] == '/data0/core/atwai'
    second = c.get('/api/external-index/browse', query_string={'scan_id': SCAN, 'offset': first['next_offset']}).get_json()
    assert len(second['entries']) == 5 and not second['has_more']
    assert c.get('/api/external-index/browse', query_string={'scan_id': 'nope'}).status_code == 404


def test_datasets_match_the_folder_or_below_never_a_sibling_prefix(index):
    _, c, _ = index
    got = c.get('/api/external-index/datasets', query_string={'scan_id': SCAN, 'path': '/data0/core/atwai/huang'}).get_json()
    assert [d['root_path'] for d in got['datasets']] == ['/data0/core/atwai/huang', '/data0/core/atwai/huang/s1']
    # LIKE wildcards in the folder name are literal.
    got = c.get('/api/external-index/datasets', query_string={'scan_id': SCAN, 'path': '/data0/core/atwai/hu_ng'}).get_json()
    assert [d['root_path'] for d in got['datasets']] == ['/data0/core/atwai/hu_ng/s3']
    # a name that merely starts with the folder name ("<folder>.old", "<folder>-x") is not part of it
    assert _get(c, 'datasets', scan_id='demo-new', path=D + '/sub')['datasets'][0]['root_path'] == D + '/sub'
    assert _get(c, 'datasets', scan_id='demo-new', path=D + '/su')['datasets'] == []


def test_file_is_never_written_and_open_is_read_only(index):
    db, c, _ = index
    before = _digest(db)
    for route in ('scans', 'browse?scan_id=scan-1', 'datasets?scan_id=scan-1&path=/data0/core/atwai/huang'):
        assert c.get('/api/external-index/' + route).status_code == 200
    assert _digest(db) == before
    from scidk.web.routes.api_external_index import _open
    conn = _open()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO scans (id) VALUES ('x')")
    finally:
        conn.close()
    assert _digest(db) == before


def test_missing_configuration_is_a_clear_message(index, monkeypatch):
    _, c, _ = index
    monkeypatch.delenv('SCIDK_EXTERNAL_INDEX_DB')
    r = c.get('/api/external-index/scans')
    assert r.status_code == 503 and 'configured' in r.get_json()['error']
    monkeypatch.setenv('SCIDK_EXTERNAL_INDEX_DB', '/nonexistent/files.db')
    assert 'not found' in c.get('/api/external-index/scans').get_json()['error']


def _get(c, route, **args):
    return c.get('/api/external-index/' + route, query_string=args).get_json()


def test_one_total_per_share_older_and_partial_scans_nested(index):
    _, c, _ = index
    got = _get(c, 'scans')
    shares = {x['share']: x for x in got['shares']}
    demo = shares['demo']
    # latest complete full-root scan is the primary; unfinished, other-mount, subfolder and older are never added.
    assert demo['primary_id'] == 'demo-new' and demo['files'] == 1000 and demo['primary_is_full_root']
    assert demo['older_ids'] == ['demo-run', 'demo-sub', 'demo-old']
    assert sum(x['files'] for x in got['shares'] if x['share'] == 'demo') == 1000
    by_id = {s['id']: s for s in got['scans']}
    assert by_id['demo-new']['role'] == 'primary' and by_id['demo-old']['role'] == 'older'
    assert by_id['demo-new']['date'] and by_id['demo-run']['date'] and by_id['demo-sub']['is_full_root'] is False
    # No full-root scan at all: the latest complete scan is shown and flagged.
    solo = shares['solo']
    assert solo['primary_id'] == 'solo-sub' and solo['primary_is_full_root'] is False


def test_browse_hides_system_files_unless_asked(index):
    _, c, _ = index
    names = lambda r: [e['name'] for e in r['entries']]
    hidden = names(_get(c, 'browse', scan_id='demo-new', path=D))
    assert '._a' not in hidden and '.DS_Store' not in hidden and '.snapshot' not in hidden and '.Trash-1000' not in hidden
    assert 'real.txt' in hidden and 'sub' in hidden
    shown = names(_get(c, 'browse', scan_id='demo-new', path=D, system='1'))
    assert {'._a', '.DS_Store', '.snapshot', '.Trash-1000'} <= set(shown)


def test_numbered_series_share_a_key(index):
    _, c, _ = index
    entries = {e['name']: e for e in _get(c, 'browse', scan_id='demo-new', path=D)['entries']}
    keys = {entries['img_%d.tif' % i]['series'] for i in range(1, 6)}
    assert keys == {'img_*.tif'}
    assert entries['x_C1_1.tif']['series'] == 'x_C1_*.tif' and entries['notes2']['series'] == 'notes*'
    assert entries['readme']['series'] is None and entries['sub']['series'] is None
    from scidk.web.routes.api_external_index import series_key
    assert series_key('2026-08-20-19-08-09_3dSlices_C1_110.tif') == '2026-08-20-19-08-09_3dSlices_C1_*.tif'
    assert series_key('a.ome.tif') is None and series_key('7') is None and series_key('v1_2.tar.gz') == 'v1_*.tar.gz'


def test_datasets_hide_noise_and_workspace_candidates_and_fill_counts(index):
    _, c, _ = index
    ids = lambda r: [d['id'] for d in r['datasets']]
    plain = _get(c, 'datasets', scan_id='demo-new', path=D)
    assert ids(plain) == ['d4', 'd5', 'd3'] or sorted(ids(plain)) == ['d3', 'd4', 'd5']
    by_id = {d['id']: d for d in plain['datasets']}
    assert by_id['d4']['file_count'] == 3 and not by_id['d4']['count_pending']      # from object_members
    assert by_id['d5']['file_count'] is None and by_id['d5']['count_pending'] is True   # nothing to count: pending
    assert by_id['d3']['file_count'] == 40
    assert sorted(ids(_get(c, 'datasets', scan_id='demo-new', path=D, workspace='1'))) == ['d2', 'd3', 'd4', 'd5']
    assert sorted(ids(_get(c, 'datasets', scan_id='demo-new', path=D, system='1'))) == ['d1', 'd3', 'd4', 'd5', 'd6']


def test_search_in_folder_prefix_and_contains_paged(index):
    _, c, _ = index
    got = _get(c, 'search', scan_id='demo-new', path=D, q='img_')
    assert [e['name'] for e in got['entries']] == ['img_%d.tif' % i for i in range(1, 6)] and not got['capped']
    assert [e['name'] for e in _get(c, 'search', scan_id='demo-new', path=D, q='eadm', mode='contains')['entries']] == ['readme']
    assert _get(c, 'search', scan_id='demo-new', path=D, q='eadm')['entries'] == []          # prefix does not match inside the name
    first = _get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', q='f')
    assert len(first['entries']) == 200 and first['has_more']
    second = _get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', q='f', cursor=first['next_cursor'])
    assert len(second['entries']) == 5 and not second['has_more']
    assert c.get('/api/external-index/search', query_string={'scan_id': SCAN, 'q': ''}).status_code == 400
    # LIKE wildcards are literal.
    assert _get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', q='f%')['entries'] == []


def test_search_subtree_stays_below_the_folder_and_hides_system_paths(index):
    _, c, _ = index
    sub = lambda **kw: [e['name'] for e in _get(c, 'search', scan_id='demo-new', path=D, scope='subtree', **kw)['entries']]
    assert sub(q='target', mode='contains') == ['deep_target.txt']
    assert sorted(sub(q='target', mode='contains', system='1')) == sorted(
        ['deep_target.txt', 'ghost_target.txt', '._hidden_target', 'trash_target.txt'])
    # a sibling-prefix folder is not part of the subtree
    assert _get(c, 'search', scan_id='demo-new', path=D + '/sub', scope='subtree', q='deep')['entries'][0]['name'] == 'deep_target.txt'
    assert _get(c, 'search', scan_id='demo-new', path=D + '/su', scope='subtree', q='deep')['entries'] == []
    got = _get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', scope='subtree', q='f')
    assert len(got['entries']) == 200 and got['has_more']
    assert len(_get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', scope='subtree', q='f', cursor=got['next_cursor'])['entries']) == 5


def test_search_time_cap_says_narrow_the_search(index, monkeypatch):
    _, c, _ = index
    from scidk.web.routes import api_external_index
    monkeypatch.setattr(api_external_index, 'SEARCH_BUDGET_S', -1.0)
    got = _get(c, 'search', scan_id=SCAN, path='/data0/core/atwai', scope='subtree', q='zzz-no-match')
    assert got['capped'] is True and 'narrow the search' in got['message'] and not got['has_more']


def test_new_routes_are_get_only_and_never_write(index):
    db, c, _ = index
    before = _digest(db)
    for route in ('scans', 'browse?scan_id=demo-new&system=1', 'datasets?scan_id=demo-new&workspace=1&system=1',
                  'search?scan_id=demo-new&q=img&scope=subtree'):
        assert c.get('/api/external-index/' + route).status_code == 200
    for verb in (c.post, c.put, c.delete):
        assert verb('/api/external-index/search?scan_id=demo-new&q=a').status_code in (403, 405)
    assert _digest(db) == before

