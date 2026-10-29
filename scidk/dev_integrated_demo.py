"""Disposable Prompt 17 simulation. No operational graph or remote provider.

Use seed_reviewed only as an explicit local operator decision to accept the
bundled synthetic assertions. Subsequent starts use configure, which never seeds.
This development hook intentionally requires the checkout's tested FakeGraph.
"""
from pathlib import Path
import json
import os
import sqlite3

from .dev_system_demo import RESOURCE


def seed_reviewed(app):
    """Explicit operator opt-in via --configure ...:seed_reviewed on fresh state."""
    with app.app_context():
        return _configure(app, seed=True)


def configure(app):
    with app.app_context():
        return _configure(app, seed=False)


def _configure(app, *, seed):
    from .core.auth import AuthManager
    from .core.settings import InterpreterSettings
    from .pipeline.store import PipelineStore
    from .curation.auth import GRANT_KEY, granted_user
    from .curation.ontology import Ontology
    from .curation.contracts import digest
    from .curation.ledger import Ledger, migrate
    from .curation.review import ReviewService
    from .agent_tools.security import PolicyStore
    from .agent_tools.capabilities import CapabilityStore
    from .agent_tools.facts import FactDisclosure
    from .agent_tools.assertions import AssertionAccess
    from .agent_tools.knowledge import KnowledgeServices
    from .knowledge.projection import content_hash, ContextService, Projection, git_revision
    from .knowledge.ontology import ontology_projection
    from .services.human_policy import HumanPolicyStore, human_context, resolve_workspace
    from .services.human_legacy import LegacySnapshot
    from tests.curation.test_review import FakeGraph
    from flask import jsonify, request, render_template_string

    db = Path(app.config['SCIDK_SETTINGS_DB']).resolve()
    state = db.parent
    # The normal factory registers home/mounted/rclone providers. A disposable
    # demo must not discover the operator's remotes or browse outside its files.
    from .core.providers import LocalFSProvider, ProviderRegistry
    synthetic_root = state / 'synthetic-files'

    class ConfinedFiles(LocalFSProvider):
        def _norm(self, value):
            resolved = super()._norm(value)
            if not resolved.is_relative_to(synthetic_root.resolve()):
                raise PermissionError('Outside disposable synthetic files')
            return resolved

    provider = ConfinedFiles(str(synthetic_root))
    provider.initialize(app, {})
    providers = ProviderRegistry(enabled=['local_fs'])
    providers.register(provider)
    app.extensions.setdefault('scidk', {})['providers'] = providers
    manifest = state / 'prompt17-manifest.json'
    ledger_path = state / 'prompt17-ledger.sqlite'
    graph_path = state / 'prompt17-simulation.json'
    if seed and any(p.exists() for p in (manifest, ledger_path, graph_path)):
        raise ValueError('Seeding requires fresh disposable Prompt 17 state')
    if not seed and not all(p.exists() for p in (manifest, ledger_path, graph_path)):
        raise ValueError('Initialize explicitly with seed_reviewed in fresh disposable state first')
    auth = AuthManager(str(db))
    try:
        admins = [u for u in auth.list_users() if u['role'] == 'admin' and u['enabled']]
        if len(admins) != 1:
            raise ValueError('Demo requires exactly one named enabled administrator')
        uid = admins[0]['id']
    finally:
        auth.close()
    root = Path(__file__).resolve().parents[1]
    fixtures = root / 'tests/fixtures/knowledge_curation'
    definitions = json.loads((fixtures / 'catalog.json').read_text()) + json.loads(
        (fixtures / 'dataset_catalog.json').read_text())
    ontology = Ontology([], definitions)
    policy = PolicyStore(str(db))
    human = HumanPolicyStore(str(db))

    class PersistentSimulation(FakeGraph):
        target = 'prompt17-simulation:' + str(state)

        def apply_batch(self, operations):
            result = super().apply_batch(operations)
            temporary = graph_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(nodes=self.nodes, edges=self.edges, markers=self.markers)))
            temporary.chmod(0o600)
            os.replace(temporary, graph_path)
            return result

    graph = PersistentSimulation()
    if not seed:
        saved = json.loads(graph_path.read_text())
        graph.nodes, graph.edges, graph.markers = saved['nodes'], saved['edges'], saved['markers']

    def evidence_authority(actor, evidence):
        try:
            if actor != str(uid) or not granted_user(actor):
                return False
            from .services.human_policy import HumanIdentity
            with human.resolve(HumanIdentity(uid), 'review_read') as current:
                current.resource(evidence.get('source_scope'))
                current.evidence_metadata(digest('evidence', evidence), evidence)
            return True
        except Exception:
            return False

    if seed:
        PipelineStore(str(db))
        with sqlite3.connect(db) as conn:
            conn.execute('INSERT INTO pipeline_source(id,name,plugin_type) VALUES (?,?,?)',
                         (RESOURCE['resource_id'], 'Synthetic integrated demo only', 'synthetic-demo'))
        policy.initialize(admin_id=uid)
        policy.classify(**RESOURCE, risk='low', admin_id=uid)
        policy.grant_resource(uid, **RESOURCE, admin_id=uid)
        human.initialize(admin_id=uid)
        for purpose in ('research_browse', 'review_read'):
            human.grant_purpose(uid, purpose, 'low', admin_id=uid)
        settings = InterpreterSettings(str(db))
        settings.db.execute('INSERT OR REPLACE INTO interpreter_settings(key,value) VALUES (?,?)',
                            (GRANT_KEY, json.dumps([uid])))
        settings.db.commit(); settings.close()
        migrate(ledger_path)
    ledger = Ledger(ledger_path, ontology, evidence_authority)
    service = ReviewService(ledger, lambda who: who == str(uid) and granted_user(who))
    app.extensions['curation_review'] = service
    facts = FactDisclosure(ledger, str(db), graph_target=graph.target)
    access = AssertionAccess(ledger, facts)
    if seed:
        # These bytes are explicitly fictional text artifacts, not medical images.
        files = {'MRI/phantom.txt': b'SYNTHETIC MRI PHANTOM\n',
                 'microCT/phantom.txt': b'SYNTHETIC MICROCT PHANTOM\n'}
        for name, data in files.items():
            destination = state / 'synthetic-files' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        evidence = dict(source_type='synthetic_demo', source_id='prompt17-phantoms', source_scope=RESOURCE,
            citation='Fictional MRI/microCT phantom study; Synthetic Investigator; no human subjects',
            version='prompt17-simulation/1', accessed_at='2026-10-29T00:00:00Z',
            content_hash=content_hash(b''.join(files.values())), locator='synthetic-only',
            retrieval_method='bundled-offline-synthetic/1', visibility='restricted', derivation_root='prompt17-demo')
        eid = ledger.add_evidence(evidence)
        policy.grant_evidence(uid, eid, admin_id=uid)
        common = dict(domain='research', ontology_version=ontology.version, epistemic_status='observed',
            method='explicit-synthetic-demo/1', visibility='restricted', source_scope=RESOURCE, evidence_refs=[eid])
        assertions = []

        def submit(body, key):
            aid = ledger.submit(dict(common, **body), actor=str(uid), caller_key=key)
            policy.grant_evidence(uid, aid, admin_id=uid)
            assertions.append(aid)
            return ledger.get_internal(aid)

        def node(label, key):
            return submit(dict(target_kind='node', candidate=dict(label=label, source_scope=RESOURCE,
                source_identifier={'record_id': key, 'role': label}, identity_claims={})), key)['claim']['entity_ref']

        dataset = node('Dataset', 'phantom-study')
        submit(dict(target_kind='property', target_ref=dataset, property_key='name',
                    proposed_value='Synthetic MRI microCT phantom study'), 'dataset-name')
        for name, data in files.items():
            ref = node('File', name)
            for key, value in [('relative_path', name), ('size_bytes', len(data)), ('extension', '.txt')]:
                submit(dict(target_kind='property', target_ref=ref, property_key=key, proposed_value=value), name + ':' + key)
            submit(dict(target_kind='relationship', subject_ref=dataset, predicate='CONTAINS',
                        object_ref=ref, qualifiers={}), name + ':membership')
        # Actual explicit decisions and actual outbox/materializer, never receipt inserts.
        with app.app_context():
            operations = []
            for aid in assertions:
                preview = service.preview(aid, reviewer=str(uid))
                result = service.review(aid, dict(action='accept', expected_revision=preview['expected_revision'],
                    preview_digest=preview['preview_digest'], rationale='Operator opted into bundled synthetic demo decisions'),
                    reviewer=str(uid))
                operations.append(result['operation_id'])
            service.materialize(operations, reviewer=str(uid), graph=graph)
        pending = submit(dict(target_kind='property', target_ref=dataset, property_key='name',
                              proposed_value='Synthetic MRI microCT study — proposed revision'), 'pending-name')['assertion_id']
        manifest.write_text(json.dumps(dict(dataset=dataset, pending=pending, evidence=eid, synthetic=True,
            simulation=True, source_root=str(state / 'synthetic-files')), indent=2))
        manifest.chmod(0o600)
    info = json.loads(manifest.read_text())
    legacy = LegacySnapshot(ontology, [dict(record_key='legacy-phantom', source_scope=RESOURCE,
        evidence_id=info['evidence'], label='Dataset', properties={'name': 'Synthetic legacy phantom collection'})], ledger=ledger)
    if seed:
        for ref in legacy._records:
            policy.grant_evidence(uid, ref, admin_id=uid)
    canonical = ontology_projection([], definitions, revision='prompt17-fixture/1',
        bindings={key: RESOURCE for key in ['catalog', *['sqlite:' + d['name'] for d in definitions]]})
    system_node = dict(id='system:synthetic-demo', name='Synthetic System workflow', type='documentation',
        visibility='restricted', source_scope=RESOURCE, git_revision=git_revision(root), applicability='knowledge-context/1',
        sources=[dict(path='tests/fixtures/knowledge_curation/catalog.json', source_scope=RESOURCE,
                      hash=content_hash((fixtures / 'catalog.json').read_bytes()))])
    system = Projection([system_node], [], {'domain': 'system', 'synthetic': True})
    if seed:
        caps = CapabilityStore(str(db)); caps.initialize(admin_id=uid)
        for profile, names in [('overview', ['explain_fact', 'get_system_context', 'get_ontology_context']),
                               ('review', ['get_assertion', 'explain_fact'])]:
            for name in names:
                caps.grant_tool(uid, profile, name, admin_id=uid)
        for projection in (canonical, system):
            for record in projection.snapshot()['nodes']:
                policy.grant_evidence(uid, ContextService.grant_id(record), admin_id=uid)
    app.extensions['knowledge_services'] = KnowledgeServices(legacy=legacy, assertions=access, system_root=root,
        system=ContextService(system, str(db), enabled=True),
        ontologies={'canonical': ContextService(canonical, str(db), enabled=True)})
    app.extensions['prompt17_demo'] = dict(info, graph=graph, ledger=ledger)
    if 'nih_dms' not in app.blueprints:
        from plugins.nih_dms.routes import bp
        app.register_blueprint(bp)

    @app.get('/demo/prompt17')
    def demo_index():
        ctx = human_context(app)
        from .services.knowledge_workspace import research
        research(ctx, 'inspect', {'id': info['dataset']})
        return render_template_string('''{% extends 'base.html' %}{% block content %}
          <h1>Synthetic integrated demonstration</h1><p>Simulated graph application; fictional text artifacts.
          No real imaging acquisition or live Neo4j verification.</p>
          <p><a href="/datasets">Files &amp; Datasets</a> ·
          <a href="/knowledge?domain=research&amp;id={{ dataset }}">Curated dataset</a> ·
          <a href="/review?id={{ pending }}">Review proposed revision</a> ·
          <a href="/overview">Ask SciDK</a></p>
          <p>Use Files → Datasets search “Synthetic” to inspect this collection and prepare sharing.</p>
          {% endblock %}''', **info)

    @app.before_request
    def synthetic_collection_search():
        # Narrow development-only adapter over the same real governed ledger;
        # never intercept other labels, queries, writes or operational graph data.
        if (request.method == 'GET' and request.path == '/api/canvas/nodes/search'
                and request.args.get('label') == 'Dataset'):
            try:
                from .services.knowledge_workspace import research
                nodes = research(human_context(app), 'search', {'q': request.args.get('q', ''), 'label': 'Dataset'})['nodes']
                return jsonify(results=[dict(id=n['id'], entity_ref=n['id'], name=n['properties'].get('name', 'Dataset'),
                    label='Dataset', labels=['Dataset'], properties=dict(n['properties'], entity_ref=n['id'],
                    curation_status=n['curation_status'], provenance={'method': 'Prompt17 synthetic simulation'}))
                    for n in nodes if n['curation_status'] == 'accepted']), 200, {'Cache-Control': 'no-store'}
            except Exception:
                from .agent_tools.security import REFUSAL
                return jsonify(REFUSAL), 403
