"""User-visible behavior over a disposable HTTP server, without backend duplication."""
import pytest
from playwright.sync_api import expect


def open_files(page, origin):
    page.goto(origin+'/datasets')
    expect(page.locator('#file-list')).to_contain_text('vevo')


def select_file(page):
    page.locator('#file-list tr[data-id]').dblclick()
    expect(page.locator('#file-list')).to_contain_text('metadata.xml')
    page.locator('#file-list tr[data-id]').click()
    expect(page.locator('#inspector-title')).to_have_text('File / folder: metadata.xml')


def select_dataset(page):
    page.get_by_role('tab', name='Datasets', exact=True).click()
    page.get_by_label('Search Dataset nodes by name or path').fill('Vevo')
    page.locator('#dataset-search button').click()
    page.locator('#dataset-results button').click()
    expect(page.locator('#inspector-title')).to_have_text('Dataset: Synthetic Vevo study')


def test_navigation_and_placeholders(gui_page):
    page, origin, app = gui_page
    page.goto(origin+'/overview?profile=review')
    expect(page.get_by_label('Your question')).to_be_disabled()
    expect(page.get_by_role('button', name='Ask SciDK', exact=True)).to_be_disabled()
    for name, path in [('Files & Datasets','/datasets'), ('Resources','/pipeline/sources'),
                       ('Knowledge','/knowledge'), ('Review','/review'), ('Overview','/overview')]:
        page.locator('header nav').get_by_role('link', name=name, exact=True).click()
        expect(page).to_have_url(origin+path)
        expect(page.get_by_role('heading', level=1).first).to_be_visible()
        if name == 'Knowledge':
            expect(page.get_by_role('link', name='Maps & Canvas')).to_have_attribute('href', '/map')
        if name == 'Review':
            expect(page.get_by_text('Review workspace unavailable', exact=False)).to_be_visible()
    # Settings renders the preserved legacy page; its broad administration scripts
    # are covered separately, and this slice doesn't operate any admin controls.
    expect(page.locator('header nav').get_by_role('link', name='Settings')).to_have_attribute('href','/settings')
    client = app.test_client()
    for path in ['/settings', '/chat', '/map', '/entities', '/labels', '/links', '/results', '/pipeline/sources']:
        assert client.get(path, follow_redirects=True).status_code == 200, path
    assert client.get('/integrate').status_code in (301,302)
    assert not any('/chat/tools' in path or 'nih_dms' in path for _,path in app.extensions['gui_test_requests'])


def test_selection_inspector_and_annotations(gui_page):
    page, origin, _ = gui_page
    open_files(page, origin)
    select_file(page)
    expect(page.locator('#inspector-content')).to_contain_text('Ultrasound')
    expect(page.locator('#inspector-content')).to_contain_text('<instrument>')
    page.get_by_role('tab', name='Annotations', exact=True).click()
    expect(page.locator('#inspector-content')).to_contain_text('Synthetic annotation')
    page.get_by_role('tab', name='Provenance', exact=True).click()
    expect(page.locator('#inspector-content')).to_contain_text('local_fs')
    cursor = page.evaluate('[window.currentServer,window.currentRoot,window.currentPath]')
    select_dataset(page)
    page.get_by_role('tab', name='Metadata', exact=True).click()
    expect(page.locator('#inspector-content')).to_contain_text('frames')
    page.get_by_role('button', name='Expand', exact=True).click()
    expect(page.locator('#inspector-expand')).to_have_attribute('aria-expanded','true')
    page.get_by_role('button', name='Restore docked inspector').click()
    expect(page.locator('#inspector-title')).to_have_text('Dataset: Synthetic Vevo study')
    expect(page.get_by_role('button', name='Prepare for Sharing')).to_be_disabled()
    expect(page.locator('#sharing-unavailable')).to_contain_text('whole graph')
    page.get_by_role('button', name='Close inspector').click()
    expect(page.locator('#shared-inspector')).to_be_hidden()
    page.locator('#dataset-results button').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    page.get_by_role('tab', name='Files', exact=True).click()
    expect(page.locator('#inspector-title')).to_have_text('File / folder: metadata.xml')
    assert page.evaluate('[window.currentServer,window.currentRoot,window.currentPath]') == cursor
    expect(page.locator('#dataset-sharing')).to_be_hidden()
    # Existing annotation workflow remains reachable.
    page.locator('#inspector-close').click()
    expect(page.locator('#annotate-btn')).to_be_visible()


def test_keyboard_and_focus(gui_page):
    page, origin, _ = gui_page
    open_files(page, origin)
    page.get_by_role('tab', name='Files', exact=True).focus()
    page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab', name='Datasets', exact=True)).to_be_focused()
    expect(page.get_by_role('tab', name='Datasets', exact=True)).to_have_attribute('aria-selected','true')
    page.keyboard.press('ArrowLeft')
    row = page.locator('#file-list tr[data-id]')
    row.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#shared-inspector')).to_be_visible()
    # Inspecting a folder uses Space; opening it retains legacy double-click behavior.
    page.locator('#inspector-expand').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#inspector-expand')).to_have_attribute('aria-expanded','true')
    page.keyboard.press('Escape')
    expect(page.locator('#shared-inspector')).to_be_hidden()
    expect(row).to_be_focused()
    page.keyboard.press('Space')
    expect(page.locator('#shared-inspector')).to_be_visible()
    page.get_by_role('tab', name='Metadata', exact=True).focus()
    page.keyboard.press('End')
    expect(page.get_by_role('tab', name='Provenance', exact=True)).to_be_focused()
    outline = page.get_by_role('tab', name='Provenance', exact=True).evaluate('e => getComputedStyle(e).outlineStyle')
    assert outline not in ('none', 'hidden')
    for selector in ['#gui-files-tab','#gui-datasets-tab','#inspector-expand','#inspector-close']:
        assert page.locator(selector).inner_text().strip()


def test_loading_empty_and_errors(gui_page):
    page, origin, _ = gui_page
    open_files(page, origin)
    page.get_by_role('tab', name='Datasets', exact=True).click()
    page.locator('#dataset-query').fill('missing')
    # Hold the request to assert the loading state without timing sleeps.
    pending = []
    def hold(route): pending.append(route)
    page.route('**/api/canvas/nodes/search?*', hold)
    page.locator('#dataset-search button').click()
    expect(page.locator('#dataset-results')).to_have_text('Searching…')
    page.wait_for_timeout(50)
    assert pending
    pending.pop().fulfill(json={'results':[]})
    expect(page.locator('#dataset-results')).to_have_text('No records found.')
    page.unroute('**/api/canvas/nodes/search?*', hold)
    page.route('**/api/canvas/nodes/search?*', lambda route: route.fulfill(status=503,json={'error':'Synthetic outage'}))
    page.gui_expected_http.add('/api/canvas/nodes/search')
    page.locator('#dataset-search button').click()
    expect(page.locator('#dataset-results')).to_have_text('Service unavailable (503)')


class OfflineDependencyError(RuntimeError):
    pass


def test_settings_offline_navigation(gui_page):
    page, origin, _ = gui_page
    page.goto(origin+'/overview')
    page.locator('header nav').get_by_role('link',name='Settings',exact=True).click()
    expect(page).to_have_url(origin+'/settings')
    expect(page.get_by_role('heading',level=1).first).to_be_visible()
    page.wait_for_load_state('networkidle')
    if page.gui_known_external:
        raise OfflineDependencyError('Settings still requests external Cytoscape')


def test_narrow_viewport_and_tab_semantics(gui_page):
    page, origin, _ = gui_page
    page.set_viewport_size({'width':800,'height':700})
    open_files(page, origin)
    select_dataset(page)
    page.locator('#inspector-expand').scroll_into_view_if_needed()
    expect(page.locator('#inspector-expand')).to_be_in_viewport()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    panel = page.locator('#shared-inspector').bounding_box()
    assert panel['width'] <= 800 and panel['x'] >= 0
    for button in page.locator('#gui-files').get_by_role('tab').all():
        target = button.get_attribute('aria-controls')
        assert target and page.locator('#'+target).count() == 1
        assert button.inner_text().strip()
    page.get_by_role('tab',name='Provenance',exact=True).click()
    expect(page.locator('#inspector-content')).to_contain_text('fixture-1')
    page.set_viewport_size({'width':1280,'height':800})
    expect(page.locator('#inspector-title')).to_have_text('Dataset: Synthetic Vevo study')
    expect(page.get_by_role('tab',name='Provenance',exact=True)).to_have_attribute('aria-selected','true')



def test_folder_mouse_inspection_timer(gui_page):
    page, origin, _ = gui_page
    open_files(page, origin)
    page.locator('#file-list tr[data-id]').click()
    expect(page.locator('#inspector-title')).to_have_text('File / folder: vevo')
    page.get_by_role('button',name='Close inspector').click()
    select_file(page)
    # Wait beyond the explicit 400ms single-click debounce to catch stale folder selection.
    page.wait_for_timeout(450)
    expect(page.locator('#inspector-title')).to_have_text('File / folder: metadata.xml')


def test_existing_annotations_adapter_and_resources(gui_page, gui_artifacts):
    page, origin, app = gui_page
    # Display-only legacy attribution responses; no graph write is exercised.
    page.route('**/api/schema/labels', lambda route: route.fulfill(json={'labels': []}))
    page.route('**/api/schema/relationship-types', lambda route: route.fulfill(json={'types': []}))
    page.route('**/api/schema/property-types?*', lambda route: route.fulfill(json={'properties': []}))
    page.route('**/api/files/attribution/**', lambda route: route.fulfill(json={'anchors': [], 'properties': [], 'suggestions': [], 'types': []}))
    page.goto(origin + '/annotations')
    expect(page).to_have_url(origin + '/datasets?panel=annotations')
    expect(page.locator('#annotate-drawer')).to_be_visible()
    expect(page.locator('#annotate-scope-label')).to_contain_text('nothing selected')
    for tab in ['attribute', 'collect', 'interpret']:
        expect(page.locator('[data-annotate-tab="' + tab + '"]')).to_be_visible()
    page.screenshot(path=str(gui_artifacts / 'prompt15-existing-annotate-drawer.png'), full_page=True)
    page.goto(origin + '/pipeline/sources')
    expect(page.get_by_role('heading', level=1)).to_be_visible()
    assert not any(method not in ('GET', 'HEAD') for method, _ in app.extensions['gui_test_requests'])


@pytest.mark.parametrize('viewport', [(1440, 900), (1280, 800), (1024, 768)])
def test_prompt16_settings_candidate(gui_page, gui_artifacts, viewport):
    page, origin, _ = gui_page
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    page.goto(origin + '/settings')
    expect(page.locator('.settings-container')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(gui_artifacts / f'prompt16-settings-{viewport[0]}x{viewport[1]}.png'), full_page=True)
