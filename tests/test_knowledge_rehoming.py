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
    for url in ('/entities', '/map', '/knowledge?view=entities', '/knowledge?view=maps', '/knowledge?view=graph'):
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


def test_tabs_are_exactly_entities_maps_sketch(client):
    for view in ('entities', 'maps', 'sketch', 'graph'):
        assert tabs(page(client, f'/knowledge?view={view}')) == ['Entities', 'Maps', 'Sketch']


def test_legacy_top_links_are_absent_from_knowledge(client):
    for view in ('entities', 'maps', 'sketch'):
        html = page(client, f'/knowledge?view={view}')
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
    assert '/datasets?panel=annotations' in html
    assert 'annotations-fallback' not in page(client, '/knowledge?view=entities')


def test_advanced_schema_surfaces_stay_reachable(client):
    html = page(client, '/knowledge?view=entities')
    assert '/entities?tab=relationships' in html
    assert client.get('/entities?tab=relationships').status_code == 200


def test_governed_workspace_remains_reachable_for_deep_links(client):
    for url in ('/knowledge?view=governed', '/knowledge?governed=1&domain=research&view=graph',
                '/knowledge?domain=research&id=x'):
        html = page(client, url)
        assert 'kw-graph-pane' in html and 'kw-tab-graph' in html, url


def test_direct_legacy_routes_still_work(client):
    labels = page(client, '/entities')
    assert 'btn-pull-instances' in labels and 'data-testid="entities-tabs"' in labels
    assert 'Relationships' in page(client, '/entities?tab=relationships')
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
    assert knowledge_view({}) == 'entities'
    assert knowledge_view({'domain': 'research'}) == 'governed'
    assert knowledge_view({'view': 'bogus'}) == 'entities'
    app = make_gui_app()
    for url, expected in (('/knowledge?view=entities', True), ('/knowledge?view=graph', True),
                          ('/knowledge?view=maps', True), ('/knowledge?view=sketch', False),
                          ('/knowledge?view=governed', False), ('/overview', False)):
        with app.test_request_context(url):
            assert management_page() is expected, url
