"""Deterministic, bounded discovery over released Overview records only.

No model planning, raw graph access, inferred identity or unscoped fallback.
"""
from dataclasses import replace
import json
import re
import time
from urllib.parse import urlencode

from ..agent_tools.knowledge import KnowledgeServices
from ..agent_tools.registry import available_tool_definitions, run_tool
from ..agent_tools.security import DisclosureDenied, REFUSAL
from .knowledge_workspace import research, WorkspaceLimit
from .overview_chat import context_turn

MAX_RESULTS = 3
MAX_CONTEXT_BYTES = 48000
MAX_PROJECTION = 64
STOP = frozenset('a an the is are was were what which who how does do can could please tell me about show find explain list my accessible knowledge current selection documentation context in on of to for and with this that'.split())


class DiscoveryEmpty(ValueError):
    pass


def terms(question):
    words = {w[:-1] if len(w) > 4 and w.endswith('s') else w for w in re.findall(r'[\w-]+', question.casefold()) if w not in STOP}
    if not words or len(words) > 16:
        raise DiscoveryEmpty()
    return words


def discover(ctx, body):
    ctx = replace(ctx, profile='overview')
    if (not isinstance(body, dict) or set(body) - {'message', 'scope', 'selection', 'send_question'}
            or not isinstance(body.get('message'), str) or not body['message'].strip()
            or len(body['message']) > 4000 or body.get('send_question') is not True
            or body.get('scope', 'accessible') not in {'accessible', 'system', 'selection'}):
        raise DisclosureDenied()
    if not ctx.identity or ctx.identity.token_id or ctx.identity.channel != 'chat':
        raise DisclosureDenied()
    words = set() if body.get('scope') == 'selection' else terms(body['message'])
    deadline = time.monotonic() + 3
    permitted = {d['name'] for d in available_tool_definitions(ctx)}
    scope = body.get('scope', 'accessible')
    matches = []

    def add(domain, node, context, tool, arguments, *, selected=False):
        if time.monotonic() > deadline:
            raise WorkspaceLimit()
        # Only released fields are searched. Candidate identity claims, hidden
        # properties, evidence bodies and raw projection previews are never used.
        text = json.dumps([node.get('type'), node.get('name'), node.get('description'), node.get('properties', {})], ensure_ascii=False).casefold()
        score = sum(bool(re.search(r'(?<!\w)' + re.escape(word) + r'\w*', text)) for word in words)
        if selected or (words and score >= min(len(words), 2)):
            matches.append((score, domain, node['id'], {'domain': domain,
                'title': node.get('properties', {}).get('name') or node.get('name') or node.get('type') or 'Authorized source',
                'id': node['id'], 'href': '/knowledge?' + urlencode({'domain': domain, 'id': node['id']}),
                'context': context, 'tool': tool, 'arguments': arguments}))

    if scope == 'selection':
        selection = body.get('selection')
        if (not isinstance(selection, dict) or set(selection) != {'domain', 'id'}
                or selection['domain'] not in {'research', 'system', 'ontology'}
                or not isinstance(selection['id'], str) or not 0 < len(selection['id']) <= 256):
            raise DisclosureDenied()
        domain, ref = selection['domain'], selection['id']
        if domain == 'research':
            result = research(ctx, 'inspect', {'id': ref}, deadline=deadline)
            for node in result['nodes']:
                add(domain, node, node, 'explain_fact', {'fact_id': node['support'][0]['fact_id']}, selected=True)
        else:
            tool = 'get_system_context' if domain == 'system' else 'get_ontology_context'
            result = run_tool(tool, {'entry_id': ref, 'depth': 0, 'limit': 1}, ctx)
            if result.get('status') != 'success':
                raise DisclosureDenied()
            add(domain, result['context']['nodes'][0], result, tool, {'entry_id': ref, 'depth': 0, 'limit': 1}, selected=True)
    else:
        if 'selection' in body:
            raise DisclosureDenied()
        if scope == 'accessible' and 'explain_fact' in permitted:
            result = research(ctx, 'search', {'q': ''}, deadline=deadline)
            # First slice: refuse rather than silently search an incomplete page.
            if result['next_offset'] is not None:
                raise WorkspaceLimit()
            for node in result['nodes']:
                add('research', node, node, 'explain_fact', {'fact_id': node['support'][0]['fact_id']})
        if 'get_system_context' in permitted:
            service = ctx.knowledge.system
            entries = service.projection.snapshot()['nodes']
            if len(entries) > MAX_PROJECTION:
                raise WorkspaceLimit()
            for entry in entries:
                if time.monotonic() > deadline:
                    raise WorkspaceLimit()
                args = {'entry_id': entry['id'], 'depth': 0, 'limit': 1}
                result = run_tool('get_system_context', args, ctx)
                if result.get('status') == 'success':
                    add('system', result['context']['nodes'][0], result, 'get_system_context', args)
        if not permitted.intersection({'get_system_context'} if scope == 'system' else {'explain_fact', 'get_system_context'}):
            raise DisclosureDenied()
    if time.monotonic() > deadline:
        raise WorkspaceLimit()
    if not matches:
        raise DiscoveryEmpty()
    if len(matches) > MAX_RESULTS:
        raise WorkspaceLimit()
    ordered = [m[3] for m in sorted(matches, key=lambda m: (-m[0], m[1], m[2]))]
    if len(json.dumps(ordered).encode()) > MAX_CONTEXT_BYTES:
        raise WorkspaceLimit()
    return ordered


def discovery_turn(ctx, body):
    try:
        if not isinstance(ctx.knowledge, KnowledgeServices) or not any(ctx.knowledge.ready(t) for t in ('explain_fact', 'get_system_context', 'get_ontology_context')):
            return {'status': 'unavailable', 'error': 'Knowledge is not connected. Ask an administrator to connect the governed knowledge services.'}
        found = discover(ctx, body)
        first = found[0]
        explicit = {'message': body['message'], 'send_question': True,
                    'context': {'tool': first['tool'], 'arguments': first['arguments']}}
        def fresh(current, _):
            return {'retrieved_sources': discover(current, body)}
        return context_turn(ctx, explicit, profile='overview',
                            allowed={'explain_fact', 'get_system_context', 'get_ontology_context'}, enrich=fresh, transport_timeout=30)
    except DiscoveryEmpty:
        return {'status': 'empty', 'error': 'No authorized matches for that question. Try a dataset or entity name, or a term from System documentation.'}
    except WorkspaceLimit:
        return {'status': 'bounded', 'error': 'This search exceeds the discovery limits. Narrow the question to a specific entity or documentation topic.'}
    except Exception:
        return dict(REFUSAL)
