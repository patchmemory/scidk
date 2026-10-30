"""Files → manual Dataset, saved-collection reopening, and collection-scoped DMS prose.

Synthetic names only. A fake graph client records the Cypher it is handed.
"""
import re

from plugins.nih_dms.generator import render_plan
from plugins.nih_dms.graph_facts import FormatRow, GraphFacts
from scidk.services import collection_service as cs
from tests.test_collections import (  # noqa: F401 - fixtures
    FakeNeo4jClient, _Reads, _synthetic_reads, _write_for, _writes, client, fake_graph)

MEMBERS = [
    {'kind': 'folder', 'path': '/net/hostx/data/sharea/notes', 'name': 'notes', 'host': 'files.db:hostx'},
    {'kind': 'file', 'path': '/net/hostx/data/sharea/notes/a.csv', 'name': 'a.csv', 'host': 'files.db:hostx', 'size': 12},
]


# ── POST /api/datasets/manual ────────────────────────────────────────────────

def test_manual_dataset_merges_a_manual_dataset_with_contains_edges(client, fake_graph, monkeypatch):
    # No path to files.db may be touched: any attempt to open it fails the request.
    from scidk.web.routes import api_external_index as ex
    from scidk.core import path_index_sqlite as pix

    def boom(*a, **k):
        raise AssertionError('files.db must not be opened')
    monkeypatch.setattr(ex, '_open', boom)
    monkeypatch.setattr(pix, 'connect', boom)

    graph = fake_graph(write_results=[[], [{'linked': 1}], [{'linked': 1}]])
    r = client.post('/api/datasets/manual', json={'name': 'Synthetic dataset', 'description': 'by hand', 'members': MEMBERS})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['status'] == 'ok' and body['name'] == 'Synthetic dataset' and body['dataset_id']
    assert body['linked'] == {'folder': 1, 'file': 1}

    head_q, head_p = _write_for(graph, 'MERGE (d:Dataset {id: $id})')
    assert "d.source = 'manual'" in head_q and 'd.created_by' in head_q and 'd.updated_at' in head_q
    assert head_p['id'] == body['dataset_id'] and head_p['name'] == 'Synthetic dataset'
    assert 'Collection' not in head_q and 'INCLUDES' not in head_q
    folder_q, _ = _write_for(graph, 'MERGE (f:Folder')
    file_q, file_p = _write_for(graph, 'MERGE (f:File')
    assert 'MERGE (d)-[:CONTAINS]->(f)' in folder_q and 'MERGE (d)-[:CONTAINS]->(f)' in file_q
    assert 'f.stub = true' in file_q and file_p['rows'][0]['host'] == 'files.db:hostx'
    for q, _ in _writes(graph):
        assert 'DELETE' not in q.upper() and 'DETACH' not in q.upper() and 'CREATE (' not in q.upper()


def test_manual_dataset_ids_are_fresh_and_never_a_recognized_dataset(client, fake_graph):
    fake_graph(write_results=[[], [{'linked': 1}]] * 2)
    a = client.post('/api/datasets/manual', json={'name': 'D', 'members': MEMBERS[:1]}).get_json()
    b = client.post('/api/datasets/manual', json={'name': 'D', 'members': MEMBERS[:1]}).get_json()
    assert a['dataset_id'] != b['dataset_id']


def test_manual_dataset_needs_name_and_members_and_only_takes_files_and_folders(client, fake_graph):
    fake_graph()
    assert client.post('/api/datasets/manual', json={'members': MEMBERS}).status_code == 400
    assert client.post('/api/datasets/manual', json={'name': 'D', 'members': []}).status_code == 400
    r = client.post('/api/datasets/manual', json={'name': 'D', 'members': [{'kind': 'context', 'label': 'Sample', 'id': 'x'}]})
    assert r.status_code == 400 and r.get_json()['problems']


# ── GET /api/collections/<id> ────────────────────────────────────────────────

def _collection_reads():
    head = [{'id': 'cid', 'name': 'Synthetic collection', 'description': 'for sharing',
             'created_by': 'tester', 'created_at': 5, 'updated_at': 6}]
    members = [
        {'eid': 'e1', 'labels': ['Dataset'], 'p': {'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runA', 'name': 'runA',
                                                     'profile': 'Vevo', 'file_count': 12, 'bytes': 3400, 'source': 'files.db'}},
        {'eid': 'e2', 'labels': ['Folder'], 'p': {'path': '/p/notes', 'host': 'files.db:hostx', 'name': 'notes'}},
        {'eid': 'e3', 'labels': ['File'], 'p': {'path': '/p/notes/a.csv', 'host': 'files.db:hostx', 'filename': 'a.csv', 'size_bytes': 12, 'stub': True}},
        {'eid': 'e4', 'labels': ['Sample'], 'p': {'uid': 'S-1', 'patient_name': 'Synthetic Person', 'Link_PrimaryData': 'x'}},
    ]
    return FakeNeo4jClient(read_results=[head, members])


def test_get_collection_returns_typed_grouped_members(client, fake_graph, monkeypatch):
    from scidk.web.routes import api_annotation
    graph = _collection_reads()
    monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: graph)
    r = client.get('/api/collections/cid')
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d['collection'] == {'id': 'cid', 'name': 'Synthetic collection', 'description': 'for sharing',
                               'created_by': 'tester', 'created_at': 5, 'updated_at': 6}
    assert set(d['members']) == {'dataset', 'folder', 'file', 'context'}
    assert d['members']['dataset'] == [{'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runA', 'name': 'runA',
                                         'profile': 'Vevo', 'file_count': 12, 'bytes': 3400}]
    assert d['members']['folder'] == [{'path': '/p/notes', 'host': 'files.db:hostx', 'name': 'notes'}]
    assert d['members']['file'] == [{'path': '/p/notes/a.csv', 'host': 'files.db:hostx', 'filename': 'a.csv', 'size_bytes': 12}]
    assert d['members']['context'] == [{'id': 'e4', 'label': 'Sample', 'display': 'S-1'}]
    assert 'Synthetic Person' not in r.get_data(as_text=True)      # no unrelated properties
    assert all(kind == 'read' for kind, _, _ in graph.calls)


def test_get_unknown_collection_is_404(client, monkeypatch):
    from scidk.web.routes import api_annotation
    monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: FakeNeo4jClient())
    assert client.get('/api/collections/nope').status_code == 404


# ── collection facts and prose ───────────────────────────────────────────────

def _summary_with_files():
    reads = _synthetic_reads()
    reads.members.append({'eid': 'e8', 'labels': ['File'], 'p': {'path': '/p/notes/a.csv', 'host': 'files.db:hostx', 'filename': 'a.csv', 'size_bytes': 12}})
    return cs.collection_summary(reads, 'cid', dataset_types=lambda scan, root: ({}, False))


def test_collection_facts_are_collection_scoped_and_count_files():
    facts = cs.collection_facts(_summary_with_files())
    assert facts.scope == 'collection' and facts.rocrate_export_available is False
    assert ('File', 1) in facts.label_counts and ('Folder', 1) in facts.label_counts


def test_graph_facts_defaults_keep_existing_callers_global():
    facts = GraphFacts()
    assert facts.scope == 'graph' and facts.rocrate_export_available is False


def test_collection_plan_is_honest_about_scope_and_export():
    text = cs.collection_plan(_summary_with_files(), {})
    low = text.lower()
    assert 'selected collection' in low
    assert 'this project\'s data' not in low and 'the graph records' not in low
    assert 'planned future work' in low and 'does not export ro-crate' in low
    for claim in ('sciDK generates these crates', 'exportable as', 'each released ro-crate', 'packaged as an **ro-crate**'):
        assert claim.lower() not in low
    assert 'could be detected' not in low and 'can be detected' not in low
    assert 'no comparison to detect missing or altered files was run' in low
    assert 'included collection members' in low                    # PHI wording scoped to members
    assert 'no property naming a measurement modality or assay was found in the selected collection' in low
    assert '[REPOSITORY_NAME]' in text or '[' in text               # NIH placeholders preserved
    assert 'folder(s) are included as folders' in text               # folder warning
    assert not re.search(r'came from|where it came from', low)       # no unsupported provenance claim


def test_collection_plan_phi_wording_is_member_scoped():
    reads = _synthetic_reads()
    summary = cs.collection_summary(reads, 'cid', dataset_types=lambda scan, root: ({}, False))
    low = cs.collection_plan(summary, {}).lower()
    assert 'this graph holds property names' not in low and 'this graph contains property names' not in low
    assert 'included collection members' in low


def test_global_plan_keeps_its_established_wording():
    facts = GraphFacts(label_counts=(('Sample', 3),), relationship_counts=(('HAS', 2),), file_count=4, file_bytes=100,
                       formats=(FormatRow('.csv', 4, 100, 'CSV', 'RFC 4180'),))
    text = render_plan(facts, generated_at='T')
    assert 'This project\'s data are managed in a SciDK knowledge graph' in text
    assert 'Generated by SciDK from the live graph on T' in text
    assert 'SciDK generates these crates directly from the graph' in text
    assert 'exportable as RO-Crate' in text


# ── access: the same signed-in audience as browsing/collecting ───────────────

def test_manual_dataset_is_open_to_a_regular_signed_in_user_but_not_anonymous(monkeypatch, tmp_path):
    """No new role gate: a plain 'user' may create one; normal authentication still applies."""
    import os
    from scidk.app import create_app
    from scidk.core.auth import get_auth_manager
    from scidk.web.routes import api_annotation

    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')   # enforce, instead of the test-mode bypass
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    user_id = auth.create_user('plain-user', 'password123', role='user')   # turns auth on
    token = auth.create_user_session(user_id, 'plain-user')

    graph = FakeNeo4jClient(write_results=[[], [{'linked': 1}], [{'linked': 1}]])
    monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: graph)
    payload = {'name': 'Synthetic dataset', 'members': MEMBERS}
    anon = app.test_client().post('/api/datasets/manual', json=payload)
    assert anon.status_code == 401
    ok = app.test_client().post('/api/datasets/manual', json=payload,
                                headers={'Authorization': f'Bearer {token}'})
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()['linked'] == {'folder': 1, 'file': 1}
