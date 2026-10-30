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
from scidk.agent_tools.security import REFUSAL

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
        assert out == REFUSAL


def test_unreadable_sharing_settings_refuse_every_tool(tmp_path):
    bad = tmp_path / 'settings.db'
    bad.write_bytes(b'not a database' * 50)
    out = run_tool('scan_summary', {}, ToolContext(settings_db=str(bad)))
    assert out == REFUSAL


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
    from scidk.agent_tools import tools_sql
    out = tools_sql.scan_summary(ToolContext(files_db=files_db))
    assert out['status'] == 'success' and out['total'] == 1
    assert out['scans'][0]['file_count'] == 3746 and out['scans'][0]['folder_count'] == 2449
    one = tools_sql.scan_summary(ToolContext(files_db=files_db), scan_id=scan_id)
    assert one['top_extensions'] and one['top_extensions'][0]['files'] > 0
    assert one['hosts'] and one['hosts'][0].startswith('local:')


def test_profile_tools_say_not_profiled_yet(demo_index):
    files_db, _ = demo_index
    for name, args in [('list_collections', {}), ('get_collection', {'id': 'x'}),
                       ('search_datasets', {'query': 'wk9'}), ('unclaimed_summary', {})]:
        assert run_tool(name, args, ToolContext(files_db=files_db)) == REFUSAL


def test_search_datasets_caps_at_50_and_reports_total(demo_index):
    files_db, scan_id = demo_index
    with sqlite3.connect(files_db) as conn:  # the spec's Pass 3 table, as Profile will write it
        conn.execute("CREATE TABLE data_objects (id TEXT PRIMARY KEY, pattern_name TEXT, root_path TEXT,"
                     " scan_id TEXT, status TEXT, confidence REAL, file_count INTEGER, total_bytes INTEGER,"
                     " sentinel_path TEXT, metadata_json TEXT, created_at REAL, updated_at REAL)")
        conn.executemany("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, status, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?,?)",
                         [(f'obj{i}', 'bruker_microct', f'/d/wk9_{i}_Rec', scan_id, 'candidate', i, i) for i in range(60)])
    from scidk.agent_tools import tools_sql
    out = tools_sql.search_datasets(ToolContext(files_db=files_db), profile='bruker_microct', owner='Anderson')
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
    mcp = {t['name'] for t in mcp_server.ScidkMcpServer().tool_definitions()}
    # Static catalog membership no longer grants runtime tool discovery.
    assert http == funcs == openapi == mcp == set()
    assert spec['openapi'] == '3.1.0'


def test_http_adapter_runs_a_tool(client):
    out = client.post('/api/agent/tools/scan_summary', json={}).get_json()
    assert out == REFUSAL
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
    assert out == REFUSAL
    refused = client.post('/api/agent/tools/query_knowledge_graph',
                          json={'cypher': 'MATCH (s:Subject) RETURN s.ear_tag'}).get_json()
    assert refused['status'] == 'refused'


# Graph adapter authorization is now tested offline with forbidden-execution
# spies in tests/security; never load a real graph just to verify a refusal.
