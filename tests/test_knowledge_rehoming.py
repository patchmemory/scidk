"""Knowledge re-homes the working Labels browser and Maps application (UI only, no new backend)."""
import re

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
                   'filter-rel-type', 'group-by-toggle', 'id="link-wizard"', 'btn-refresh-all', 'data-filter="active"',
                   'data-filter="pending"', 'data-filter="available"', 'btn-execute', 'loadLinksPage'):
        assert needle in html, needle
    for script in ('links-core.js', 'links-wizard.js', 'links-index.js', 'links-discovery.js', 'links-active.js',
                   'links-import.js'):
        assert f'js/links/{script}' in html, script
    assert 'iframe' not in html
    assert 'btn-pull-instances' not in html and 'map-library-panel' not in html and 'kw-sketch' not in html
    assert 'id="management-connection"' in html and 'id="knowledge-return-slot"' in html


def test_relationships_view_shares_one_implementation_with_the_legacy_page(client):
    knowledge, direct = page(client, '/knowledge?view=relationships'), page(client, '/entities?tab=relationships')
    def app_markup(html):
        start = html.index('<div class="links-container">')
        return html[start:html.index('document.addEventListener(\'DOMContentLoaded\', loadLinksPage);')]
    assert app_markup(knowledge) == app_markup(direct)
    assert knowledge.count('id="links-list"') == 1 and knowledge.count('js/links/links-core.js') == 1


def test_relationships_browse_and_detail_interactions_are_wired(client):
    """The same browse/detail hooks the legacy page uses: type filter, grouping, tabs, detail wizard, APIs."""
    html = page(client, '/knowledge?view=relationships')
    for needle in ('id="filter-source-label"', 'id="filter-target-label"', 'sort-links', 'id="source-node-btn"',
                   'id="relationship-node-btn"', 'id="target-node-btn"', 'id="preview-container"', 'id="btn-save-def"',
                   'toggle-advanced-filters'):
        assert needle in html, needle
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
