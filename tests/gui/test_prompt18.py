"""Same frontend and actual Prompt 17 ledger, assembled by operational hook."""
import pytest
from playwright.sync_api import expect

from tests.gui.test_prompt17 import gui_server
from tests.knowledge_e2e.test_prompt15 import fake_provider
from scidk.services.operational_knowledge import assemble
from scidk.services.human_policy import HumanPolicyStore
from scidk.core.auth import AuthManager


@pytest.mark.parametrize('viewport', [(1440, 900), (1024, 768)])
def test_operational_assembly_frontend(gui_page, gui_artifacts, viewport):
    page, origin, app = gui_page
    info = app.extensions['prompt17_demo']
    legacy = list(app.extensions['knowledge_services'].legacy._records.values())
    app.extensions.pop('knowledge_services'); app.extensions.pop('curation_review')
    assemble(app, ledger_path=info['ledger'].path, ontology=info['ledger'].ontology,
             graph_target=info['graph'].target, legacy_records=legacy)
    page.context.add_cookies([{'name': 'scidk_session', 'value': app.extensions['prompt17_session'], 'url': origin}])
    page.set_viewport_size(dict(width=viewport[0], height=viewport[1]))
    page.goto(origin + '/knowledge?view=entities')
    dataset = page.locator('#kw-entities button').filter(has_text='Synthetic MRI microCT phantom study')
    expect(dataset).to_have_count(1)
    dataset.click()
    expect(page.locator('#kw-selection-title')).to_have_text('Synthetic MRI microCT phantom study')
    expect(page.locator('#kw-trust')).to_contain_text('Accepted and applied')
    page.locator('#kw-inspector details').click()
    expect(page.locator('#kw-inspection')).to_contain_text('Fictional MRI/microCT')
    page.screenshot(path=str(gui_artifacts / f'prompt18-entities-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.locator('#kw-show-graph').click()
    page.locator('#kw-expand').click()
    page.locator('#kw-advanced').evaluate('(e) => e.open = true')
    expect(page.locator('#kw-edge-filter option[value="CONTAINS"]')).to_have_count(1)
    page.locator('#kw-edge-filter').select_option('CONTAINS')
    expect(page.locator('#kw-entities button')).to_have_count(4)  # includes permitted legacy result
    page.screenshot(path=str(gui_artifacts / f'prompt18-graph-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.locator('#kw-show-entities').click()
    page.locator('#kw-entities button').filter(has_text='File').first.click()
    expect(page.locator('#kw-inspection')).to_contain_text('relative_path')
    page.locator('#kw-search').fill('legacy phantom')
    page.locator('#kw-search-button').click()
    expect(page.locator('#kw-entities button')).to_have_count(1)
    page.locator('#kw-entities button').click()
    expect(page.locator('#kw-trust')).to_contain_text('Legacy / unreviewed')
    expect(page.locator('#kw-inspection')).to_contain_text('unverified')
    db = app.config['SCIDK_SETTINGS_DB']
    auth = AuthManager(db)
    uid = auth.get_user_by_username('demo-admin')['id']
    auth.close()
    HumanPolicyStore(db).grant_purpose(uid, 'research_browse', 'low', admin_id=uid, allow=False)
    page.gui_expected_http.add('/api/knowledge/research/search')
    page.locator('#kw-search-button').click()
    expect(page.locator('#kw-entities button')).to_have_count(0)
    expect(page.locator('#kw-status')).to_contain_text('research_browse')
    app.extensions.pop('knowledge_services')
    page.locator('#kw-search-button').click()
    expect(page.locator('#kw-status')).to_contain_text('/api/knowledge/readiness')
    # Request native pages without loading their external legacy script assets.
    for route in ('/entities', '/entities?tab=relationships', '/map'):
        assert page.request.get(origin + route).status == 200
