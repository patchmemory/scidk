"""Explicit isolated assembly of existing services; never deployment bootstrap."""
import csv
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS
from scidk.pipeline.mapping_engine import MappingEngine
from scidk.pipeline.store import PipelineStore
from scidk.core.auth import AuthManager
from scidk.core.settings import InterpreterSettings
from scidk.curation.auth import GRANT_KEY, granted_user
from scidk.curation.ledger import Ledger, migrate
from scidk.curation.ontology import Ontology
from scidk.curation.review import ReviewService
from scidk.curation.contracts import digest
from scidk.agent_tools.security import PolicyStore, BoundIdentity
from scidk.agent_tools.capabilities import CapabilityStore
from scidk.agent_tools.profiles import PROFILES
from scidk.agent_tools.facts import FactDisclosure
from scidk.agent_tools.assertions import AssertionAccess
from scidk.agent_tools.knowledge import KnowledgeServices
from scidk.agent_tools.registry import ToolContext, run_tool
from scidk.knowledge.projection import ContextService, system_projection, content_hash
from scidk.knowledge.system_manifest import ENTRIES
from scidk.knowledge.ontology import ontology_projection
from scidk.knowledge.external import mondo_fixture
from scidk.web.routes import api_agent, api_chat, api_curation
from scidk.web.auth_middleware import init_auth_middleware
from tests.curation.test_review import FakeGraph

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/fixtures/knowledge_curation'
SCOPE = {'namespace': 'synthetic-intake', 'resource_id': 'intake-demo-a'}
OTHER_SCOPE = dict(SCOPE, resource_id='intake-demo-b')


class Scenario(SimpleNamespace):
    def tool(self, name, args, *, profile='review', principal='alice'):
        ctx = ToolContext(settings_db=self.db, identity=self.identities[principal], profile=profile,
                          knowledge=self.knowledge, knowledge_enabled=True, proposal_enabled=True)
        return run_tool(name, args, ctx)

    def evidence(self, source_id='export-a', scope=None, record_id='WO-DEMO-001'):
        scope = scope or SCOPE
        body = dict(source_type='synthetic_csv_export', source_id=source_id, source_scope=scope,
                    citation='Synthetic intake demonstration; no real investigators or acquisitions',
                    version=self.mapping_revision, accessed_at='2026-10-29T00:00:00Z',
                    content_hash=content_hash(self.intake_bytes), locator='RecordID:' + record_id,
                    retrieval_method='offline-fixture/1', visibility='restricted', derivation_root=source_id)
        eid = self.ledger.add_evidence(body)
        self.policy.grant_evidence(self.alice, eid, admin_id=self.reviewer)
        return eid, body

    def submit(self, body, key):
        result = self.tool('submit_assertion', {'assertion': body, 'caller_key': key})
        assert result['status'] == 'success', result
        aid = result['assertion_id']
        self.policy.grant_evidence(self.alice, aid, admin_id=self.reviewer)
        return self.ledger.get_internal(aid)

    def mapped_assertions(self, row=0, scope=None, *, actor='agent'):
        """Small test adapter: consume real declarations, never rerun transforms.

        Project uses the mapped CAC key within its Resource. A name-only Person
        uses upstream RecordID+role, never the engine's name-only merge hint.
        """
        scope = scope or SCOPE
        raw = self.rows[row]
        mapped = self.engine.map_row(raw, row)
        assert not mapped.errors and not mapped.skipped
        eid, _ = self.evidence(scope=scope, record_id=raw['RecordID'])
        common = dict(domain='research', ontology_version=self.ledger.ontology.version,
                      epistemic_status='inferred', method='synthetic-mapping-adapter/1',
                      visibility='restricted', source_scope=scope, evidence_refs=[eid])
        assertions, by_mapping = {}, {}
        def submit(body, key):
            if actor == 'agent':
                return self.submit(body, key)
            aid = self.ledger.submit(body, actor='fixture-importer', caller_key=key)
            return self.ledger.get_internal(aid)
        for item in mapped.nodes:
            assert item.mapping_id in {'project', 'pi'}
            record = 'cac:' + item.key_value if item.mapping_id == 'project' else raw['RecordID']
            candidate = dict(label=item.label, source_scope=scope,
                             source_identifier={'record_id': record, 'role': item.mapping_id},
                             identity_claims=item.properties)
            key = f"{scope['resource_id']}:{raw['RecordID']}:{item.mapping_id}"
            n = submit(dict(common, target_kind='node', candidate=candidate), key)
            assertions[item.mapping_id] = n
            by_mapping[item.mapping_id] = n['claim']['entity_ref']
            for prop, value in item.properties.items():
                assertions[item.mapping_id + '.' + prop] = submit(dict(common, target_kind='property',
                    target_ref=n['claim']['entity_ref'], property_key=prop, proposed_value=value), key + ':' + prop)
        assert len(mapped.relationships) == 1 and mapped.relationships[0]['type'] == 'PI_OF'
        edge = mapped.relationships[0]
        person = next(n for n in mapped.nodes if n.label == edge['from_label'] and n.match == edge['from_match'])
        project = next(n for n in mapped.nodes if n.label == edge['to_label'] and n.match == edge['to_match'])
        assertions['PI_OF'] = submit(dict(common, target_kind='relationship',
            subject_ref=by_mapping[person.mapping_id], predicate=edge['type'],
            object_ref=by_mapping[project.mapping_id], qualifiers={}),
            f"{scope['resource_id']}:{raw['RecordID']}:PI_OF")
        return assertions

    def review(self, assertion, action='accept', **extra):
        aid = assertion if isinstance(assertion, str) else assertion['assertion_id']
        path = '/api/curation/assertions/' + aid
        preview = self.human.post(path + '/preview')
        assert preview.status_code == 200, preview.json
        out = self.human.post(path + '/review', json=dict(action=action,
            expected_revision=preview.json['expected_revision'], preview_digest=preview.json['preview_digest'],
            rationale='Named reviewer examined synthetic intake evidence', **extra))
        return out

    def apply(self, operations, **kwargs):
        with self.app.app_context():
            return self.service.materialize(operations, reviewer=str(self.reviewer), graph=self.graph, **kwargs)

    def history_grant(self, aid):
        with sqlite3.connect(self.ledger.path) as conn:
            rows = conn.execute('SELECT action,revision,rationale,created_at FROM decisions WHERE assertion_id=? '
                                'ORDER BY revision DESC', (aid,)).fetchall()
        history = [dict(action=a, revision=r, rationale=t, created_at=c) for a, r, t, c in rows]
        self.policy.grant_evidence(self.alice, AssertionAccess.history_grant_id(aid, history), admin_id=self.reviewer)


@pytest.fixture
def scenario(tmp_path):
    db = str(tmp_path / 'settings.sqlite')
    auth = AuthManager(db_path=db)
    reviewer = auth.create_user('reviewer', 'synthetic-password', role='admin')
    alice = auth.create_user('alice', 'synthetic-password', role='user')
    bob = auth.create_user('bob', 'synthetic-password', role='user')
    PipelineStore(db)
    settings = InterpreterSettings(db)
    settings.db.execute('INSERT OR REPLACE INTO interpreter_settings(key,value) VALUES (?,?)',
                        (GRANT_KEY, json.dumps([reviewer])))
    settings.db.commit()
    settings.close()
    with sqlite3.connect(db) as conn:
        for scope in (SCOPE, OTHER_SCOPE):
            conn.execute('INSERT INTO pipeline_source(id,name,plugin_type) VALUES (?,?,?)',
                         (scope['resource_id'], 'Synthetic intake only', 'fixture'))
    policy = PolicyStore(db)
    policy.initialize(admin_id=reviewer)
    for scope in (SCOPE, OTHER_SCOPE):
        policy.classify(**scope, risk='medium', admin_id=reviewer)
    policy.grant_resource(alice, **SCOPE, admin_id=reviewer)
    policy.grant_resource(bob, **OTHER_SCOPE, admin_id=reviewer)
    policy.approve_destination('demo', 'https://provider.example/v1', 'synthetic-model', 'medium', admin_id=reviewer)
    caps = CapabilityStore(db)
    caps.initialize(admin_id=reviewer)
    identities, tokens = {}, {}
    for name, uid in (('alice', alice), ('bob', bob)):
        token = auth.create_api_token(uid, 'synthetic test client')
        tokens[name] = token
        policy.bind_token(token['id'], 'demo', admin_id=reviewer)
        identities[name] = BoundIdentity(uid, 'http', token['id'])
        for profile, tools in PROFILES.items():
            for tool in tools:
                caps.grant_tool(uid, profile, tool, admin_id=reviewer)
    caps.grant_proposal(alice, **SCOPE, admin_id=reviewer)
    definitions = json.loads((FIXTURES / 'catalog.json').read_text())
    ontology = Ontology([], definitions)
    path = tmp_path / 'ledger.sqlite'
    migrate(path)
    ledger = Ledger(path, ontology, lambda actor, ev: actor in {'fixture-importer', str(reviewer)}
                    and ev.get('source_scope') in (SCOPE, OTHER_SCOPE))
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=db, SCIDK_KNOWLEDGE_CONTEXT_ENABLED=True,
                      SCIDK_CURATION_ENABLED=True, SCIDK_ASSISTANT_PROFILE='overview')
    service = ReviewService(ledger, lambda who: who == str(reviewer) and granted_user(who))
    app.extensions['curation_review'] = service
    app.register_blueprint(api_agent.bp)
    app.register_blueprint(api_chat.bp)
    api_curation.register_curation(app)
    init_auth_middleware(app)
    graph = FakeGraph()
    facts = FactDisclosure(ledger, db, graph_target=graph.target)
    system = system_projection(ROOT, {n['id']: SCOPE for n in ENTRIES})
    canonical = ontology_projection([], definitions, revision='synthetic-stage-6/1',
        bindings={key: SCOPE for key in ['catalog', *['sqlite:' + d['name'] for d in definitions]]})
    for projection in (system, canonical):
        for n in projection.snapshot()['nodes']:
            policy.grant_evidence(alice, ContextService.grant_id(n), admin_id=reviewer)
    knowledge = KnowledgeServices(system=ContextService(system, db, enabled=True), system_root=ROOT,
        ontologies={'canonical': ContextService(canonical, db, enabled=True),
                    'MONDO': ContextService(mondo_fixture().projection('MONDO', source_scope=SCOPE,
                                            revision='synthetic-stage-6/1'), db, enabled=True)},
        assertions=AssertionAccess(ledger, facts))
    app.extensions['knowledge_services'] = knowledge
    human = app.test_client()
    human.set_cookie('scidk_session', auth.create_user_session(reviewer, 'reviewer'))
    mapping_path = ROOT / 'plugins/sharepoint_intake/configs/aipt_intake_mapping.json'
    engine = MappingEngine(json.loads(mapping_path.read_text()), transform_library=SHAREPOINT_TRANSFORMS)
    assert engine.validate().ok, engine.validate().errors
    intake_bytes = (FIXTURES / 'intake.csv').read_bytes()
    rows = list(csv.DictReader(intake_bytes.decode().splitlines()))
    yield Scenario(db=db, auth=auth, reviewer=reviewer, alice=alice, bob=bob, policy=policy, caps=caps,
        identities=identities, tokens=tokens, ledger=ledger, app=app, service=service, graph=graph,
        facts=facts, knowledge=knowledge, human=human, engine=engine, rows=rows,
        intake_bytes=intake_bytes, mapping_revision=content_hash(mapping_path.read_bytes()),
        definitions=definitions)
    auth.close()
