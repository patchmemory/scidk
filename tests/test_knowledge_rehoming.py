"""Knowledge re-homes the working Labels browser and Maps application (UI only, no new backend)."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

LEGACY_LINKS = ['Entities &amp; Labels', 'Properties', 'Relationships &amp; Links', 'Maps &amp; saved views',
                'Governed records']


@pytest.fixture
def gui_app():
    from tests.gui.harness import make_gui_app
    app = make_gui_app()
    app.config['SCIDK_GUI_V3_ENABLED'] = True
    return app


@pytest.fixture
def client(gui_app, monkeypatch):
    # The management pages are gated by graph_management_policy; open its existing full-access switch.
    monkeypatch.setattr('scidk.agent_tools.security.FULL_ACCESS', True)
    return gui_app.test_client()


def test_embedded_views_are_denied_exactly_like_the_direct_pages(gui_app):
    client = gui_app.test_client()
    for url in ('/entities', '/entities?tab=relationships', '/map', '/knowledge?view=entities',
                '/knowledge?view=relationships', '/knowledge?view=maps', '/knowledge?view=graph'):
        assert client.get(url).status_code == 403, url
    for url in ('/knowledge?view=sketch', '/knowledge?view=governed'):
        assert client.get(url).status_code == 200, url


def page(client, url):
    response = client.get(url)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


def tabs(html):
    nav = re.search(r'<nav class="knowledge-tabs".*?</nav>', html, re.S).group(0)
    return re.findall(r'<a\b[^>]*>([^<]*)</a>', nav)


def test_entities_view_renders_the_real_labels_browser(client):
    html = page(client, '/knowledge?view=entities')
    assert 'id="label-list"' in html or 'labels-container' in html
    assert 'btn-pull-instances' in html and 'instance-table-container' in html
    assert 'entities-selection-actions' in html
    assert 'Search authorized Research entities' not in html
    assert 'kw-entities-pane' not in html


def test_default_knowledge_view_is_entities(client):
    assert 'btn-pull-instances' in page(client, '/knowledge')


def test_maps_view_renders_the_real_maps_application(client):
    html = page(client, '/knowledge?view=maps')
    for needle in ('map-library-panel', 'map-workspace-panel', 'save-current-map', 'add-tab-btn', 'Query Editor'):
        assert needle in html, needle
    assert '.maps-container' in html
    assert 'kw-graph' not in html


def test_graph_is_a_compatibility_alias_for_maps(client):
    html = page(client, '/knowledge?view=graph')
    assert 'map-library-panel' in html
    assert re.search(r'aria-current="page"[^>]*>Maps<|data-testid="knowledge-tab-maps" aria-current="page"', html)
    assert 'Graph' not in tabs(html)


FOUR_TABS = ['Entities', 'Relationships', 'Maps', 'Sketch']


def test_tabs_are_exactly_entities_relationships_maps_sketch(client):
    for view in ('entities', 'relationships', 'maps', 'sketch', 'graph', 'links'):
        assert tabs(page(client, f'/knowledge?view={view}')) == FOUR_TABS, view
    html = page(client, '/knowledge?view=relationships')
    assert 'href="/knowledge?view=relationships" data-testid="knowledge-tab-relationships" aria-current="page"' in html
    for key in ('entities', 'maps', 'sketch'):
        assert f'href="/knowledge?view={key}" data-testid="knowledge-tab-{key}">' in html


def test_relationships_view_renders_the_real_relationship_browser(client):
    html = page(client, '/knowledge?view=relationships')
    for needle in ('links-container', 'id="links-list"', 'id="link-list"', 'link-type-dropdown-btn', 'links-search',
                   'filter-rel-type', 'id="link-wizard"', 'btn-refresh-all', 'btn-execute', 'loadLinksPage',
                   'id="kr-panel"'):
        assert needle in html, needle
    legacy = page(client, '/entities?tab=relationships')
    for needle in ('links-container', 'group-by-toggle', 'data-filter="active"', 'data-filter="pending"',
                   'data-filter="available"', 'btn-save-def', 'btn-execute'):
        assert needle in legacy, needle
    for script in ('links-core.js', 'links-wizard.js', 'links-index.js', 'links-discovery.js', 'links-active.js',
                   'links-import.js'):
        assert f'js/links/{script}' in html, script
    assert 'iframe' not in html
    assert 'btn-pull-instances' not in html and 'map-library-panel' not in html and 'kw-sketch' not in html
    assert 'id="management-connection"' in html and 'id="knowledge-return-slot"' in html


def test_relationships_view_shares_one_implementation_with_the_legacy_page(client):
    knowledge, direct = page(client, '/knowledge?view=relationships'), page(client, '/entities?tab=relationships')
    def app_markup(html):
        start = html.index('<div class="links-container"')
        return html[start:html.index('document.addEventListener(\'DOMContentLoaded\', loadLinksPage);')]
    # One shared partial: Knowledge is a mode of it, not a copy.
    assert 'data-links-mode="knowledge"' in app_markup(knowledge) and 'data-links-mode' not in app_markup(direct)
    for html in (knowledge, direct):
        for script in ('links-core.js', 'links-discovery.js', 'links-import.js'):
            assert html.count(f'js/links/{script}') == 1
        assert html.count('id="links-list"') == 1
    templates = pathlib.Path(__file__).resolve().parents[1] / 'scidk' / 'ui' / 'templates'
    assert "{% include '_links_app.html' %}" in (templates / 'links.html').read_text()
    assert "{% include '_links_app.html' %}" in (templates / 'gui' / 'knowledge.html').read_text()


def test_relationships_browse_and_detail_interactions_are_wired(client):
    """The same browse/detail hooks the legacy page uses: type filter, grouping, tabs, detail wizard, APIs."""
    html = page(client, '/knowledge?view=relationships')
    for needle in ('id="filter-source-label"', 'id="filter-target-label"', 'sort-links', 'id="source-node-btn"',
                   'id="relationship-node-btn"', 'id="target-node-btn"', 'id="preview-container"',
                   'toggle-advanced-filters', 'relationship-detail-panel'):
        assert needle in html, needle
    assert 'id="btn-save-def"' in page(client, '/entities?tab=relationships')
    core = client.get('/static/js/links/links-core.js').get_data(as_text=True)
    assert 'function loadLinksPage' in core and '/api/links' in core
    assert client.get('/static/js/links/links-active.js').status_code == 200


def test_relationship_browse_apis_stay_on_existing_routes(client):
    for url in ('/api/links', '/api/schema/relationship-types'):
        assert client.get(url).status_code in (200, 404, 500, 503), url
    assert '/api/knowledge/relationships' not in page(client, '/knowledge?view=relationships')


def test_relationships_cross_links_stay_inside_knowledge(client):
    html = page(client, '/knowledge?view=relationships')
    assert 'href="/knowledge?view=maps" data-testid="relationships-to-maps"' in html
    assert 'href="/knowledge?view=entities"' in html
    context = re.search(r'<p[^>]*data-testid="relationships-context">.*?</p>', html, re.S).group(0)
    assert '/map' not in context.replace('view=maps', '') and '/entities' not in context
    entities = page(client, '/knowledge?view=entities')
    assert 'data-testid="knowledge-tab-relationships"' in entities
    assert 'href="/knowledge?view=relationships"' in entities


def test_links_alias_resolves_to_relationships(client):
    assert 'id="links-list"' in page(client, '/knowledge?view=links')
    assert page(client, '/knowledge?view=relationship').count('id="links-list"') == 1


def test_legacy_top_links_are_absent_from_knowledge(client):
    for view in ('entities', 'relationships', 'maps', 'sketch'):
        html = page(client, f'/knowledge?view={view}')
        assert '<nav class="kw-toolbar" aria-label="Research tools"' not in html
        assert 'data-testid="entities-tabs"' not in html and 'class="entities-tabs"' not in html
        for text in LEGACY_LINKS:
            assert f'>{text}</a>' not in html, (view, text)


def test_sketch_keeps_the_canvas_and_drops_governance_copy(client):
    html = page(client, '/knowledge?view=sketch')
    assert 'Sketch ideas and proposed schema changes before adding them to the knowledge graph.' in html
    for needle in ('id="kw-sketch"', 'kw-place-node', 'kw-connect', 'knowledge_workspace.js'):
        assert needle in html, needle
    assert 'data-kw-mode="sketch"' in html
    for banned in ('Unavailable:', 'Submit proposal', 'Commit to graph', 'Investigate', 'Human Research access',
                   'authorized Research entities', 'btn-pull-instances', 'map-library-panel'):
        assert banned not in html, banned


def test_annotations_deep_link_falls_back_visibly(client):
    html = page(client, '/knowledge?view=entities&panel=annotations')
    assert 'data-testid="annotations-fallback"' in html
    assert '/datasets?view=browse&amp;panel=annotations' in html
    assert 'annotations-fallback' not in page(client, '/knowledge?view=entities')


def test_advanced_schema_disclosure_is_not_a_relationships_entry_point(client):
    html = page(client, '/knowledge?view=entities')
    disclosure = re.search(r'<details[^>]*advanced-schema-tools.*?</details>', html, re.S).group(0)
    assert 'Relationship definitions (legacy page)' not in disclosure
    assert 'Relationships have their own tab' in disclosure
    assert 'href="/entities?tab=relationships">Relationships (legacy page)</a>' in disclosure  # direct legacy tool kept
    assert client.get('/entities?tab=relationships').status_code == 200


def test_governed_workspace_remains_reachable_for_deep_links(client):
    for url in ('/knowledge?view=governed', '/knowledge?governed=1&domain=research&view=graph',
                '/knowledge?domain=research&id=x'):
        html = page(client, url)
        assert 'kw-graph-pane' in html and 'kw-tab-graph' in html, url


def test_direct_legacy_routes_still_work(client):
    labels = page(client, '/entities')
    assert 'btn-pull-instances' in labels and 'data-testid="entities-tabs"' in labels
    rel = page(client, '/entities?tab=relationships')
    assert 'data-testid="entities-tabs"' in rel and 'id="links-list"' in rel and '<h1>Links</h1>' in rel
    assert 'knowledge-tabs' not in rel
    for legacy in ('/links', '/integrate'):
        response = client.get(legacy)
        assert response.status_code == 302 and response.headers['Location'].endswith('/entities?tab=relationships'), legacy
    maps = page(client, '/map')
    assert 'map-library-panel' in maps and 'Query Editor' in maps
    assert client.get('/labels').status_code == 302


def test_legacy_pages_and_knowledge_share_one_implementation(client):
    """Same partial on both routes: the application markup is not duplicated."""
    knowledge, direct = page(client, '/knowledge?view=entities'), page(client, '/entities')
    marker = re.search(r'<script>\s*let currentLabel = null;', direct)
    assert marker and re.search(r'<script>\s*let currentLabel = null;', knowledge)
    assert 'iframe' not in knowledge


def test_policy_gates_embedded_views_like_direct_pages():
    from tests.gui.harness import make_gui_app
    from scidk.services.graph_management_policy import knowledge_view, management_page
    assert knowledge_view({'view': 'graph'}) == 'maps'
    assert knowledge_view({'view': 'relationships'}) == 'relationships'
    assert knowledge_view({'view': 'links'}) == 'relationships'
    assert knowledge_view({}) == 'entities'
    assert knowledge_view({'domain': 'research'}) == 'governed'
    assert knowledge_view({'view': 'bogus'}) == 'entities'
    app = make_gui_app()
    for url, expected in (('/knowledge?view=entities', True), ('/knowledge?view=graph', True),
                          ('/knowledge?view=maps', True), ('/knowledge?view=relationships', True),
                          ('/knowledge?view=sketch', False),
                          ('/knowledge?view=governed', False), ('/overview', False)):
        with app.test_request_context(url):
            assert management_page() is expected, url


def test_cross_links_stay_inside_knowledge_and_legacy_links_are_unchanged(client):
    """Open in Graph / Return to entity inspector keep the user in Knowledge; /entities and /map are as before."""
    k_entities, k_maps = page(client, '/knowledge?view=entities'), page(client, '/knowledge?view=maps')
    assert '/knowledge?view=maps&management_label=' in k_entities
    assert '/knowledge?view=entities&management_label=' in k_maps
    assert '/map?management_label=' in page(client, '/entities')
    assert '/entities?tab=entities&management_label=' in page(client, '/map')
    assert '/map?management_label=' not in k_entities


def test_return_to_inspector_link_has_a_host_in_knowledge_and_legacy_maps(client):
    """The Maps script appends the return link to a host element; each page must provide one."""
    k_maps, legacy_map = page(client, '/knowledge?view=maps'), page(client, '/map')
    assert 'id="knowledge-return-slot"' in k_maps and "getElementById('knowledge-return-slot')" in k_maps
    assert '<nav class="kw-toolbar" aria-label="Research tools"' in legacy_map
    assert '<nav class="kw-toolbar" aria-label="Research tools"' not in k_maps
    assert tabs(k_maps) == FOUR_TABS


# ---- Relationships → Active is graph-derived (no saved link definitions needed) ----

import json
import pathlib
import shutil
import subprocess

LINKS_JS = pathlib.Path(__file__).resolve().parents[1] / 'scidk' / 'ui' / 'static' / 'js' / 'links'

# Loads the real links-discovery.js in a bare VM with the globals links-core.js would supply, then drives
# the real Active renderer. `linkDefinitions` is always empty: nothing may depend on saved definitions.
ACTIVE_HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const triples = JSON.parse(process.argv[2]);
const state = process.argv[3];
const ctx = {
  console, discoveredRelationships: triples, discoveryState: state, linkDefinitions: [], currentFilter: 'active',
  linksNavState: {searchQuery: '', sourceLabel: '', targetLabel: '', relType: '', sortBy: 'name', groupByRelType: false},
  escapeHtml: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  highlightMatch: s => s, opened: [], counts: [],
  updateResultCount: (a, b, n) => ctx.counts.push([a, b, n]),
  openImportWizardForRelationship: rel => ctx.opened.push(rel),
  renderFlatLinks: () => {},
  document: {getElementById: () => ({style: {}})},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const handlers = [];
const container = {innerHTML: '', querySelector: () => null,
  querySelectorAll: sel => sel === '.btn-view-active-type' ? [{dataset: {typeIndex: '0'}, addEventListener: (e, f) => handlers.push(f)}] : []};
vm.runInContext('renderActiveRelationshipTypes', ctx)(container);
handlers.forEach(h => h({stopPropagation() {}}));
console.log(JSON.stringify({html: container.innerHTML, types: ctx.graphRelationshipTypes().map(t => ({
  rel_type: t.rel_type, edges: t.edge_count, sources: [...t.sources.keys()].sort(), targets: [...t.targets.keys()].sort(),
  patterns: t.triples.length})), opened: ctx.opened, counts: ctx.counts}));
"""

GRAPH_TRIPLES = [
    {'source_label': 'Sample', 'rel_type': 'DERIVED_FROM', 'target_label': 'Sample', 'triple_count': 40, 'database': 'PRIMARY'},
    {'source_label': 'Sample', 'rel_type': 'DERIVED_FROM', 'target_label': 'SampleType', 'triple_count': 2, 'database': 'PRIMARY'},
    {'source_label': 'Assay', 'rel_type': 'HAS_INPUT', 'target_label': 'Sample', 'triple_count': 7, 'database': 'PRIMARY'},
    {'source_label': 'Other', 'rel_type': 'EXTERNAL_ONLY', 'target_label': 'Other', 'triple_count': 9, 'database': 'SomeProfile'},
]


def run_active(triples, state='ready'):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required to execute the Relationships scripts')
    out = subprocess.run([node, '-e', ACTIVE_HARNESS, '--', str(LINKS_JS / 'links-discovery.js'),
                          json.dumps(triples), state], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def test_active_lists_graph_relationship_types_with_no_saved_definitions():
    result = run_active(GRAPH_TRIPLES)
    by_type = {t['rel_type']: t for t in result['types']}
    assert sorted(by_type) == ['DERIVED_FROM', 'HAS_INPUT']  # only the current (primary) graph
    assert by_type['DERIVED_FROM'] == {'rel_type': 'DERIVED_FROM', 'edges': 42, 'sources': ['Sample'],
                                       'targets': ['Sample', 'SampleType'], 'patterns': 2}
    assert by_type['HAS_INPUT']['edges'] == 7 and by_type['HAS_INPUT']['sources'] == ['Assay']
    html = result['html']
    assert html.count('data-testid="active-relationship-type"') == 2
    assert 'data-rel-type="DERIVED_FROM"' in html and 'data-rel-type="HAS_INPUT"' in html
    assert '42 edges' in html and '7 edges' in html
    assert 'data-testid="active-sources"' in html and 'data-testid="active-targets"' in html
    assert 'SampleType' in html and 'Assay' in html
    assert 'btn-view-active-type' in html and 'View Details' in html
    assert 'EXTERNAL_ONLY' not in html
    assert 'No link definitions' not in html and 'saved-definitions' not in html
    assert result['counts'] == [[2, 2, 'relationship type']]


def test_active_view_details_opens_the_dominant_discovered_pattern():
    opened = run_active(GRAPH_TRIPLES)['opened']
    assert opened and opened[0]['rel_type'] == 'DERIVED_FROM'
    assert (opened[0]['source_label'], opened[0]['target_label'], opened[0]['triple_count']) == ('Sample', 'Sample', 40)


def test_active_shows_discovering_while_loading_not_an_empty_state():
    html = run_active([], state='loading')['html']
    assert 'Discovering relationships' in html and 'data-testid="active-discovering"' in html
    assert 'No link definitions' not in html and 'No active links' not in html and 'No relationships found' not in html


def test_active_reports_an_empty_graph_and_a_failed_discovery_distinctly():
    assert 'No relationships found in the current graph.' in run_active([], state='ready')['html']
    failed = run_active([], state='error')['html']
    assert 'Could not discover relationships' in failed and 'Discovering relationships' not in failed


def test_active_tab_is_wired_to_graph_discovery_not_saved_definitions(client):
    html = page(client, '/knowledge?view=relationships')
    assert 'data-testid="active-discovering"' in html and 'Discovering relationships' in html
    assert 'No link definitions' not in html
    core = (LINKS_JS / 'links-core.js').read_text()
    assert "let discoveryState = 'loading'" in core
    branch = core[core.index("if (currentFilter === 'active') {\n    renderActiveRelationshipTypes"):]
    assert branch.index('renderActiveRelationshipTypes(container)') < branch.index('linkDefinitions.filter')
    discovery = (LINKS_JS / 'links-discovery.js').read_text()
    assert 'function graphRelationshipTypes' in discovery and 'discoveredRelationships.forEach' in discovery
    assert "'/api/links/discovered'" in core  # the existing read-only discovery API; no new endpoint
    assert '/api/knowledge/relationships' not in html and '/api/links/active-types' not in core


def test_legacy_relationships_page_shares_the_graph_derived_active_list(client):
    legacy = page(client, '/entities?tab=relationships')
    assert 'data-testid="active-discovering"' in legacy and 'js/links/links-discovery.js' in legacy


# ---- Knowledge → Relationships is a simplified, graph-first, read-only-first viewer ----

LEGACY_WORKFLOW_MARKUP = ('data-filter="pending"', 'data-filter="available"', 'btn-save-def', 'btn-export-csv',
                          'btn-import-csv', 'btn-delete-def', 'Save Definition', 'Export CSV', 'Import Validated CSV',
                          '+ New Link', 'Script Link', 'Import from Graph', 'link-type-dropdown-menu', 'group-by-toggle',
                          'Group by Relationship Type', 'Definitions</h3>')


def test_knowledge_relationships_is_one_graph_browser_without_legacy_workflow_controls(client):
    html = page(client, '/knowledge?view=relationships')
    for needle in LEGACY_WORKFLOW_MARKUP:
        assert needle not in html, needle
    assert 'link-filter-tab ' not in html and 'Pending (' not in html and 'Available (' not in html
    assert 'data-testid="relationships-heading"' in html and 'Relationships in graph (' in html
    assert 'window.LINKS_KNOWLEDGE_MODE = true' in html
    assert 'data-testid="link-builder-btn"' in html and '+ Link builder' in html
    for needle in ('id="links-search"', 'id="filter-source-label"', 'id="filter-target-label"', 'id="filter-rel-type"',
                   'btn-refresh-all', 'id="kr-panel"', 'data-testid="active-discovering"'):
        assert needle in html, needle
    # the builder can still execute a link; it just isn't a governance/import surface
    assert 'btn-execute' in html


def test_direct_legacy_pages_keep_their_workflow_controls(client):
    for url in ('/entities?tab=relationships', '/links'):
        response = client.get(url, follow_redirects=True)
        assert response.status_code == 200, url
        html = response.get_data(as_text=True)
        for needle in ('data-filter="active"', 'data-filter="pending"', 'data-filter="available"', 'btn-save-def',
                       'btn-export-csv', 'btn-import-csv', 'btn-delete-def', '+ New Link', 'Script Link',
                       'Import from Graph', 'group-by-toggle', 'Definitions</h3>'):
            assert needle in html, (url, needle)
        assert 'LINKS_KNOWLEDGE_MODE' not in html and 'kr-panel' not in html and 'link-builder-btn' not in html
    # the legacy-only actions still live in the shared scripts, which the legacy page loads
    discovery = (LINKS_JS / 'links-discovery.js').read_text()
    imports = (LINKS_JS / 'links-import.js').read_text()
    assert 'Adopt as Definition' in discovery and 'Import to Primary Graph' in imports and 'Preview Import' in imports


def test_knowledge_scripts_never_offer_legacy_actions_in_the_viewer():
    discovery = (LINKS_JS / 'links-discovery.js').read_text()
    start = discovery.index('// ===== Knowledge mode')
    knowledge_part = discovery[start:discovery.index('function renderActiveRelationshipTypes')]
    for forbidden in ('Adopt', 'Save as Link Definition', 'Preview Import', 'Import to Primary', 'badge-adopted',
                      'openImportWizardForRelationship', '/api/links/verify', 'method: \'DELETE\'', 'MERGE', 'CREATE'):
        assert forbidden not in knowledge_part, forbidden
    core = (LINKS_JS / 'links-core.js').read_text()
    assert core.index('if (!isKnowledgeMode()) try {') < core.index("'/api/links/verify'")  # Refresh: read-only in Knowledge


KNOWLEDGE_HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const triples = JSON.parse(process.argv[2]);
const fetchMode = process.argv[3];
const make = () => ({innerHTML: '', style: {}, dataset: {}, classList: {toggle() {}}, querySelectorAll: () => [], querySelector: () => null});
const panel = make(), box = make(), wizard = make(), calls = [];
panel.querySelector = sel => sel === '#kr-examples' ? box : null;
wizard.style.display = process.argv[4] === 'builder-open' ? 'block' : 'none';
const ctx = {
  console, discoveredRelationships: triples, discoveryState: 'ready', currentFilter: 'active',
  linkDefinitions: [{id: 'x', status: 'active', name: 'Saved one'}],
  linksNavState: {searchQuery: '', sourceLabel: '', targetLabel: '', relType: '', sortBy: 'name', groupByRelType: false},
  escapeHtml: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  highlightMatch: s => s, opened: [], counts: [],
  updateResultCount: (a, b, n) => ctx.counts.push([a, b, n]),
  openImportWizardForRelationship: rel => ctx.opened.push(rel),
  renderFlatLinks: () => {},
  window: {LINKS_KNOWLEDGE_MODE: true, SCIDK_BASE: '/base'},
  document: {getElementById: id => id === 'kr-panel' ? panel : id === 'link-wizard' ? wizard : make(),
             querySelectorAll: () => []},
  fetch: async (url, opts) => {
    calls.push({url, body: JSON.parse(opts.body)});
    if (fetchMode === 'fail') return {ok: false, json: async () => ({status: 'error', error: 'boom'})};
    return {ok: true, json: async () => ({status: 'success', records: [
      {source_name: 'Alpha sample', rel_properties: ['since'], target_name: 'Beta sample'},
      {source_name: null, rel_properties: [], target_name: 'Gamma sample'}]})};
  },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
(async () => {
  const handlers = [];
  const container = {innerHTML: '', querySelector: () => null,
    querySelectorAll: sel => sel === '.btn-view-active-type' ? [{dataset: {typeIndex: '0'}, addEventListener: (e, f) => handlers.push(f)}] : []};
  vm.runInContext('renderActiveRelationshipTypes', ctx)(container);
  const overview = panel.innerHTML;
  for (const h of handlers) await h({stopPropagation() {}});
  await new Promise(r => setTimeout(r, 20));
  console.log(JSON.stringify({list: container.innerHTML, overview, detail: panel.innerHTML, examples: box.innerHTML,
    wizardDisplay: wizard.style.display, opened: ctx.opened, calls}));
})();
"""


def run_knowledge(triples, fetch_mode='ok', wizard='closed'):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required to execute the Relationships scripts')
    out = subprocess.run([node, '-e', KNOWLEDGE_HARNESS, '--', str(LINKS_JS / 'links-discovery.js'),
                          json.dumps(triples), fetch_mode, wizard], capture_output=True, text=True, timeout=60,
                         check=True)
    return json.loads(out.stdout)


def test_knowledge_overview_fills_the_right_side_before_any_selection():
    result = run_knowledge(GRAPH_TRIPLES)
    overview = result['overview']
    assert 'data-testid="relationship-overview"' in overview
    assert '2 relationship types' in overview and '49 edges' in overview
    assert 'DERIVED_FROM' in overview and 'HAS_INPUT' in overview and 'EXTERNAL_ONLY' not in overview
    assert '/base/knowledge?view=entities' in overview and '/base/knowledge?view=maps' in overview


def test_knowledge_empty_graph_overview_is_explicit():
    overview = run_knowledge([])['overview']
    assert 'No relationships found in the current graph.' in overview and '/base/knowledge?view=maps' in overview


def test_knowledge_view_details_leads_with_a_readable_summary_and_examples():
    result = run_knowledge(GRAPH_TRIPLES, wizard='builder-open')
    detail, examples = result['detail'], result['examples']
    assert result['opened'] == []  # no legacy import wizard in Knowledge
    assert result['wizardDisplay'] == 'none'  # the legacy wizard panel is hidden, the readable panel is shown
    assert 'data-testid="relationship-detail"' in detail and 'data-rel-type="DERIVED_FROM"' in detail
    assert 'Sample &rarr; DERIVED_FROM &rarr; Sample' in detail
    assert '<strong>40</strong> edges in this pattern' in detail and '<strong>42</strong> across 2 patterns' in detail
    assert 'Sample &rarr; SampleType' in detail  # other patterns are one click away
    assert '/base/knowledge?view=entities' in detail and '/base/knowledge?view=maps' in detail
    assert 'Alpha sample' in examples and 'Beta sample' in examples and '(unnamed Sample)' in examples
    assert '1 property' in examples
    # raw ids, query text and import material stay inside the collapsed advanced section
    assert '<details data-testid="relationship-advanced">' in detail
    assert 'id(' not in detail and 'uid' not in detail.lower() and 'import' not in detail.lower()
    assert detail.index('data-testid="relationship-summary"') < detail.index('data-testid="relationship-advanced"')


def test_knowledge_detail_uses_one_bounded_read_only_query_on_the_existing_api():
    calls = run_knowledge(GRAPH_TRIPLES)['calls']
    assert len(calls) == 1 and calls[0]['url'] == '/base/api/neo4j/query'
    query = calls[0]['body']['query']
    assert query.lstrip().startswith('MATCH') and 'LIMIT 8' in query and 'RETURN' in query
    assert calls[0]['body']['database'] == 'PRIMARY'
    for write in ('MERGE', 'CREATE', 'SET ', 'DELETE', 'REMOVE'):
        assert write not in query, write


def test_knowledge_detail_reports_example_failures_without_going_blank():
    result = run_knowledge(GRAPH_TRIPLES, 'fail')
    assert 'Could not load examples: boom' in result['examples']
    assert 'Sample &rarr; DERIVED_FROM &rarr; Sample' in result['detail']


def test_knowledge_list_hides_saved_definitions_and_keeps_graph_rows():
    html = run_knowledge(GRAPH_TRIPLES)['list']
    assert html.count('data-testid="active-relationship-type"') == 2 and 'View Details' in html
    assert 'saved-definitions' not in html and 'Saved definitions' not in html


def test_knowledge_overview_never_replaces_an_open_link_builder():
    assert run_knowledge(GRAPH_TRIPLES, wizard='builder-open')['overview'] == ''


def test_shared_helpers_are_defined_once_so_later_scripts_cannot_override_them():
    sources = {f.name: f.read_text() for f in LINKS_JS.glob('*.js')}
    for helper in ('populateFilterDropdowns', 'updateResultCount'):
        owners = [name for name, text in sources.items() if re.search(rf'^(async )?function {helper}\(', text, re.M)]
        assert owners == ['links-core.js'], (helper, owners)
    core = sources['links-core.js']
    assert 'graph.map(r => r.source_label)' in core and "r.database === 'PRIMARY'" in core


def test_knowledge_panel_returns_to_the_overview_after_a_refresh_replaces_an_open_detail():
    discovery = (LINKS_JS / 'links-discovery.js').read_text()
    loading = discovery[discovery.index("if (discoveryState === 'loading') {\n    container.innerHTML = '<div class=\"empty-state small\" data-testid=\"active-discovering\""):]
    loading = loading[:loading.index("return;")]
    assert 'krSelectedType = null' in loading and 'kr-loading' in loading
    # once discovery is ready again, a cleared selection renders the overview instead of leaving the loading message
    assert run_knowledge(GRAPH_TRIPLES)['overview'].count('relationship-overview') == 1
