"""Boolean-only, no-network readiness for the current named administrator."""
from dataclasses import replace

from ..agent_tools.registry import available_tool_definitions, run_tool
from ..agent_tools.knowledge import KnowledgeServices
from ..agent_tools.security import PolicyStore
from ..ai.shared_provider import resolve


def checklist(app, ctx, body):
    if (not isinstance(body, dict) or set(body) - {'profile', 'context'}
            or body.get('profile', 'overview') not in {'overview', 'review'}):
        raise ValueError()
    profile = body.get('profile', 'overview')
    ctx = replace(ctx, profile=profile)
    selected = body.get('context')
    tools = {'explain_fact', 'get_system_context', 'get_ontology_context'} if profile == 'overview' else {'get_assertion'}
    if selected is not None and (not isinstance(selected, dict) or set(selected) != {'tool', 'arguments'} or selected['tool'] not in tools):
        raise ValueError()
    checks = []
    def check(name, ok, remediation):
        checks.append({'check': name, 'ok': bool(ok), 'remediation': remediation})
    check('named_admin_session', bool(ctx.identity and not ctx.identity.token_id), 'Sign in using an unlocked named administrator account.')
    check('gui_v3', app.config.get('SCIDK_GUI_V3_ENABLED') is True, 'Set SCIDK_GUI_V3_ENABLED to the Python boolean True in the development app.')
    check('knowledge_context', ctx.knowledge_enabled, 'Enable SCIDK_KNOWLEDGE_CONTEXT_ENABLED explicitly in the development app.')
    check('chat_flag', app.config.get('SCIDK_OVERVIEW_CHAT_ENABLED' if profile == 'overview' else 'SCIDK_REVIEW_CHAT_ENABLED') is True,
          'Enable the selected assistant flag explicitly; shell strings are insufficient.')
    if profile == 'review':
        check('review_workspace', app.config.get('SCIDK_REVIEW_WORKSPACE_ENABLED') is True, 'Enable SCIDK_REVIEW_WORKSPACE_ENABLED explicitly.')
    configured = approved = resource_grants = credential_present = False
    try:
        from ..core.auth import get_auth_manager
        auth = get_auth_manager(db_path=ctx.settings_db)
        try:
            user = auth.get_user(ctx.identity.user_id)
            provider = resolve(ctx.settings_db, user['username'])
            configured = bool(provider)
            credential_present = bool(provider and provider.get('api_key'))
        finally:
            auth.close()
    except Exception:
        pass
    try:
        with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
            approved = True
            resource_grants = policy.conn.execute('SELECT 1 FROM agent_resource_grant g '
                'JOIN agent_resource_classification c ON c.namespace=g.namespace AND c.resource_id=g.resource_id '
                "WHERE g.user_id=? AND (c.risk='low' OR (c.risk='medium' AND ?='medium')) LIMIT 1",
                (ctx.identity.user_id, policy.destination[3])).fetchone() is not None
    except Exception:
        pass
    check('approved_provider', approved, 'Select a stored endpoint/model and have an administrator approve that exact destination. Model discovery alone is insufficient.')
    check('provider_configuration', configured, 'Configure a personal provider or an explicitly granted shared credential for the selected destination; this check makes no network request.')
    check('resource_grant_available', resource_grants, 'Grant this user a classified Resource within the destination risk ceiling. The selected context still requires its own exact grants.')
    name = selected['tool'] if selected else ('get_system_context' if profile == 'overview' else 'get_assertion')
    services = isinstance(ctx.knowledge, KnowledgeServices) and ctx.knowledge.ready(name)
    check('knowledge_service', services, 'Attach trusted KnowledgeServices with explicit source bindings and policy database; flags do not assemble services.')
    check('profile_tool_grant', name in {d['name'] for d in available_tool_definitions(ctx)}, 'Grant the selected fixed tool to this user in the selected profile; no arbitrary graph query is enabled.')
    check('selected_context', selected is not None, 'Select a stable fact, System/Ontology context, or Review assertion ID that you are authorized to inspect.')
    authorized = False
    if selected is not None:
        authorized = run_tool(name, selected['arguments'], ctx).get('status') == 'success'
    check('context_authorized', authorized, 'Check the selected stable identity, source classification, Resource/evidence and property grants, pinned ontology and current support. No inaccessible records are listed.')
    return {'ready': all(c['ok'] for c in checks), 'checks': checks,
            'transport': {'connectivity_verified': False, 'credential_present': credential_present},
            'notice': 'Configuration and authorization checks only. Provider reachability, billing and live model behavior are unverified.'}
