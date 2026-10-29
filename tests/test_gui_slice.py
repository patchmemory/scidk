"""Opt-in GUI boundaries and real browser selection/state checks."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def gui_app():
    from tests.gui.harness import make_gui_app
    return make_gui_app()


def test_shell_opt_in_and_legacy_routes(gui_app):
    client = gui_app.test_client()
    assert client.get('/overview').status_code == 404
    assert b'nav-chats' in client.get('/').data
    gui_app.config['SCIDK_GUI_V3_ENABLED'] = True
    for path in ['/', '/overview', '/knowledge', '/review', '/settings', '/datasets', '/map', '/entities', '/chat', '/pipeline/sources']:
        response = client.get(path)
        assert response.status_code == 200, path
    page = client.get('/overview?profile=review').data
    for name in [b'Overview', b'Files &amp; Datasets', b'Resources', b'Knowledge', b'Review', b'Settings']:
        assert name in page
    assert b'<textarea id="overview-question" disabled' in page
    assert b'<button disabled>Send</button>' in page
    assert b'gui_slice.js' not in page
    assert b'Chat unavailable' in client.get('/').data
    assert b'Chat unavailable' not in client.get('/settings').data


def test_browser_selection_and_inspector(gui_app, tmp_path):
    from playwright.sync_api import sync_playwright
    gui_app.config['SCIDK_GUI_V3_ENABLED'] = True
    with sync_playwright() as pw:
        try:
            import shutil
            executable = shutil.which('google-chrome')
            browser = pw.chromium.launch(headless=True, executable_path=executable)
        except Exception as error:
            pytest.skip('Local Chromium unavailable: ' + str(error).splitlines()[0])
        page = browser.new_page(viewport={'width':1280, 'height':900})
        calls = []
        def serve(route):
            from urllib.parse import urlsplit
            parsed = urlsplit(route.request.url)
            calls.append(parsed.path)
            if parsed.path == '/api/datasets':
                route.fulfill(json=[{'id':'file-1', 'path':'/data/raw.xml', 'interpretations':{'xml':{'nested':{'value':'<safe>'}}}}]); return
            if parsed.path == '/api/canvas/nodes/search':
                route.fulfill(json={'results':[{'id':'42','element_id':'dataset:42','name':'Study', 'properties':{'source':'collection','metadata':{'nested':1}}}]}); return
            if parsed.path == '/api/annotations':
                route.fulfill(json={'items':[{'label':'Stored annotation'}]}); return
            if parsed.path.startswith('/api/'):
                route.fulfill(json=[]); return
            response = gui_app.test_client().get(parsed.path + ('?' + parsed.query if parsed.query else ''))
            route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)
        page.route('**/*', serve)
        page.goto('http://scidk.test/datasets')
        page.locator('#gui-datasets-tab').click()
        page.locator('#dataset-query').fill('Study')
        page.locator('#dataset-search button').click()
        page.locator('#dataset-results button').click()
        assert page.locator('#inspector-title').inner_text() == 'Dataset: Study'
        assert page.locator('#dataset-sharing button').is_disabled()
        page.locator('#inspector-expand').click()
        assert page.locator('#inspector-expand').get_attribute('aria-expanded') == 'true'
        page.locator('[data-inspector-tab="Annotations"]').click()
        page.get_by_text('Stored annotation', exact=False).wait_for()
        page.locator('#gui-files-tab').click()
        page.evaluate("document.dispatchEvent(new CustomEvent('scidk:inspect',{detail:{kind:'file',key:'/data/file.xml',record:{name:'file.xml',raw:'<xml>safe</xml>'}}}))")
        assert page.locator('#inspector-title').inner_text() == 'File / folder: file.xml'
        assert page.locator('#dataset-sharing').is_hidden()
        page.locator('#gui-datasets-tab').click()
        assert page.locator('#inspector-title').inner_text() == 'Dataset: Study'
        assert page.locator('[data-inspector-tab="Annotations"]').get_attribute('aria-selected') == 'true'
        page.locator('[data-inspector-tab="Metadata"]').click()
        assert 'nested' in page.locator('#inspector-content').inner_text()
        assert not any('nih_dms' in call or '/chat/' in call for call in calls)
        page.screenshot(path=str(tmp_path/'gui-dataset-inspector.png'))
        page.locator('#inspector-expand').click()
        page.screenshot(path=str(tmp_path/'gui-dataset-docked.png'))
        calls.clear()
        page.goto('http://scidk.test/overview?profile=review')
        assert page.locator('#overview-question').is_disabled()
        assert page.get_by_role('button', name='Send', exact=True).is_disabled()
        assert not any('/chat/' in call or '/agent/' in call for call in calls)
        page.screenshot(path=str(tmp_path/'gui-overview.png'))
        browser.close()


def test_inspector_runtime_state():
    import subprocess
    subprocess.run(['node', str(ROOT/'tests/gui/inspector_state.cjs'), str(ROOT/'scidk/ui/static/js/gui_slice.js')], check=True)
