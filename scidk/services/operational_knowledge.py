"""Explicit trusted-local assembly over existing governed state.

No migrations, grants, graph connections, receipts or ontology changes. The
operator supplies the reconciled ontology and the existing ledger's target.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from ..agent_tools.assertions import AssertionAccess
from ..agent_tools.facts import FactDisclosure
from ..agent_tools.knowledge import KnowledgeServices
from ..curation.auth import granted_user
from ..curation.contracts import digest
from ..curation.ledger import Ledger
from ..curation.ontology import Ontology
from ..curation.review import ReviewService
from .human_legacy import LegacySnapshot
from .human_policy import HumanIdentity, HumanPolicyStore


def assemble(app, *, ledger_path, ontology, graph_target, legacy_records=None):
    """Attach existing services; caller must authorize access to supplied state.

    Legacy input has exactly Prompt 17's bounded, evidence-bound contract. It is
    an explicit snapshot, never an unrestricted legacy graph query adapter.
    """
    if 'knowledge_services' in app.extensions or 'curation_review' in app.extensions:
        raise ValueError('Knowledge or Review services already assembled')
    if not isinstance(graph_target, str) or not graph_target or len(graph_target) > 256:
        raise ValueError('An explicit existing graph target is required')
    db = Path(app.config['SCIDK_SETTINGS_DB']).resolve()
    if not db.is_file():
        raise ValueError('Existing settings store required')
    human = HumanPolicyStore(str(db))

    def evidence_authority(actor, evidence):
        try:
            if not granted_user(actor):
                return False
            with human.resolve(HumanIdentity(int(actor)), 'review_read') as policy:
                policy.resource(evidence.get('source_scope'))
                policy.evidence_metadata(digest('evidence', evidence), evidence)
            return True
        except Exception:
            return False

    ledger = Ledger(ledger_path, ontology, evidence_authority)
    with closing(sqlite3.connect(ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
        binding = conn.execute('SELECT graph_target FROM graph_binding WHERE singleton=1').fetchone()
        if binding != (graph_target,):
            raise ValueError('Existing ledger graph binding does not match configured target')
        versions = conn.execute("SELECT DISTINCT json_extract(body,'$.ontology_version') FROM assertions").fetchall()
        if any(row != (ontology.version,) for row in versions):
            raise ValueError('Existing assertion ontology requires administrator reconciliation')
    legacy = None if legacy_records is None else LegacySnapshot(ontology, legacy_records, ledger=ledger)
    services = KnowledgeServices(assertions=AssertionAccess(ledger,
        FactDisclosure(ledger, str(db), graph_target=graph_target)), legacy=legacy)
    review = ReviewService(ledger, granted_user)
    # Attach atomically after validation. No new graph writer is registered.
    app.extensions.update(knowledge_services=services, curation_review=review)
    return services


def configure(app):
    """dev_gui --configure hook; manifest path comes from explicit environment."""
    path = Path(os.environ['SCIDK_KNOWLEDGE_MANIFEST']).resolve(strict=True)
    if path.stat().st_size > 262144:
        raise ValueError('Knowledge manifest exceeds limit')
    config = json.loads(path.read_text())
    required = {'ledger_path', 'catalog_path', 'ontology_version', 'graph_target'}
    if not isinstance(config, dict) or set(config) - required - {'legacy_path'} or not required <= set(config):
        raise ValueError('Invalid Knowledge manifest fields')

    def local(name, limit):
        value = (path.parent / config[name]).resolve(strict=True)
        if value.stat().st_size > limit:
            raise ValueError('Knowledge input exceeds limit')
        return json.loads(value.read_text())

    # An explicit already reconciled snapshot, never live LabelService discovery.
    ontology = Ontology([], local('catalog_path', 1048576))
    if ontology.version != config['ontology_version']:
        raise ValueError('Pinned ontology version does not match catalog')
    assemble(app, ledger_path=path.parent / config['ledger_path'], ontology=ontology,
             graph_target=config['graph_target'],
             legacy_records=local('legacy_path', 131072) if 'legacy_path' in config else None)


def readiness(app, ctx):
    """Administrator's own access only; no names, paths, IDs or record counts.

    Assembly does not prove live Neo4j availability. Applied support is verified
    by the shared serializer when records are retrieved.
    """
    services = app.extensions.get('knowledge_services')
    ready = isinstance(services, KnowledgeServices) and services.ready('explain_fact')
    checks = dict(knowledge_service=ready,
                  review_service=isinstance(app.extensions.get('curation_review'), ReviewService),
                  ui=app.config.get('SCIDK_GUI_V3_ENABLED') is True,
                  research_enabled=app.config.get('SCIDK_KNOWLEDGE_CONTEXT_ENABLED') is True,
                  purpose_grant=False, resource_grants='not_checked', evidence_grants='not_checked',
                  source_access='not_verified', provenance='not_verified', live_graph='not_probed')
    if ready:
        facts = services.assertions.facts
        if facts.store.path != Path(ctx.settings_db).resolve():
            checks['knowledge_service'] = False
            return checks
        try:
            with HumanPolicyStore(ctx.settings_db).resolve(ctx.identity, 'research_browse') as policy:
                checks['purpose_grant'] = True
                # Bounded source checks, separate from record discovery. Never
                # return which source failed or how many were withheld.
                with closing(sqlite3.connect(facts.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
                    rows = conn.execute('SELECT evidence_id,body FROM evidence LIMIT 501').fetchall()
                if not rows or len(rows) > 500:
                    checks['source_access'] = 'empty_or_limit'
                    return checks
                resources, evidence_access = True, True
                for eid, body in rows:
                    value = json.loads(body)
                    try:
                        policy.resource(value.get('source_scope'))
                    except Exception:
                        resources = False
                    try:
                        policy.evidence_metadata(eid, value)
                    except Exception:
                        evidence_access = False
                checks.update(resource_grants=resources, evidence_grants=evidence_access,
                              source_access='ledger_readable', provenance='ledger_evidence_available')
        except Exception:
            pass
    return checks
