"""Chromium checks: Chat is a shared workspace (real browser Back, Overview/Review links, unsent draft kept) and the
collection pill opens the existing collection panel where the active collection can be cleared."""
import json

from playwright.sync_api import expect
from tests.gui.test_workflows import *  # noqa: F401,F403  (reuse the gui_page fixture)

COLLECTION = {'id': 'c1', 'name': 'Synthetic set', 'description': '', 'members': 2, 'datasets': 2}


def stub_collections(page):
    detail = {'collection': COLLECTION, 'members': {'dataset': [{'name': 'ds-a'}, {'name': 'ds-b'}]}}
    page.route('**/api/collections', lambda route: route.fulfill(json={'collections': [COLLECTION]}))
    page.route('**/api/collections/c1', lambda route: route.fulfill(json=detail))
    page.add_init_script("if (!localStorage.getItem('scidk.collection.opened.v1')) localStorage.setItem('scidk.collection.opened.v1', JSON.stringify({id:'c1',name:'Synthetic set',description:'',total:2}))")


def test_browser_back_returns_to_the_actual_prior_page_and_links_are_destinations(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/review')
    page.get_by_test_id('discuss-evaluate').click()                      # opens the inset workbench: no navigation
    expect(page.get_by_test_id('chat-workbench')).to_be_visible()
    expect(page).to_have_url(origin + '/review')
    page.get_by_test_id('chat-open-full').click()                        # a deliberate move to the full page
    expect(page).to_have_url(origin + '/review?view=guidance')
    expect(page.get_by_test_id('guidance-back')).to_have_count(0)
    page.go_back()
    expect(page).to_have_url(origin + '/review')
    page.goto(origin + '/overview')
    page.get_by_test_id('home-advanced-link').click()
    expect(page).to_have_url(origin + '/review/guidance#advanced-query')
    page.go_back()
    expect(page).to_have_url(origin + '/overview')
    page.go_forward()
    page.get_by_test_id('chat-link-overview').click()
    expect(page).to_have_url(origin + '/overview')
    page.go_back()
    page.get_by_test_id('chat-link-review').click()
    expect(page).to_have_url(origin + '/review')


def test_unsent_chat_draft_survives_advanced_toggle_and_prefill_arrives_unsent(gui_page):
    page, origin, app = gui_page
    page.goto(origin + '/review')
    page.get_by_test_id('discuss-curate').click()
    box = page.get_by_test_id('guidance-input')
    assert 'curating a collection' in box.input_value()
    expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
    box.fill('my unsent draft')
    summary = page.locator('#advanced-query > summary')
    summary.click()
    expect(page.locator('#overview-question')).to_be_visible()
    summary.click()
    expect(page.locator('#overview-question')).not_to_be_visible()
    assert box.input_value() == 'my unsent draft'
    expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
    assert page.evaluate("localStorage.length + sessionStorage.length + document.cookie.length") == 0


def test_collection_pill_opens_panel_and_clear_selection_keeps_the_collection(gui_page):
    page, origin, _ = gui_page
    stub_collections(page)
    page.goto(origin + '/review')
    pill = page.get_by_test_id('collection-basket-pill')
    expect(pill).to_have_text('Collection: Synthetic set \u00b7 2 members')
    expect(pill).to_have_attribute('aria-expanded', 'false')
    expect(pill).to_have_attribute('aria-haspopup', 'dialog')
    pill.focus()
    page.keyboard.press('Enter')
    panel = page.get_by_test_id('collection-basket-panel')
    expect(panel).to_be_visible()
    expect(pill).to_have_attribute('aria-expanded', 'true')
    expect(panel.locator('[data-action="open-collection"]')).to_have_count(1)     # switching = opening a saved collection
    page.get_by_test_id('collection-clear-selection').click()
    expect(pill).to_have_text('Collection \u00b7 0 picks')
    assert page.evaluate("localStorage.getItem('scidk.collection.opened.v1')") is None
    expect(panel.locator('.cb-card')).to_have_count(1)                              # the saved collection itself is untouched
    page.keyboard.press('Escape')
    expect(panel).not_to_be_visible()
    expect(pill).to_be_focused()
