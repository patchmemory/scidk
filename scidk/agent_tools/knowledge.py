"""Shared scoped handlers and schemas; wired only by trusted application setup."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security import DisclosureDenied
from .assertions import AssertionAccess
from ..knowledge.projection import ContextService, git_revision


def schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def string(maximum=256):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum}


_CONTEXT = {'entry_id': string(), 'depth': {'type': 'integer', 'minimum': 0, 'maximum': 6},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 128}}
DEFINITIONS = [
    dict(name='get_system_context', category='schema',
         description='Retrieve permitted bounded System Knowledge traversal with source hashes, versions and freshness warnings.',
         input_schema=schema(_CONTEXT, ['entry_id'])),
    dict(name='get_ontology_context', category='schema',
         description='Retrieve permitted canonical ontology or selected external concepts; unresolved catalog conflicts remain blockers.',
         input_schema=schema(dict(_CONTEXT, catalog=string()), ['entry_id'])),
    dict(name='explain_fact', category='data_query',
         description='Explain current applied ledger support and permitted citations for one stable research fact; no arbitrary graph queries.',
         input_schema=schema({'fact_id': string(), 'include_evidence': {'type': 'boolean'}}, ['fact_id'])),
    dict(name='get_assertion', category='data_query',
         description='Inspect one permitted assertion, current review state and evidence metadata; history needs a separate grant.',
         input_schema=schema({'assertion_id': string(), 'include_history': {'type': 'boolean'}}, ['assertion_id'])),
    dict(name='submit_assertion', category='data_query',
         description='Submit an idempotent proposed assertion using existing evidence and a pinned ontology; explicit scoped proposal grant required. Never reviews or materializes.',
         input_schema=schema({'assertion': {'type': 'object', 'maxProperties': 24}, 'caller_key': string()},
                             ['assertion', 'caller_key'])),
]
NAMES = frozenset(d['name'] for d in DEFINITIONS)


@dataclass
class KnowledgeServices:
    system: Any = None  # Stage 4 ContextService, not an unrestricted callback.
    ontologies: dict = field(default_factory=dict)  # canonical + explicit external registry projections
    assertions: Any = None  # AssertionAccess over existing ledger + FactDisclosure
    system_root: Any = None
    applicability: str = 'knowledge-context/1'

    def ready(self, name):
        if name == 'get_system_context':
            return isinstance(self.system, ContextService) and self.system.enabled and self.system_root is not None
        if name == 'get_ontology_context':
            return any(isinstance(s, ContextService) and s.enabled for s in self.ontologies.values())
        return isinstance(self.assertions, AssertionAccess)

    def settings_paths(self, name):
        if name == 'get_system_context':
            return [self.system.policy.path]
        if name == 'get_ontology_context':
            return [s.policy.path for s in self.ontologies.values() if isinstance(s, ContextService)]
        return [self.assertions.facts.store.path]


def dispatch(name, args, ctx, policy):
    services = ctx.knowledge
    # Prevent a caller's identity/destination approval from authorizing content
    # configured against some other instance's settings DB.
    if any(p != Path(ctx.settings_db).resolve() for p in services.settings_paths(name)):
        raise DisclosureDenied()
    if name == 'get_system_context':
        out = services.system.read(args['entry_id'], ctx.identity, depth=args.get('depth', 3), limit=args.get('limit', 128))
        if out['status'] == 'success':
            ids = {n['id'] for n in out['context']['nodes']}
            warnings = services.system.projection.freshness(services.system_root,
                revision=git_revision(services.system_root), applicability=services.applicability)
            policy.property('KnowledgeContext', 'warnings')
            out['context']['warnings'] = [w for w in warnings if w['id'] in ids]
        return out
    if name == 'get_ontology_context':
        service = services.ontologies.get(args.get('catalog', 'canonical'))
        if not isinstance(service, ContextService) or not service.enabled:
            raise DisclosureDenied()
        return service.read(args['entry_id'], ctx.identity, depth=args.get('depth', 3), limit=args.get('limit', 128))
    if name == 'explain_fact':
        return services.assertions.explain(policy, ctx.identity, args['fact_id'], include_evidence=args.get('include_evidence', True))
    if name == 'get_assertion':
        return {'status': 'success', 'assertion': services.assertions.inspect(policy, args['assertion_id'],
                                                                            include_history=args.get('include_history', False))}
    if name == 'submit_assertion':
        return services.assertions.submit(policy, args['assertion'], caller_key=args['caller_key'])
    raise DisclosureDenied()
