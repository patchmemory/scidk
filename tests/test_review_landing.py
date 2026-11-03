"""Review landing: heading, action cards, deep links, no AI calls and legacy route compatibility."""
import re
from urllib.parse import urlsplit

import pytest

PROMPT = 'What would you like to do with your science data?'
CARD_TITLES = ['Understand data', 'Organize context', 'Improve metadata', 'Explore', 'Prepare to share', 'Get guidance']
EXPECTED = {
    'understand': ['/knowledge?view=relationships', '/knowledge?view=entities', '/knowledge?view=maps'],
    'organize': ['/datasets?view=collections', '/datasets?view=datasets'],
    'metadata': ['/resources?view=plugins', '/resources?view=sources'],
    'explore': ['/datasets?view=browse', '/knowledge?view=maps'],
    'share': ['/datasets?view=collections'],
    'guidance': [],
}


@pytest.fixture
def app():
    from tests.gui.harness import make_gui_app
    app = make_gui_app()
    app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_DATASET_SHARING_ENABLED=True)
    return app


def html(app, path='/review'):
    response = app.test_client().get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def card(page, action):
    match = re.search(r'<article class="rl-card[^>]*data-action="%s".*?</article>' % action, page, re.S)
    assert match, action
    return match.group(0)


def test_heading_prompt_and_all_cards(app):
    page = html(app)
    assert '<h1>Review</h1>' in page
    assert PROMPT in page
    for title in CARD_TITLES:
        assert title in page
    assert len(re.findall(r'<article class="rl-card', page)) == 6
    assert 'review-landing' in page and 'id="review-workspace"' not in page


def test_cards_deep_link_to_real_destinations(app):
    page = html(app)
    adapter = app.url_map.bind('localhost')
    for action, destinations in EXPECTED.items():
        found = re.findall(r'data-destination="([^"]+)"', card(page, action))
        assert found == destinations, action
        for destination in found:
            # Every destination is a registered route, and its view parameter is one that route accepts.
            endpoint, _ = adapter.match(urlsplit(destination).path)
            assert endpoint.startswith('ui.'), destination
    assert 'href="/knowledge?view=relationships"' in card(page, 'understand')
    assert 'href="/datasets?view=collections"' in card(page, 'organize')
    assert 'href="/resources?view=plugins"' in card(page, 'metadata')


def test_destination_views_are_known_to_their_workspaces():
    from scidk.services.graph_management_policy import KNOWLEDGE_VIEWS
    from scidk.web.routes.ui import RESOURCES_VIEWS, WORKSPACE_VIEWS
    known = {'knowledge': KNOWLEDGE_VIEWS, 'datasets': WORKSPACE_VIEWS, 'resources': RESOURCES_VIEWS}
    for destinations in EXPECTED.values():
        for destination in destinations:
            parts = urlsplit(destination)
            view = parts.query.split('=')[1]
            assert view in known[parts.path.strip('/')], destination


def test_future_guidance_is_honest_and_has_no_link(app):
    guidance = card(html(app), 'guidance')
    assert 'data-status="future"' in guidance
    assert 'Coming later' in guidance
    assert 'interpret data' in guidance and 'propose queries' in guidance and 'recommend next steps' in guidance
    assert 'No AI provider is configured or called' in guidance
    assert '<a ' not in guidance and '<button' not in guidance and '<form' not in guidance


@pytest.mark.parametrize('sharing_enabled', [True, False])
def test_share_card_always_links_to_collections_regardless_of_sharing_flag(app, sharing_enabled):
    app.config['SCIDK_DATASET_SHARING_ENABLED'] = sharing_enabled
    share = card(html(app), 'share')
    assert 'data-status="ready"' in share
    assert 'Not enabled' not in share and 'rl-note' not in share
    assert re.findall(r'data-destination="([^"]+)"', share) == ['/datasets?view=collections']
    assert 'href="/datasets?view=collections"' in share


def test_landing_makes_no_ai_or_provider_calls(app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Review landing must not call an AI provider')
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', forbidden)
    app.config.update(SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_REVIEW_CHAT_ENABLED=True)
    requests = []
    app.before_request(lambda: requests.append(__import__('flask').request.path))
    page = html(app)
    section = page[page.index('id="review-landing"'):]
    section = section[:section.index('</section>')]
    assert '<script' not in section and 'fetch(' not in section and '<form' not in section
    assert '/api/' not in section
    assert requests == ['/review']


def test_review_is_the_active_sidebar_item_and_sidebar_is_unchanged(app):
    page = html(app)
    nav = page[page.index('data-testid="nav"'):]
    nav = nav[:nav.index('</nav>')]
    labels = re.findall(r'>([^<]+)</a>', nav)
    assert labels == ['Overview', 'Datasets', 'Resources', 'Knowledge', 'Review', 'Settings']
    assert 'href="/review"' in nav


@pytest.mark.parametrize('path', ['/review?view=assertions', '/review/assertions',
                                  '/review?domain=research&id=assertion-1', '/review?id=assertion-1'])
def test_legacy_review_urls_still_open_the_assertion_workspace(app, path):
    app.config.update(SCIDK_REVIEW_WORKSPACE_ENABLED=True)
    page = html(app, path)
    assert 'id="review-workspace"' in page and 'Assertion queue' in page
    assert PROMPT not in page
    assert 'id="rw-home" href="/review"' in page


def test_plain_review_with_workspace_enabled_links_to_legacy_queue(app):
    app.config.update(SCIDK_REVIEW_WORKSPACE_ENABLED=True)
    page = html(app)
    assert PROMPT in page
    assert 'data-destination="/review?view=assertions"' in page
    app.config.update(SCIDK_REVIEW_WORKSPACE_ENABLED=False)
    assert 'view=assertions' not in html(app)


def test_review_remains_gated_by_the_gui_shell_flag():
    from tests.gui.harness import make_gui_app
    assert make_gui_app().test_client().get('/review').status_code == 404
