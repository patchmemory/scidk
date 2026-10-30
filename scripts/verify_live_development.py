"""Acceptance against an already running operator runtime, never a fixture server.

Traces contain session cookies: keep the output inside the private state directory.
No graph writes or model calls are made. Only existing non-personal Sample stub
metadata is used; scientific content and person/investigator records are excluded.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

# This virtualenv also serves another checkout; pin this script's repository.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--artifacts', required=True, help='New subdirectory within private state')
    args = parser.parse_args()
    state = Path(args.state_dir).resolve()
    artifacts = Path(args.artifacts).resolve()
    if state not in artifacts.parents:
        parser.error('Keep cookie-bearing traces within the private state directory')
    artifacts.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = json.loads((state / 'runtime.json').read_text())
    login = json.loads((state / 'operator-login.json').read_text())
    origin = f'http://127.0.0.1:{config["port"]}'
    report = dict(origin=origin, connection_id=config['connection_key'], capabilities={},
                  scope='Existing development graph; bounded imported Sample/SampleType metadata only; no seeding')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome'))
        context = browser.new_context(viewport=dict(width=1440, height=900), locale='en-US', timezone_id='UTC')
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
        page.goto(origin + '/login')
        page.locator('#username').fill(login['username'])
        page.locator('#password').fill(login['password'])
        page.get_by_test_id('login-submit').click()
        page.wait_for_url(lambda url: '/login' not in url)
        report['capabilities']['login'] = 'PASS'
        # Start after credentials have left the login form; the trace still has
        # cookies and therefore remains private, never committed or exported.
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        try:
            response = page.request.post(origin + '/api/development/readiness', data={})
            assert response.status == 200
            checks = response.json()['checks']
            assert checks['runtime']['profile'] == 'live-development-readonly'
            assert checks['graph']['connection_id'] == config['connection_key']
            assert checks['graph']['status'] == 'ready'
            assert checks['graph']['grants']['graph_entity_write'] is False
            assert checks['graph']['grants']['graph_schema_write'] is False
            report['readiness'] = checks
            page.goto(origin + '/admin/development-readiness')
            expect(page.locator('#development-readiness')).to_contain_text('"reachability": "connected"')
            page.screenshot(path=str(artifacts / 'live-readiness.png'), full_page=True)
            page.goto(origin + '/knowledge?view=entities')
            page.get_by_role('navigation', name='Research tools').get_by_role('link', name='Entities & Labels').click()
            expect(page.locator('#management-connection')).to_contain_text(config['connection_key'][:12])
            page.locator('#label-list .label-item').filter(has_text='Sample').filter(has_not_text='SampleType').click()
            expect(page.locator('#readonly-properties-container')).to_contain_text('uuid')
            expect(page.locator('#readonly-relationships-container')).to_contain_text('OF_TYPE')
            report['capabilities']['labels_and_property_types'] = 'PASS'
            page.screenshot(path=str(artifacts / 'live-labels-1440x900.png'), full_page=True)
            # Independently identify one existing, non-personal metadata example
            # on the approved backend; do not rely on arbitrary first-page order.
            # This is a fixed read query, not an HTTP raw-query permission.
            from scidk.live_development import load
            from neo4j import GraphDatabase, READ_ACCESS, Query
            _, connection, graph_password = load(state)
            graph_auth = None if connection['auth_mode'] == 'none' else (connection['user'], graph_password)
            query = ("MATCH (:Sample)-[:DERIVED_FROM]->(n:Sample)-[:OF_TYPE]->(:SampleType) "
                     "WHERE all(k IN keys(n) WHERE k IN ['uuid','_imported_stub']) "
                     "AND NOT EXISTS { MATCH (n)--(other) WHERE any(l IN labels(other) WHERE NOT l IN ['Sample','SampleType']) } "
                     "RETURN elementId(n) AS id LIMIT 1")
            with GraphDatabase.driver(connection['uri'], auth=graph_auth, connection_timeout=5) as driver:
                with driver.session(database=connection['database'], default_access_mode=READ_ACCESS) as session:
                    reference = session.run(Query(query, timeout=5)).single()
            assert reference, 'No non-personal existing metadata example; do not broaden content access automatically'
            instances = page.request.get(origin + '/api/labels/Sample/instances?limit=1&with_relationships=true&instance_id=' + reference['id'])
            assert instances.status == 200
            selected = instances.json()['instances'][0]
            assert selected['id'] == reference['id']
            assert set(selected['properties']) <= {'uuid', '_imported_stub'}
            assert all(set(r.get('neighbor_labels') or []) <= {'Sample', 'SampleType'} for r in selected.get('relatedTo', []))
            assert {r['direction'] for r in selected['relatedTo']} == {'in', 'out'}
            report['independent_backend_match'] = True
            page.goto(origin + '/entities?tab=entities&management_label=Sample&management_id=' + selected['id'])
            expect(page.locator('#instance-table-container')).to_contain_text('Open in Graph')
            page.locator('#instance-table-container [id$="-badge"]').click()
            expect(page.locator('.related-instance').first).to_be_visible()
            report['capabilities']['instances_properties_incoming_outgoing'] = 'PASS'
            expect(page.locator('#toast-container > *')).to_have_count(0)
            page.wait_for_load_state('networkidle')
            page.locator('#instance-table-container').evaluate("el => el.scrollIntoView({block: 'center'})")
            page.screenshot(path=str(artifacts / 'live-entities-1440x900.png'), full_page=True)
            page.locator('.related-instance').first.click()
            expect(page.locator('#instance-table-container')).to_contain_text('Open in Graph')
            page.wait_for_load_state('networkidle')
            report['capabilities']['related_entity_selection'] = 'PASS'
            for width, height in [(1440, 900), (1024, 768)]:
                page.set_viewport_size(dict(width=width, height=height))
                expect(page.locator('#toast-container > *')).to_have_count(0)
                page.locator('#instance-table-container').evaluate("el => el.scrollIntoView({block: 'center'})")
                page.screenshot(path=str(artifacts / f'live-inspector-{width}x{height}.png'), full_page=True)
            page.get_by_role('link', name='Open in Graph', exact=True).click()
            expect(page.get_by_role('link', name='Return to entity inspector')).to_be_visible()
            expect(page.locator('#neo4j-connection-select')).to_contain_text(config['connection_key'][:12])
            assert page.locator('#neo4j-connection-select').input_value() == 'PRIMARY'
            assert page.evaluate('Object.values(window.cytoscapeInstances || {}).some(cy => cy.nodes().length > 0)')
            expect(page.locator('#save-current-map')).to_be_visible()
            def map_dialog(dialog):
                dialog.accept('Live development metadata view' if 'map name' in dialog.message else
                              'Existing development metadata; graph unchanged' if dialog.type == 'prompt' else None)
            page.on('dialog', map_dialog)
            if not page.locator('#map-list .map-item').count():
                with page.expect_response(lambda response: response.url.endswith('/api/maps/saved') and response.request.method == 'POST') as saved:
                    page.locator('#save-current-map').click()
                assert saved.value.status == 201
            expect(page.locator('#map-list .map-item').first).to_be_visible()
            page.locator('#map-list .map-item').first.get_by_role('button', name='Load', exact=True).click()

            for width, height in [(1440, 900), (1024, 768)]:
                page.set_viewport_size(dict(width=width, height=height))
                page.screenshot(path=str(artifacts / f'live-maps-{width}x{height}.png'), full_page=True)
            page.get_by_role('link', name='Return to entity inspector').click()
            expect(page.locator('#instance-table-container')).to_contain_text('Open in Graph')
            report['capabilities']['maps_selection_and_return'] = 'PASS'
            report['capabilities']['saved_views'] = 'PASS: save/load in the new private settings store; no existing shared views modified'
            page.remove_listener('dialog', map_dialog)
            with page.expect_response('**/api/links/discovered') as discovered:
                page.get_by_role('navigation', name='Research tools').get_by_role('link', name='Relationships & Links').click()
            assert discovered.value.status == 200
            expect(page.locator('#links-container, .links-container').first).to_be_visible()
            page.locator('.link-filter-tab[data-filter="available"]').click()
            expect(page.locator('#link-list')).to_contain_text('OF_TYPE')
            page.screenshot(path=str(artifacts / 'live-relationships.png'), full_page=True)
            report['capabilities']['relationship_types'] = 'PASS'
            for name, route in [('files_datasets','/datasets'), ('resources','/pipeline/sources'),
                                ('knowledge','/knowledge'), ('review','/review'), ('ask','/overview')]:
                page.goto(origin + route)
                expect(page.get_by_role('heading', level=1).first).to_be_visible()
                if name == 'knowledge':
                    for tab in ('Graph', 'Entities', 'Sketch'):
                        page.get_by_role('tab', name=tab, exact=True).click()
                    report['capabilities'][name] = 'BLOCKED: governed source provenance unavailable; management remains independent'
                elif name in {'review', 'ask'}:
                    report['capabilities'][name] = 'BLOCKED: no governed service/source authority' + (' or approved provider; no model call made' if name == 'ask' else '')
                else:
                    report['capabilities'][name] = 'PARTIAL: live local workspace available; separate state has no imported datasets or Resources'
                page.screenshot(path=str(artifacts / f'live-{name}.png'), full_page=True)
            assert page.request.post(origin + '/api/graph/query', data=dict(query='RETURN 1')).status == 403
            assert page.request.patch(origin + '/api/labels/Sample/instances/' + selected['id'], data=dict(property='uuid', value='denied')).status == 403
            report['capabilities']['write_and_raw_query_refusal'] = 'PASS'
            report['readiness'] = page.request.post(origin + '/api/development/readiness', data={}).json()['checks']
            page.goto(origin + '/admin/development-readiness')
            expect(page.locator('#development-readiness')).to_contain_text('"reachability": "connected"')
            page.screenshot(path=str(artifacts / 'live-readiness.png'), full_page=True)
            assert not errors, 'Unexpected browser JavaScript error'
            report['browser'] = browser.version
            report['status'] = 'graph_management_gate_passed_with_remaining_workspace_blockers'
        finally:
            context.tracing.stop(path=str(artifacts / 'live-private-trace.zip'))
            (artifacts / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
            context.close()
            browser.close()
    print(json.dumps(dict(status=report['status'], capabilities=report['capabilities'])))


if __name__ == '__main__':
    main()
