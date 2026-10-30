"""Explicit assembly must preserve existing authority and real receipt state."""
import json
import sqlite3

import pytest

from scidk.agent_tools.security import REFUSAL
from scidk.services.human_policy import HumanPolicyStore
from scidk.services.operational_knowledge import assemble, configure
from .test_prompt17_demo import integrated


def reassemble(app, **overrides):
    info = app.extensions['prompt17_demo']
    app.extensions.pop('knowledge_services', None)
    app.extensions.pop('curation_review', None)
    args = dict(ledger_path=info['ledger'].path, ontology=info['ledger'].ontology,
                graph_target=info['graph'].target)
    args.update(overrides)
    with app.app_context():
        return assemble(app, **args)


def test_assembly_uses_existing_receipts_and_never_grants(integrated):
    app, client, _, uid = integrated
    info = app.extensions['prompt17_demo']
    before = info['ledger'].path.read_bytes()
    db = app.config['SCIDK_SETTINGS_DB']
    HumanPolicyStore(db).grant_purpose(uid, 'research_browse', 'low', admin_id=uid, allow=False)
    with sqlite3.connect(db) as conn:
        grants = conn.execute('SELECT * FROM human_purpose_grant').fetchall()
    reassemble(app)
    assert client.post('/api/knowledge/research/search', json={}).json == REFUSAL
    assert info['ledger'].path.read_bytes() == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM human_purpose_grant').fetchall() == grants
    HumanPolicyStore(db).grant_purpose(uid, 'research_browse', 'low', admin_id=uid)
    result = client.post('/api/knowledge/research/expand', json={'id': info['dataset']})
    assert len(result.json['result']['edges']) == 2
    assert all(n['curation_status'] == 'accepted' for n in result.json['result']['nodes'])
    assert client.post('/api/review/queue', json={'status': 'proposed'}).status_code == 200
    with pytest.raises(ValueError, match='already assembled'):
        assemble(app, ledger_path=info['ledger'].path, ontology=info['ledger'].ontology,
                 graph_target=info['graph'].target)


def test_bad_binding_and_missing_ledger_attach_nothing(integrated, tmp_path):
    app, _, _, _ = integrated
    with pytest.raises(ValueError, match='binding'):
        reassemble(app, graph_target='wrong-target')
    assert 'knowledge_services' not in app.extensions
    missing = tmp_path / 'absent.sqlite'
    with pytest.raises(sqlite3.OperationalError):
        reassemble(app, ledger_path=missing)
    assert not missing.exists()
    assert 'curation_review' not in app.extensions


def test_manifest_reuses_pinned_catalog(integrated, tmp_path, monkeypatch):
    app, client, _, _ = integrated
    info = app.extensions['prompt17_demo']
    from pathlib import Path
    fixture = Path(__file__).parents[1] / 'fixtures/knowledge_curation'
    definitions = json.loads((fixture / 'catalog.json').read_text())
    definitions += json.loads((fixture / 'dataset_catalog.json').read_text())
    (tmp_path / 'catalog.json').write_text(json.dumps(definitions))
    config = dict(ledger_path=str(info['ledger'].path), catalog_path='catalog.json',
                  ontology_version=info['ledger'].ontology.version, graph_target=info['graph'].target)
    manifest = tmp_path / 'operational.json'
    manifest.write_text(json.dumps(config))
    monkeypatch.setenv('SCIDK_KNOWLEDGE_MANIFEST', str(manifest))
    app.extensions.pop('knowledge_services'); app.extensions.pop('curation_review')
    configure(app)
    assert client.post('/api/knowledge/research/search', json={}).json['result']['nodes']
    app.extensions.pop('knowledge_services'); app.extensions.pop('curation_review')
    config['ontology_version'] = 'wrong'
    manifest.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='Pinned ontology'):
        configure(app)


def test_readiness_current_admin_authority_and_no_source_details(integrated):
    app, client, auth, uid = integrated
    endpoint = '/api/knowledge/readiness'
    checks = client.post(endpoint, json={}).json['checks']
    assert checks['knowledge_service'] and checks['review_service']
    assert checks['resource_grants'] and checks['evidence_grants']
    assert checks['live_graph'] == 'not_probed'
    HumanPolicyStore(app.config['SCIDK_SETTINGS_DB']).grant_purpose(
        uid, 'research_browse', 'low', admin_id=uid, allow=False)
    checks = client.post(endpoint, json={}).json['checks']
    assert not checks['purpose_grant'] and checks['resource_grants'] == 'not_checked'
    app.extensions.pop('knowledge_services')
    checks = client.post(endpoint, json={}).json['checks']
    assert not checks['knowledge_service']
    for headers in ({'Authorization': 'Bearer test'}, {'Origin': 'https://elsewhere.invalid'},
                    {'Sec-Fetch-Site': 'cross-site'}):
        assert client.post(endpoint, json={}, headers=headers).json == REFUSAL
    assert app.test_client().post(endpoint, json={}).status_code in (401, 403)
    other = auth.create_user('ordinary', 'synthetic-password', role='user')
    client.set_cookie('scidk_session', auth.create_user_session(other, 'ordinary'))
    assert client.post(endpoint, json={}).json == REFUSAL
