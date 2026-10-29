"""Real ledger/review/policy/HTTP boundaries; synthetic sources and provider."""
import io
import json
import sqlite3
import subprocess
import zipfile

import pytest

from plugins.nih_dms.routes import bp as dms_bp
from scidk.ai import provider_settings
from scidk.agent_tools.security import REFUSAL
from scidk.curation.ontology import Ontology
from scidk.services.dataset_sharing import safe_relative, sharing_package
from scidk.agent_tools.security import DisclosureDenied
from .conftest import SCOPE, OTHER_SCOPE


def session(d, name='alice'):
    uid = getattr(d, name)
    provider_settings.save(d.db, name, base_url='https://provider.example/v1', model='synthetic-model')
    client = d.app.test_client()
    client.set_cookie('scidk_session', d.auth.create_user_session(uid, name))
    d.app.config.update(SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_DATASET_SHARING_ENABLED=True)
    return client


def overview_body(fid):
    return {'message': 'What does this source establish?', 'send_question': True,
            'context': {'tool': 'explain_fact', 'arguments': {'fact_id': fid}}}


def test_overview_http_forces_profile_and_discloses_current_only(scenario, monkeypatch):
    d = scenario
    client = session(d)
    assertions = d.mapped_assertions()
    person = assertions['pi']
    calls = []
    def provider(*args, **kwargs):
        calls.append((args, kwargs))
        return {'content': '<script>untrusted answer</script>'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    body = overview_body(person['fact_id'])
    assert client.post('/api/chat/overview?profile=review', json=body).json == REFUSAL
    assert not calls
    result = d.review(person)
    d.apply([result.json['operation_id']])
    out = client.post('/api/chat/overview?profile=review', json=body)
    assert out.status_code == 200, out.json
    assert out.json['context']['fact']['curation_status'] == 'accepted'
    assert calls[0][0][2] == 'synthetic-model'
    assert 'history' not in calls[0][0][3][1]['content']
    assert 'tools' not in calls[0][1]
    for field, value in [('profile', 'review'), ('history', [{'content': 'secret'}]),
                         ('base_url', 'https://attacker.example')]:
        assert client.post('/api/chat/overview', json=dict(body, **{field: value})).json == REFUSAL
    assert len(calls) == 1
    body['context'] = {'tool': 'get_assertion', 'arguments': {'assertion_id': person['assertion_id']}}
    assert client.post('/api/chat/overview?profile=review', json=body).json == REFUSAL
    assert len(calls) == 1


def test_overview_revocation_after_send_discards_answer(scenario, monkeypatch):
    d = scenario
    client = session(d)
    person = d.mapped_assertions()['pi']
    d.apply([d.review(person).json['operation_id']])
    def provider(*args, **kwargs):
        with sqlite3.connect(d.db) as conn:
            conn.execute('DELETE FROM agent_resource_grant WHERE user_id=?', (d.alice,))
        return {'content': 'must not escape'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    assert client.post('/api/chat/overview', json=overview_body(person['fact_id'])).json == REFUSAL


@pytest.fixture
def datasets(scenario, request):
    d = scenario
    # Fixture-only catalog; no production ontology migration or auto-import.
    definitions = d.definitions + [
        {'name': 'Dataset', 'properties': [{'name': 'name', 'type': 'string'}],
         'relationships': [{'type': 'CONTAINS', 'to_label': 'File'}]},
        {'name': 'File', 'properties': [{'name': 'relative_path', 'type': 'string'},
          {'name': 'size_bytes', 'type': 'integer'}, {'name': 'extension', 'type': 'string'}]},
    ]
    d.ledger.ontology = Ontology([], definitions)
    d.app.register_blueprint(dms_bp)
    collections = []
    for index, scope in enumerate((SCOPE, OTHER_SCOPE)):
        eid, _ = d.evidence(scope=scope, source_id=f'dataset-{index}')
        if scope == OTHER_SCOPE:
            d.policy.grant_evidence(d.bob, eid, admin_id=d.reviewer)
        common = dict(domain='research', ontology_version=d.ledger.ontology.version,
            epistemic_status='observed', method='fixture-only', visibility='restricted',
            source_scope=scope, evidence_refs=[eid])
        assertions = []
        def submit(body):
            aid = d.ledger.submit(dict(common, **body), actor='fixture-importer', caller_key=f'{index}:{len(assertions)}')
            value = d.ledger.get_internal(aid)
            assertions.append(value)
            return value
        def node(label):
            return submit(dict(target_kind='node', candidate=dict(label=label, source_scope=scope,
                source_identifier={'record_id': str(index), 'role': label}, identity_claims={})))
        dataset, file = node('Dataset'), node('File')
        ref, fref = dataset['claim']['entity_ref'], file['claim']['entity_ref']
        edge = submit(dict(target_kind='relationship', subject_ref=ref, predicate='CONTAINS', object_ref=fref, qualifiers={}))
        for target, key, value in [(ref, 'name', f'collection-{index}'),
                (fref, 'relative_path', f'folder/data-{index}.txt'), (fref, 'size_bytes', 3 + index),
                (fref, 'extension', '.txt')]:
            if key == 'relative_path' and getattr(request, 'param', True) is False:
                continue
            submit(dict(target_kind='property', target_ref=target, property_key=key, proposed_value=value))
        operations = [d.review(a).json['operation_id'] for a in assertions]
        d.apply(operations)
        collections.append((ref, fref, edge, assertions))
    return d, collections


def test_selected_dataset_isolation_and_package(datasets):
    d, collections = datasets
    client = session(d)
    a, b = collections
    url = f'/api/plugins/nih_dms/datasets/{a[0]}/prepare'
    preview = client.post(url, json={'fields': {'repository': 'Investigator choice'}})
    assert preview.status_code == 200, preview.json
    serialized = json.dumps(preview.json)
    assert a[0] in serialized and 'data-0.txt' in serialized
    assert b[0] not in serialized and 'data-1.txt' not in serialized
    assert preview.json['snapshot']['files'][0]['size_bytes'] == 3
    assert 'Investigator choice' in preview.json['markdown']
    assert 'Field provenance' in preview.json['markdown']
    download = client.post(url, json={'download': True})
    assert download.status_code == 200, download.json
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        assert set(archive.namelist()) == {'README.md', 'files.txt', 'manifest.json',
            'nih-dms-plan-draft.md', 'prepare.sh', 'prepare.ps1'}
        assert archive.read('files.txt') == b'folder/data-0.txt\n'
        assert 'data-1.txt' not in archive.read('manifest.json').decode()
    for id in (b[0], 'unknown-dataset'):
        denied = client.post(f'/api/plugins/nih_dms/datasets/{id}/prepare', json={})
        assert denied.status_code == 403 and denied.json == REFUSAL
    bob = session(d, 'bob')
    assert bob.post(url, json={}).json == REFUSAL
    b_preview = bob.post(f'/api/plugins/nih_dms/datasets/{b[0]}/prepare', json={})
    assert b_preview.status_code == 200
    assert a[0] not in json.dumps(b_preview.json)


def test_dataset_hidden_property_revocation_and_unsupported_membership(datasets):
    d, collections = datasets
    client = session(d)
    ref, _, edge, _ = collections[0]
    url = f'/api/plugins/nih_dms/datasets/{ref}/prepare'
    with sqlite3.connect(d.db) as conn:
        conn.execute("INSERT INTO agent_sharing(label,property,mode) VALUES ('File','size_bytes','hidden')")
    assert client.post(url, json={}).json == REFUSAL
    with sqlite3.connect(d.db) as conn:
        conn.execute("DELETE FROM agent_sharing WHERE label='File'")
        conn.execute('DELETE FROM agent_evidence_grant WHERE user_id=?', (d.alice,))
    assert client.post(url, json={'download': True}).json == REFUSAL
    eid = edge['claim']['evidence_refs'][0]
    d.policy.grant_evidence(d.alice, eid, admin_id=d.reviewer)
    assert client.post(url, json={}).status_code == 200
    replacement = d.ledger.submit(edge['claim'], actor='fixture-importer', caller_key='replacement-edge')
    assert d.review(edge, action='supersede', superseded_by=replacement).status_code == 200
    # A retained graph relationship never overrides the current ledger decision.
    assert client.post(url, json={}).json == REFUSAL


def test_new_routes_reject_token_anonymous_and_disabled(datasets):
    d, collections = datasets
    client = session(d)
    url = f'/api/plugins/nih_dms/datasets/{collections[0][0]}/prepare'
    token = {'Authorization': 'Bearer ' + d.tokens['alice']['token']}
    assert client.post(url, json={}, headers=token).status_code == 403
    assert client.post('/api/chat/overview', json={}, headers=token).status_code == 403
    assert d.app.test_client().post(url, json={}).status_code in {401, 403}
    d.app.config['SCIDK_DATASET_SHARING_ENABLED'] = False
    assert client.post(url, json={}).json == REFUSAL
    d.app.config['SCIDK_OVERVIEW_CHAT_ENABLED'] = False
    assert client.post('/api/chat/overview', json={}).json == REFUSAL


@pytest.mark.parametrize('datasets', [False], indirect=True)
def test_investigator_validation_and_package_readiness(datasets):
    d, collections = datasets
    client = session(d)
    ref, _, _, assertions = collections[0]
    url = f'/api/plugins/nih_dms/datasets/{ref}/prepare'
    for fields in ({'sharing_mode': 'restricted'}, {'retention_years': '-1'}, {'history': 'private'}):
        assert client.post(url, json={'fields': fields}).status_code == 400
    assert client.post(url, json={'fields': {'sharing_mode': 'controlled_access'}}).status_code == 200
    # A missing supported path does not make byte counts or the DMS draft unusable.
    # But a package must not guess a source path from a name or graph element ID.
    preview = client.post(url, json={})
    assert preview.status_code == 200 and preview.json['package_ready'] is False
    assert client.post(url, json={'download': True}).json == REFUSAL


@pytest.mark.parametrize('path', ['/etc/passwd', '../secret', 'a/../secret', 'a//file', 'a\\file',
    '$(touch hacked)', 'a\nfile', '-option', 'CON.txt', 'a:stream', 'a/file.', 'a/file '])
def test_package_rejects_unsafe_paths(path):
    with pytest.raises(DisclosureDenied):
        safe_relative(path)


def test_shell_script_copies_only_manifest_and_refuses_links(tmp_path):
    # Execute the shipped artifact, with spaces in both paths; no source interpolation.
    snapshot = {'dataset_id': 'fixture', 'dataset': {}, 'files': [
        {'entity_ref': 'file', 'relative_path': 'folder/a file.txt', 'size_bytes': 3}],
        'provenance': [], 'scope': 'fixture only'}
    package = tmp_path / 'preparation'; package.mkdir()
    with zipfile.ZipFile(io.BytesIO(sharing_package(snapshot, {}))) as archive:
        archive.extractall(package)
    source = tmp_path / 'source root'; (source / 'folder').mkdir(parents=True)
    (source / 'folder/a file.txt').write_text('abc')
    (source / 'unlisted.txt').write_text('secret')
    script = str(package / 'prepare.sh')
    assert subprocess.run(['bash', '-n', script], capture_output=True).returncode == 0
    target = tmp_path / 'new copy'
    result = subprocess.run(['bash', script, str(source), str(target)], input='COPY\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (target / 'folder/a file.txt').read_text() == 'abc'
    assert not (target / 'unlisted.txt').exists()
    assert subprocess.run(['bash', script, str(source), str(target)], input='COPY\n', text=True, capture_output=True).returncode != 0
    (source / 'folder/a file.txt').unlink()
    (source / 'folder/a file.txt').symlink_to(source / 'unlisted.txt')
    assert subprocess.run(['bash', script, str(source), str(tmp_path / 'denied')],
        input='COPY\n', text=True, capture_output=True).returncode != 0
    assert not (tmp_path / 'denied').exists()
