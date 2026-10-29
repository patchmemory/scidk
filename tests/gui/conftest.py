"""Reuse installed Python Playwright; loopback-only server, no production factory."""
import json
import os
import shutil
import threading
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from werkzeug.serving import make_server
from tests.gui.harness import make_disposable_app


def pytest_addoption(parser):
    parser.addoption('--gui-record-candidates', action='store_true',
                     help='Capture candidates only; never alter checked-in visual references.')
    parser.addoption('--gui-artifacts', default=None, help='New/empty artifact directory for this run.')


@pytest.fixture(scope='session')
def gui_artifacts(request, tmp_path_factory):
    destination = request.config.getoption('--gui-artifacts')
    path = Path(destination) if destination else tmp_path_factory.mktemp('gui-artifacts')
    if destination:
        path.mkdir(parents=True, exist_ok=False)  # Never overwrite an existing run.
    return path


@pytest.fixture(scope='session')
def gui_browser(gui_artifacts):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        executable = os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome')
        browser = pw.chromium.launch(headless=True, executable_path=executable)
        (gui_artifacts/'environment.json').write_text(json.dumps({
            'browser': browser.version, 'engine': 'chromium', 'locale': 'en-US',
            'timezone': 'UTC', 'device_scale_factor': 1, 'human_review': 'pending',
        }, indent=2)+'\n')
        yield browser
        browser.close()


@pytest.fixture
def gui_server():
    app = make_disposable_app()
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.fixture
def gui_page(gui_browser, gui_server, gui_artifacts, request):
    origin, app = gui_server
    context = gui_browser.new_context(viewport={'width':1280, 'height':800},
        locale='en-US', timezone_id='UTC', device_scale_factor=1,
        color_scheme='light', reduced_motion='reduce', service_workers='block')
    context.add_init_script('Date.now = () => 1793289600000;')
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    errors, expected_http = [], set()
    expected_external, known_external = set(), []
    page.on('pageerror', lambda error: errors.append('pageerror: '+str(error)))
    page.on('console', lambda message: errors.append('console: '+message.text)
            if message.type == 'error' and not (message.text.startswith('Failed to load resource:')
                and (urlsplit(message.location.get('url', '')).path in expected_http
                     or message.location.get('url', '') in expected_external)) else None)
    page.on('requestfailed', lambda req: errors.append('network: '+req.url+' '+str(req.failure))
            if req.url not in expected_external else None)
    page.on('response', lambda res: errors.append(f'HTTP {res.status}: {res.url}')
            if res.status >= 400 and urlsplit(res.url).path not in expected_http else None)
    def guard(route):
        if route.request.url.startswith(origin+'/'):
            route.continue_()
        else:
            if route.request.url in expected_external:
                known_external.append(route.request.url)
            else:
                errors.append('Blocked outside request: '+route.request.url)
            route.abort()
    context.route('**/*', guard)
    # Expected error tests may declare only the precise endpoint under test.
    page.gui_expected_http = expected_http
    page.gui_expected_external = expected_external
    page.gui_known_external = known_external
    page.gui_errors = errors
    yield page, origin, app
    name = request.node.name.replace('/', '_').replace('[', '-').replace(']', '')
    (gui_artifacts/(name+'-requests.json')).write_text(json.dumps({
        'requests': app.extensions['gui_test_requests'], 'browser_errors': errors, 'known_blocked_external': known_external}, indent=2)+'\n')
    context.tracing.stop(path=str(gui_artifacts/(name+'.zip')))
    context.close()
    assert not errors, '\n'.join(errors)
