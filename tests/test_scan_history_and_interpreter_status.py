"""Task group H — interpretation timestamps, the scan timeline, and the
Interpret tab's status and run routes.
"""
import time

import pytest

from scidk.app import create_app
from scidk.core import path_index_sqlite as pix
from tests.conftest import authenticate_test_client


PATH = 'remote:bucket/data/session_001.fcs'
PARENT = 'remote:bucket/data'


def _insert_file(conn, path, scan_id, size, mtime, parent=PARENT, name=None,
                 ext='.fcs', interpreted_as=None, interpreted_at=None, version=None):
    conn.execute(
        "INSERT INTO files(path, parent_path, name, depth, type, size, modified_time,"
        " file_extension, mime_type, etag, hash, remote, scan_id, extra_json,"
        " interpreted_as, interpretation_json, interpreted_at, interpreter_version)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (path, parent, name or path.rsplit('/', 1)[-1], 3, 'file', size, mtime,
         ext, None, None, None, 'remote', scan_id, None,
         interpreted_as, None, interpreted_at, version),
    )


def _insert_scan(conn, scan_id, completed, extra_json=None):
    conn.execute(
        "INSERT INTO scans(id, root, started, completed, status, extra_json) VALUES (?,?,?,?,?,?)",
        (scan_id, PARENT, completed - 10, completed, 'completed', extra_json),
    )


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    conn = pix.connect()
    pix.init_db(conn)
    # migrations owns the `scans` table.
    from scidk.core import migrations as migs
    migs.migrate(conn)
    yield conn
    conn.close()


@pytest.fixture()
def client(db):
    app = create_app()
    app.config['TESTING'] = True
    return authenticate_test_client(app.test_client(), app)


# ── H1 — interpreted_at is recorded ────────────────────────────────────────

def test_persist_interpretation_stamps_the_row(db):
    from scidk.core.interpreter_persistence import persist_interpretation

    _insert_file(db, PATH, 'scan1', 100, 1000.0)
    db.commit()

    before = time.time()
    updated = persist_interpretation(
        db, PATH, 'scan1', 'fcs_interpreter',
        {'status': 'success', 'data': {}}, interpreter_version='1.3',
    )
    db.commit()
    assert updated == 1

    row = db.execute(
        "SELECT interpreted_as, interpreted_at, interpreter_version FROM files WHERE path = ?",
        (PATH,),
    ).fetchone()
    assert row[0] == 'fcs_interpreter'
    assert row[1] >= before
    assert row[2] == '1.3'


def test_files_table_has_the_h1_columns(db):
    cols = {r[1] for r in db.execute('PRAGMA table_info(files);').fetchall()}
    assert {'interpreted_at', 'interpreter_version'} <= cols


# ── H2 — /api/scans/history ────────────────────────────────────────────────

def test_history_reports_first_seen_scanned_changed_and_interpreted(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_scan(db, 'scan2', 2_000, '{"file_count": 5, "provider_id": "rclone"}')
    _insert_file(db, PATH, 'scan1', 28_400_000, 900.0)
    _insert_file(db, PATH, 'scan2', 31_100_000, 1_900.0,
                 interpreted_as='fcs_interpreter', interpreted_at=2_100.0, version='1.3')
    db.commit()

    d = client.get('/api/scans/history', query_string={'path': PATH}).get_json()
    assert d['path'] == PATH
    assert d['scope'] == 'file'

    kinds = [e['type'] for e in d['events']]
    # Newest first.
    assert kinds == ['interpreted', 'changed', 'scanned', 'first_seen']
    assert [e['timestamp'] for e in d['events']] == [2_100.0, 2_000, 2_000, 1_000]

    interpreted = d['events'][0]
    assert interpreted['interpreter'] == 'fcs_interpreter'
    assert interpreted['version'] == '1.3'

    changed = d['events'][1]
    assert '27.1 MB → 29.7 MB' in changed['detail']
    assert 'mtime updated' in changed['detail']

    assert '5 files' in d['events'][2]['detail']
    assert d['events'][3]['scan_id'] == 'scan1'


def test_history_emits_no_change_event_when_nothing_moved(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_scan(db, 'scan2', 2_000)
    _insert_file(db, PATH, 'scan1', 100, 50.0)
    _insert_file(db, PATH, 'scan2', 100, 50.0)
    db.commit()

    kinds = [e['type'] for e in client.get(
        '/api/scans/history', query_string={'path': PATH}).get_json()['events']]
    assert kinds == ['scanned', 'first_seen']


def test_history_orders_by_scan_completion_not_insertion(db, client):
    """A rescan of an old root inserted last still lands in the middle."""
    _insert_scan(db, 'recent', 3_000)
    _insert_scan(db, 'old', 1_000)
    _insert_file(db, PATH, 'recent', 100, 10.0)
    _insert_file(db, PATH, 'old', 100, 10.0)   # inserted second, older scan
    db.commit()

    events = client.get('/api/scans/history', query_string={'path': PATH}).get_json()['events']
    assert [e['scan_id'] for e in events] == ['recent', 'old']
    assert events[-1]['type'] == 'first_seen'


def test_history_surfaces_a_deletion_recorded_in_file_history(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_scan(db, 'scan2', 2_000)
    _insert_file(db, PATH, 'scan1', 100, 10.0)
    db.execute(
        "INSERT INTO file_history(path, scan_id, change_type, previous_size) VALUES (?,?,?,?)",
        (PATH, 'scan2', 'deleted', 100),
    )
    db.commit()

    events = client.get('/api/scans/history', query_string={'path': PATH}).get_json()['events']
    assert events[0]['type'] == 'deleted'
    assert events[0]['timestamp'] == 2_000


def test_history_of_a_folder_covers_its_files(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_file(db, f'{PARENT}/a.fcs', 'scan1', 1, 1.0)
    _insert_file(db, f'{PARENT}/b.fcs', 'scan1', 2, 2.0)
    db.commit()

    d = client.get('/api/scans/history', query_string={'path': PARENT}).get_json()
    assert d['scope'] == 'folder'
    assert sorted(d['files']) == [f'{PARENT}/a.fcs', f'{PARENT}/b.fcs']
    assert {e['path'] for e in d['events']} == set(d['files'])


def test_history_requires_a_path(client):
    assert client.get('/api/scans/history').status_code == 400


def test_history_of_an_unknown_path_is_empty_not_an_error(client):
    d = client.get('/api/scans/history', query_string={'path': 'nowhere/at/all'}).get_json()
    assert d['events'] == []
    assert d['scope'] == 'unknown'


def test_history_route_is_not_shadowed_by_the_scan_id_route(client):
    """`/api/scans/history` must not be read as scan id "history"."""
    r = client.get('/api/scans/history', query_string={'path': PATH})
    # The scan-id route would 404 with {'error': 'scan not found'}; this one
    # answers with a timeline envelope.
    assert 'events' in r.get_json()


# ── H3 — /api/interpreters/status ──────────────────────────────────────────

def test_status_reports_ok_and_missing_per_interpreter(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_file(db, f'{PARENT}/session_001.fcs', 'scan1', 1, 1.0,
                 interpreted_as='fcs_interpreter', interpreted_at=1_500.0, version='1.3')
    _insert_file(db, f'{PARENT}/session_002.fcs', 'scan1', 1, 1.0)
    db.commit()

    d = client.get('/api/interpreters/status', query_string=[
        ('paths[]', f'{PARENT}/session_001.fcs'),
        ('paths[]', f'{PARENT}/session_002.fcs'),
    ]).get_json()

    fcs = next(i for i in d['interpreters'] if i['id'] == 'fcs_interpreter')
    assert fcs['files']['session_001.fcs'] == {
        'path': f'{PARENT}/session_001.fcs', 'status': 'ok', 'interpreted_at': 1_500.0,
    }
    # Never interpreted, but the extension says fcs_interpreter should have.
    assert fcs['files']['session_002.fcs']['status'] == 'missing'
    assert fcs['files']['session_002.fcs']['interpreted_at'] is None
    assert fcs['version'] == '1.3'


def test_status_takes_the_most_recent_run_when_a_path_spans_scans(db, client):
    _insert_scan(db, 'scan1', 1_000)
    _insert_scan(db, 'scan2', 2_000)
    _insert_file(db, PATH, 'scan1', 1, 1.0,
                 interpreted_as='fcs_interpreter', interpreted_at=1_100.0, version='1.2')
    _insert_file(db, PATH, 'scan2', 1, 1.0,
                 interpreted_as='fcs_interpreter', interpreted_at=2_100.0, version='1.3')
    db.commit()

    d = client.get('/api/interpreters/status', query_string=[('paths[]', PATH)]).get_json()
    fcs = next(i for i in d['interpreters'] if i['id'] == 'fcs_interpreter')
    assert fcs['files']['session_001.fcs']['interpreted_at'] == 2_100.0
    assert fcs['version'] == '1.3'


def test_status_names_paths_the_index_has_never_seen(db, client):
    d = client.get('/api/interpreters/status',
                   query_string=[('paths[]', 'never/scanned.fcs')]).get_json()
    assert d['interpreters'] == []
    assert d['unknown_paths'] == ['never/scanned.fcs']


def test_status_requires_paths(client):
    assert client.get('/api/interpreters/status').status_code == 400


def test_status_bounds_the_request(client):
    qs = [('paths[]', f'f{i}.fcs') for i in range(600)]
    r = client.get('/api/interpreters/status', query_string=qs)
    assert r.status_code == 400
    assert 'too many paths' in r.get_json()['error']


# ── H4 — /api/interpreters/run ─────────────────────────────────────────────

def test_run_returns_a_pollable_task_id(db, client, monkeypatch):
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return {'files_enriched': 1, 'errors': []}

    monkeypatch.setattr('scidk.services.enrichment_service.run_enrichment', fake_run)

    r = client.post('/api/interpreters/run', json={'paths': [PATH], 'mode': 'missing_only'})
    assert r.status_code == 202
    task_id = r.get_json()['task_id']

    # The worker is a thread; give it a moment, then read it back through the
    # same route the page polls.
    for _ in range(50):
        detail = client.get(f'/api/tasks/{task_id}').get_json()
        if detail['status'] != 'running':
            break
        time.sleep(0.02)
    assert detail['status'] == 'completed'
    assert detail['type'] == 'interpret'
    assert seen['paths'] == [PATH]
    assert seen['force'] is False


def test_run_all_forces_reinterpretation(db, client, monkeypatch):
    seen = {}
    monkeypatch.setattr('scidk.services.enrichment_service.run_enrichment',
                        lambda **kw: seen.update(kw) or {'files_enriched': 0, 'errors': []})
    client.post('/api/interpreters/run', json={'paths': [PATH], 'mode': 'all'})
    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert seen['force'] is True


def test_run_rejects_bad_input(client):
    assert client.post('/api/interpreters/run', json={'paths': []}).status_code == 400
    assert client.post('/api/interpreters/run',
                       json={'paths': [PATH], 'mode': 'sideways'}).status_code == 400
    r = client.post('/api/interpreters/run', json={'paths': [PATH], 'interpreter': 'nope'})
    assert r.status_code == 400
    assert 'known_interpreters' in r.get_json()


def test_enrichment_paths_filter_selects_only_the_named_rows(db):
    from scidk.services.enrichment_service import _find_work

    _insert_scan(db, 'scan1', 1_000)
    _insert_file(db, f'{PARENT}/wanted.fcs', 'scan1', 1, 1.0)
    _insert_file(db, f'{PARENT}/other.fcs', 'scan1', 1, 1.0)
    db.commit()

    rows = _find_work(db, None, 100, None, paths=[f'{PARENT}/wanted.fcs'])
    assert [r['path'] for r in rows] == [f'{PARENT}/wanted.fcs']

    # An unrelated interpreter filters the selection out entirely rather than
    # running the wrong thing over it.
    assert _find_work(db, 'csv', 100, None, paths=[f'{PARENT}/wanted.fcs']) == []
