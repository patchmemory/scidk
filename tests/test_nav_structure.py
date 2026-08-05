"""
Tests for the top-level navigation structure and the Entities page.

Covers the nav restructure: Labels and Links folded into a single Entities item
with two tabs, Scripts and Plugins moved out of the top nav into Settings →
Advanced, and Pipeline relabelled Resources.
"""

EXPECTED_NAV = ['Results', 'Chats', 'Maps', 'Entities', 'Files', 'Resources']


def _header_nav(html):
    """Return the anchor text of the header nav, in document order."""
    import re

    nav = re.search(r'<nav data-testid="nav">(.*?)</nav>', html, re.S)
    assert nav, 'header nav should be present'
    return re.findall(r'<a\b[^>]*>([^<]*)</a>', nav.group(1))


def test_top_nav_items(client):
    """The top nav shows exactly the six researcher-facing pages."""
    response = client.get('/results')
    assert response.status_code == 200
    assert _header_nav(response.data.decode('utf-8')) == EXPECTED_NAV


def test_scripts_and_plugins_are_not_in_top_nav(client):
    """Scripts and Plugins are admin tools and live in Settings → Advanced."""
    nav = _header_nav(client.get('/results').data.decode('utf-8'))
    assert 'Scripts' not in nav
    assert 'Plugins' not in nav


def test_resources_label_keeps_its_url(client):
    """The Pipeline → Resources relabel is display-only."""
    html = client.get('/results').data.decode('utf-8')
    assert '/pipeline/sources" data-testid="nav-pipeline">Resources<' in html
    assert client.get('/pipeline/sources').status_code == 200


def test_entities_defaults_to_the_entities_tab(client):
    """/entities with no tab renders the Labels content."""
    response = client.get('/entities')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert '<div class="labels-container">' in html
    assert '<div class="links-container">' not in html


def test_entities_relationships_tab(client):
    """?tab=relationships renders the Links content instead."""
    response = client.get('/entities?tab=relationships')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert 'links-core.js' in html
    assert '<div class="labels-container">' not in html


def test_unknown_tab_falls_back_to_entities(client):
    response = client.get('/entities?tab=nonsense')
    assert response.status_code == 200
    assert 'labels-container' in response.data.decode('utf-8')


def test_entities_page_renders_both_tabs(client):
    """Both tabs are always reachable, with the current one marked active."""
    html = client.get('/entities?tab=entities').data.decode('utf-8')
    assert 'entities-tab-entities' in html
    assert 'entities-tab-relationships' in html
    assert 'data-testid="entities-tab-entities"\n     class="active"' in html


def test_legacy_label_and_link_urls_redirect(client):
    """Existing bookmarks and in-app links keep working."""
    for url, expected in [
        ('/labels', '/entities?tab=entities'),
        ('/links', '/entities?tab=relationships'),
        ('/integrate', '/entities?tab=relationships'),
    ]:
        response = client.get(url)
        assert response.status_code == 302, url
        assert response.headers['Location'].endswith(expected), url


def test_settings_sidebar_has_advanced_section(client):
    """Scripts (admin-only) and Plugins are reachable from Settings → Advanced."""
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert '<span>Advanced</span>' in html
    assert 'data-testid="settings-advanced-scripts"' in html
    assert 'data-testid="settings-advanced-plugins"' in html
    # The Scripts entry is gated by the existing admin-only sidebar mechanism.
    import re

    scripts_link = re.search(r'<a[^>]*data-testid="settings-advanced-scripts"[^>]*>', html)
    assert scripts_link and 'admin-only' in scripts_link.group(0)


def test_scripts_and_plugins_pages_still_load(client):
    """Only the navigation entry point moved; the pages are unchanged."""
    assert client.get('/scripts').status_code == 200
    assert client.get('/plugins').status_code == 200
