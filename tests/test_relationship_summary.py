"""Knowledge -> Relationships performance: a narrow primary-only summary, cached, with details on demand."""
import json
import pathlib
import re
import shutil
import subprocess
import threading
import time

import pytest

from scidk.services import relationship_summary as rs

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINKS_JS = ROOT / 'scidk' / 'ui' / 'static' / 'js' / 'links'

ROWS = [
    {'source_label': 'Sample', 'rel_type': 'DERIVED_FROM', 'target_label': 'Sample', 'edge_count': 40},
    {'source_label': 'Sample', 'rel_type': 'DERIVED_FROM', 'target_label': 'SampleType', 'edge_count': 2},
    {'source_label': 'Run', 'rel_type': 'HAS_INPUT', 'target_label': 'Sample', 'edge_count': 7},
    {'source_label': None, 'rel_type': 'HAS_INPUT', 'target_label': 'Sample', 'edge_count': 99},   # unlabelled endpoint
    {'source_label': 'Run', 'rel_type': 'HAS_INPUT', 'target_label': None, 'edge_count': 99},
]


@pytest.fixture(autouse=True)
def clean_cache():
    rs.invalidate()
    yield
    rs.invalidate()


class Counter:
    def __init__(self, rows=ROWS, delay=0.0, fail=False):
        self.rows, self.delay, self.fail, self.calls = rows, delay, fail, 0

    def __call__(self):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError('graph unavailable')
        return self.rows


# ---- the summary itself ----

def test_summary_has_only_what_the_catalog_needs():
    summary = rs.build_summary(ROWS)
    assert summary['type_count'] == 2 and summary['pattern_count'] == 3 and summary['total_edges'] == 49
    derived = summary['types'][0]
    assert derived['rel_type'] == 'DERIVED_FROM' and derived['edge_count'] == 42   # largest first
    assert derived['sources'] == [{'label': 'Sample', 'edge_count': 42}]
    assert derived['targets'] == [{'label': 'Sample', 'edge_count': 40}, {'label': 'SampleType', 'edge_count': 2}]
    assert derived['patterns'] == [{'source_label': 'Sample', 'target_label': 'Sample', 'edge_count': 40},
                                   {'source_label': 'Sample', 'target_label': 'SampleType', 'edge_count': 2}]
    # unlabelled endpoints are not attributed to any label
    assert summary['types'][1] == {'rel_type': 'HAS_INPUT', 'edge_count': 7, 'sources': [{'label': 'Run', 'edge_count': 7}],
                                   'targets': [{'label': 'Sample', 'edge_count': 7}],
                                   'patterns': [{'source_label': 'Run', 'target_label': 'Sample', 'edge_count': 7}]}
    # no per-edge rows, ids or properties: examples are fetched on demand
    assert set(derived) == {'rel_type', 'edge_count', 'sources', 'targets', 'patterns'}


def test_summary_query_is_one_read_only_aggregation_without_edge_detail():
    query = rs.SUMMARY_QUERY
    assert query.startswith('MATCH (a)-[r]->(b) RETURN') and 'count(*)' in query and query.count('MATCH') == 1
    for forbidden in ('MERGE', 'CREATE', 'SET ', 'DELETE', 'REMOVE', 'LIMIT', 'properties(', 'id(', 'elementId', 'a.', 'b.'):
        assert forbidden not in query, forbidden


def test_summary_scope_is_the_primary_graph_only(monkeypatch):
    """No external profile is listed, connected to or queried, even if some are configured."""
    from scidk.services import neo4j_client
    queried = []

    class Primary:
        def execute_read(self, query, parameters=None):
            queried.append(query)
            return ROWS

        def close(self):
            queried.append('closed')

    def boom(*args, **kwargs):
        raise AssertionError('external profiles must not be touched')

    monkeypatch.setattr(neo4j_client, 'get_neo4j_client', lambda role=None: Primary())
    monkeypatch.setattr(neo4j_client, 'get_neo4j_client_for_profile', boom)
    monkeypatch.setattr(neo4j_client, 'list_neo4j_profiles', boom)
    summary = rs.get_summary()
    assert queried == [rs.SUMMARY_QUERY, 'closed'] and summary['scope'] == 'primary' and summary['total_edges'] == 49


def test_a_profile_pointing_at_the_primary_graph_cannot_double_the_counts():
    """The legacy discovery summed the primary scan with a same-database profile scan; the summary cannot."""
    assert rs.get_summary(query=Counter())['total_edges'] == 49
    source = (ROOT / 'scidk' / 'services' / 'relationship_summary.py').read_text()
    assert 'list_neo4j_profiles' not in source and 'for_profile' not in source


# ---- cache and refresh ----

def test_second_request_is_served_from_the_cache():
    query = Counter()
    first = rs.get_summary(query=query)
    second = rs.get_summary(query=query)
    assert query.calls == 1
    assert first['cached'] is False and second['cached'] is True
    assert first['types'] == second['types'] and second['generated_at'] == first['generated_at']
    assert 'age_seconds' in second and second['ttl_seconds'] == rs.TTL_SECONDS and first['elapsed_ms'] >= 0


def test_refresh_bypasses_the_cache_and_replaces_it():
    query = Counter()
    rs.get_summary(query=query)
    query.rows = ROWS[:1]
    refreshed = rs.get_summary(query=query, refresh=True)
    assert query.calls == 2 and refreshed['cached'] is False and refreshed['total_edges'] == 40
    after = rs.get_summary(query=query)
    assert query.calls == 2 and after['cached'] is True and after['total_edges'] == 40


def test_cache_expires_after_the_ttl():
    now = [1000.0]
    query = Counter()
    rs.get_summary(query=query, ttl=60, clock=lambda: now[0])
    now[0] += 59
    assert rs.get_summary(query=query, ttl=60, clock=lambda: now[0])['cached'] is True
    now[0] += 2
    assert rs.get_summary(query=query, ttl=60, clock=lambda: now[0])['cached'] is False
    assert query.calls == 2


def test_failures_are_not_cached_and_do_not_poison_later_requests():
    with pytest.raises(RuntimeError):
        rs.get_summary(query=Counter(fail=True))
    good = Counter()
    assert rs.get_summary(query=good)['cached'] is False and good.calls == 1


def test_invalidate_forces_the_next_request_to_query():
    query = Counter()
    rs.get_summary(query=query)
    rs.invalidate()
    assert rs.get_summary(query=query)['cached'] is False and query.calls == 2


def test_concurrent_requests_share_one_query():
    query = Counter(delay=0.2)
    results = []
    threads = [threading.Thread(target=lambda: results.append(rs.get_summary(query=query))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert query.calls == 1 and len(results) == 4 and sorted(r['cached'] for r in results) == [False, True, True, True]


def test_a_refresh_that_arrives_during_another_refresh_reuses_its_result():
    query = Counter(delay=0.2)
    out = []
    threads = [threading.Thread(target=lambda: out.append(rs.get_summary(query=query, refresh=True))) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert query.calls == 1


# ---- endpoint ----

@pytest.fixture
def api(client, monkeypatch):
    # The management APIs are gated by graph_management_policy; open its existing full-access switch.
    monkeypatch.setattr('scidk.agent_tools.security.FULL_ACCESS', True)
    return client


@pytest.fixture
def gui_client(monkeypatch):
    from tests.gui.harness import make_gui_app
    monkeypatch.setattr('scidk.agent_tools.security.FULL_ACCESS', True)
    app = make_gui_app()
    app.config['SCIDK_GUI_V3_ENABLED'] = True
    return app.test_client()


def test_endpoint_returns_the_summary_cached_then_refreshed(api, monkeypatch):
    client = api
    query = Counter()
    monkeypatch.setattr(rs, '_query_primary', query)
    first = client.get('/api/links/graph-summary').get_json()
    second = client.get('/api/links/graph-summary').get_json()
    assert first['status'] == 'success' and first['scope'] == 'primary' and first['cached'] is False
    assert second['cached'] is True and query.calls == 1
    assert [t['rel_type'] for t in first['types']] == ['DERIVED_FROM', 'HAS_INPUT'] and first['total_edges'] == 49
    for flag in ('1', 'true', 'yes'):
        assert client.get('/api/links/graph-summary?refresh=' + flag).get_json()['cached'] is False
    assert query.calls == 4
    assert client.get('/api/links/graph-summary?refresh=0').get_json()['cached'] is True


def test_endpoint_reports_errors_without_caching_them(api, monkeypatch):
    client = api
    monkeypatch.setattr(rs, '_query_primary', Counter(fail=True))
    response = client.get('/api/links/graph-summary')
    assert response.status_code == 500 and response.get_json()['status'] == 'error'
    monkeypatch.setattr(rs, '_query_primary', Counter())
    assert client.get('/api/links/graph-summary').get_json()['cached'] is False


def test_endpoint_is_gated_like_the_other_links_apis(client, monkeypatch):
    queried = Counter()
    monkeypatch.setattr(rs, '_query_primary', queried)
    assert client.get('/api/links/discovered').status_code == 403
    assert client.get('/api/links/graph-summary').status_code == 403
    assert queried.calls == 0


def test_a_successful_links_write_invalidates_the_cache_but_reads_and_failures_do_not():
    from flask import Flask
    from scidk.web.routes import api_links

    def after(method, status):
        rs.get_summary(query=Counter())
        app = Flask(__name__)
        with app.test_request_context('/api/links/x', method=method):
            class R:
                status_code = status
            api_links._invalidate_relationship_summary_after_write(R())
        return rs.get_summary(query=Counter())['cached']

    assert after('GET', 200) is True
    assert after('POST', 400) is True
    assert after('POST', 500) is True
    assert after('POST', 200) is False
    assert after('DELETE', 200) is False


def test_legacy_discovery_endpoint_is_unchanged_for_legacy_pages():
    source = (ROOT / 'scidk' / 'web' / 'routes' / 'api_links.py').read_text()
    assert "@bp.route('/links/discovered', methods=['GET'])" in source
    assert 'include_primary=True' in source and 'promote_to_active=False' in source
    core = (LINKS_JS / 'links-core.js').read_text()
    assert "'/api/links/discovered'" in core   # legacy pages still use it


# ---- page script: cached render, quiet refresh, Refresh bypass, details on demand ----

CATALOG_HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const scenario = JSON.parse(process.argv[1]);
const events = [];
const store = Object.assign({}, scenario.storage || {});
const el = {textContent: '', innerHTML: '', style: {}};
const ctx = {
  console: {log() {}, warn() {}}, discoveredRelationships: [], discoveryState: 'loading', currentFilter: 'active',
  linkDefinitions: [], linksNavState: {searchQuery: '', sourceLabel: '', targetLabel: '', relType: '', sortBy: 'name'},
  escapeHtml: s => String(s), highlightMatch: s => s,
  renderLinkList: () => events.push('render:' + ctx.discoveryState + ':' + ctx.discoveredRelationships.length),
  populateFilterDropdowns: () => events.push('dropdowns'),
  updateResultCount() {},
  window: {SCIDK_BASE: '/base', LINKS_KNOWLEDGE_MODE: true,
    sessionStorage: {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; events.push('store'); }}},
  document: {getElementById: id => id === 'kr-freshness' ? el : {textContent: '', innerHTML: '', style: {}},
             querySelectorAll: () => []},
  fetch: async (url) => {
    events.push('fetch:' + url);
    if (scenario.fail) throw new Error('network down');
    return {ok: true, json: async () => scenario.response};
  },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
(async () => {
  for (const refresh of scenario.loads) await vm.runInContext('loadKnowledgeSummary(' + refresh + ')', ctx);
  console.log(JSON.stringify({events, freshness: el.textContent, state: ctx.discoveryState, rows: ctx.discoveredRelationships, store}));
})();
"""

SUMMARY = {'status': 'success', 'cached': False, 'age_seconds': 0, 'generated_at': 1700000000,
           'types': [{'rel_type': 'DERIVED_FROM', 'edge_count': 42, 'patterns': [
               {'source_label': 'Sample', 'target_label': 'Sample', 'edge_count': 40},
               {'source_label': 'Sample', 'target_label': 'SampleType', 'edge_count': 2}]}]}
KEY = 'scidk.relationships.summary:/base'


def stored(summary=SUMMARY, age_ms=1000):
    return {KEY: json.dumps({'types': summary['types'], 'generated_at': 1, 'saved_at': int(time.time() * 1000) - age_ms})}


def run_catalog(**scenario):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required to execute the Relationships scripts')
    scenario.setdefault('loads', ['false'])
    scenario.setdefault('response', SUMMARY)
    out = subprocess.run([node, '-e', CATALOG_HARNESS, '--', json.dumps(scenario), str(LINKS_JS / 'links-discovery.js')],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def fetches(result):
    return [e[len('fetch:'):] for e in result['events'] if e.startswith('fetch:')]


def test_cold_load_shows_discovering_then_one_summary_request_and_no_detail_queries():
    result = run_catalog()
    assert result['events'][0] == 'render:loading:0'                       # "Discovering relationships..." first
    assert fetches(result) == ['/base/api/links/graph-summary']             # one narrow request, no refresh flag
    assert result['state'] == 'ready' and len(result['rows']) == 2
    assert all(r['database'] == 'PRIMARY' for r in result['rows'])
    assert not any('neo4j/query' in f or 'discovered' in f for f in fetches(result))   # details come later, on demand
    assert json.loads(result['store'][KEY])['types'] == SUMMARY['types']      # remembered for this session
    assert result['freshness'].startswith('Updated ')


def test_rows_keep_the_exact_pattern_counts_from_the_summary():
    rows = run_catalog()['rows']
    assert [(r['source_label'], r['rel_type'], r['target_label'], r['triple_count']) for r in rows] == [
        ('Sample', 'DERIVED_FROM', 'Sample', 40), ('Sample', 'DERIVED_FROM', 'SampleType', 2)]


def test_recent_session_copy_renders_immediately_then_refreshes_quietly():
    result = run_catalog(storage=stored())
    events = [e for e in result['events'] if e != 'dropdowns']
    assert events[0] == 'render:ready:2'                                    # cached list drawn before any request
    assert events.index('render:ready:2') < events.index('fetch:/base/api/links/graph-summary')
    assert 'render:loading:0' not in events
    assert events.count('render:ready:2') == 1                              # unchanged background result: no redraw
    assert fetches(result) == ['/base/api/links/graph-summary']             # the quiet refresh does not force a re-query
    assert result['freshness'].startswith('Updated ')


def test_changed_background_result_redraws_the_list():
    newer = json.loads(json.dumps(SUMMARY))
    newer['types'][0]['patterns'][0]['edge_count'] = 41
    result = run_catalog(storage=stored(), response=newer)
    assert result['events'].count('render:ready:2') == 2
    assert [r['triple_count'] for r in result['rows']] == [41, 2]


def test_stale_session_copy_is_not_used():
    result = run_catalog(storage=stored(age_ms=60 * 60 * 1000))
    assert result['events'][0] == 'render:loading:0'


def test_failed_background_refresh_keeps_the_cached_list():
    result = run_catalog(storage=stored(), fail=True)
    assert result['state'] == 'ready' and len(result['rows']) == 2
    assert 'could not update' in result['freshness'] and 'render:ready:0' not in result['events']


def test_failed_cold_load_shows_the_error_state_not_an_empty_list():
    result = run_catalog(fail=True)
    assert result['state'] == 'error' and result['rows'] == []


def test_refresh_button_bypasses_both_caches():
    result = run_catalog(storage=stored(), loads=['true'])
    assert fetches(result) == ['/base/api/links/graph-summary?refresh=1']
    assert result['events'][0] == 'render:loading:0'                        # explicit refresh shows the loading state
    assert 'render:ready:2' in result['events']


def test_corrupt_session_storage_is_ignored():
    result = run_catalog(storage={KEY: '{not json'})
    assert result['events'][0] == 'render:loading:0' and result['state'] == 'ready'


def test_core_routes_knowledge_loads_to_the_summary_and_refresh_passes_the_flag():
    core = (LINKS_JS / 'links-core.js').read_text()
    assert re.search(r'function loadDiscoveredRelationships\(refresh\) \{\s*//[^\n]*\n\s*if \(isKnowledgeMode\(\)\) return loadKnowledgeSummary\(!!refresh\);', core)
    assert 'await loadDiscoveredRelationships(true);' in core
    discovery = (LINKS_JS / 'links-discovery.js').read_text()
    catalog = discovery[discovery.index('function loadKnowledgeSummary'):discovery.index('// Shown whenever nothing is selected')]
    assert '/api/links/graph-summary' in catalog and '/api/links/discovered' not in catalog and 'neo4j/query' not in catalog


def test_knowledge_page_has_a_freshness_note_and_legacy_pages_keep_their_markup(gui_client):
    client = gui_client
    knowledge = client.get('/knowledge?view=relationships').get_data(as_text=True)
    assert 'data-testid="relationships-freshness"' in knowledge
    legacy = client.get('/entities?tab=relationships').get_data(as_text=True)
    assert 'relationships-freshness' not in legacy and 'LINKS_KNOWLEDGE_MODE' not in legacy
    assert 'data-filter="available"' in legacy
