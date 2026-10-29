"""Legacy snapshots stay bounded, source-bound, human-only and unreviewed."""
import sqlite3

import pytest

from scidk.agent_tools.security import DisclosureDenied, REFUSAL
from scidk.services.human_legacy import LegacySnapshot
from scidk.services.human_policy import HumanPolicyStore
from .test_prompt17_demo import integrated
from .test_prompt15 import fake_provider


def test_legacy_hidden_properties_record_revocation_and_unknown_ids(integrated):
    app, client, _, uid = integrated
    info = app.extensions['prompt17_demo']
    legacy = app.extensions['knowledge_services'].legacy
    ref = next(iter(legacy._records))
    endpoint = '/api/knowledge/research/inspect'
    assert client.post(endpoint, json={'id': ref}).json['result']['nodes'][0]['curation_status'] == 'legacy/unreviewed'
    with sqlite3.connect(app.config['SCIDK_SETTINGS_DB']) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('Dataset','name','hidden')")
    assert client.post('/api/knowledge/research/search', json={'q': 'legacy phantom'}).json['result']['nodes'] == []
    assert client.post(endpoint, json={'id': ref}).json['result']['nodes'][0]['properties'] == {}
    HumanPolicyStore(app.config['SCIDK_SETTINGS_DB']).grant_evidence(uid, ref, admin_id=uid, allow=False)
    assert client.post(endpoint, json={'id': ref}).json == REFUSAL
    assert client.post(endpoint, json={'id': 'legacy:unknown'}).json == REFUSAL
    assert not info['graph'].nodes.get(ref)


def test_legacy_snapshot_cannot_release_locators_or_unbounded_input(integrated):
    app, _, _, _ = integrated
    legacy = app.extensions['knowledge_services'].legacy
    record = next(iter(legacy._records.values()))
    ledger = app.extensions['prompt17_demo']['ledger']
    for bad in ([record] * 129, [dict(record, record_key='')],
                [dict(record, properties={'path': '/private/location'})], [record, record]):
        with pytest.raises(DisclosureDenied):
            LegacySnapshot(ledger.ontology, bad, ledger=ledger)


def test_legacy_snapshot_is_excluded_from_ai_discovery(integrated, fake_provider):
    app, client, _, uid = integrated
    from scidk.ai import provider_settings
    from scidk.agent_tools.security import PolicyStore
    endpoint, calls = fake_provider
    db = app.config['SCIDK_SETTINGS_DB']
    provider_settings.save(db, 'demo-admin', base_url=endpoint, model='synthetic-model')
    PolicyStore(db).approve_destination('loopback-only', endpoint, 'synthetic-model', 'low', admin_id=uid)
    out = client.post('/api/chat/overview', json={'message': 'Find legacy phantom',
        'scope': 'accessible', 'send_question': True})
    assert out.json['status'] == 'empty', out.json
    assert calls == []


def test_sharing_requires_human_purpose_and_cookie_origin(integrated):
    app, client, _, uid = integrated
    dataset = app.extensions['prompt17_demo']['dataset']
    path = '/api/plugins/nih_dms/datasets/' + dataset + '/prepare'
    assert client.post(path, json={}).status_code == 200
    for headers in ({'Origin': 'https://elsewhere.example'}, {'Authorization': 'Bearer invalid'}):
        assert client.post(path, json={}, headers=headers).json == REFUSAL
    HumanPolicyStore(app.config['SCIDK_SETTINGS_DB']).grant_purpose(
        uid, 'research_browse', 'low', admin_id=uid, allow=False)
    assert client.post(path, json={'download': True}).json == REFUSAL


def test_disposable_files_are_confined_and_remotes_absent(integrated, tmp_path):
    app, _, _, _ = integrated
    providers = app.extensions['scidk']['providers']
    assert set(providers.providers) == {'local_fs'}
    provider = providers.get('local_fs')
    root = provider.base_dir
    assert provider.list(str(root), str(root))['entries']
    with pytest.raises(PermissionError):
        provider.list(str(root), str(tmp_path.parent))
    (root / 'escape').symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(PermissionError):
        provider.list(str(root), str(root / 'escape'))


def test_legacy_evidence_must_match_the_record_source(integrated):
    app, client, _, uid = integrated
    from scidk.services.human_policy import HumanIdentity
    store = HumanPolicyStore(app.config['SCIDK_SETTINGS_DB'])
    scope = {'namespace': 'synthetic-other', 'resource_id': 'synthetic-other'}
    with sqlite3.connect(store.path) as conn:
        conn.execute("INSERT INTO pipeline_source(id,name,plugin_type) VALUES ('synthetic-other','Other synthetic','fixture')")
    store.classify(**scope, risk='low', admin_id=uid)
    store.grant_resource(uid, **scope, admin_id=uid)
    legacy = app.extensions['knowledge_services'].legacy
    record = next(iter(legacy._records.values()))
    ledger = app.extensions['prompt17_demo']['ledger']
    mismatch = LegacySnapshot(ledger.ontology, [dict(record, source_scope=scope)], ledger=ledger)
    ref = next(iter(mismatch._records))
    store.grant_evidence(uid, ref, admin_id=uid)
    with store.resolve(HumanIdentity(uid), 'research_browse') as policy:
        with pytest.raises(DisclosureDenied):
            mismatch.read(policy, ref)


def test_legacy_snapshot_cannot_be_assembled_against_another_ledger(integrated):
    app, client, _, _ = integrated
    from scidk.curation.ledger import Ledger
    legacy = app.extensions['knowledge_services'].legacy
    original = legacy.ledger
    legacy.ledger = Ledger(original.path, original.ontology, original.can_read_evidence)
    assert client.post('/api/knowledge/research/search', json={}).json == REFUSAL
