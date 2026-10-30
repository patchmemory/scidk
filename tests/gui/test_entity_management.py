"""Mature Labels/Links UI against a separately created disposable Neo4j.

Requires explicit SCIDK_TEST_DISPOSABLE_NEO4J_URI. Never uses app/operational env.
"""
import os
import threading
import pytest
from werkzeug.serving import make_server
from playwright.sync_api import expect

from scidk.core.auth import AuthManager
from scidk.dev_gui import build_app
from scidk.services.label_service import LabelService
from scidk.services.graph_management_policy import ManagementPolicyStore, connection_key


@pytest.fixture
def gui_server(tmp_path, monkeypatch):
    uri = os.environ.get('SCIDK_TEST_DISPOSABLE_NEO4J_URI')
    if not uri:
        pytest.skip('Explicit disposable Neo4j URI required; operational config is never used')
    assert uri.startswith('bolt://127.0.0.1:')
    for key in ('NEO4J_URI', 'BOLT_URI', 'CHAT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_URI',
                'NEO4J_AUTH', 'CHAT_NEO4J_AUTH', 'SCIDK_CONCEPT_NEO4J_AUTH'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / 'scidk_settings.db')
    auth = AuthManager(db)
    admin = auth.create_user('operator', 'disposable-password', role='admin')
    user = auth.create_user('researcher', 'disposable-password', role='user')
    app = build_app(tmp_path)
    monkeypatch.setenv('NEO4J_AUTH', 'none')
    app.extensions['scidk']['neo4j_config'] = dict(uri=uri, user=None, database='neo4j')
    target = connection_key(uri, None, 'neo4j', 'none')
    app.config['SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS'] = [target]
    policy = ManagementPolicyStore(db); policy.initialize(admin_id=admin)
    for permission in ('graph_management_read', 'graph_entity_write', 'graph_schema_write'):
        policy.grant(user, target, permission, admin_id=admin)
    from neo4j import GraphDatabase
    with GraphDatabase.driver(uri, auth=None) as driver:
        with driver.session(database='neo4j') as session:
            session.run('MATCH (n:Prompt1802Fixture) DETACH DELETE n').consume()
            session.run('CREATE (s:SyntheticSpecimen:Prompt1802Fixture {name:"Fictional specimen"}), '
                        '(i:SyntheticImage:Prompt1802Fixture {name:"Fictional image"}), '
                        '(s)-[:HAS_IMAGE]->(i), (i)-[:DERIVED_FROM]->(s)').consume()
    with app.app_context():
        service = LabelService(app)
        service.save_label(dict(name='SyntheticSpecimen', properties=[dict(name='name', type='string')],
            relationships=[dict(type='HAS_IMAGE', target_label='SyntheticImage')]))
        service.save_label(dict(name='SyntheticImage', properties=[dict(name='name', type='string')],
            relationships=[dict(type='DERIVED_FROM', target_label='SyntheticSpecimen')]))
    app.extensions['management_test'] = dict(session=auth.create_user_session(user, 'researcher'),
        policy=policy, user=user, admin=admin, target=target)
    app.extensions['gui_test_requests'] = []
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown(); thread.join(timeout=5); server.server_close(); auth.close()


@pytest.mark.parametrize('viewport', [(1440, 900), (1024, 768)])
def test_original_entity_management(gui_page, gui_artifacts, viewport):
    page, origin, app = gui_page
    info = app.extensions['management_test']
    page.context.add_cookies([dict(name='scidk_session', value=info['session'], url=origin)])
    page.set_viewport_size(dict(width=viewport[0], height=viewport[1]))
    # No governed purpose/provider is needed for separately granted management.
    page.gui_expected_http.update(['/api/knowledge/research/load', '/api/knowledge/research/search'])
    page.goto(origin + '/knowledge?view=entities')
    page.get_by_role('navigation', name='Research tools').get_by_role('link', name='Entities & Labels').click()
    page.locator('#label-list .label-item').filter(has_text='SyntheticSpecimen').click()
    expect(page.locator('#readonly-properties-container')).to_contain_text('name')
    expect(page.locator('#readonly-relationships-container')).to_contain_text('HAS_IMAGE')
    expect(page.locator('#readonly-incoming-relationships-container')).to_contain_text('DERIVED_FROM')
    expect(page.locator('#toast-container').locator(':scope > *')).to_have_count(0)
    page.screenshot(path=str(gui_artifacts / f'management-labels-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.locator('#toggle-with-relationships').check()
    page.locator('#btn-pull-instances').click()
    expect(page.locator('#instance-table-container')).to_contain_text('Fictional specimen')
    expect(page.locator('#instance-table-container')).to_contain_text('2 relationships')
    page.locator('#instance-table-container [id$="-badge"]').click()
    expect(page.locator('#instance-table-container')).to_contain_text('HAS_IMAGE')
    expect(page.locator('#instance-table-container')).to_contain_text('DERIVED_FROM')
    page.locator('#instance-table-container').evaluate("el => el.scrollIntoView({block:'center'})")
    expect(page.locator('#toast-container').locator(':scope > *')).to_have_count(0)
    page.screenshot(path=str(gui_artifacts / f'management-entities-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    response = page.request.get(origin + '/api/labels/SyntheticSpecimen/instances?with_relationships=true')
    node = response.json()['instances'][0]
    page.locator('.instance-cell-editable[data-prop="name"]').fill('Fictional edited specimen')
    page.locator('#editor-title').click()
    page.locator('#btn-push-instances').click()
    with page.expect_response(lambda response: response.request.method == 'PATCH') as updated:
        page.locator('#confirm-modal-action-btn').click()
    assert updated.value.status == 200
    with page.expect_response('**/api/labels/SyntheticSpecimen/instances?*'):
        page.locator('#btn-refresh-instances').click()
    page.wait_for_load_state('networkidle')
    expect(page.locator('#instance-table-container')).to_contain_text('Fictional edited specimen')
    page.locator('#instance-table-container [id$="-badge"]').click()
    page.locator('.related-instance').first.click()
    expect(page.locator('#instance-table-container')).to_contain_text('Fictional image')
    expect(page.locator('#toast-container').locator(':scope > *')).to_have_count(0)
    page.screenshot(path=str(gui_artifacts / f'management-inspector-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    saved = page.request.post(origin + '/api/maps/saved', data=dict(name='Synthetic saved view'))
    assert saved.status == 201
    page.get_by_role('link', name='Open in Graph', exact=True).click()
    expect(page.locator('#map-list')).to_contain_text('Synthetic saved view')
    expect(page.get_by_role('link', name='Return to entity inspector')).to_be_visible()
    expect(page.locator('#tab-content-area')).to_be_visible()
    assert page.evaluate('Object.values(window.cytoscapeInstances || {}).some(cy => cy.nodes().some(n => n.data("displayLabel") === "Fictional image"))')
    expect(page.locator('#toast-container').locator(':scope > *')).to_have_count(0)
    page.screenshot(path=str(gui_artifacts / f'management-map-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#map-list').get_by_role('button', name='Load', exact=True).click()
    page.get_by_role('link', name='Return to entity inspector').click()
    expect(page.locator('#instance-table-container')).to_contain_text('Fictional image')
    with page.expect_response('**/api/links/discovered') as discovery:
        page.get_by_role('navigation', name='Research tools').get_by_role('link', name='Relationships & Links').click()
    assert discovery.value.status == 200
    expect(page.locator('#links-container, .links-container').first).to_be_visible()
    page.locator('.link-filter-tab[data-filter="available"]').click()
    expect(page.locator('#link-list')).to_contain_text('HAS_IMAGE')
    expect(page.locator('#toast-container').locator(':scope > *')).to_have_count(0)
    page.screenshot(path=str(gui_artifacts / f'management-relationships-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.wait_for_load_state('networkidle')
    info['policy'].grant(info['user'], info['target'], 'graph_management_read', admin_id=info['admin'], allow=False)
    assert page.request.get(origin + '/api/labels').status == 403
    assert page.request.patch(origin + '/api/labels/SyntheticSpecimen/instances/' + node['id'],
                              data=dict(property='name', value='denied')).status == 403
