"""Enabled product flows with synthetic HTTP replies; security tested separately."""
from playwright.sync_api import expect
from tests.gui.harness import DATASET
from tests.gui.test_workflows import open_files, select_dataset


def test_enabled_overview_renders_answer_as_text(gui_page):
    page, origin, app = gui_page
    app.config['SCIDK_OVERVIEW_CHAT_ENABLED'] = True
    sent = []
    def answer(route):
        sent.append(route.request.post_data_json)
        route.fulfill(json={'status': 'success', 'reply': '<img src=x onerror=alert(1)>',
            'notice': 'Verify sources', 'context': {'fact': {'fact_id': 'fact:demo', 'citations': ['Synthetic']}}})
    page.route('**/api/chat/overview', answer)
    page.goto(origin + '/overview?profile=review')
    page.get_by_label('Your question').fill('Explain this fact')
    page.locator('#overview-consent').check()
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    expect(page.locator('#overview-answer')).to_have_text('<img src=x onerror=alert(1)>')
    expect(page.locator('#overview-answer img')).to_have_count(0)
    expect(page.locator('#overview-sources')).to_contain_text('Synthetic')
    assert sent == [{'message': 'Explain this fact', 'send_question': True,
                     'scope': 'accessible'}]


def test_sharing_preview_edit_reset_and_download(gui_page):
    page, origin, app = gui_page
    app.config['SCIDK_DATASET_SHARING_ENABLED'] = True
    record = dict(DATASET, properties=dict(DATASET['properties'], entity_ref='entity:fixture-dataset'))
    page.route('**/api/canvas/nodes/search?*', lambda route: route.fulfill(json={'results': [record]}))
    sent = []
    def prepare(route):
        body = route.request.post_data_json
        sent.append(body)
        if body['download']:
            route.fulfill(body=b'synthetic zip response', content_type='application/zip',
                headers={'Content-Disposition': 'attachment; filename="dataset-sharing-draft.zip"'})
        else:
            route.fulfill(json={'status': 'success', 'package_ready': True, 'markdown': '# Dataset draft\nSynthetic citations',
                                'notice': 'Review file membership and investigator fields'})
    page.route('**/api/plugins/nih_dms/datasets/entity%3Afixture-dataset/prepare', prepare)
    open_files(page, origin)
    select_dataset(page)
    expect(page.locator('#dataset-knowledge')).to_have_attribute('href', '/knowledge?domain=research&id=entity%3Afixture-dataset')
    expect(page.locator('#dataset-review')).to_have_attribute('href', '/review?domain=research&id=entity%3Afixture-dataset')
    page.get_by_role('button', name='Prepare for Sharing', exact=True).click()
    page.get_by_label('Repository', exact=True).fill('Investigator repository')
    page.get_by_role('button', name='Preview dataset DMS draft').click()
    expect(page.locator('#sharing-draft')).to_contain_text('Synthetic citations')
    expect(page.locator('#sharing-download')).to_be_enabled()
    page.get_by_label('Repository', exact=True).fill('Changed repository')
    expect(page.locator('#sharing-download')).to_be_disabled()
    page.get_by_role('button', name='Preview dataset DMS draft').click()
    expect(page.locator('#sharing-download')).to_be_enabled()
    with page.expect_download() as download:
        page.locator('#sharing-download').click()
    assert download.value.suggested_filename == 'dataset-sharing-draft.zip'
    assert sent[-1]['fields']['repository'] == 'Changed repository'
    assert sent[-1]['download'] is True
    page.locator('#dataset-results button').click()
    expect(page.locator('#sharing-guide')).to_be_hidden()
    expect(page.locator('#sharing-download')).to_be_disabled()
