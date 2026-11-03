"""Dataset catalog: global ordering, search, state filters, confirmation, human metadata, collections, locations.

API tests use a synthetic scan index (opened read-only by the app) and a fake graph client that records every query.
Browser tests run the real pages in Chromium against synthetic API answers. All names are synthetic.
"""
import hashlib
import json
import os
import socket
import sqlite3

import pytest

from tests.test_collections import _writes
from tests.test_datasets_workspace import (  # noqa: F401 - fixtures and shared constants
    COLLECTIONS, DATASET_ROOT, GRAPH, RECOGNIZED, SCAN_ROOT, WsApi, signed_in, ws_page)
from tests.test_selection_actions import browser_page, serve  # noqa: F401

SCAN = 'scan-1'
ROOT = '/data0/core/atwai'


def _digest(db):
    return hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns


def _sidecars_ok(db):
    """The main index file is compared by digest and mtime. Reading a WAL-mode database read-only makes SQLite itself create
    empty -wal / -shm side files if none exist; nothing may be written to them, and nothing else may appear or vanish."""
    names = set(os.listdir(db.parent))
    wal = db.parent / 'files.db-wal'
    return names <= {'files.db', 'files.db-wal', 'files.db-shm', 'settings.db', 'settings.db-wal', 'settings.db-shm'} \
        and 'files.db' in names and (not wal.exists() or wal.stat().st_size == 0)


def _add_candidates(db, n):
    conn = sqlite3.connect(db)
    for i in range(n):
        root = f'{ROOT}/g{i % 7}/n{n - i:04d}'
        conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, file_count, total_bytes) VALUES (?,?,?,?,?,?)",
                     (root, 'synthetic_profile', root, SCAN, i, i * 10))
    # Alphabetically first by name, but the very last root path: an old "first 1,000 by path" read would drop it.
    first = f'{ROOT}/zzz/a_first'
    conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, file_count, total_bytes) VALUES (?,?,?,?,?,?)",
                 (first, 'synthetic_profile', first, SCAN, 1, 10))
    conn.commit()
    conn.close()


def _all_pages(client, query='', limit=200):
    names, offset, pages = [], 0, []
    while offset is not None:
        body = client.get(f'/api/datasets/catalog?limit={limit}&offset={offset}' + query).get_json()
        assert body['status'] == 'success' and body['read_only'] is True
        pages.append(body)
        names += [d['name'] for d in body['datasets']]
        offset = body['next_offset']
    return names, pages


# ── catalog: ordering, completeness, search, filters ─────────────────────────

def test_catalog_is_globally_alphabetical_across_pages_and_never_truncated_before_sorting(signed_in):
    client, _, db, graph = signed_in
    _add_candidates(db, 1205)
    graph(read_results=[[]])
    before = _digest(db)
    names, pages = _all_pages(client)
    assert len(names) == 1205 + 1 + 8 == pages[0]['total']             # every candidate, none cut at 1,000
    assert len(pages) == 7 and [len(p['datasets']) for p in pages] == [200] * 6 + [14]
    assert names[0] == 'a_first'                                       # last by path, first by name
    assert names == sorted(names, key=str.casefold)                    # one order across all pages
    assert [(p['first'], p['last']) for p in pages][:2] == [(1, 200), (201, 400)] and pages[-1]['next_offset'] is None
    assert pages[0]['has_more'] and pages[0]['prev_offset'] is None and pages[1]['prev_offset'] == 0
    # A request for more than the maximum page is clamped, and a repeated request gives the same page.
    big = client.get('/api/datasets/catalog?limit=5000').get_json()
    assert big['limit'] == 200 and len(big['datasets']) == 200
    assert client.get('/api/datasets/catalog?limit=50&offset=100').get_json()['datasets'] == \
        client.get('/api/datasets/catalog?limit=50&offset=100').get_json()['datasets']
    assert _digest(db) == before and _sidecars_ok(db)
    # The paginated legacy-shaped list is complete and ordered the same way.
    legacy, offset = [], 0
    while offset is not None:
        body = client.get(f'/api/external-index/datasets/all?limit=200&offset={offset}').get_json()
        legacy += [d['name'] for d in body['datasets']]
        offset = body['next_offset']
    assert legacy == names


def test_catalog_search_and_all_four_state_filters(signed_in):
    client, _, _, graph = signed_in
    huang = f'{ROOT}/huang'
    rows = [{'id': None, 'name': 'Alpha human name', 'name_source': 'human', 'source': 'files.db', 'scan_id': SCAN, 'root_path': huang,
             'profile': 'vevo_ultrasound', 'human_profile': 'corrected_type', 'description': 'Synthetic description', 'members': 0},
            {'id': 'mm1', 'name': 'Zed manual', 'source': 'manual', 'files': 2, 'folders': 1, 'bytes': 30, 'members': 3}]

    def get(query):
        graph(read_results=[rows])
        return client.get('/api/datasets/catalog?' + query).get_json()

    everything = get('')
    assert everything['total'] == 9 and everything['counts'] == {'all': 9, 'candidate': 7, 'confirmed': 1, 'manual': 1}
    names = [d['name'] for d in everything['datasets']]
    assert names == sorted(names, key=str.casefold) and names[0] == 'Alpha human name'       # sorted by displayed name
    states = {d['name']: d['state'] for d in everything['datasets']}
    assert states['Alpha human name'] == 'confirmed' and states['Zed manual'] == 'manual' and states['s1'] == 'candidate'
    confirmed = everything['datasets'][0]
    assert confirmed['observed_profile'] == 'vevo_ultrasound' and confirmed['human_profile'] == 'corrected_type'
    assert confirmed['profile'] == 'corrected_type' and confirmed['name_is_human'] is True
    for state, expected in (('candidate', 7), ('confirmed', 1), ('manual', 1), ('all', 9), ('nonsense', 9)):
        got = get('state=' + state)
        assert got['total'] == expected, state
        if state in ('candidate', 'confirmed', 'manual'):
            assert {d['state'] for d in got['datasets']} == {state}
    assert get('q=vevo')['total'] == 6                       # observed profile fragment
    assert get('q=corrected_type')['total'] == 1             # human profile
    assert [d['name'] for d in get('q=huangw')['datasets']] == ['s2']          # root fragment
    assert get('q=data0')['total'] == 8                      # host, from scan provenance
    assert get('q=atwai')['total'] == 5                      # share
    assert [d['name'] for d in get('q=ZED')['datasets']] == ['Zed manual']     # case-insensitive name
    assert get('q=vevo&state=confirmed')['total'] == 1 and get('q=nothing-like-this')['total'] == 0
    assert get('q=vevo')['counts'] == {'all': 6, 'candidate': 5, 'confirmed': 1, 'manual': 0}


def test_catalog_still_lists_candidates_when_the_graph_is_down_and_says_so(signed_in, monkeypatch):
    client, _, _, _ = signed_in
    from scidk.web.routes import api_annotation

    def down():
        raise api_annotation.Neo4jUnavailable('No Neo4j connection is configured.')
    monkeypatch.setattr(api_annotation, '_neo4j_client', down)
    body = client.get('/api/datasets/catalog').get_json()
    assert body['total'] == 8 and body['notes'] and 'unavailable' in body['notes'][0]
    assert {d['state'] for d in body['datasets']} == {'candidate'}


# ── confirmation: MERGE only, human fields kept, evidence untouched ──────────

def test_confirm_merges_by_scan_and_root_without_touching_human_fields_or_the_scan_record(signed_in):
    client, _, db, graph = signed_in
    g = graph(write_results=[[{'name': 'huang', 'description': 'Kept description', 'human_profile': 'kept_override',
                               'name_source': 'human', 'profile': 'vevo_ultrasound'}]])
    before = _digest(db)
    r = client.post('/api/datasets/confirm', json={'scan_id': SCAN, 'root_path': f'{ROOT}/huang', 'name': 'Browser-supplied name',
                                                   'pattern_name': 'browser_supplied_profile'})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['state'] == 'confirmed' and body['description'] == 'Kept description' and body['human_profile'] == 'kept_override'
    (query, params), = _writes(g)
    assert query.startswith('MERGE (d:Dataset {scan_id: $scan_id, root_path: $root_path})')
    on_create = query.split('ON CREATE SET')[1].split('d.created_at = timestamp() SET')[0]
    assert 'd.name = $name' in on_create
    after_create = query.split('d.created_at = timestamp() SET ')[1].split(' RETURN')[0]
    for human in ('d.name', 'd.description', 'human_profile', 'name_source'):
        assert human not in after_create, human                      # never written on an existing Dataset
    for word in ('DELETE', 'DETACH', 'REMOVE', 'CREATE ('):
        assert word not in query.upper().replace('ON CREATE SET', '')
    # Observed facts come from the scan index itself, not from the request.
    assert params['profile'] == 'vevo_ultrasound' and params['file_count'] == 1 and params['bytes'] == 10
    assert params['name'] == 'huang' and params['scan_id'] == SCAN and params['root_path'] == f'{ROOT}/huang'
    assert _digest(db) == before and _sidecars_ok(db)                    # the scan record and its files are untouched
    # Unknown evidence is refused without writing; a missing body is a plain 400.
    g2 = graph()
    assert client.post('/api/datasets/confirm', json={'scan_id': SCAN, 'root_path': '/nowhere'}).status_code == 404
    assert client.post('/api/datasets/confirm', json={}).status_code == 400
    assert not _writes(g2)


def test_confirm_needs_a_signed_in_user_and_has_no_delete_route(signed_in):
    client, app, _, _ = signed_in
    assert app.test_client().post('/api/datasets/confirm', json={'scan_id': SCAN, 'root_path': ROOT}).status_code in (401, 403)
    assert client.delete('/api/datasets/confirm').status_code == 405 and client.delete('/api/datasets/metadata').status_code == 405


# ── editing: human metadata only ─────────────────────────────────────────────

def test_edit_sets_only_human_fields_and_never_the_observed_evidence(signed_in):
    client, _, _, graph = signed_in
    row = {'name': 'New name', 'description': 'New description', 'human_profile': 'new_type', 'profile': 'vevo_ultrasound', 'name_source': 'human'}
    g = graph(write_results=[[row]])
    r = client.post('/api/datasets/metadata', json={'scan_id': SCAN, 'root_path': f'{ROOT}/huang', 'name': ' New name ',
                                                    'description': 'New description', 'human_profile': 'new_type'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['observed_profile'] == 'vevo_ultrasound' and r.get_json()['human_profile'] == 'new_type'
    (query, params), = _writes(g)
    assert query.startswith('MATCH (d:Dataset {scan_id: $scan_id, root_path: $root_path}) SET ')
    assigned = query.split(' SET ')[1].split(' RETURN')[0]
    for needle in ('d.name = $name', "d.name_source = 'human'", 'd.description = $description', 'd.human_profile = $human_profile',
                   'd.human_edited_at', 'd.updated_by = $by'):
        assert needle in assigned, needle
    for observed in ('d.profile', 'd.file_count', 'd.bytes', 'd.scan_id', 'd.root_path', 'd.source'):
        assert observed not in assigned, observed
    assert 'DELETE' not in query.upper() and 'DETACH' not in query.upper() and 'REMOVE' not in query.upper()
    assert params['name'] == 'New name' and params['human_profile'] == 'new_type'
    # Only the fields sent are written; a manual Dataset is addressed by its own id.
    g = graph(write_results=[[{'name': 'Zed manual', 'description': 'Only this', 'human_profile': None, 'profile': None}]])
    assert client.post('/api/datasets/metadata', json={'dataset_id': 'mm1', 'description': 'Only this'}).status_code == 200
    (query, params), = _writes(g)
    assert query.startswith('MATCH (d:Dataset {id: $dataset_id}) SET ')
    assert 'd.description = $description' in query and 'd.name =' not in query and 'human_profile' not in query.split(' RETURN')[0]
    assert params['dataset_id'] == 'mm1'


def test_edit_refuses_an_unconfirmed_candidate_and_bad_input_without_writing(signed_in):
    client, _, _, graph = signed_in
    g = graph(write_results=[[]])                                  # MATCH finds no node: not confirmed yet
    r = client.post('/api/datasets/metadata', json={'scan_id': SCAN, 'root_path': f'{ROOT}/huang', 'name': 'x'})
    assert r.status_code == 404 and 'Confirm it first' in r.get_json()['error']
    assert not any('MERGE' in q for q, _ in _writes(g))            # editing never creates a Dataset
    bad = graph()
    for body in ({'dataset_id': 'mm1'}, {'dataset_id': 'mm1', 'name': '  '}, {'dataset_id': 'mm1', 'name': 5},
                 {'dataset_id': 'mm1', 'description': 'x' * 4001}, {'name': 'x'}):
        assert client.post('/api/datasets/metadata', json=body).status_code == 400, body
    assert not _writes(bad)


# ── collections ──────────────────────────────────────────────────────────────

def test_confirmed_and_manual_datasets_both_join_a_collection(signed_in):
    client, _, _, graph = signed_in
    g = graph(write_results=[[], [{'linked': 1}], [{'linked': 1}]])
    r = client.post('/api/collections', json={'name': 'Synthetic mixed', 'members': [
        {'kind': 'dataset', 'scan_id': SCAN, 'root_path': f'{ROOT}/huang', 'name': 'Alpha human name', 'profile': 'vevo_ultrasound',
         'file_count': 1, 'bytes': 10},
        {'kind': 'dataset', 'dataset_id': 'mm1', 'name': 'Zed manual'}]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['linked']['dataset'] == 2 and 'not_found' not in r.get_json()
    ref_q, ref_p = next((q, p) for q, p in _writes(g) if 'MERGE (d:Dataset {scan_id' in q)
    assert 'MERGE (c)-[:INCLUDES]->(d)' in ref_q and ref_p['rows'][0]['profile'] == 'vevo_ultrasound'      # the observed profile
    assert 'human_profile' not in ref_q and 'd.description' not in ref_q                                  # human fields untouched
    assert 'ON CREATE SET d.name' in ref_q and 'SET d.name' not in ref_q.replace('ON CREATE SET d.name', '')
    id_q, id_p = next((q, p) for q, p in _writes(g) if 'MATCH (d:Dataset {id: row.dataset_id})' in q)
    assert 'MERGE (c)-[:INCLUDES]->(d)' in id_q and id_p['rows'][0]['dataset_id'] == 'mm1'
    for q, _ in _writes(g):
        assert 'DELETE' not in q.upper() and 'DETACH' not in q.upper()


# ── the external index is only ever opened read-only ─────────────────────────

def test_every_catalog_read_opens_the_scan_index_read_only(signed_in, monkeypatch):
    client, _, db, graph = signed_in
    from scidk.web.routes import api_external_index as ei
    real, opened = sqlite3.connect, []

    def spy(target, *args, **kwargs):
        opened.append((str(target), kwargs.get('uri')))
        return real(target, *args, **kwargs)
    monkeypatch.setattr(ei.sqlite3, 'connect', spy)
    before = _digest(db)
    graph(write_results=[[{'name': 'huang'}]], read_results=[[], []])
    assert client.get('/api/datasets/catalog').status_code == 200
    assert client.post('/api/datasets/confirm', json={'scan_id': SCAN, 'root_path': f'{ROOT}/huang'}).status_code == 200
    assert client.get('/api/external-index/locations').status_code == 200
    assert client.get('/api/external-index/datasets/all').status_code == 200
    index = [(t, u) for t, u in opened if str(db) in t]               # connections to the external index file
    assert index and all(u is True and 'mode=ro' in t for t, u in index), opened
    assert _digest(db) == before and _sidecars_ok(db)                    # main file untouched; at most SQLite's own empty -wal/-shm sidecars


# ── legacy direct routes still work ──────────────────────────────────────────

def test_legacy_direct_routes_still_answer(signed_in):
    client, _, _, graph = signed_in
    graph(read_results=[[], []])
    assert client.get('/api/external-index/scans').status_code == 200
    assert client.get(f'/api/external-index/browse?scan_id={SCAN}').status_code == 200
    assert client.get(f'/api/external-index/datasets?scan_id={SCAN}&path={ROOT}').get_json()['datasets']
    assert client.get('/api/datasets/graph').status_code == 200 and client.get('/api/datasets/manual').status_code == 200
    assert client.get('/api/external-index/datasets/all').get_json()['datasets']
    for method, url in (('post', '/api/external-index/scans'), ('post', '/api/datasets/catalog'), ('post', '/api/external-index/locations')):
        assert getattr(client, method)(url).status_code == 405


# ── scanned locations: grouping and conservative access badges ───────────────

def test_scanned_locations_group_scans_and_badge_access_conservatively(signed_in, tmp_path, monkeypatch):
    client, _, db, _ = signed_in
    mounted, ssh_like = tmp_path / 'mounted-dir', tmp_path / 'ssh-dir'
    mounted.mkdir(); ssh_like.mkdir()
    conn = sqlite3.connect(db)
    for sid, root, extra, files in (('loc-mounted', str(mounted), {}, 4), ('loc-ssh', str(ssh_like), {'provider_id': 'ssh'}, 6),
                                    ('loc-rclone', 'gdrive:data', {}, 3), ('loc-gone', str(tmp_path / 'not-here'), {}, 2)):
        conn.execute('INSERT INTO scans VALUES (?,?,?,?,?,?)', (sid, root, 10.0, 11.0, 'complete', json.dumps(extra)))
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (sid, 'files_scanned', files, 0))
    conn.commit(); conn.close()

    def no_network(*args, **kwargs):
        raise AssertionError('a remote host was contacted')
    monkeypatch.setattr(socket, 'create_connection', no_network)
    monkeypatch.setattr(socket, 'getaddrinfo', no_network)
    body = client.get('/api/external-index/locations?shortcuts=missing-shortcut,loc-mounted').get_json()
    by_id = {x['scan_id']: x for x in body['locations']}
    assert by_id['loc-mounted']['access'] == 'mounted'                  # a readable local folder here
    assert by_id['loc-ssh']['access'] == 'indexed'                      # same kind of path, but scanned through a remote provider
    assert by_id['loc-rclone']['access'] == 'indexed'                   # a remote:path root
    assert by_id['loc-gone']['access'] == 'indexed'                     # not a local folder here: indexed, not 'unavailable'
    assert by_id[SCAN]['access'] == 'indexed' and by_id[SCAN]['host'] == 'data0' and by_id[SCAN]['share'] == 'atwai'
    assert all(x['access'] in ('mounted', 'indexed') for x in body['locations'])
    assert body['unavailable'] == [{'scan_id': 'missing-shortcut', 'access': 'unavailable', 'label': 'Unavailable', 'root': None}]
    roles = [x['role'] for x in body['locations']]
    assert roles == sorted(roles, key=lambda r: r != 'primary')         # primary scan of each share first
    assert {'share', 'host', 'root', 'files', 'date'} <= set(by_id['loc-mounted'])
    assert 'extra_json' not in json.dumps(body)


# ── browser: paged catalog, search, filters, confirm, edit, collections ──────

def _bulk(n):
    return [{'id': f'b{i}', 'scan_id': 's1', 'name': f'bulk{i:03d}', 'pattern_name': 'bulk_profile', 'root_path': f'{SCAN_ROOT}/bulk{i:03d}',
             'file_count': i, 'total_bytes': i * 10, 'confidence': 0.9, 'status': 'recognized', 'scan_root': SCAN_ROOT,
             'host': 'synthetic-host', 'share': 'synthetic-share', 'scan_date': '2026-01-01'} for i in range(n)]


def test_browser_paging_search_and_state_filters(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    api.candidates = list(RECOGNIZED) + _bulk(120)
    page.goto(serve() + '/datasets?view=datasets')
    cards = page.locator('#datasets-list .ds-card')
    expect(page.locator('#datasets-range')).to_have_text('Showing 1–50 of 123')
    expect(cards).to_have_count(50)
    seen = [t.strip() for t in page.locator('#datasets-list .ds-name').all_inner_texts()]
    expect(page.locator('#datasets-prev')).to_be_disabled()
    page.locator('#datasets-next').click()
    expect(page.locator('#datasets-range')).to_have_text('Showing 51–100 of 123')
    seen += [t.strip() for t in page.locator('#datasets-list .ds-name').all_inner_texts()]
    page.locator('#datasets-next-bottom').click()
    expect(page.locator('#datasets-range')).to_have_text('Showing 101–123 of 123')
    expect(cards).to_have_count(23)
    seen += [t.strip() for t in page.locator('#datasets-list .ds-name').all_inner_texts()]
    expect(page.locator('#datasets-next')).to_be_disabled()
    assert len(seen) == 123 and seen == sorted(seen, key=str.casefold)         # one alphabetical order across pages
    page.locator('#datasets-prev').click()
    expect(page.locator('#datasets-range')).to_have_text('Showing 51–100 of 123')

    page.locator('#datasets-q').fill('bulk01')
    expect(page.locator('#datasets-range')).to_have_text('Showing 1–10 of 10')
    expect(page.locator('#datasets-count')).to_contain_text('matching “bulk01”')
    page.locator('#datasets-q').fill('bulk_profile')                            # profile fragment, with the paging reset to the start
    expect(page.locator('#datasets-range')).to_have_text('Showing 1–50 of 120')
    page.locator('#datasets-reset').click()
    expect(page.locator('#datasets-range')).to_have_text('Showing 1–50 of 123')
    for state, total in (('Candidate', 121), ('Confirmed', 1), ('Manual', 1), ('All', 123)):
        page.locator('#datasets-state').select_option(label=state)
        expect(page.locator('#datasets-range')).to_have_text(f'Showing 1–{min(50, total)} of {total}')
        if state in ('Confirmed', 'Manual'):
            expect(cards.first.locator('.ds-badge').first).to_be_visible()
            expect(cards.first).to_have_attribute('data-kind', state.lower())
    assert not errors, errors


def test_browser_confirm_a_candidate_then_edit_it_and_both_kinds_join_the_basket(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    base = serve()
    page.goto(base + '/datasets?view=datasets')
    page.locator('#datasets-state').select_option(label='Candidate')
    card = page.locator('#datasets-list .ds-card', has_text='runB')
    expect(card.locator('.ds-state-candidate')).to_have_text('candidate')
    card.get_by_role('button', name='Confirm dataset').click()
    expect(page.locator('#datasets-status')).to_contain_text('Confirmed runB')
    assert api.posts[-1] == ('/api/datasets/confirm', {'scan_id': 's1', 'root_path': SCAN_ROOT + '/runB'})     # the reference only
    panel = page.locator('#inspector-dataset-panel')
    expect(panel).to_be_visible()
    expect(panel).to_have_attribute('data-state', 'confirmed')                      # the state changed in place
    expect(panel.locator('#ds-evidence')).to_contain_text('Observed profile: synthetic_pattern')
    expect(panel.locator('#ds-human')).to_contain_text('Human-confirmed metadata')
    page.locator('#ds-edit-name').fill('Synthetic renamed')
    page.locator('#ds-edit-description').fill('Synthetic human description')
    page.locator('#ds-edit-profile').fill('corrected_type')
    page.locator('#ds-edit-save').click()
    expect(page.locator('#datasets-status')).to_contain_text('Saved Synthetic renamed')
    assert api.posts[-1] == ('/api/datasets/metadata', {'scan_id': 's1', 'root_path': SCAN_ROOT + '/runB', 'name': 'Synthetic renamed',
                                                         'description': 'Synthetic human description', 'human_profile': 'corrected_type'})
    # Reload: the edit persists and the observed profile is still shown beside the human override.
    page.goto(base + '/datasets?view=datasets&q=renamed')
    card = page.locator('#datasets-list .ds-card')
    expect(card).to_have_count(1)
    expect(card.locator('.ds-name')).to_have_text('Synthetic renamed')
    expect(card.locator('.ds-state-confirmed')).to_have_text('confirmed')
    expect(card).to_contain_text('Synthetic human description')
    expect(card).to_contain_text('profile: corrected_type (human) · observed synthetic_pattern')
    expect(card.get_by_role('button', name='Confirm dataset')).to_have_count(0)    # nothing left to confirm
    card.get_by_role('button', name='Add to collection').click()
    page.locator('#datasets-q').fill('Synthetic manual')
    expect(page.locator('#datasets-list .ds-state-manual')).to_have_count(1)         # the debounced search has replaced the list
    page.locator('#datasets-list .ds-card').get_by_role('button', name='Add to collection').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
    stored = page.evaluate("JSON.parse(localStorage.getItem('scidk.collection.draft.v1'))")
    confirmed = next(x for x in stored if x['key'] != 'dataset|manual|m1')
    assert confirmed['p']['profile'] == 'synthetic_pattern'                         # the observed profile, never the override
    assert next(x for x in stored if x['key'] == 'dataset|manual|m1')['p'] == {'dataset_id': 'm1', 'name': 'Synthetic manual'}
    assert not errors, errors


def test_browser_manual_dataset_can_be_edited_and_has_no_confirm_action(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=datasets&state=manual')
    card = page.locator('#datasets-list .ds-card')
    expect(card.get_by_role('button', name='Confirm dataset')).to_have_count(0)
    card.locator('.ds-name').click()
    expect(page.locator('#inspector-dataset-panel')).to_have_attribute('data-state', 'manual')
    page.locator('#ds-edit-description').fill('Edited by hand')
    page.locator('#ds-edit-save').click()
    expect(page.locator('#datasets-status')).to_contain_text('Saved Synthetic manual')
    assert api.posts[-1] == ('/api/datasets/metadata', {'dataset_id': 'm1', 'description': 'Edited by hand'})
    page.locator('#inspector-add-to-collection').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    assert not errors, errors


# ── browser: Locations ───────────────────────────────────────────────────────

LOC_KEY = 'scidk.browse.locations.v1'


def _stored_basket(page):
    return page.evaluate("JSON.parse(localStorage.getItem('scidk.collection.draft.v1'))")


def test_browser_locations_sidebar_local_and_scanned_with_honest_badges(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=browse')
    expect(page.locator('#servers-header')).to_have_text('LOCATIONS')
    expect(page.locator('#servers-tree .tree-node[data-root]')).to_have_count(1)         # the local drive is still there
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)                      # and still browses
    group = page.locator('[data-testid="scanned-locations"]')
    expect(group).to_contain_text('SCANNED LOCATIONS')
    nodes = group.locator('.loc-node')
    expect(nodes).to_have_count(2)
    expect(nodes.locator('[data-testid="location-badge"]')).to_have_text(['Mounted', 'Indexed'])
    expect(nodes.nth(1)).to_have_attribute('title', SCAN_ROOT + ' — Known from a scan only. It opens in the scan-index browser; raw files cannot be opened from here.')
    # "+ Add drive or location" offers both kinds.
    page.locator('[data-testid="add-location-btn"]').click()
    menu = page.locator('[data-testid="add-location-menu"]')
    expect(menu.get_by_role('button')).to_have_text(['Local folder / mounted path…', 'Folder from an existing Scan'])
    # A Mounted location browses through the local browser; selection and Add to collection work there.
    nodes.nth(0).click()
    page.wait_for_function("window.currentPath === '/synthetic/mounted'")
    assert any(q.get('path') == ['/synthetic/mounted'] for p, q in api.queries if p == '/api/browse')
    expect(page.locator('#indexed-banner')).to_be_hidden()
    page.locator('#file-list .row-cb').first.check()
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    stored = _stored_basket(page)
    assert 'host' not in stored[0]['p'] and stored[0]['p']['provider_id'] == 'local_fs'        # local members keep the local shape
    assert not errors, errors


def test_browser_add_a_scan_folder_as_a_logical_drive_and_browse_it_in_place(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    base = serve()
    page.goto(base + '/datasets?view=browse')
    page.locator('[data-testid="add-location-btn"]').click()
    page.locator('[data-testid="add-location-menu"]').get_by_role('button', name='Folder from an existing Scan').click()
    panel = page.locator('[data-testid="add-location-scan-panel"]')
    expect(panel).to_be_visible()
    expect(page.locator('#loc-scan-select option')).to_have_count(1)                      # choose the scan
    expect(page.locator('#loc-chosen')).to_have_text(SCAN_ROOT)                          # its root by default
    expect(page.locator('#loc-label')).to_have_value('share')
    panel.locator('#loc-folder-list button', has_text='raw').click()                       # or an indexed descendant folder
    expect(page.locator('#loc-chosen')).to_have_text(SCAN_ROOT + '/raw')
    expect(page.locator('#loc-label')).to_have_value('raw')
    page.locator('#loc-label').fill('Synthetic raw data')                                  # editable display label
    page.locator('#loc-save').click()
    # Persisted as a logical shortcut in browser storage only; nothing is posted anywhere.
    assert json.loads(page.evaluate(f"localStorage.getItem('{LOC_KEY}')")) == [
        {'label': 'Synthetic raw data', 'scan_id': 's1', 'root_path': SCAN_ROOT + '/raw', 'access_mode': 'indexed'}]
    assert not [p for p, _ in api.posts if p.startswith('/api/')], api.posts
    mine = page.locator('[data-testid="saved-locations"] .loc-node')
    expect(mine).to_have_count(1)
    expect(mine.locator('[data-testid="location-badge"]')).to_have_text('Indexed')
    expect(mine).to_contain_text('Synthetic raw data')
    # Clicking it stays in Browse and fills the main file table from the scan index.
    mine.click()
    assert 'view=browse' in page.url and 'view=scans' not in page.url
    banner = page.locator('[data-testid="indexed-banner"]')
    expect(banner).to_be_visible()
    expect(banner).to_contain_text('Indexed')
    expect(banner).to_contain_text('raw files cannot be opened from here')
    expect(page.locator('#breadcrumb-nav')).to_contain_text('Synthetic raw data')
    assert any(p == '/api/external-index/browse' and q.get('scan_id') == ['s1'] and q.get('path') == [SCAN_ROOT + '/raw'] for p, q in api.queries)
    rows = page.locator('#file-list tr[data-id]')
    expect(rows).to_have_count(2)
    # The standard checkboxes, selection actions and Add to collection work on indexed rows.
    page.locator(f'.row-cb[data-id="{SCAN_ROOT}/a.csv"]').check()
    page.locator(f'.row-cb[data-id="{SCAN_ROOT}/raw"]').check()
    bar = page.locator('#files-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_visible()
    for label in ('Add to collection', 'Interpret', 'Ask about this'):
        expect(bar.get_by_role('button', name=label)).to_be_visible()
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
    stored = {x['kind']: x['p'] for x in _stored_basket(page)}
    assert stored['file'] == {'path': SCAN_ROOT + '/a.csv', 'name': 'a.csv', 'host': 'files.db:synthetic-host', 'scan_id': 's1', 'size': 10}
    assert stored['folder']['path'] == SCAN_ROOT + '/raw' and stored['folder']['scan_id'] == 's1'
    # The inspector opens for an indexed row.
    page.locator('#file-list tr[data-name="a.csv"] .name-cell').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    expect(page.locator('#inspector-title')).to_contain_text('a.csv')
    # Dataset recognition: the datasets recognized in this folder, each addable to the Collection by reference.
    strip = page.locator('[data-testid="indexed-datasets"]')
    expect(strip).to_be_visible()
    line = strip.locator(f'.indexed-dataset[data-root="{DATASET_ROOT}"]')
    line.locator('input.coll-add-cb').check()
    page.locator('#indexed-add-datasets').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 3 picks')
    ds = next(x for x in _stored_basket(page) if x['kind'] == 'dataset')['p']
    assert ds == {'scan_id': 's1', 'root_path': DATASET_ROOT, 'profile': 'synthetic_pattern', 'file_count': 3, 'bytes': 300}
    line.get_by_role('button', name='runA').click()
    expect(page.locator('#inspector-title')).to_contain_text('Dataset: runA')
    expect(page.locator('#inspector-add-to-collection')).to_be_visible()
    # Going back to a local drive leaves the indexed view cleanly.
    page.locator('#servers-tree .tree-node[data-root]').click()
    expect(banner).to_be_hidden()
    expect(strip).to_be_hidden()
    assert page.evaluate('window.indexedContext') is None
    # The shortcut is still there after a reload.
    page.goto(base + '/datasets?view=browse')
    expect(page.locator('[data-testid="saved-locations"] .loc-node')).to_have_count(1)
    assert not errors, errors


def test_browser_discovered_indexed_location_opens_in_browse_and_a_stale_shortcut_is_unavailable(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    base = serve()
    page.goto(base + '/datasets?view=browse')
    page.evaluate(f"localStorage.setItem('{LOC_KEY}', JSON.stringify([{{label: 'Synthetic stale', scan_id: 'gone', root_path: '/synthetic/gone', access_mode: 'indexed'}}]))")
    page.goto(base + '/datasets?view=browse')
    stale = page.locator('[data-testid="saved-locations"] .loc-node')
    expect(stale.locator('[data-testid="location-badge"]')).to_have_text('Unavailable')
    stale.click()
    expect(page.locator('#browser-status')).to_contain_text('Unavailable')
    expect(page.locator('#indexed-banner')).to_be_hidden()
    page.locator('[data-testid="scanned-locations"] .loc-node', has_text='indexed-share').click()
    assert 'view=browse' in page.url                                                         # no redirect to the Scans tab
    expect(page.locator('[data-testid="indexed-banner"]')).to_be_visible()
    assert any(p == '/api/external-index/browse' and q.get('path') == [SCAN_ROOT] for p, q in api.queries)
    expect(page.locator('#file-list tr[data-id]')).to_have_count(2)
    page.locator(f'.row-cb[data-id="{SCAN_ROOT}/a.csv"]').check()
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    # The Scans tab is still the backend inspector, and a stale link there says so.
    page.goto(base + '/datasets?view=scans&scan_id=gone')
    expect(page.locator('[data-testid="scans-access-badge"]')).to_have_text('Unavailable')
    assert not errors, errors


def test_legacy_files_page_keeps_its_drives_sidebar(monkeypatch, tmp_path):
    from tests.test_selection_actions import _app
    client = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True).test_client()
    legacy = client.get('/datasets').get_data(as_text=True)
    assert '<span id="servers-header">DRIVES</span>' in legacy and 'scanned-locations' not in legacy and 'Add Drive' in legacy
    browse = client.get('/datasets?view=browse').get_data(as_text=True)
    assert '<span id="servers-header">LOCATIONS</span>' in browse and 'data-testid="scanned-locations"' in browse
    assert '+ Add drive or location' in browse


# ── Browse polish: Add Drive "From Scan" tab, basket layering, page frame ─────

def test_add_drive_drawer_has_a_third_scan_tab_and_keeps_local_and_rclone(monkeypatch, tmp_path):
    from tests.test_selection_actions import _app
    client = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True).test_client()
    for url in ('/datasets?view=browse', '/datasets'):
        html = client.get(url).get_data(as_text=True)
        tabs = [t for t in ('local', 'rclone', 'scan') if f'data-drive-tab="{t}"' in html]
        assert tabs == ['local', 'rclone', 'scan'], url
        assert 'id="drive-tab-local"' in html and 'id="drive-tab-rclone"' in html and 'id="drive-tab-scan"' in html
        assert 'Local / Mounted</button>' in html and 'Rclone Remote</button>' in html and 'From Scan</button>' in html
    js = client.get('/static/js/add_drive.js').get_data(as_text=True)
    assert "access_mode: 'indexed'" in js and 'scidk.browse.locations.v1' in js


def test_browse_has_the_page_frame_and_legacy_files_keeps_its_full_bleed_layout(monkeypatch, tmp_path):
    from tests.test_selection_actions import _app
    client = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True).test_client()
    browse = client.get('/datasets?view=browse').get_data(as_text=True)
    legacy = client.get('/datasets').get_data(as_text=True)
    assert 'main { max-width:100% !important; padding:0 !important; }' not in browse     # shell padding and card frame kept
    assert 'main { max-width:100% !important; padding:0 !important; }' in legacy          # legacy page unchanged


def test_browser_add_drive_from_scan_tab_saves_an_indexed_drive_and_opens_it_in_browse(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    base = serve()
    page.goto(base + '/datasets?view=browse')
    page.locator('[data-testid="add-location-btn"]').click()
    page.locator('#add-location-local').click()                                            # the drawer: Local tab first
    drawer = page.locator('#add-drive-drawer')
    expect(drawer.locator('[data-drive-tab]')).to_have_text(['Local / Mounted', 'Rclone Remote', 'From Scan'])
    expect(drawer.locator('#drive-tab-local')).to_be_visible()
    drawer.locator('[data-drive-tab="rclone"]').click()
    expect(drawer.locator('#drive-tab-rclone')).to_be_visible()                           # unchanged
    drawer.locator('[data-drive-tab="scan"]').click()
    expect(drawer.locator('#drive-tab-scan')).to_be_visible()
    expect(drawer.locator('#drv-scan-select option')).to_have_count(1)                     # select scan
    expect(drawer.locator('#drv-scan-chosen')).to_have_text(SCAN_ROOT)                     # scan root by default
    expect(drawer.locator('#drv-scan-label')).to_have_value('share')
    drawer.locator('#drv-scan-folders button', has_text='raw').click()                     # or an indexed descendant
    expect(drawer.locator('#drv-scan-chosen')).to_have_text(SCAN_ROOT + '/raw')
    drawer.locator('#drv-scan-label').fill('Synthetic drawer drive')                      # editable label
    drawer.locator('#drv-scan-save').click()
    assert json.loads(page.evaluate(f"localStorage.getItem('{LOC_KEY}')")) == [
        {'label': 'Synthetic drawer drive', 'scan_id': 's1', 'root_path': SCAN_ROOT + '/raw', 'access_mode': 'indexed'}]
    assert not [p for p, _ in api.posts if p.startswith('/api/')], api.posts               # nothing written server-side
    expect(drawer).not_to_have_class(__import__('re').compile('open'))                      # drawer closed
    assert 'view=browse' in page.url and 'view=scans' not in page.url
    banner = page.locator('[data-testid="indexed-banner"]')
    expect(banner).to_be_visible()
    expect(banner).to_contain_text('raw files cannot be opened from here')
    expect(page.locator('#breadcrumb-nav')).to_contain_text('Synthetic drawer drive')
    expect(page.locator('[data-testid="saved-locations"] .loc-node [data-testid="location-badge"]')).to_have_text('Indexed')
    expect(page.locator('#file-list tr[data-id]')).to_have_count(2)
    page.locator(f'.row-cb[data-id="{SCAN_ROOT}/a.csv"]').check()                          # standard selection + collection
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    # A drive created from another page lands in Browse through ?open_scan=&open_path=.
    page.goto(base + '/datasets?view=browse&open_scan=s1&open_path=' + SCAN_ROOT + '/raw')
    expect(banner).to_be_visible()
    assert not errors, errors


def test_browser_the_collection_bubble_never_sits_above_an_open_overlay_and_returns_after(serve, ws_page):
    from playwright.sync_api import expect
    page, _, errors = ws_page
    page.goto(serve() + '/datasets?view=browse')
    pill = page.locator('#cb-pill')
    visibility = lambda sel: page.evaluate("(s) => getComputedStyle(document.querySelector(s)).visibility", sel)  # noqa: E731
    expect(pill).to_be_visible()
    page.locator('#cb-pill').click()                                                       # basket panel open: still shown
    assert visibility('#cb-panel') == 'visible'
    page.locator('[data-testid="add-location-btn"]').click()
    page.locator('#add-location-local').click()                                            # Add Drive drawer opens
    expect(page.locator('#add-drive-drawer')).to_have_class(__import__('re').compile('open'))
    assert visibility('#cb-pill') == 'hidden' and visibility('#cb-panel') == 'hidden'
    page.locator('#add-drive-drawer [data-close-drawer]').first.click()
    expect(pill).to_be_visible()                                                           # available again
    assert visibility('#cb-panel') == 'visible'
    # Any other modal, plan panel or dialog hides it the same way.
    for markup in ('<div id="t-modal" aria-modal="true" role="dialog">x</div>', '<div class="modal show" id="t-modal">x</div>'):
        page.evaluate("(h) => document.body.insertAdjacentHTML('beforeend', h)", markup)
        assert visibility('#cb-pill') == 'hidden', markup
        page.evaluate("document.getElementById('t-modal').remove()")
        assert visibility('#cb-pill') == 'visible'
    page.evaluate("document.getElementById('collection-plan-panel').hidden = false")      # the plan panel (a page element) opens
    assert visibility('#cb-pill') == 'hidden'
    page.evaluate("document.getElementById('collection-plan-panel').hidden = true")
    assert visibility('#cb-pill') == 'visible'
    assert not errors, errors


def test_browser_browse_is_framed_like_the_other_datasets_views(serve, ws_page):
    page, _, errors = ws_page
    base = serve()
    page.set_viewport_size({'width': 1400, 'height': 900})
    frame = """() => { const m = document.querySelector('main'); const f = document.querySelector('.files-page'); const r = f.getBoundingClientRect(), cs = getComputedStyle(f);
        return {pad: parseFloat(getComputedStyle(m).paddingLeft), left: r.left, radius: parseFloat(cs.borderTopLeftRadius), border: parseFloat(cs.borderTopWidth),
                shell: getComputedStyle(document.body).backgroundColor, card: cs.backgroundColor, bottom: r.bottom, vh: innerHeight, table: !!document.querySelector('.files-page .file-table')}; }"""
    page.goto(base + '/datasets?view=browse')
    page.wait_for_selector('.files-page .file-table')
    got = page.evaluate(frame)
    assert got['pad'] >= 20 and got['left'] > 190 + got['pad'] - 1          # page padding beside the 190px shell nav
    assert got['radius'] >= 10 and got['border'] >= 1                        # rounded, bordered workspace container
    assert got['card'] != got['shell'] and got['table']                      # separated from the shell; dense table inside
    assert got['bottom'] < got['vh'] - 8                                     # a visible buffer below
    page.goto(base + '/datasets?view=datasets')
    assert page.evaluate("parseFloat(getComputedStyle(document.querySelector('main')).paddingLeft)") == got['pad']   # same padding as Datasets
    assert not errors, errors


# ── the cached candidate list gives the same pages as the plain merge, and refreshes when the index changes ──

def test_cached_pages_match_the_plain_catalog_and_refresh_when_the_index_changes(signed_in):
    client, _, db, graph = signed_in
    from scidk.services import dataset_catalog as dc
    from scidk.web.routes import api_external_index as ei
    _add_candidates(db, 130)
    rows = [{'id': None, 'name': 'Mid human name', 'name_source': 'human', 'source': 'files.db', 'scan_id': SCAN, 'root_path': f'{ROOT}/g3/n0100',
             'profile': 'synthetic_profile', 'human_profile': 'override_type', 'description': 'd', 'members': 0},
            {'id': 'mm9', 'name': 'a_first', 'source': 'manual', 'files': 1, 'folders': 0, 'bytes': 5, 'members': 1},
            {'id': None, 'name': 'Gone from index', 'source': 'files.db', 'scan_id': 'ghost', 'root_path': '/ghost/x', 'members': 0}]
    conn = ei._open()
    try:
        prov = ei.scan_provenance(conn)
        plain = [ei.candidate_entry(r, prov) for r in ei.candidate_rows(conn)]
    finally:
        conn.close()
    cands = ei.candidate_set()
    assert len(cands) == len(plain)
    for q in ('', 'n01', 'synthetic_profile', 'override', 'a_first', 'data0', 'zzz', 'no-such-thing'):
        for state in ('all', 'candidate', 'confirmed', 'manual'):
            for offset in (0, 7, 60):
                want = dc.catalog_page(dc.build_items(plain, rows), q=q, state=state, limit=25, offset=offset)
                got = dc.cached_page(cands, rows, q=q, state=state, limit=25, offset=offset)
                assert got == want, (q, state, offset)
    # The same set is reused while the index is unchanged, and rebuilt when the file changes.
    assert ei.candidate_set() is cands
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id) VALUES ('late', 'late_profile', ?, ?)", (f'{ROOT}/late_one', SCAN))
    conn.commit(); conn.close()
    graph(read_results=[[]])
    body = client.get('/api/datasets/catalog?q=late_profile').get_json()
    assert body['total'] == 1 and body['datasets'][0]['name'] == 'late_one'
    assert ei.candidate_set() is not cands
