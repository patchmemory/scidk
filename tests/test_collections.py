"""Collections as their own level: (:Collection)-[:INCLUDES]->(Dataset | Folder | File | context).

Driven against a fake Neo4j client that records the Cypher it is handed. Names are
synthetic. Writes must be MERGE only, and a recognized dataset joins by reference.
"""
import pytest

from scidk.app import create_app
from scidk.services import collection_service as cs
from scidk.web.routes import api_annotation
from tests.conftest import authenticate_test_client


class FakeNeo4jClient:
    def __init__(self, write_results=None, read_results=None):
        self.calls = []
        self._write = list(write_results or [])
        self._read = list(read_results or [])

    def execute_write(self, query, parameters=None):
        self.calls.append(('write', query, parameters or {}))
        return self._write.pop(0) if self._write else []

    def execute_read(self, query, parameters=None):
        self.calls.append(('read', query, parameters or {}))
        return self._read.pop(0) if self._read else []

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    app = create_app()
    app.config['TESTING'] = True
    return authenticate_test_client(app.test_client(), app)


@pytest.fixture()
def fake_graph(monkeypatch):
    holder = {}

    def install(**kwargs):
        holder['client'] = FakeNeo4jClient(**kwargs)
        monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: holder['client'])
        return holder['client']

    return install


def _writes(graph):
    return [(q, p) for kind, q, p in graph.calls if kind == 'write']


def _write_for(graph, needle):
    return next((q, p) for q, p in _writes(graph) if needle in q)


MEMBERS = [
    {'kind': 'dataset', 'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runA', 'name': 'runA',
     'profile': 'Vevo', 'file_count': 12, 'bytes': 3400},
    {'kind': 'dataset', 'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runB', 'profile': 'Vevo',
     'file_count': 8, 'bytes': 1000},
    {'kind': 'folder', 'path': '/net/hostx/data/sharea/notes', 'name': 'notes', 'host': 'files.db:hostx'},
    {'kind': 'context', 'label': 'Request', 'id': '4:x:1'},
]


def test_save_writes_collection_with_includes_edges_by_kind(client, fake_graph):
    graph = fake_graph(write_results=[[], [{'linked': 2}], [{'linked': 1}], [{'linked': 1}]])
    r = client.post('/api/collections', json={'name': 'Demo collection', 'description': 'for sharing', 'members': MEMBERS})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['linked'] == {'dataset': 2, 'folder': 1, 'file': 0, 'context': 1}
    assert body['created'] is True and body['collection_id']

    head_q, head_p = _write_for(graph, 'MERGE (c:Collection')
    assert head_p['name'] == 'Demo collection' and head_p['created_by']
    for field in ('c.created_by', 'c.created_at', 'c.description'):
        assert field in head_q
    for q, _ in _writes(graph):
        assert 'DELETE' not in q.upper() and 'DETACH' not in q.upper()
        assert 'CREATE (' not in q.upper()          # MERGE only
    assert all('MERGE (c)-[:INCLUDES]->' in q for q, _ in _writes(graph)[1:])


def test_recognized_dataset_joins_by_reference_without_file_rows(client, fake_graph):
    graph = fake_graph(write_results=[[], [{'linked': 2}]])
    client.post('/api/collections', json={'name': 'C', 'members': MEMBERS[:2]})
    q, p = _write_for(graph, 'MERGE (d:Dataset')
    assert 'MERGE (d:Dataset {scan_id: row.scan_id, root_path: row.root_path})' in q
    assert "d.source = 'files.db'" in q
    assert 'File' not in q                              # never copies its file rows
    assert set(p['rows'][0]) == {'scan_id', 'root_path', 'name', 'profile', 'file_count', 'bytes'}
    assert p['rows'][0]['profile'] == 'Vevo' and p['rows'][0]['file_count'] == 12 and p['rows'][0]['bytes'] == 3400


def test_context_nodes_are_matched_not_created(client, fake_graph):
    graph = fake_graph(write_results=[[], [{'linked': 2}]])
    client.post('/api/collections', json={'name': 'C', 'members': [
        {'kind': 'context', 'label': 'Sample', 'id': '4:x:2'}, {'kind': 'context', 'label': 'SampleType', 'id': '4:x:3'}]})
    q, p = _write_for(graph, 'elementId(n) = row.id')
    assert 'MATCH (n)' in q and 'row.label IN labels(n)' in q and 'MERGE (n' not in q
    assert p['rows'] == [{'label': 'Sample', 'id': '4:x:2'}, {'label': 'SampleType', 'id': '4:x:3'}]


def test_existing_name_is_refused_unless_adding(client, fake_graph):
    graph = fake_graph(read_results=[[{'id': 'abc', 'members': 3}]])
    r = client.post('/api/collections', json={'name': 'Taken', 'members': MEMBERS[:1]})
    assert r.status_code == 409 and r.get_json()['exists'] and r.get_json()['members'] == 3
    assert not _writes(graph)


def test_add_to_existing_reuses_the_collection_id(client, fake_graph):
    graph = fake_graph(read_results=[[{'id': 'abc', 'members': 3}]], write_results=[[], [{'linked': 1}]])
    r = client.post('/api/collections', json={'name': 'Taken', 'add_to_existing': True, 'members': MEMBERS[:1]})
    assert r.status_code == 200 and r.get_json()['created'] is False and r.get_json()['collection_id'] == 'abc'
    assert _write_for(graph, 'MERGE (c:Collection')[1]['id'] == 'abc'


def test_needs_name_and_members_and_reports_malformed_entries(client, fake_graph):
    fake_graph()
    assert client.post('/api/collections', json={'members': MEMBERS}).status_code == 400
    assert client.post('/api/collections', json={'name': 'C', 'members': []}).status_code == 400
    r = client.post('/api/collections', json={'name': 'C', 'members': [{'kind': 'dataset'}, {'kind': 'nope'}]})
    assert r.status_code == 400 and len(r.get_json()['problems']) == 2


def test_neo4j_missing_is_a_503_with_the_reason(client, monkeypatch):
    def unavailable():
        raise api_annotation.Neo4jUnavailable('No Neo4j connection is configured')
    monkeypatch.setattr(api_annotation, '_neo4j_client', unavailable)
    r = client.post('/api/collections', json={'name': 'C', 'members': MEMBERS[:1]})
    assert r.status_code == 503 and r.get_json()['error'] == 'No Neo4j connection is configured'


# ── the Files-page Collect panel route now writes a Collection ─────────────────

def test_files_page_route_writes_a_collection_not_a_dataset(client, fake_graph):
    graph = fake_graph(write_results=[[], [{'linked': 1}], [{'linked': 1}]])
    r = client.post('/api/datasets/collections', json={'name': 'From files page', 'files': [
        {'name': 'a.tif', 'path': 'hostz/data/p', 'host': 'hostz'},
        {'name': 'sub', 'path': 'hostz/data/p', 'host': 'hostz', 'type': 'folder'},
    ]})
    body = r.get_json()
    assert r.status_code == 200, body
    assert body['linked']['file'] == 1 and body['linked']['folder'] == 1 and body['files_linked'] == 1
    assert not any('MERGE (d:Dataset {name' in q for q, _ in _writes(graph))
    _, fp = _write_for(graph, 'MERGE (f:File')
    assert fp['rows'][0]['path'] == 'hostz/data/p/a.tif' and fp['rows'][0]['host'] == 'hostz'
    _, op = _write_for(graph, 'MERGE (f:Folder')
    assert op['rows'][0]['path'] == 'hostz/data/p/sub'          # a folder stays a folder, not expanded


def test_unplaceable_file_is_reported_not_stubbed(client, fake_graph):
    fake_graph(write_results=[[]])
    r = client.post('/api/datasets/collections', json={'name': 'C', 'files': [{'name': 'a.fcs', 'path': '/mnt/x', 'provider_id': 'mounted_fs'}]})
    assert r.status_code == 400 and 'host' in r.get_json()['problems'][0]


# ── sharing plan ─────────────────────────────────────────────────────────────

class _Reads:
    """Answers the three reads collection_summary makes, in order."""
    def __init__(self, members, neighbours):
        self.members, self.neighbours = members, neighbours
        self.calls = []

    def execute_read(self, query, parameters=None):
        self.calls.append(query)
        if 'RETURN c.name AS name' in query:
            return [{'name': 'Synthetic collection', 'description': None, 'created_by': 'tester', 'created_at': 1}]
        if 'RETURN elementId(m) AS eid, labels(m)' in query and 'INCLUDES' in query:
            return self.members
        return self.neighbours

    def close(self):
        pass


def _synthetic_reads():
    members = [
        {'eid': 'e1', 'labels': ['Dataset'], 'p': {'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runA', 'profile': 'Vevo', 'file_count': 12, 'bytes': 3400}},
        {'eid': 'e2', 'labels': ['Dataset'], 'p': {'scan_id': 's1', 'root_path': '/net/hostx/data/sharea/runB', 'profile': 'Vevo', 'file_count': 8, 'bytes': 1000}},
        {'eid': 'e3', 'labels': ['Folder'], 'p': {'path': '/p/notes', 'host': 'files.db:hostx'}},
        {'eid': 'e4', 'labels': ['Request'], 'p': {'uid': 'REQ-1'}},
        {'eid': 'e5', 'labels': ['Sample'], 'p': {'uid': 'S-1', 'Link_PrimaryData': 'https://www.immport.org/shared/study/SDYTEST1', 'patient_name': 'x'}},
        {'eid': 'e6', 'labels': ['Sample'], 'p': {'uid': 'S-2', 'Link_PrimaryData': 'see https://zenodo.org/records/12345 and https://www.immport.org/shared/study/SDYTEST1'}},
    ]
    neighbours = [
        {'mid': 'e5', 'mlabels': ['Sample'], 'xlabels': ['SampleType'], 'xp': {'name': 'Plasma'}},
        {'mid': 'e6', 'mlabels': ['Sample'], 'xlabels': ['SampleType'], 'xp': {'name': 'Plasma'}},
        {'mid': 'e5', 'mlabels': ['Sample'], 'xlabels': ['Study'], 'xp': {'uid': 'STUDY-1'}},
    ]
    return _Reads(members, neighbours)


def test_summary_counts_members_by_kind_and_profile():
    summary = cs.collection_summary(_synthetic_reads(), 'cid', dataset_types=lambda scan, root: ({'.tif': [10, 3000], '.csv': [10, 1400]}, True))
    assert summary['members'] == {'dataset': 2, 'folder': 1, 'file': 0, 'context': 3}
    assert summary['datasets_by_profile'] == {'Vevo': {'datasets': 2, 'files': 20, 'bytes': 4400}}
    assert summary['total_files'] == 20 and summary['total_bytes'] == 4400
    assert summary['file_types']['.tif'] == [20, 6000]
    assert summary['samples'] == {'count': 2, 'by_type': {'Plasma': 2}}
    assert summary['storage_locations']['hostx / sharea'] == 2
    repos = {l['repository'] for l in summary['public_links']}
    assert repos == {'ImmPort', 'Zenodo'}


def test_plan_lists_members_links_and_keeps_phi_warnings():
    summary = cs.collection_summary(_synthetic_reads(), 'cid', dataset_types=lambda scan, root: ({}, False))
    text = cs.collection_plan(summary, {'repository': 'Example repository'})
    assert 'Datasets by profile' in text and 'Vevo: 2 dataset(s), 20 files' in text
    assert 'https://www.immport.org/shared/study/SDYTEST1' in text and 'Zenodo' in text
    assert 'REQ-1' in text and 'STUDY-1' in text and 'sample type Plasma: 2' in text
    assert 'No PHI, consent or de-identification assessment has been performed' in text
    assert 'patient_name' in text                      # PHI-looking property on a member is flagged by the NIH renderer
    assert 'Example repository' in text


def test_investigators_are_counted_never_listed():
    reads = _synthetic_reads()
    reads.members.append({'eid': 'e7', 'labels': ['Investigator'], 'p': {'name': 'Synthetic Person'}})
    summary = cs.collection_summary(reads, 'cid', dataset_types=lambda scan, root: ({}, False))
    text = cs.collection_plan(summary, {})
    assert summary['context_counts']['Investigator'] == 1
    assert 'Synthetic Person' not in text


def test_plan_route_is_gated_by_the_existing_sharing_flag(client, monkeypatch):
    from plugins.nih_dms import routes as nih_routes
    monkeypatch.setattr(nih_routes, '_neo4j_client', lambda: _synthetic_reads())
    monkeypatch.setattr(cs, '_dataset_types', lambda scan, root: ({}, False))
    client.application.config['SCIDK_DATASET_SHARING_ENABLED'] = False
    url = '/api/plugins/nih_dms/collections/cid/draft_plan'
    assert client.post(url, json={'fields': {}}).status_code == 403
    client.application.config['SCIDK_DATASET_SHARING_ENABLED'] = True
    r = client.post(url, json={'fields': {}})
    assert r.status_code == 200, r.get_json()
    assert 'Collection' in r.get_json()['markdown'] and r.get_json()['summary']['members']['dataset'] == 2


def test_dev_launcher_enables_dataset_sharing():
    import inspect
    from scidk import dev_gui
    assert 'SCIDK_DATASET_SHARING_ENABLED=True' in inspect.getsource(dev_gui.build_app)
