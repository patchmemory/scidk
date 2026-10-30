"""Redacted live-runtime diagnostics; no credentials, entity names or research data."""
import sqlite3
from pathlib import Path

from .graph_management_policy import ManagementPolicyStore, connection_key, primary


def connection_description(app):
    from ..core.neo4j_config import get_neo4j_params
    uri, user, _, database, mode = get_neo4j_params(app)
    try:
        target = connection_key(uri, user, database, mode)
    except Exception:
        from ..agent_tools import security
        if not security.FULL_ACCESS:
            raise
        # Full access: a profile with a blank database (the server default) must not break the banner.
        target = None
    return dict(id='PRIMARY', display_name='Configured development primary', database=database,
                connection_id=target, backend='Neo4j', raw_query_execution=False)


def readiness(app, identity):
    from ..core.neo4j_config import get_neo4j_params
    runtime = app.extensions.get('development_runtime')
    result = dict(runtime=runtime or dict(profile='unrecorded', git_revision='unknown'),
                  named_authentication=True, graph=dict(status='not_configured'),
                  knowledge=dict(status='governed_source_provenance_unavailable'),
                  review=dict(status='not_configured'), ai=dict(status='not_configured', disclosure_approved=False))
    uri, user, password, database, mode = get_neo4j_params(app)
    if uri and database:
        graph = dict(status='configured_but_unauthorized', reachability='not_probed', grants={})
        result['graph'] = graph
        try:
            description = connection_description(app)
            target = description['connection_id']
            # A trusted development binding is required even for diagnostics.
            if target not in app.config.get('SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS', ()):
                raise PermissionError()
            graph.update(connection_id=target, backend='Neo4j', database=database)
            policy = ManagementPolicyStore(app.config['SCIDK_SETTINGS_DB'])
            for permission in ('graph_management_read', 'graph_entity_write', 'graph_schema_write'):
                try:
                    policy.check(identity['id'], target, permission)
                    graph['grants'][permission] = True
                except Exception:
                    graph['grants'][permission] = False
            primary()  # named, unlocked, same-origin and current read grant
        except Exception:
            pass
        else:
            try:
                from neo4j import GraphDatabase, READ_ACCESS, Query
                with GraphDatabase.driver(uri, auth=None if mode == 'none' else (user, password),
                                          connection_timeout=3, max_transaction_retry_time=0) as driver:
                    with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
                        present = session.run(Query('MATCH (n) RETURN 1 AS present LIMIT 1', timeout=3)).single()
                graph.update(status='ready' if present else 'authorized_but_empty', reachability='connected')
            except Exception:
                graph.update(status='configured_but_unreachable', reachability='unreachable')
    from ..agent_tools.knowledge import KnowledgeServices
    from ..curation.review import ReviewService
    services = app.extensions.get('knowledge_services')
    if isinstance(services, KnowledgeServices) and services.ready('explain_fact'):
        result['knowledge']['status'] = 'configured_authorization_requires_selected_context'
    if isinstance(app.extensions.get('curation_review'), ReviewService):
        result['review']['status'] = 'configured_authorization_requires_selected_context'
    try:
        from ..agent_tools.context import context_from_app
        from .chat_readiness import checklist
        checks = {c['check']: c['ok'] for c in checklist(app, context_from_app(app), {})['checks']}
        result['ai'].update(status='configured' if checks.get('provider_configuration') else 'not_configured',
                            disclosure_approved=checks.get('approved_provider', False),
                            authorized_source_context=False, connectivity='not_probed')
    except Exception:
        pass
    for name, db, table in (('files', app.config.get('SCIDK_DB_PATH'), 'scans'),
                            ('resources', app.config.get('SCIDK_SETTINGS_DB'), 'pipeline_source')):
        # The canonical launcher contains both stores in its private state.
        if name == 'files' and runtime:
            import os
            db = os.environ.get('SCIDK_DB_PATH')
        try:
            path = Path(db).resolve()
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
                # Only fixed table names above; no content is serialized.
                present = conn.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
            result[name] = dict(status='ready' if present else 'authorized_but_empty')
        except Exception:
            result[name] = dict(status='not_configured')
    return result
