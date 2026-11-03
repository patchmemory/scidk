"""Overview/Review entry experience: compact Chat launcher, real destination cards, five task cards with contextual Chat
prefills, the Chat prefill contract (escaped, unsent, unstored), legacy URL compatibility and no AI/provider calls."""
import html as htmllib
import re
from urllib.parse import parse_qs, quote, urlsplit

import pytest

PROMPT = 'What scientific work are you trying to do?'
TASK_TITLES = ['Curate', 'Annotate', 'Evaluate', 'Enrich', 'Publish']
EXPECTED = {
    'curate': ['/datasets?view=collections', '/datasets?view=datasets', '/datasets?view=browse'],
    'annotate': ['/datasets?view=browse'],
    'evaluate': ['/knowledge?view=relationships', '/knowledge?view=entities', '/knowledge?view=maps', '/resources?view=runs'],
    'enrich': ['/resources?view=plugins', '/resources?view=sources'],
    'publish': ['/datasets?view=collections'],
}
HOME_EXPECTED = {
    'browse': ['/datasets?view=browse'],
    'explore': ['/knowledge?view=relationships'],
    'curate': ['/review'],
}
HOME_PROMPTS = {
    'browse': 'Help me find the relevant data.',
    'explore': 'Help me understand how these things relate.',
    'curate': 'Help me decide what to do next.',
}
REVIEW_PROMPTS = {
    'curate': 'I am curating a collection of datasets. Help me think through how to group them and what provenance and context to keep.',
    'annotate': 'I want to annotate my data. Help me decide which notes, descriptions, tags or corrections would be most useful.',
    'evaluate': 'I am evaluating my data. Help me look for gaps in metadata, weak evidence or inconsistencies between relationships and runs.',
    'enrich': 'I want to enrich my data. Help me plan which sources, schema and mappings to prepare first.',
    'publish': 'I want to prepare a collection to share. Help me work out what metadata and context a sharing package needs.',
}
BANNED_SCRIPT = ('fetch(', 'XMLHttpRequest', 'WebSocket', 'sendBeacon', 'localStorage', 'sessionStorage', 'document.cookie', 'EventSource')


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
    match = re.search(r'<li class="tn-row[^>]*data-action="%s".*?</li>' % action, page, re.S)
    assert match, action
    return match.group(0)


def home_card(page, name):
    match = re.search(r'<li class="sn-row"[^>]*id="home-card-%s".*?</li>' % name, page, re.S)
    assert match, name
    return match.group(0)


def inline_script(page):
    script = page[page.index('<script>', page.index('id="guidance-shell"')):]
    return script[:script.index('</script>')]


def forbid_provider(app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Entry pages must not call an AI provider')
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', forbidden)
    app.config.update(SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_REVIEW_CHAT_ENABLED=True)
    requests = []
    app.before_request(lambda: requests.append(__import__('flask').request.path))
    return requests


# ------------------------------------------------------------------ Overview / Home

@pytest.mark.parametrize('path', ['/', '/overview'])
def test_home_is_a_compact_launcher_with_three_real_destination_cards(app, path):
    page = html(app, path)
    assert '<h1 class="ws-title">Overview</h1>' in page
    assert 'Where would you like to begin?' in page and 'Your research workspace' not in page     # one title, one prompt
    assert len(re.findall(r'<h1 class="ws-title"', page)) == 1
    launcher = page[page.index('id="overview-launcher"'):]
    launcher = launcher[:launcher.index('</form>')]
    assert 'method="get"' in launcher and 'name="view" value="guidance"' in launcher and 'name="prefill"' in launcher
    assert 'Ask about your data' in launcher and 'Open Chat →' in launcher
    assert '<textarea' not in launcher and 'checkbox' not in launcher
    assert len(re.findall(r'<li class="sn-row"', page)) == 3
    assert 'class="rl-card' not in page and 'home-cards' not in page          # no grid of large generic cards
    assert re.findall(r'<h2 id="start-elsewhere-title">([^<]+)</h2>', page) == ['Start elsewhere']
    adapter = app.url_map.bind('localhost')
    for name, destinations in HOME_EXPECTED.items():
        found = re.findall(r'data-destination="([^"]+)"', home_card(page, name))
        assert found == destinations, name
        for destination in found:
            assert adapter.match(urlsplit(destination).path)[0].startswith('ui.'), destination
    for title in ('Browse data', 'Explore knowledge', 'Curate and review'):
        assert '>%s</h3>' % title in page
    assert [re.findall(r'class="sn-open"[^>]*>([^<]+)</a>', home_card(page, n))[0] for n in HOME_EXPECTED] == [
        'Open Datasets →', 'Open Knowledge →', 'Open Review →']


def test_home_ask_chat_actions_prefill_fixed_prompts_without_sending(app, monkeypatch):
    requests = forbid_provider(app, monkeypatch)
    page = html(app, '/')
    for name, prompt in HOME_PROMPTS.items():
        row = home_card(page, name)
        links = re.findall(r'<a class="sn-chat" href="([^"]+)" data-chat-prompt="([^"]+)" data-testid="ask-chat-%s"[^>]*>Ask Chat</a>' % name, row)
        assert len(links) == 1, name
        assert htmllib.unescape(links[0][1]) == prompt
        assert parse_qs(urlsplit(htmllib.unescape(links[0][0])).query) == {'view': ['guidance'], 'prefill': [prompt]}
        assert row.index('class="sn-open"') < row.index('class="sn-chat"')          # primary first, Ask Chat quieter and adjacent
    assert requests == ['/']
    assert len(page[page.index('id="start-elsewhere"'):page.index('id="workspace-status"')]) < 2600       # compact, not a card grid


def test_home_landing_hides_provider_consent_and_low_level_query_mechanics(app):
    page = html(app, '/')
    landing = page[:page.index('<dialog')]                 # the visible landing: everything before the shared Chat dialog
    for banned in ('overview-consent', 'overview-scope', 'Look in', 'Graph (read-only tools)', 'overview_chat.js',
                   'Send this question', 'overview-question'):
        assert banned not in landing, banned
        assert banned in page[page.index('<dialog'):], banned      # still reachable, inside the closed Chat workbench
    assert '<script' not in page[page.index('id="overview-launcher"'):page.index('id="workspace-status"')]
    assert not re.search(r'<dialog[^>]*\bopen\b', page) and not re.search(r'<details class="gd-advanced"[^>]*\bopen\b', page)


def test_home_status_strip_is_honest_and_read_only(app):
    page = html(app, '/')
    strip = page[page.index('id="workspace-status"'):]
    strip = strip[:strip.index('</section>')]
    assert 'Current workspace' in strip
    ids = re.findall(r'data-status-id="(\w+)" data-state="(\w+)"', strip)
    assert [i for i, _ in ids] == ['graph', 'inventory', 'plugins']
    assert all(state in ('ok', 'off', 'unknown') for _, state in ids)
    assert 'data-testid="home-advanced-link"' in strip and '/review/guidance#advanced-query' in strip


def test_home_status_reports_unknown_when_a_check_fails(app, monkeypatch):
    def broken(_app):
        raise RuntimeError('no')
    monkeypatch.setattr('scidk.core.neo4j_config.get_neo4j_params', broken)
    page = html(app, '/')
    assert re.search(r'data-status-id="graph" data-state="unknown"><span class="ws-status-label">Graph</span> '
                     r'<span class="ws-status-value">Unknown', page)


def test_home_makes_no_provider_call_and_keeps_old_selection_deep_links(app, monkeypatch):
    requests = forbid_provider(app, monkeypatch)
    page = html(app, '/overview')
    assert requests == ['/overview']
    assert '/api/' not in page[page.index('id="overview-launcher"'):page.index('data-testid="home-advanced-link"')]
    response = app.test_client().get('/overview?domain=research&id=abc')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/review/guidance?domain=research&id=abc#advanced-query')


# ------------------------------------------------------------------ Review

def test_review_has_central_chat_and_exactly_five_task_cards(app):
    page = html(app)
    assert '<h1 class="ws-title">Review</h1>' in page and PROMPT in page
    assert page.index('id="review-chat-launcher"') < page.index('id="rl-card-curate"')
    composer = page[page.index('id="review-chat-launcher"'):page.index('id="review-tasks"')]
    assert 'name="prefill"' in composer and 'Open Chat →' in composer and 'name="view" value="guidance"' in composer
    assert 'No AI provider is configured' in composer and 'nothing is sent' in composer
    assert 'data-action="guidance"' not in page
    assert re.findall(r'<h3 id="rl-title-\w+">([^<]+)</h3>', page) == TASK_TITLES
    assert len(re.findall(r'<li class="tn-row', page)) == 5 and 'class="rl-card' not in page and 'rl-grid' not in page
    assert re.findall(r'<h2 id="rl-tasks-title">([^<]+)</h2>', page) == ['Or pick a task']
    sequence = re.sub(r'<[^>]+>', '', re.search(r'data-testid="task-sequence">(.*?)</p>', page, re.S).group(1))
    assert ' '.join(sequence.split()).startswith('Typical sequence: Curate → Annotate → Evaluate → Enrich → Publish.')
    assert '<ol class="tn-list">' in page             # an ordered list: the work sequence is also exposed to assistive tech
    for retired in ('Understand data', 'Organize context', 'Improve metadata', 'Prepare to share'):
        assert retired not in page
    assert 'id="review-workspace"' not in page


def test_task_cards_deep_link_to_real_destinations(app):
    page = html(app)
    adapter = app.url_map.bind('localhost')
    for action, destinations in EXPECTED.items():
        found = re.findall(r'data-destination="([^"]+)"', card(page, action))
        assert sorted(found) == sorted(destinations), action          # the primary action sits in the footer, after the related links
        assert found[-1] == destinations[0], action
        for destination in found:
            assert adapter.match(urlsplit(destination).path)[0].startswith('ui.'), destination
    assert 'href="/datasets?view=collections"' in card(page, 'curate')
    assert 'href="/datasets?view=browse"' in card(page, 'annotate')
    assert 'href="/knowledge?view=relationships"' in card(page, 'evaluate')
    assert 'href="/resources?view=plugins"' in card(page, 'enrich')
    assert 'href="/datasets?view=collections"' in card(page, 'publish')


def test_destination_views_are_known_to_their_workspaces():
    from scidk.services.graph_management_policy import KNOWLEDGE_VIEWS
    from scidk.web.routes.ui import RESOURCES_VIEWS, WORKSPACE_VIEWS
    known = {'knowledge': KNOWLEDGE_VIEWS, 'datasets': WORKSPACE_VIEWS, 'resources': RESOURCES_VIEWS}
    for destinations in list(EXPECTED.values()) + list(HOME_EXPECTED.values()):
        for destination in destinations:
            parts = urlsplit(destination)
            if parts.query:
                assert parts.query.split('=')[1] in known[parts.path.strip('/')], destination


def test_every_task_has_a_discuss_in_chat_link_with_a_fixed_prompt(app):
    page = html(app)
    prompts = set()
    for action in EXPECTED:
        links = re.findall(r'<a class="rl-discuss" href="([^"]+)" data-chat-prompt="([^"]+)" data-testid="discuss-%s" aria-label="Ask Chat: \w+">Ask Chat</a>' % action,
                           card(page, action))
        assert len(links) == 1, action
        href = htmllib.unescape(links[0][0])
        parts = urlsplit(href)
        assert parts.path == '/review' and parse_qs(parts.query)['view'] == ['guidance']
        prefill = parse_qs(parts.query)['prefill'][0]
        assert prefill == htmllib.unescape(links[0][1]) and 20 < len(prefill) <= 1000
        assert prefill == REVIEW_PROMPTS[action]
        prompts.add(prefill)
    assert len(prompts) == 5


def test_review_landing_makes_no_ai_or_provider_calls_and_has_no_script(app, monkeypatch):
    requests = forbid_provider(app, monkeypatch)
    page = html(app)
    landing = page[page.index('id="review-landing"'):page.index('<dialog')]       # the landing itself, before the shared dialog
    assert '<script' not in landing and 'fetch(' not in landing and '/api/' not in landing
    script = inline_script(page)
    for banned in BANNED_SCRIPT:
        assert banned not in script, banned
    assert requests == ['/review']


def test_review_is_the_active_sidebar_item_and_sidebar_is_unchanged(app):
    page = html(app)
    nav = page[page.index('data-testid="nav"'):]
    nav = nav[:nav.index('</nav>')]
    assert re.findall(r'>([^<]+)</a>', nav) == ['Datasets', 'Resources', 'Knowledge', 'Review']
    assert 'href="/review" data-testid="nav-review" class="active" aria-current="page"' in nav


# ------------------------------------------------------------------ Chat shell and prefill

@pytest.mark.parametrize('path', ['/review?view=guidance', '/review/guidance'])
def test_chat_without_prefill_is_empty_honest_and_makes_no_provider_call(app, monkeypatch, path):
    requests = forbid_provider(app, monkeypatch)
    page = html(app, path)
    assert requests == [path.split('?')[0]]
    assert 'data-testid="guidance-shell"' in page and 'data-provider-state="not-configured"' in page
    assert 'Chat is unavailable' in page and 'data-testid="guidance-input"' in page
    assert '<h1 class="ws-title">Chat</h1>' in page and 'guidance-back' not in page and 'Back to Review' not in page
    assert re.search(r'<textarea id="guidance-input"[^>]*></textarea>', page) and 'data-prefilled="true"' not in page
    for banned in BANNED_SCRIPT:
        assert banned not in inline_script(page), banned
    assert 'class="gd-msg user"' not in page and 'guidance-assistant' not in page


@pytest.mark.parametrize('path', ['/review?view=guidance', '/review/guidance'])
def test_prefill_fills_only_the_input_escaped_and_never_submits(app, monkeypatch, path):
    requests = forbid_provider(app, monkeypatch)
    payload = '</textarea><img src=x onerror=alert(1)>&amp; "quote"'
    page = html(app, path + ('&' if '?' in path else '?') + 'prefill=' + quote(payload))
    assert requests == [path.split('?')[0]]
    assert '<img src=x' not in page and '</textarea><img' not in page
    area = re.search(r'<textarea id="guidance-input"[^>]*>(.*?)</textarea>', page, re.S)
    assert htmllib.unescape(area.group(1)) == payload
    assert 'data-prefilled="true"' in page
    messages = page[page.index('id="guidance-messages"'):page.index('id="guidance-form"')]
    assert 'gd-msg user' not in messages and 'gd-msg notice' not in messages
    assert 'Chat is unavailable' in page


def test_prefill_is_bounded_and_whitespace_trimmed(app):
    page = html(app, '/review?view=guidance&prefill=' + '%20' * 3 + 'a' * 5000)
    area = re.search(r'<textarea id="guidance-input"[^>]*>(.*?)</textarea>', page, re.S).group(1)
    assert area == 'a' * 1000


def test_chat_script_never_reads_the_prefill_into_html_storage_or_network(app):
    script = inline_script(html(app, '/review?view=guidance&prefill=hello'))
    assert 'innerHTML' not in script and 'URLSearchParams' not in script and 'prefill=' not in script
    for banned in BANNED_SCRIPT:
        assert banned not in script, banned


def test_visible_terminology_says_chat_not_guidance(app):
    from tests.test_demo_polish import visible_text
    for path in ('/', '/review', '/review?view=guidance', '/review/guidance'):
        assert 'guidance' not in visible_text(html(app, path)).lower(), path
    for path in ('/review?view=guidance', '/review/guidance', '/review?view=guidance&prefill=x'):
        assert app.test_client().get(path).status_code == 200


def test_advanced_query_tools_remain_reachable_under_chat(app):
    page = html(app, '/review/guidance')
    advanced = page[page.index('id="advanced-query"'):]
    for needle in ('id="overview-chat"', 'id="overview-question"', 'id="overview-scope"', 'id="overview-consent"',
                   'id="overview-send"', 'Graph (read-only tools)', '/chat">Existing chat sessions', 'ai-chat/llm-provider'):
        assert needle in advanced, needle
    assert 'js/overview_chat.js' in page
    assert '<details class="gd-advanced" id="advanced-query"' in page
    assert app.test_client().get('/chat').status_code == 200


def test_advanced_query_form_is_disabled_when_the_assistant_is_not_enabled(app):
    app.config['SCIDK_OVERVIEW_CHAT_ENABLED'] = False
    page = html(app, '/review/guidance')
    assert 'maxlength="4000" placeholder="Find a dataset' in page and 'rows="3" disabled></textarea>' in page
    assert '<button id="overview-send" class="primary" disabled>' in page


# ------------------------------------------------------------------ legacy Review URLs

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


def test_review_and_overview_remain_gated_by_the_gui_shell_flag():
    from tests.gui.harness import make_gui_app
    client = make_gui_app().test_client()
    assert client.get('/review').status_code == 404
    assert client.get('/overview').status_code == 404


def test_empty_launcher_submission_redirects_to_the_clean_chat_address(app):
    client = app.test_client()
    response = client.get('/review?view=guidance&prefill=')
    assert response.status_code == 302 and response.headers['Location'].endswith('/review?view=guidance')
    response = client.get('/review/guidance?prefill=%20%20')
    assert response.status_code == 302 and response.headers['Location'].endswith('/review/guidance')
    assert client.get('/review?view=guidance', follow_redirects=False).status_code == 200


# ------------------------------------------------------------------ Chat as a shared workspace; compact cards; collection pill

@pytest.mark.parametrize('path', ['/review?view=guidance', '/review/guidance', '/review?view=guidance&prefill=Hello'])
def test_chat_is_a_shared_workspace_with_direct_overview_and_review_links(app, path):
    page = html(app, path)
    assert 'Back to Review' not in page and 'guidance-back' not in page and 'gd-back' not in page
    links = page[page.index('data-testid="chat-links"'):]
    links = links[:links.index('</nav>')]
    assert re.findall(r'<a href="([^"]*)" data-testid="([^"]*)">([^<]*)</a>', links) == [
        ('/overview', 'chat-link-overview', 'Overview'), ('/review', 'chat-link-review', 'Review workspace')]
    assert page.index('<h1 class="ws-title">Chat</h1>') < page.index('data-testid="chat-links"') < page.index('id="guidance-welcome"')
    for banned in ('origin=', 'referrer', 'return_to', 'returnTo', 'document.referrer', 'history.back'):
        assert banned not in page, banned


def test_chat_entry_links_carry_no_origin_or_return_parameters(app):
    for page in (html(app, '/'), html(app, '/review')):
        for href in re.findall(r'href="([^"]*view=guidance[^"]*)"', page):
            assert set(parse_qs(urlsplit(htmllib.unescape(href)).query)) <= {'view', 'prefill'}, href
        for form in re.findall(r'<form class="chat-launcher".*?</form>', page, re.S):
            assert set(re.findall(r'name="(\w+)"', form)) == {'view', 'prefill'}


def test_chat_draft_is_never_stored_and_advanced_toggle_cannot_reset_it(app):
    page = html(app, '/review?view=guidance&prefill=Keep%20me')
    script = inline_script(page)
    for banned in BANNED_SCRIPT + ('beforeunload', 'pagehide', 'form.reset', '.reset('):
        assert banned not in script, banned
    advanced = page[page.index('<details class="gd-advanced"'):]
    assert 'guidance-input' not in advanced[:advanced.index('</details>')]
    assert not re.search(r'<details class="gd-advanced"[^>]*\bopen\b', page)


def test_task_rows_are_compact_with_one_consistent_action_area(app):
    page = html(app)
    for action, destinations in EXPECTED.items():
        body = card(page, action)
        actions = re.findall(r'<div class="tn-actions">(.*?)</div>', body, re.S)
        assert len(actions) == 1, action
        assert re.findall(r'class="([\w-]+)"', actions[0]) == ['rl-primary', 'rl-discuss'], action
        assert re.findall(r'data-destination="([^"]+)"', actions[0]) == destinations[:1], action
        assert '>Ask Chat</a>' in actions[0] and 'Discuss in Chat' not in body and 'data-testid="discuss-%s"' % action in actions[0]
        assert re.findall(r'data-destination="([^"]+)"', body.replace(actions[0], '')) == destinations[1:], action
        summary = re.search(r'</h3><p>([^<]+)', body).group(1).strip()
        assert len(summary) <= 90, (action, len(summary))
    css = open('scidk/ui/static/css/gui_design.css').read()
    assert '.tn-row {' in css and '.sn-row,' in css and '.rl-grid' not in css and '.home-cards' not in css
    assert 'focus-visible' in css[css.index('.sn-open:focus-visible'):][:300]


def test_collection_pill_is_an_accessible_control_over_supported_infrastructure():
    src = open('scidk/ui/static/js/collection_basket.js').read()
    # The pill is a button that opens the existing panel (switch = Open a saved collection; clear = detach it).
    assert "el('button', '', {id: 'cb-pill'" in src and "'aria-haspopup', 'dialog'" in src
    assert "'aria-controls', 'cb-panel'" in src and "'aria-expanded'" in src
    assert "'Clear selection'" in src and "data-testid', 'collection-clear-selection'" in src
    assert "'Open', {type: 'button'}" in src and "data-action', 'open-collection'" in src
    clear = re.search(r"cl\.onclick = \(\) => \{([^\n]*)\};", src).group(1)
    assert '_opened = null' in clear and '_persistOpened()' in clear
    for forbidden in ('_json', 'fetch', 'DELETE', 'POST'):
        assert forbidden not in clear, forbidden            # clearing never touches membership or data
    assert set(re.findall(r"localStorage\.(?:set|remove)Item\((\w+)", src)) == {'KEY', 'OPEN_KEY'}   # no new persisted state


# ------------------------------------------------------------------ Shared Chat workbench (dialog on Overview and Review, page on the Chat routes)

def dialog_of(page):
    start = page.index('<dialog')
    return page[start:page.index('</dialog>') + len('</dialog>')]


@pytest.mark.parametrize('path', ['/', '/overview', '/review'])
def test_overview_and_review_open_the_same_shared_chat_workbench_dialog(app, path):
    page = html(app, path)
    dialog = dialog_of(page)
    assert page.count('<dialog') == 1 and 'id="chat-workbench"' in dialog and 'aria-labelledby="cw-title"' in dialog
    assert '<h2 class="ws-title" id="cw-title">Chat</h2>' in dialog
    for testid in ('guidance-shell', 'guidance-messages', 'guidance-input', 'advanced-query', 'chat-history',
                   'chat-workbench-close', 'chat-open-full'):
        assert 'data-testid="%s"' % testid in dialog, testid
    assert re.search(r'<button type="button" class="cw-close"[^>]*aria-label="Close Chat"', dialog)
    assert not re.search(r'<dialog[^>]*\bopen\b', dialog)                                    # closed on arrival
    assert not re.search(r'<details class="gd-advanced"[^>]*\bopen\b', dialog)               # Advanced collapsed
    assert 'Chat is unavailable' in dialog and 'data-provider-state="not-configured"' in dialog
    assert 'guidance-input' not in dialog[dialog.index('<details class="gd-advanced"'):dialog.index('</details>')]


def test_workbench_markup_is_identical_on_overview_and_review(app):
    def normal(page):
        return re.sub(r'\s+', ' ', dialog_of(page))
    assert normal(html(app, '/overview')) == normal(html(app, '/review'))


@pytest.mark.parametrize('path', ['/', '/review'])
def test_workbench_script_is_in_page_only_and_launchers_stay_plain_links(app, path):
    page = html(app, path)
    script = inline_script(page)
    for banned in BANNED_SCRIPT + ('beforeunload', 'pagehide', '.reset(', 'pushState', 'replaceState', 'location.href', 'location.assign'):
        assert banned not in script, banned
    assert 'showModal' in script and 'data-chat-prompt' in script and 'chat-workbench-close' in script
    for form in re.findall(r'<form class="chat-launcher".*?</form>', page, re.S):          # no-script fallback is still a GET to Chat
        assert 'method="get"' in form and 'name="view" value="guidance"' in form
    assert re.search(r'(?<![\w-])data-chat-prompt', script)
    if path == '/review':
        for action in EXPECTED:
            body = card(page, action)
            assert 'href="/review?view=guidance&amp;prefill=' in body and 'data-chat-prompt="' in body


def test_workbench_history_is_an_honest_empty_state_without_sample_conversations(app):
    for path in ('/', '/review', '/review?view=guidance', '/review/guidance'):
        page = html(app, path)
        rail = page[page.index('id="chat-history"'):]
        rail = rail[:rail.index('</aside>')]
        assert 'Recent conversations' in rail
        assert 'No conversations available yet. Conversation history will appear when Chat is configured.' in rail
        assert 'data-testid="chat-history-list"' not in rail and '<li' not in rail and '<a ' not in rail


def test_full_page_chat_remains_a_deep_link_and_reuses_the_workbench(app):
    for path in ('/review?view=guidance', '/review/guidance'):
        page = html(app, path)
        assert '<dialog' not in page and '<h1 class="ws-title">Chat</h1>' in page
        assert 'data-testid="chat-links"' in page and 'id="chat-workbench-close"' not in page
        assert 'data-testid="chat-history"' in page and 'data-testid="advanced-query"' in page
        assert 'data-testid="guidance-hints"' in page


def test_chat_prefill_still_arrives_visible_unsent_and_escaped_on_the_full_page(app, monkeypatch):
    requests = forbid_provider(app, monkeypatch)
    page = html(app, '/review?view=guidance&prefill=' + quote('<b>x</b> & "y"'))
    box = re.search(r'<textarea id="guidance-input"[^>]*>(.*?)</textarea>', page, re.S).group(1)
    assert box == '&lt;b&gt;x&lt;/b&gt; &amp; &#34;y&#34;' and '<b>x</b>' not in page
    assert 'data-testid="guidance-user-message"' not in page
    assert requests == ['/review']
