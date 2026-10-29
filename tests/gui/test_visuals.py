"""Frozen initial references; candidates are always separate and need human review."""
import json
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.gui.test_workflows import open_files, select_file, select_dataset
from tests.gui.visual import difference

BASELINES = Path(__file__).parent/'baselines'
VIEWS = [(1440,900),(1280,800),(1024,768)]
SCREENS = ['overview','files','datasets','expanded-metadata','resources','knowledge','review']


@pytest.mark.parametrize('viewport', VIEWS, ids=lambda v:f'{v[0]}x{v[1]}')
@pytest.mark.parametrize('screen', SCREENS)
def test_visual_reference(gui_page, gui_artifacts, request, screen, viewport):
    page, origin, _ = gui_page
    page.set_viewport_size({'width':viewport[0],'height':viewport[1]})
    if screen in ['files','datasets','expanded-metadata']:
        open_files(page, origin)
        if screen == 'files':
            select_file(page)
        else:
            select_dataset(page)
            expect(page.get_by_role('button',name='Prepare for Sharing')).to_be_disabled()
        if screen == 'expanded-metadata':
            page.get_by_role('button',name='Expand',exact=True).click()
            expect(page.locator('#inspector-expand')).to_have_attribute('aria-expanded','true')
    else:
        page.goto(origin+{'resources':'/pipeline/sources'}.get(screen,'/'+screen))
        if screen == 'resources':
            expect(page.get_by_test_id('sources-empty')).to_be_visible()
        elif screen == 'overview':
            expect(page.get_by_role('button',name='Ask SciDK',exact=True)).to_be_disabled()
        elif screen == 'review':
            expect(page.get_by_text('Review workspace unavailable',exact=False)).to_be_visible()
    page.evaluate('document.fonts.ready')
    expect(page.locator('header nav a')).to_have_count(6)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal page overflow'
    for control in page.locator('header nav a').all():
        expect(control).to_be_in_viewport()
    if screen in ['files','datasets','expanded-metadata']:
        for control in ['#inspector-close','#inspector-expand','[data-inspector-tab="Metadata"]']:
            expect(page.locator(control)).to_be_in_viewport()
        if screen == 'datasets':
            assert page.locator('#dataset-search button').evaluate('''e => {
                const r=e.getBoundingClientRect();
                return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
            }'''), 'Dataset search is obscured by inspector'
        box = page.locator('#shared-inspector').bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= viewport[0]
        assert box['y'] >= 0 and box['y'] + box['height'] <= viewport[1]
    name = f'{screen}-{viewport[0]}x{viewport[1]}.png'
    current = page.screenshot(path=str(gui_artifacts/name),animations='disabled',caret='hide')
    if request.config.getoption('--gui-record-candidates'):
        return  # Capture-only mode is explicitly not a visual regression pass.
    reference = BASELINES/name
    assert reference.exists(), 'Missing frozen reference; capture candidates and review manually.'
    result = difference(page, reference.read_bytes(), current)
    (gui_artifacts/(name+'.diff.json')).write_text(json.dumps(result,indent=2)+'\n')
    assert not result['dimensionMismatch'] and result['ratio'] <= 0.002, result


def test_visual_change_detector(gui_page):
    page, origin, _ = gui_page
    page.goto(origin+'/overview')
    original = page.screenshot(animations='disabled')
    assert difference(page, original, original)['ratio'] == 0
    page.evaluate("document.body.style.background = '#ff0000'")
    changed = page.screenshot(animations='disabled')
    assert difference(page, original, changed)['ratio'] > 0.002
