"""Browse > Scanned: host -> exact scan root -> latest scan, older scans under History.

API tests use a synthetic scan index (opened read-only by the app). Browser tests run the real Browse page in Chromium against
synthetic API answers built by the real grouping code. All hosts, roots and names are synthetic.
"""
import json
import socket
import sqlite3

from tests.test_dataset_catalog import LOC_KEY, _digest, _sidecars_ok, _stored_basket  # noqa: F401
from tests.test_datasets_workspace import (  # noqa: F401 - fixtures and shared helpers
    SCAN_ROOT, WsApi, loc, signed_in, ws_page)
from tests.test_selection_actions import browser_page, serve  # noqa: F401

DAY = 86400.0
T_NEW, T_MID, T_OLD = 1767312000.0, 1767225600.0, 1767139200.0   # 2026-01-02, 2026-01-01, 2025-12-31 (UTC midnight)


def _scan(conn, sid, root, started, status='complete', extra=None, files=None, size=None, rows=()):
    conn.execute('INSERT INTO scans VALUES (?,?,?,?,?,?)', (sid, root, started, started + 5, status, json.dumps(extra or {})))
    if files is not None:
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (sid, 'files_scanned', files, 0))
    if size is not None:
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (sid, 'bytes_scanned', size, 0))
    for i, nbytes in enumerate(rows):
        conn.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)',
                     (f'{root}/f{i}.txt', root, f'f{i}.txt', 1, 'file', nbytes, 5.0, '.txt', sid))


def _synthetic_scans(db):
    """Scan rows are inserted newest-LAST for host A so database row order is the opposite of timestamp order."""
    conn = sqlite3.connect(db)
    a, b = {'host_id': 'local:host-a', 'provider_id': 'local_fs'}, {'host_id': 'ssh:host-b', 'provider_id': 'ssh'}
    _scan(conn, 'a-old', '/data0/atwai', T_OLD, extra=a, files=100, size=500, rows=(5,))
    _scan(conn, 'a-new', '/data0/atwai', T_NEW, extra=a, files=3, rows=(10, 20, 30))       # no recorded bytes: summed from its own rows
    _scan(conn, 'a-mid', '/data0/atwai/', T_MID, extra=a, files=50, size=900, rows=(7,))    # trailing slash: same root
    _scan(conn, 'b-new', '/data0/atwai', T_MID, extra=b, files=40, size=4000)               # same root string, other host
    _scan(conn, 'c-new', '/net/host-c/data/imaging-study', T_MID, files=9, size=90)         # host named in the path
    _scan(conn, 'm-new', '/data0/mount-only', T_MID, extra={'host_id': 'mounted:/data0'}, files=2, size=20)   # a mount, not a host
    _scan(conn, 'run-1', '/data0/atwai', T_NEW + DAY, status='running', extra=a, files=1, size=1)             # unfinished: never latest
    conn.commit(); conn.close()


def _body(client):
    body = client.get('/api/external-index/locations').get_json()
    assert body['status'] == 'success' and body['read_only'] is True
    return body, {h['host']: h for h in body['hosts']}


# ── grouping: host, then exact scan root ─────────────────────────────────────

def test_scanned_locations_group_by_host_then_exact_root_and_a_mount_segment_is_never_identity(signed_in):
    client, _, db, _ = signed_in
    _synthetic_scans(db)
    body, hosts = _body(client)
    assert {'host-a', 'host-b', 'host-c'} <= set(hosts) and 'data0' not in hosts          # the mount segment is not a host
    assert [h['label'] for h in body['hosts']][-1] == 'Host not recorded' and hosts['']['label'] == 'Host not recorded'
    a = hosts['host-a']['roots']
    assert [(r['root'], r['name']) for r in a] == [('/data0/atwai', 'atwai')]               # leaf name + full configured root
    assert hosts['host-b']['roots'][0]['root'] == '/data0/atwai'                           # same root, other host: its own group
    assert hosts['host-b']['roots'][0]['latest']['scan_id'] == 'b-new'
    c = hosts['host-c']['roots'][0]
    assert (c['root'], c['name']) == ('/net/host-c/data/imaging-study', 'imaging-study')
    # No group, name or label is the mount segment 'data0'; the unrecorded-host scan keeps its own leaf.
    names = {r['name'] for h in body['hosts'] for r in h['roots']}
    assert 'data0' not in names and 'mount-only' in names
    assert all(r['host'] == h['host'] for h in body['hosts'] for r in h['roots'])
    # A trailing slash is the same configured root; host A's three runs of /data0/atwai form ONE group.
    assert a[0]['history_count'] == 2 and len(a) == 1
    assert 'extra_json' not in json.dumps(body)


def test_latest_scan_is_chosen_by_scan_timestamp_not_row_order_and_unfinished_scans_never_win(signed_in):
    client, _, db, _ = signed_in
    _synthetic_scans(db)
    _, hosts = _body(client)
    root = hosts['host-a']['roots'][0]
    assert root['latest']['scan_id'] == 'a-new'                                           # newest timestamp; inserted second
    assert [r['scan_id'] for r in root['history']] == ['a-mid', 'a-old']                  # newest first
    assert [r['timestamp'] for r in root['history']] == ['2026-01-01T00:00:05+00:00', '2025-12-31T00:00:05+00:00']
    assert 'run-1' not in json.dumps(hosts)                                               # status running: not a browsable scan
    # Every history entry stays openable: a read-only browse of that exact scan answers.
    for run in root['history']:
        got = client.get(f"/api/external-index/browse?scan_id={run['scan_id']}&path=/data0/atwai")
        assert got.status_code == 200 and got.get_json()['read_only'] is True


def test_metrics_come_only_from_the_latest_scan_and_host_totals_do_not_double_count(signed_in):
    client, _, db, _ = signed_in
    _synthetic_scans(db)
    before = _digest(db)
    _, hosts = _body(client)
    a = hosts['host-a']
    assert a['root_count'] == 1 and a['files'] == 3                                       # a-new only: not 3+50+100
    latest = a['roots'][0]['latest']
    assert latest['files'] == 3 and latest['bytes'] is None                               # no recorded total: not invented, not summed
    assert a['bytes'] is None and a['bytes_unknown_roots'] == 1
    # The size of ONE scan is the sum over that scan's own file rows; other runs of the root do not leak in.
    sized = client.get('/api/external-index/scan-size?scan_id=a-new').get_json()
    assert sized['status'] == 'success' and sized['bytes'] == 60 and sized['read_only'] is True
    assert client.get('/api/external-index/scan-size?scan_id=a-old').get_json()['bytes'] == 5
    assert client.get('/api/external-index/scan-size?scan_id=a-new').get_json()['cached'] is True
    assert client.get('/api/external-index/scan-size?scan_id=nope').status_code == 404
    # Recorded totals are used as they are (no file-row scan needed); host totals add only each root's latest scan.
    assert hosts['host-b']['bytes'] == 4000 and hosts['host-b']['files'] == 40
    assert hosts['host-c']['bytes'] == 90 and hosts['host-c']['files'] == 9
    assert client.get('/api/external-index/scan-size').status_code == 404 and client.post('/api/external-index/scan-size').status_code == 405
    assert _digest(db) == before and _sidecars_ok(db)


def test_a_root_readable_here_is_represented_by_local_and_not_listed_as_a_normal_scanned_location(signed_in, tmp_path):
    client, _, db, _ = signed_in
    here = tmp_path / 'local-data'
    here.mkdir()
    conn = sqlite3.connect(db)
    _scan(conn, 'l-1', str(here), T_MID, files=4, size=40)
    conn.commit(); conn.close()
    body, hosts = _body(client)
    assert [r['latest']['scan_id'] for r in body['local_roots']] == ['l-1']
    assert body['local_roots'][0]['represented'] == 'local' and body['local_roots'][0]['access'] == 'mounted'
    assert 'l-1' not in json.dumps(body['hosts'])
    assert any(x['scan_id'] == 'l-1' for x in body['locations'])                          # the flat legacy list is unchanged


def test_scanned_location_reads_are_read_only_and_legacy_routes_keep_their_shape(signed_in, monkeypatch):
    client, _, db, _ = signed_in
    _synthetic_scans(db)
    from scidk.web.routes import api_external_index as ei
    real, opened = sqlite3.connect, []

    def spy(target, *args, **kwargs):
        opened.append((str(target), kwargs.get('uri')))
        return real(target, *args, **kwargs)
    monkeypatch.setattr(ei.sqlite3, 'connect', spy)

    def no_network(*args, **kwargs):
        raise AssertionError('a remote host was contacted')
    monkeypatch.setattr(socket, 'create_connection', no_network)
    before = _digest(db)
    assert client.get('/api/external-index/locations').status_code == 200
    assert client.get('/api/external-index/scan-size?scan_id=a-new').status_code == 200
    assert client.get('/api/external-index/browse?scan_id=a-old&path=/data0/atwai').status_code == 200
    index = [(t, u) for t, u in opened if str(db) in t]
    assert index and all(u is True and 'mode=ro' in t for t, u in index), opened
    assert _digest(db) == before and _sidecars_ok(db)                                     # no write, no new tables, no DB/WAL/SHM change
    tables = {r[0] for r in sqlite3.connect(f'file:{db}?mode=ro', uri=True).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {t for t in tables if 'location' in t or 'catalog' in t}
    legacy = client.get('/api/external-index/scans').get_json()                           # direct legacy route: same fields as before
    assert {'scans', 'shares'} <= set(legacy) and {'id', 'root', 'host', 'share', 'files', 'bytes', 'date'} <= set(legacy['scans'][0])
    flat = client.get('/api/external-index/locations').get_json()['locations']
    assert {'scan_id', 'host', 'share', 'root', 'label', 'files', 'bytes', 'date', 'role', 'access'} <= set(flat[0])
    for url in ('/api/external-index/locations', '/api/external-index/scan-size'):
        assert client.post(url).status_code == 405


# ── browser: one common Browse experience ────────────────────────────────────

A_ROOT, B_ROOT, C_ROOT = '/data0/atwai', '/research/imaging-study', '/net/host-c/data/unsized'


def _groups(api):
    big = int(1.4 * 1024 ** 4)
    api.locations = [
        loc('a-mid', A_ROOT, host='host-a', files=50, size=None, ts=T_MID),
        loc('a-new', A_ROOT, host='host-a', files=921998, size=big, ts=T_NEW),                # newest sits between the others in row order
        loc('a-old', A_ROOT, host='host-a', files=100, size=5, ts=T_OLD),
        loc('b-1', B_ROOT, host='host-b', files=12, size=None, ts=T_MID),
        loc('c-1', C_ROOT, host='host-c', files=7, size=None, ts=T_MID)]
    api.sizes = {'b-1': 2048, 'a-mid': 4096}                                              # c-1 has no size anywhere: unavailable
    api.openable = {x['scan_id'] for x in api.locations}


def test_browser_scanned_is_grouped_by_host_then_exact_root_with_latest_scan_metrics(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    _groups(api)
    page.goto(serve() + '/datasets?view=browse')
    expect(page.locator('#servers-tree .tree-node[data-root]')).to_have_count(1)           # Local is unchanged and usable
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    hosts = page.locator('[data-testid="scanned-locations"] [data-testid="scan-host"]')
    expect(hosts).to_have_count(3)
    expect(hosts.locator(':scope > summary > span:first-child')).to_have_text(['host-a', 'host-b', 'host-c'])
    summary = hosts.locator('[data-testid="scan-host-summary"]')
    # The host line counts only each root's latest scan: 921,998 files, never +50 +100 from history.
    expect(summary.nth(0)).to_have_text('1 root · 921,998 files · 1.4 TB')
    expect(summary.nth(1)).to_have_text('1 root · 12 files · 2 KB')                        # size fetched from the one latest scan
    expect(summary.nth(2)).to_have_text('1 root · 7 files · size unavailable')             # honest, not invented
    a = hosts.nth(0)
    a.locator(':scope > summary').click()
    root = a.locator('[data-testid="scan-root"]')
    expect(root).to_have_count(1)                                                          # one entry per (host, root)
    expect(root.locator('.scan-name')).to_contain_text('atwai')
    expect(root.locator('.scan-name')).not_to_contain_text('data0')
    expect(root.locator('[data-testid="location-badge"]')).to_have_text('Indexed')
    expect(root.locator('[data-testid="scan-path"]')).to_have_text('/data0/atwai')
    expect(root.locator('[data-testid="scan-stats"]')).to_have_text('921,998 files · 1.4 TB')
    expect(root.locator('[data-testid="scan-latest"]')).to_have_text('Latest scan: 2026-01-02 00:00 UTC')
    expect(root.locator('[data-testid="scan-history"] > summary')).to_have_text('History (2)')
    # Older scans do not clutter the default sidebar, and their sizes are not requested until History is opened.
    expect(root.locator('.scan-run')).to_have_count(2)
    expect(root.locator('.scan-run').first).to_be_hidden()
    assert not [q for p, q in api.queries if p == '/api/external-index/scan-size' and q.get('scan_id') == ['a-mid']]
    assert not errors, errors


def test_browser_history_lists_older_scans_newest_first_and_opens_one_in_the_same_browse(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    _groups(api)
    page.goto(serve() + '/datasets?view=browse')
    page.locator('[data-testid="scan-host"]').first.locator(':scope > summary').click()
    root = page.locator('[data-testid="scan-root"]').first
    root.locator('[data-testid="scan-history"] > summary').click()
    runs = root.locator('.scan-run')
    expect(runs).to_have_count(2)
    expect(runs.nth(0)).to_contain_text('2026-01-01 00:00 UTC')                            # newest first
    expect(runs.nth(1)).to_contain_text('2025-12-31 00:00 UTC')
    expect(runs.nth(0).locator('[data-testid="scan-run-stats"]')).to_have_text('50 files · 4 KB')
    expect(runs.nth(1).locator('[data-testid="scan-run-stats"]')).to_have_text('100 files · 5 B')
    expect(page.locator('[data-testid="scan-host-summary"]').first).to_have_text('1 root · 921,998 files · 1.4 TB')   # unchanged
    assert [q for p, q in api.queries if p == '/api/external-index/scan-size' and q.get('scan_id') == ['a-mid']]
    runs.nth(1).click()                                                                    # open the oldest scan
    assert 'view=browse' in page.url
    expect(page.locator('[data-testid="indexed-banner"]')).to_be_visible()
    expect(page.locator('[data-testid="indexed-banner"]')).to_contain_text('a-old')
    expect(page.locator('[data-testid="indexed-banner"]')).to_contain_text('raw files cannot be opened from here')
    assert any(p == '/api/external-index/browse' and q.get('scan_id') == ['a-old'] and q.get('path') == [A_ROOT] for p, q in api.queries)
    expect(runs.nth(1)).to_have_class('tree-node scan-run selected')
    expect(page.locator('#breadcrumb-nav')).to_contain_text('atwai')
    # Same Browse: the common table, checkboxes, selection bar, inspector and Collection flow, on the historical scan.
    expect(page.locator('#file-list tr[data-id]')).to_have_count(2)
    page.locator(f'.row-cb[data-id="{SCAN_ROOT}/a.csv"]').check()
    bar = page.locator('#files-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_visible()
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    assert next(x for x in _stored_basket(page) if x['kind'] == 'file')['p']['scan_id'] == 'a-old'   # index-backed, that exact run
    page.locator('#file-list tr[data-name="a.csv"] .name-cell').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    # Opening the latest scan switches the selection back; Local is still usable afterwards.
    root.locator('.scan-loc').click()
    expect(root.locator('.scan-loc')).to_have_class('tree-node loc-node scan-loc selected')
    expect(runs.nth(1)).not_to_have_class('tree-node scan-run selected')
    assert any(p == '/api/external-index/browse' and q.get('scan_id') == ['a-new'] for p, q in api.queries)
    page.locator('#servers-tree .tree-node[data-root]').click()
    expect(page.locator('[data-testid="indexed-banner"]')).to_be_hidden()
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    assert not errors, errors


def test_browser_a_direct_link_to_a_historical_scan_stays_open_selected_and_visible(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    _groups(api)
    page.goto(serve() + f'/datasets?view=browse&open_scan=a-old&open_path={A_ROOT}')
    expect(page.locator('[data-testid="indexed-banner"]')).to_be_visible()
    assert any(p == '/api/external-index/browse' and q.get('scan_id') == ['a-old'] for p, q in api.queries)
    old = page.locator('.scan-run[data-scan="a-old"]')
    expect(old).to_be_visible()                                                            # host group and History opened for it
    expect(old).to_have_class('tree-node scan-run selected')
    expect(page.locator('.scan-loc[data-scan="a-new"]')).not_to_have_class('tree-node loc-node scan-loc selected')
    expect(page.locator('#file-list tr[data-id]')).to_have_count(2)
    page.locator('.row-cb').first.check()
    expect(page.locator('#sel-badge-count')).to_have_text('1 selected')
    assert not errors, errors


def test_browser_a_root_already_listed_under_local_gets_its_scanned_status_there_and_is_not_duplicated(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    api.locations = [loc('l-1', '/', host='', files=33, size=330, ts=T_MID, access='mounted'), loc('b-1', B_ROOT, host='host-b', files=12, size=2048)]
    api.openable = {'l-1', 'b-1'}
    page.goto(serve() + '/datasets?view=browse')
    expect(page.locator('#servers-tree [data-testid="scanned-status"]')).to_have_text('Scanned · 33 files')
    hosts = page.locator('[data-testid="scanned-locations"] [data-testid="scan-host"]')
    expect(hosts).to_have_count(1)                                                         # only host-b: the Local root is not repeated
    expect(page.locator('[data-testid="scanned-locations"] .loc-node')).to_have_count(1)   # host-b's root only (collapsed until opened)
    expect(page.locator('[data-testid="scanned-locations"] .loc-node')).to_be_hidden()
    hosts.locator(':scope > summary').click()
    expect(page.locator('[data-testid="scanned-locations"] .loc-node')).to_be_visible()
    page.locator('#servers-tree .tree-node[data-root]').click()
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    assert not errors, errors
