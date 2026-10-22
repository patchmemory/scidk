"""The shared agent tool layer (Task 5): registry, disclosure filter, adapters.

Offline tests always run. Graph tests run the tools against the LwM demo study
graph loaded into a throwaway Neo4j, and skip unless SCIDK_DEMO_NEO4J_URI points
at one (as tests/test_demo_fixture.py does). Never point it at a real graph:
the fixture deletes and reloads the demo nodes.
"""
import json
import os
import sqlite3

import pytest

from scidk.agent_tools import disclosure, registry
from scidk.agent_tools.disclosure import SharingPolicy, check_cypher, filter_for_agent
from scidk.agent_tools.registry import ToolContext, run_tool
from scidk.pipeline.passes.import_scan import import_scan

HIDE_EAR_TAG = SharingPolicy(modes={('Subject', 'ear_tag'): 'hidden'})


# ── Disclosure filter ──────────────────────────────────────────────────────

def test_filter_drops_hidden_property_and_says_so():
    result = {'status': 'success', 'rows': [
        {'s': {'_labels': ['Subject'], 'id': 'M10', 'ear_tag': '1L1R'}},
        {'s': {'_labels': ['Subject'], 'id': 'M11', 'ear_tag': 'none'}},
    ]}
    out = filter_for_agent(result, HIDE_EAR_TAG)
    assert 'ear_tag' not in json.dumps(out['rows'])
    assert out['rows'][0]['s']['id'] == 'M10'
    assert out['disclosure']['withheld_properties'] == 2
    assert 'Subject' in out['disclosure']['note']


def test_same_property_name_on_another_label_is_kept():
    out = filter_for_agent({'rows': [{'n': {'_labels': ['Cage'], 'ear_tag': 'x'}}]}, HIDE_EAR_TAG)
    assert out['rows'][0]['n']['ear_tag'] == 'x' and 'disclosure' not in out


def test_label_less_maps_drop_any_hidden_name():
    """properties(n) or a map projection loses the label: be conservative."""
    out = filter_for_agent({'rows': [{'p': {'id': 'M10', 'ear_tag': '1L1R'}}]}, HIDE_EAR_TAG)
    assert out['rows'] == [{'p': {'id': 'M10'}}]


def test_unknown_mode_fails_closed():
    policy = SharingPolicy(modes={('Subject', 'ear_tag'): 'pseudonymized'})
    out = filter_for_agent({'rows': [{'s': {'_labels': ['Subject'], 'ear_tag': '1L1R'}}]}, policy)
    assert 'ear_tag' not in out['rows'][0]['s']


def test_high_risk_source_records_are_withheld_whole():
    policy = SharingPolicy(withheld_sources=frozenset({'src-high'}))
    out = filter_for_agent({'rows': [{'n': {'_labels': ['Subject'], 'id': 'a', 'source_id': 'src-high'}},
                                     {'n': {'_labels': ['Subject'], 'id': 'b'}}]}, policy)
    assert out['rows'] == [{'n': None}, {'n': {'_labels': ['Subject'], 'id': 'b'}}]
    assert out['disclosure']['withheld_records'] == 1


@pytest.mark.parametrize('cypher', [
    "MATCH (s:Subject) RETURN s.ear_tag AS tag",
    "MATCH (s) RETURN s {.ear_tag}",
    "MATCH (s) RETURN s['ear_tag']",
    "MATCH (s) RETURN s[$k]",
    "MATCH (s) RETURN apoc.convert.toJson(s)",
    "MATCH (s) WHERE s.`ear_tag` = '1L1R' RETURN count(s)",
])
def test_cypher_reading_hidden_data_is_refused(cypher):
    assert check_cypher(cypher, HIDE_EAR_TAG, {'k': 'ear_tag'})


@pytest.mark.parametrize('cypher', [
    "MATCH (s:Subject) WHERE s.id IN ['M10', 'M11'] RETURN s.id, labels(s)[0], collect(s.id)[..3]",
    "MATCH (a)-[r:HAS_SESSION]->(b) RETURN a, r, b",
    "MATCH (s) RETURN s.ear_tag_count",
])
def test_ordinary_cypher_is_not_refused(cypher):
    assert check_cypher(cypher, HIDE_EAR_TAG) is None


def test_sharing_modes_round_trip(tmp_path):
    db = str(tmp_path / 'settings.db')
    disclosure.set_mode(db, 'Subject', 'ear_tag', 'hidden', 'root')
    assert disclosure.load_policy(db).is_hidden(['Subject'], 'ear_tag')
    disclosure.set_mode(db, 'Subject', 'ear_tag', 'raw')
    assert disclosure.load_policy(db).empty
    with pytest.raises(ValueError):
        disclosure.set_mode(db, 'Subject', 'ear_tag', 'randomized')


# ── run_tool ───────────────────────────────────────────────────────────────

def test_every_registry_entry_has_a_handler():
    assert set(registry._HANDLERS) == set(registry.tool_names(include_chat_only=True))


def test_run_tool_checks_arguments():
    ctx = ToolContext()
    assert 'Unknown tool' in run_tool('drop_everything', {}, ctx)['error']
    assert 'Unexpected' in run_tool('scan_summary', {'bogus': 1}, ctx)['error']
    assert 'Missing' in run_tool('count_nodes', {}, ctx)['error']


def test_graph_tools_say_graph_not_connected():
    for name, args in [('query_knowledge_graph', {'cypher': 'MATCH (n) RETURN n'}), ('list_labels', {}),
                       ('count_nodes', {'label': 'Subject'}), ('get_schema', {})]:
        out = run_tool(name, args, ToolContext(driver=None))
        assert out['status'] == 'error' and 'not connected' in out['error']


def test_unreadable_sharing_settings_refuse_every_tool(tmp_path):
    bad = tmp_path / 'settings.db'
    bad.write_bytes(b'not a database' * 50)
    out = run_tool('scan_summary', {}, ToolContext(settings_db=str(bad)))
    assert out['status'] == 'error' and 'sharing settings' in out['error']


# ── files.db tools on the demo fixture ─────────────────────────────────────

@pytest.fixture
def demo_index(demo_files_db, tmp_path, monkeypatch):
    snap, scan_id = demo_files_db
    files_db = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(files_db))
    import_scan(str(snap), str(files_db), scan_id)
    return str(files_db), scan_id


def test_scan_summary_on_demo_index(demo_index):
    files_db, scan_id = demo_index
    out = run_tool('scan_summary', {}, ToolContext(files_db=files_db))
    assert out['status'] == 'success' and out['total'] == 1
    assert out['scans'][0]['file_count'] == 3746 and out['scans'][0]['folder_count'] == 2449
    one = run_tool('scan_summary', {'scan_id': scan_id}, ToolContext(files_db=files_db))
    assert one['top_extensions'] and one['top_extensions'][0]['files'] > 0
    assert one['hosts'] and one['hosts'][0].startswith('local:')


def test_profile_tools_say_not_profiled_yet(demo_index):
    files_db, _ = demo_index
    for name, args in [('list_collections', {}), ('get_collection', {'id': 'x'}),
                       ('search_datasets', {'query': 'wk9'}), ('unclaimed_summary', {})]:
        assert run_tool(name, args, ToolContext(files_db=files_db))['status'] == 'not_profiled'


def test_search_datasets_caps_at_50_and_reports_total(demo_index):
    files_db, scan_id = demo_index
    with sqlite3.connect(files_db) as conn:  # the spec's Pass 3 table, as Profile will write it
        conn.execute("CREATE TABLE data_objects (id TEXT PRIMARY KEY, pattern_name TEXT, root_path TEXT,"
                     " scan_id TEXT, status TEXT, confidence REAL, file_count INTEGER, total_bytes INTEGER,"
                     " sentinel_path TEXT, metadata_json TEXT, created_at REAL, updated_at REAL)")
        conn.executemany("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, status, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?,?)",
                         [(f'obj{i}', 'bruker_microct', f'/d/wk9_{i}_Rec', scan_id, 'candidate', i, i) for i in range(60)])
    out = run_tool('search_datasets', {'profile': 'bruker_microct', 'owner': 'Anderson'},
                   ToolContext(files_db=files_db))
    assert out['status'] == 'success' and out['total'] == 60 and len(out['datasets']) == 50
    assert 'owner' in out['note']


def test_files_db_is_opened_read_only(demo_index):
    files_db, _ = demo_index
    from scidk.agent_tools import tools_sql
    conn = tools_sql._connect(ToolContext(files_db=files_db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM files")
    conn.close()


# ── Adapters ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch, demo_index):
    for var in ('NEO4J_URI', 'BOLT_URI', 'NEO4J_PASSWORD', 'NEO4J_AUTH'):
        monkeypatch.delenv(var, raising=False)
    from scidk.app import create_app
    from tests.conftest import authenticate_test_client
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    app.extensions['scidk']['neo4j_config'] = {}
    return authenticate_test_client(app.test_client(), app)


def test_all_adapters_list_the_same_tools(client):
    http = {t['name'] for t in client.get('/api/agent/tools').get_json()['tools']}
    funcs = {f['function']['name'] for f in client.get('/api/agent/functions.json').get_json()}
    spec = client.get('/api/agent/openapi.json').get_json()
    openapi = {op['post']['operationId'] for op in spec['paths'].values()}
    import scidk.mcp_server as mcp_server  # list_tools reads the registry, minus CHAT_ONLY
    mcp = {t['name'] for t in mcp_server.mcp_tools.TOOL_DEFINITIONS if t['name'] not in mcp_server.CHAT_ONLY}
    assert http == funcs == openapi == mcp == set(registry.tool_names())
    assert spec['openapi'] == '3.1.0'


def test_http_adapter_runs_a_tool(client):
    out = client.post('/api/agent/tools/scan_summary', json={}).get_json()
    assert out['status'] == 'success' and out['scans'][0]['file_count'] == 3746
    assert client.post('/api/agent/tools/nope', json={}).status_code == 404


def test_hidden_property_never_leaves_through_http(client, monkeypatch):
    """The HTTP adapter goes through run_tool, so it gets the filter too."""
    class FakeDriver:
        def session(self, **kw):
            return FakeSession()
    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_read(self, work):
            return [{'s': {'_labels': ['Subject'], 'id': 'M10', 'ear_tag': '1L1R'}}]
    from scidk.agent_tools import context as ctx_mod
    monkeypatch.setattr(ctx_mod, '_driver', lambda app: (FakeDriver(), None))
    assert client.put('/api/agent/sharing', json={'label': 'Subject', 'property': 'ear_tag',
                                                  'sharing_mode': 'hidden'}).status_code == 200
    out = client.post('/api/agent/tools/query_knowledge_graph',
                      json={'cypher': 'MATCH (s:Subject) RETURN s'}).get_json()
    assert out['status'] == 'success' and '1L1R' not in json.dumps(out) and 'ear_tag' not in json.dumps(out['rows'])
    assert out['disclosure']['withheld_properties'] == 1
    refused = client.post('/api/agent/tools/query_knowledge_graph',
                          json={'cypher': 'MATCH (s:Subject) RETURN s.ear_tag'}).get_json()
    assert refused['status'] == 'refused'


# ── Graph tools on the LwM demo study graph ────────────────────────────────

needs_demo_neo4j = pytest.mark.skipif(
    not os.environ.get('SCIDK_DEMO_NEO4J_URI'),
    reason='set SCIDK_DEMO_NEO4J_URI (+ _USER/_PASSWORD) to a throwaway Neo4j')


@pytest.fixture(scope='module')
def demo_graph():
    neo4j = pytest.importorskip('neo4j')
    from tests.fixtures.demo import demo_fixture as demo
    drv = neo4j.GraphDatabase.driver(os.environ['SCIDK_DEMO_NEO4J_URI'],
                                     auth=(os.environ.get('SCIDK_DEMO_NEO4J_USER', 'neo4j'),
                                           os.environ.get('SCIDK_DEMO_NEO4J_PASSWORD', '')))
    with drv.session() as ses:
        ses.run("MATCH (n {demo_dataset: 'LWM-DEMO-2026'}) DETACH DELETE n").consume()
        demo.load_into(ses)
    yield drv, demo
    drv.close()


@needs_demo_neo4j
def test_graph_tools_on_demo_graph(demo_graph):
    drv, demo = demo_graph
    ctx = ToolContext(driver=drv)
    labels = {l['name']: l['count'] for l in run_tool('list_labels', {}, ctx)['labels']}
    for label, n in demo.EXPECTED_NODE_COUNTS.items():
        assert labels.get(label, 0) >= n
    assert run_tool('count_nodes', {'label': 'Subject'}, ctx)['count'] >= demo.EXPECTED_NODE_COUNTS['Subject']
    mri = run_tool('count_nodes', {'label': 'ImagingSession', 'where': {'modality': 'MRI'}}, ctx)
    assert mri['status'] == 'success'
    rows = run_tool('query_knowledge_graph', {'cypher': 'MATCH (s:Subject) RETURN s'}, ctx)
    assert rows['status'] == 'success' and rows['rows'][0]['s']['_labels'] == ['Subject']
    json.dumps(rows)  # serialized, not raw Neo4j objects
    assert run_tool('get_schema', {}, ctx)['status'] == 'success'


@needs_demo_neo4j
def test_query_results_are_capped(demo_graph):
    drv, _ = demo_graph
    out = run_tool('query_knowledge_graph', {'cypher': 'UNWIND range(1, 500) AS i RETURN i LIMIT 500'},
                   ToolContext(driver=drv))
    assert out['row_count'] == 50 and out['truncated'] is True


@needs_demo_neo4j
def test_writes_are_refused_even_past_the_keyword_check(demo_graph):
    drv, _ = demo_graph
    out = run_tool('query_knowledge_graph',
                   {'cypher': "CALL { CREATE (:Leak) } IN TRANSACTIONS RETURN 1"}, ToolContext(driver=drv))
    assert out['status'] == 'error'
    with drv.session() as ses:
        assert ses.run("MATCH (n:Leak) RETURN count(n) AS n").single()['n'] == 0


@needs_demo_neo4j
def test_hidden_property_never_leaves_on_demo_graph(demo_graph, tmp_path):
    drv, _ = demo_graph
    db = str(tmp_path / 'settings.db')
    disclosure.set_mode(db, 'Subject', 'ear_tag', 'hidden')
    ctx = ToolContext(driver=drv, settings_db=db)
    with drv.session() as ses:
        tags = {r['t'] for r in ses.run("MATCH (s:Subject) WHERE s.ear_tag IS NOT NULL RETURN s.ear_tag AS t")}
    assert tags, 'the demo graph should have ear tags to hide'

    def leaked(value):
        if isinstance(value, dict):
            return 'ear_tag' in value or any(leaked(v) for v in value.values())
        if isinstance(value, list):
            return any(leaked(v) for v in value)
        return False

    for cypher in ['MATCH (s:Subject) RETURN s', 'MATCH (s:Subject) RETURN properties(s) AS p',
                   'MATCH (s:Subject) RETURN s {.*} AS m', 'MATCH p=(s:Subject)--() RETURN p LIMIT 5']:
        out = run_tool('query_knowledge_graph', {'cypher': cypher}, ctx)
        assert out['status'] == 'success', out
        assert not leaked(out['rows']), cypher
        values = {v for r in out['rows'] for v in json.dumps(r).split('"')}
        assert not (tags - {'none'}) & values, cypher
