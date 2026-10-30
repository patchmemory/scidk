"""Real workspace UI + real ledger/policy/CanvasService over loopback fixtures."""
import json
import sqlite3
import threading
import re
from urllib.parse import unquote

import pytest
from flask import g, jsonify, request
from jinja2 import FileSystemLoader
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.knowledge_e2e.conftest import scenario, ROOT, SCOPE, OTHER_SCOPE
from tests.knowledge_e2e.test_workspace import workspace, accept
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.projection import ContextService


@pytest.fixture
def gui_server(workspace):
    d, _ = workspace
    app = d.app
    app.jinja_loader = FileSystemLoader(str(ROOT / 'scidk/ui/templates'))
    app.static_folder = str(ROOT / 'scidk/ui/static')
    app.extensions['gui_test_requests'] = []

    @app.before_request
    def record_request():
        app.extensions['gui_test_requests'].append((request.method, request.full_path))

    @app.get('/api/auth/status')
    def auth_status():
        return jsonify(authenticated=True, auth_enabled=True, username=getattr(g, 'scidk_user', 'alice'))

    @app.get('/api/settings/security/auto-lock')
    def lock_config():
        return jsonify(status='success', config={'enabled': False})

    records = d.mapped_assertions(); accept(d, records)
    hidden = d.mapped_assertions(scope=OTHER_SCOPE, actor='fixture-importer'); accept(d, hidden)
    app.extensions['workspace_fixture'] = (d, records, hidden)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown(); thread.join(timeout=5); server.server_close()


def open_workspace(gui_page, query=''):
    page, origin, app = gui_page
    page.add_init_script('''{
      let seed = 12345;
      Math.random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    }''')
    d, records, hidden = app.extensions['workspace_fixture']
    page.context.add_cookies([{'name': 'scidk_session', 'value': d.auth.create_user_session(d.alice, 'alice'), 'url': origin}])
    page.goto(origin + '/knowledge' + query)
    expect(page.locator('#kw-status')).not_to_contain_text('Checking')
    return page, d, records, hidden


def search_person(page):
    page.locator('#kw-search').fill('Synthetic Investigator')
    page.locator('#kw-search-button').click()
    expect(page.locator('#kw-entities button')).to_have_count(1)
    page.get_by_role('tab', name='Entities', exact=True).click()
    page.locator('#kw-entities button').click()
    expect(page.locator('#kw-inspection')).to_contain_text('Dr Synthetic Investigator')


def cy(page, expression, sketch=False):
    container = 'kw-sketch' if sketch else 'kw-graph'
    return page.evaluate('(function(){const cy = document.getElementById(' + json.dumps(container) + ')._cyreg.cy; return (' + expression + ');})()')


def test_research_graph_inspector_layout_and_saved_positions(gui_page, gui_artifacts):
    page, _, records, hidden = open_workspace(gui_page)
    search_person(page)
    expect(page.locator('#kw-inspection')).to_contain_text('accepted')
    assert hidden['pi']['claim']['entity_ref'] not in page.locator('#knowledge-workspace').inner_text()
    page.locator('#kw-show-graph').click()
    page.locator('#kw-expand').click()
    expect(page.locator('#kw-entities button')).to_have_count(2)
    assert cy(page, 'cy.edges().length') == 1
    page.locator('#kw-advanced summary').click()
    page.locator('#kw-edge-filter').select_option('PI_OF')
    page.locator('#kw-algorithm').select_option('circle'); page.locator('#kw-apply-layout').click()
    cy(page, 'cy.nodes()[0].position({x: 145,y: 202})')
    before = cy(page, 'cy.nodes()[0].position()')
    page.locator('#kw-save-graph').click(); expect(page.locator('#kw-status')).to_contain_text('Saved private graph')
    page.locator('#kw-layout').select_option('three')
    expect(page.locator('#kw-sketch-pane')).to_be_visible()
    assert cy(page, 'cy.width()') > 0
    page.locator('#kw-save-layout').click(); expect(page.locator('#kw-status')).to_contain_text('Saved private layout')
    page.reload(); expect(page.locator('#kw-layout')).to_have_value('three')
    page.locator('#kw-load-graph').click(); expect(page.locator('#kw-status')).to_contain_text('Reopened private graph')
    assert cy(page, 'cy.nodes()[0].position()') == before
    page.screenshot(path=str(gui_artifacts / 'knowledge-research-three-panes.png'), full_page=True)
    assert cy(page, 'cy.edges()[0].data("record").id') == records['PI_OF']['fact_id']


def test_sketch_nodes_edges_notes_and_private_persistence(gui_page, gui_artifacts):
    page, _, _, _ = open_workspace(gui_page)
    page.get_by_role('tab', name='Sketch', exact=True).click()
    page.locator('#kw-draft-tools summary').click()
    page.locator('#kw-draft-name').fill('Unresolved acquisition'); page.locator('#kw-add-node').click()
    page.locator('#kw-draft-name').fill('Proposed workflow'); page.locator('#kw-add-node').click()
    ids = cy(page, 'cy.nodes().map(n=>n.id())', True)
    page.locator('#kw-edge-source').fill(ids[0]); page.locator('#kw-edge-target').fill(ids[1])
    page.locator('#kw-edge-type').fill('MAY_REQUIRE'); page.locator('#kw-add-edge').click()
    page.locator('#kw-arrange-draft').click()
    assert cy(page, 'cy.edges().length', True) == 1
    cy(page, 'cy.nodes()[0].select()', True)
    page.locator('#kw-marker').select_option(label='suggested investigation'); page.locator('#kw-set-marker').click()
    page.locator('#kw-notes').fill('A private draft; no evidence or decision implied.')
    page.locator('#kw-save-sketch').click(); expect(page.locator('#kw-status')).to_contain_text('Saved private sketch')
    page.reload(); page.get_by_role('tab', name='Sketch', exact=True).click()
    page.locator('#kw-load-sketch').click(); expect(page.locator('#kw-status')).to_contain_text('Reopened private sketch')
    assert cy(page, 'cy.nodes().length', True) == 2 and cy(page, 'cy.edges().length', True) == 1
    page.locator('#kw-draft-tools summary').click()
    expect(page.locator('#kw-notes')).to_have_value('A private draft; no evidence or decision implied.')
    expect(page.get_by_role('button', name='Submit proposal', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Commit to graph', exact=True)).to_be_disabled()
    page.screenshot(path=str(gui_artifacts / 'knowledge-research-sketch.png'), full_page=True)


def test_domain_contexts_system_traversal_and_conflict_display(gui_page, gui_artifacts):
    page, d, _, _ = open_workspace(gui_page)
    page.locator('#kw-domain').select_option('system')
    expect(page.locator('#kw-entities')).to_contain_text('workflow:csv-import')
    page.get_by_role('tab', name='Entities', exact=True).click()
    page.locator('#kw-entities button').filter(has_text='workflow:csv-import').click()
    expect(page.locator('#kw-inspection')).to_contain_text('sources')
    page.locator('#kw-show-graph').click(); page.locator('#kw-expand').click()
    expect(page.locator('#kw-entities')).to_contain_text('code:mapping')
    page.screenshot(path=str(gui_artifacts / 'knowledge-system-workflow.png'), full_page=True)
    page.locator('#kw-domain').select_option('ontology')
    expect(page.locator('#kw-entities')).to_contain_text('label:Person')
    page.get_by_role('tab', name='Entities', exact=True).click()
    page.locator('#kw-entities button').filter(has_text='label:Person').first.click()
    expect(page.locator('#kw-inspection')).to_contain_text('ontology_version')
    page.screenshot(path=str(gui_artifacts / 'knowledge-ontology-entities.png'), full_page=True)
    projection = ontology_projection([], [{'name': 'Conflict', 'properties': [],
        'relationships': [{'type': 'BAD', 'to_label': 'Missing'}]}], revision='fixture-conflict',
        bindings={'catalog': SCOPE, 'sqlite:Conflict': SCOPE})
    for node in projection.snapshot()['nodes']:
        d.policy.grant_evidence(d.alice, ContextService.grant_id(node), admin_id=d.reviewer)
    d.knowledge.ontologies['canonical'] = ContextService(projection, d.db, enabled=True)
    page.locator('#kw-context-id').fill('ontology:catalog'); page.locator('#kw-context-form button').click()
    expect(page.locator('#kw-blockers')).to_contain_text('not authoritative')
    assert 'label:Person' not in page.locator('#kw-entities').inner_text()
    page.screenshot(path=str(gui_artifacts / 'knowledge-ontology-conflict.png'), full_page=True)


def test_context_link_revocation_and_no_stale_inspector(gui_page):
    page, d, records, _ = open_workspace(gui_page)
    search_person(page)
    assert records['pi']['claim']['entity_ref'] in unquote(page.url)
    page.locator('#kw-review-link').click()
    expect(page).to_have_url(re.compile('/review\\?domain=research&id='))
    page.go_back(); search_person(page)
    page.gui_expected_http.add('/api/knowledge/research/inspect')
    page.gui_expected_http.add('/api/knowledge/system/load')
    page.gui_expected_http.add('/api/knowledge/system/context')
    with sqlite3.connect(d.db) as conn:
        conn.execute('DELETE FROM agent_resource_grant WHERE user_id=?', (d.alice,))
    page.locator('#kw-entities button').click()
    expect(page.locator('#kw-status')).to_contain_text('Knowledge access was refused')
    expect(page.locator('#kw-inspection')).to_have_text('')
    expect(page.locator('#kw-entities button')).to_have_count(0)
    page.locator('#kw-domain').select_option('system')
    page.gui_expected_http.add('/api/knowledge/system/context')
    expect(page.locator('#kw-inspection')).to_have_text('')
    expect(page.locator('#kw-notes')).to_have_value('')


def test_hidden_property_refreshes_graph_and_entity_previews(gui_page):
    page, d, _, _ = open_workspace(gui_page)
    search_person(page)
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Person','name','hidden')")
    page.locator('#kw-entities button').click()
    expect(page.locator('#kw-inspection')).not_to_contain_text('Dr Synthetic Investigator')
    expect(page.locator('#kw-entities')).not_to_contain_text('Dr Synthetic Investigator')
    assert 'Dr Synthetic Investigator' not in cy(page, 'cy.nodes().map(n => n.data("label"))')


@pytest.mark.parametrize('domain', ['system', 'ontology'])
def test_domain_sketch_and_responsive_split(gui_page, gui_artifacts, domain):
    page, _, _, _ = open_workspace(gui_page, '?domain=' + domain)
    expect(page.locator('#kw-entities button').first).to_be_attached()
    page.get_by_role('tab', name='Entities', exact=True).click()
    page.locator('#kw-entities button').first.click()
    expect(page.locator('#kw-inspection')).to_contain_text('sources')
    page.get_by_role('tab', name='Sketch', exact=True).click()
    page.locator('#kw-draft-tools summary').click()
    page.locator('#kw-add-reference').click()
    expect(page.locator('#kw-status')).to_contain_text('Stable reference added')
    reference = cy(page, 'cy.nodes()[0].data()', True)
    assert reference['reference_version']
    page.get_by_role('tab', name='Graph', exact=True).click()
    page.locator('#kw-save-graph').click()
    expect(page.locator('#kw-status')).to_contain_text('Saved private graph')
    page.locator('#kw-load-graph').click()
    expect(page.locator('#kw-status')).to_contain_text('Reopened private graph')
    page.set_viewport_size({'width': 1024, 'height': 768})
    page.locator('#kw-layout').select_option('split')
    page.get_by_role('tab', name='Sketch', exact=True).click()
    expect(page.locator('#kw-graph-pane')).to_be_visible()
    expect(page.locator('#kw-sketch-pane')).to_be_visible()
    page.locator('#kw-draft-name').fill('Exploratory ' + domain + ' adaptation')
    page.locator('#kw-add-node').click()
    page.locator('#kw-save-sketch').click(); expect(page.locator('#kw-status')).to_contain_text('Saved private sketch')
    page.reload(); page.get_by_role('tab', name='Sketch', exact=True).click()
    page.locator('#kw-load-sketch').click(); expect(page.locator('#kw-status')).to_contain_text('Reopened private sketch')
    assert cy(page, 'cy.nodes().length', True) == 2
    assert cy(page, 'cy.nodes().filter(n => !!n.data("reference"))[0].data("reference_version")', True) == reference['reference_version']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(gui_artifacts / ('knowledge-' + domain + '-sketch-1024.png')), full_page=True)


def test_visual_draft_placement_connection_and_inspector(gui_page, gui_artifacts):
    page, _, _, _ = open_workspace(gui_page)
    page.get_by_role('tab', name='Sketch', exact=True).click()
    canvas = page.locator('#kw-sketch')
    page.get_by_role('button', name='Place a node', exact=True).click()
    canvas.click(position={'x': 140, 'y': 100})
    page.get_by_role('button', name='Place a node', exact=True).click()
    canvas.click(position={'x': 340, 'y': 180})
    assert cy(page, 'cy.nodes().length', True) == 2
    page.get_by_role('button', name='Connect drafts', exact=True).click()
    canvas.click(position={'x': 140, 'y': 100}); canvas.click(position={'x': 340, 'y': 180})
    assert cy(page, 'cy.edges().length', True) == 1
    canvas.click(position={'x': 140, 'y': 100})
    page.get_by_label('Draft name', exact=True).fill('Synthetic visual idea')
    page.get_by_role('button', name='Update selected draft').click()
    assert cy(page, 'cy.nodes()[0].data("properties").name', True) == 'Synthetic visual idea'
    page.get_by_role('button', name='Save private draft', exact=True).click()
    expect(page.locator('#kw-status')).to_contain_text('Saved private sketch')
    page.screenshot(path=str(gui_artifacts / 'prompt16-visual-sketch.png'), full_page=True)
    page.reload(); page.get_by_role('tab', name='Sketch', exact=True).click()
    page.get_by_role('button', name='Reopen private draft', exact=True).click()
    expect(page.locator('#kw-status')).to_contain_text('Reopened private sketch')
    assert cy(page, 'cy.edges().length', True) == 1


@pytest.mark.parametrize('viewport', [(1440, 900), (1280, 800), (1024, 768)])
def test_prompt16_knowledge_canvas_candidate(gui_page, gui_artifacts, viewport):
    page, _, _, _ = open_workspace(gui_page)
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    search_person(page)
    page.get_by_role('tab', name='Graph', exact=True).click()
    assert not page.locator('#kw-advanced').evaluate('el => el.open')
    expect(page.get_by_role('button', name='Fit canvas')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(gui_artifacts / f'prompt16-knowledge-{viewport[0]}x{viewport[1]}.png'), full_page=True)
