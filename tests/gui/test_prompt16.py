"""No-ID Ask UX over real governed System services and loopback fake provider."""
import pytest
from playwright.sync_api import expect
from tests.gui.test_prompt15 import gui_server, login
from tests.knowledge_e2e.conftest import scenario
from tests.knowledge_e2e.test_prompt15 import ready_app, fake_provider


@pytest.mark.parametrize('viewport', [(1440, 900), (1280, 800), (1024, 768)])
def test_ask_discovery_consent_citations_context_and_empty(gui_page, gui_artifacts, viewport):
    page, origin, app = gui_page
    d, calls = app.extensions['prompt15_fixture']
    login(page, origin, d)
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    page.goto(origin + '/overview')
    assert page.locator('#overview-context-id').count() == 0
    page.get_by_role('button', name='Understand a workflow', exact=True).click()
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    assert not calls  # Browser validation: consent is explicit, not suggested.
    page.locator('#overview-consent').check()
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    expect(page.locator('#overview-answer')).to_contain_text('Synthetic System context')
    expect(page.locator('#overview-source-links a')).to_have_attribute('href', '/knowledge?domain=system&id=system%3Asynthetic-demo')
    expect(page.get_by_role('heading', name='AI interpretation')).to_be_visible()
    assert len(calls) == 1 and 'tools' not in calls[0][1]
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(gui_artifacts / f'prompt16-ask-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.get_by_label('Your question').fill('unfindable-topic')
    expect(page.locator('#overview-answer')).to_have_text('')
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    expect(page.locator('#overview-status')).to_contain_text('No authorized matches')
    assert len(calls) == 1
    page.goto(origin + '/overview?domain=system&id=system%3Asynthetic-demo')
    expect(page.get_by_label('Look in')).to_have_value('selection')
    page.get_by_label('Your question').fill('Explain this context')
    page.locator('#overview-consent').check()
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    expect(page.locator('#overview-answer')).to_contain_text('Synthetic System context')
    assert len(calls) == 2
    page.get_by_label('Look in').select_option('system')
    expect(page.locator('#overview-answer')).to_have_text('')
    expect(page.locator('#overview-consent')).not_to_be_checked()
