"""Bounded human workspace adapters. No Neo4j queries or graph writes.

Every Research value comes from the Stage 3 current-support serializer, within
one ledger/policy snapshot. No candidate fields are used as search previews.
"""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json
import re
import sqlite3
import time

from ..agent_tools.registry import available_tool_definitions, run_tool
from ..agent_tools.facts import FactDisclosure
from ..agent_tools.security import DisclosureDenied, PolicyStore
from .canvas_service import CanvasService

DOMAINS = {'research': 'explain_fact', 'ontology': 'get_ontology_context', 'system': 'get_system_context'}
MAX_CANDIDATES = 500


class WorkspaceLimit(ValueError):
    """Limits refuse the whole operation, never a partially truncated result."""


def authorized(ctx, domain):
    ctx = replace(ctx, profile='overview')
    if (domain not in DOMAINS or not ctx.identity or ctx.identity.token_id
            or ctx.identity.channel != 'chat' or DOMAINS[domain] not in
            {d['name'] for d in available_tool_definitions(ctx)}):
        raise DisclosureDenied()
    return ctx


class ResearchReader:
    def __init__(self, ctx, conn, policy, *, deadline=None):
        self.deadline = deadline
        self.ctx, self.conn, self.policy = ctx, conn, policy
        self.facts = ctx.knowledge.assertions.facts
        self.bytes = 0

    def fact(self, fid):
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise WorkspaceLimit()
        value = self.facts._fact(self.conn, self.policy, fid, True, set())
        self.bytes += len(json.dumps(value).encode())
        if self.bytes > 2 * 1024 * 1024:
            raise WorkspaceLimit()
        return value

    def candidates(self, where, args, limit=MAX_CANDIDATES):
        # WHERE fragments are internal constants. Request data is parameterized.
        rows = self.conn.execute("SELECT DISTINCT fact_id FROM assertions WHERE "
            "json_extract(body,'$.domain')='research' AND " + where + " ORDER BY fact_id LIMIT ?",
            (*args, limit + 1)).fetchall()
        if len(rows) > limit:
            raise WorkspaceLimit()
        return [row[0] for row in rows]

    def node(self, ref):
        safe = self.facts._reference(self.conn, self.policy, ref, set())
        safe = self.fact(safe['fact_id'])
        if safe['target_kind'] != 'node':
            raise DisclosureDenied()
        properties, support = {}, []
        for fid in self.candidates("json_extract(body,'$.target_kind')='property' AND "
                "json_extract(body,'$.target_ref')=?", (safe['entity_ref'],), 128):
            try:
                prop = self.fact(fid)
            except DisclosureDenied:
                continue  # no hidden-property names or withholding counts
            properties[prop['property_key']] = prop['value']
            support.append(prop)
        self.policy.property(safe['label'], 'ontology_version')
        return dict(id=safe['entity_ref'], type=safe['label'], properties=properties,
                    support=[safe, *support], curation_status='accepted', materialization_status='applied',
                    ontology_version=self.facts.ledger.ontology.version)

    def inspect(self, ref, expand=False):
        if ref.startswith('fact:'):
            safe = self.fact(ref)
            if safe['target_kind'] == 'relationship':
                nodes = [self.node(safe['subject_ref']), self.node(safe['object_ref'])]
                return {'nodes': nodes, 'edges': [dict(id=ref, source=safe['subject_ref'],
                    target=safe['object_ref'], type=safe['predicate'], support=[safe],
                    curation_status='accepted', materialization_status='applied')]}
            if safe['target_kind'] != 'node':
                raise DisclosureDenied()
            ref = safe['entity_ref']
        root = self.node(ref)
        nodes, edges = {root['id']: root}, []
        if expand:
            for fid in self.candidates("json_extract(body,'$.target_kind')='relationship' AND "
                    "(json_extract(body,'$.subject_ref')=? OR json_extract(body,'$.object_ref')=?)", (ref, ref), 128):
                try:
                    safe = self.fact(fid)
                    subject, obj = self.node(safe['subject_ref']), self.node(safe['object_ref'])
                except DisclosureDenied:
                    continue
                nodes[subject['id']], nodes[obj['id']] = subject, obj
                edges.append(dict(id=fid, source=subject['id'], target=obj['id'], type=safe['predicate'],
                    support=[safe], curation_status='accepted', materialization_status='applied'))
        return {'nodes': list(nodes.values()), 'edges': edges}


def research(ctx, operation, args, *, deadline=None):
    ctx = authorized(ctx, 'research')
    facts = ctx.knowledge.assertions.facts
    if not isinstance(facts, FactDisclosure) or facts.store.path != Path(ctx.settings_db).resolve():
        raise DisclosureDenied()
    with facts.store.resolve(ctx.identity) as policy, closing(sqlite3.connect(
            facts.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
        if deadline is not None:
            conn.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        reader = ResearchReader(ctx, conn, policy, deadline=deadline)
        if operation == 'search':
            if set(args) - {'q', 'label', 'offset'} or not isinstance(args.get('q', ''), str) or len(args.get('q', '')) > 256:
                raise DisclosureDenied()
            label, offset = args.get('label', ''), args.get('offset', 0)
            if not isinstance(label, str) or len(label) > 128 or type(offset) is not int or not 0 <= offset <= 500:
                raise DisclosureDenied()
            nodes = []
            for fid in reader.candidates("json_extract(body,'$.target_kind')='node'", ()):
                try:
                    node = reader.node(fid)
                except DisclosureDenied:
                    continue
                # Search only after authorization; never candidate identity_claims.
                if (not label or node['type'] == label) and args.get('q', '').casefold() in json.dumps(
                        [node['id'], node['type'], node['properties']], ensure_ascii=False).casefold():
                    nodes.append(node)
            return {'nodes': nodes[offset:offset + 25], 'edges': [],
                    'next_offset': offset + 25 if len(nodes) > offset + 25 else None}
        if operation not in {'inspect', 'expand'} or set(args) != {'id'} or not isinstance(args['id'], str) or len(args['id']) > 256:
            raise DisclosureDenied()
        return reader.inspect(args['id'], expand=operation == 'expand')


def context(ctx, domain, args):
    ctx = authorized(ctx, domain)
    if domain == 'research' or set(args) - {'id', 'catalog'}:
        raise DisclosureDenied()
    arguments = {'entry_id': args.get('id', 'workflow:csv-import' if domain == 'system' else 'ontology:catalog'),
                 'depth': 3, 'limit': 128}
    if domain == 'ontology':
        arguments['catalog'] = args.get('catalog', 'canonical')
    result = run_tool(DOMAINS[domain], arguments, ctx)
    if result.get('status') != 'success':
        raise DisclosureDenied()
    return result['context']


def canvas(ctx, domain, body=None, *, kind='sketch'):
    """Existing per-user CanvasService storage; no second persistence system.

    Store stable references rather than cached disclosed payloads. Revalidate
    references on every save/load; user-authored drafts never confer authority.
    """
    ctx = authorized(ctx, domain)
    if kind not in {'sketch', 'layout', 'graph'}:
        raise DisclosureDenied()
    context_key = f'knowledge:{domain}:{kind}'
    # Explicit user action only. No source/graph/storage initialization on page read.
    service = CanvasService(ctx.settings_db)
    if body is None:
        record = service.load_session(str(ctx.identity.user_id), context_key)
        value = record['canvas'] if record else {}
    else:
        value = body
    if not isinstance(value, dict) or len(json.dumps(value).encode()) > 128 * 1024:
        raise DisclosureDenied()
    if kind == 'layout':
        if set(value) - {'preset', 'view'} or value.get('preset', 'single') not in {'single', 'split', 'three'} or value.get('view', 'graph') not in {'graph', 'entities', 'sketch'}:
            raise DisclosureDenied()
    else:
        if set(value) - {'elements', 'notes'} or not isinstance(value.get('elements', []), list) or len(value.get('elements', [])) > 128:
            raise DisclosureDenied()
        if not isinstance(value.get('notes', ''), str) or len(value.get('notes', '')) > 8000:
            raise DisclosureDenied()
        ids = set()
        for element in value.get('elements', []):
            if (not isinstance(element, dict) or set(element) - {'data', 'position', 'group', 'color'} or
                    not isinstance(element.get('data'), dict) or not isinstance(element.get('position', {}), dict)):
                raise DisclosureDenied()
            if 'color' in element and (not isinstance(element['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', element['color'])):
                raise DisclosureDenied()
            data = element['data']
            if set(data) - {'id', 'label', 'baseLabel', 'displayLabel', 'properties', 'provisional', 'source', 'target', 'reference', 'reference_version', 'catalog', 'marker'}:
                raise DisclosureDenied()
            if not isinstance(data.get('id'), str) or len(data['id']) > 256 or data['id'] in ids:
                raise DisclosureDenied()
            ids.add(data['id'])
            if data.get('reference'):
                ref = data['reference']
                # References never carry an offline copy of protected metadata.
                if set(data) - {'id', 'reference', 'reference_version', 'source', 'target', 'catalog'} or ref != data['id']:
                    raise DisclosureDenied()
                if domain == 'research':
                    research(ctx, 'inspect', {'id': ref})
                else:
                    current = context(ctx, domain, {'id': ref, 'catalog': data.get('catalog', 'canonical')})
                    if data.get('reference_version') != current['version']:
                        raise DisclosureDenied()
            elif kind == 'graph' or data.get('provisional') is not True:
                raise DisclosureDenied()
            elif data.get('marker', 'unresolved') not in {'unresolved', 'suggested investigation', 'proposed assertion', 'pending human review'}:
                raise DisclosureDenied()
            for key, number in element.get('position', {}).items():
                if key not in {'x', 'y'} or type(number) not in {int, float} or not -1e7 < number < 1e7:
                    raise DisclosureDenied()
        for element in value.get('elements', []):
            data = element['data']
            if 'source' in data or 'target' in data:
                if data.get('source') not in ids or data.get('target') not in ids:
                    raise DisclosureDenied()
    # Re-resolve policy after potentially slow reference checks; no model call.
    with PolicyStore(ctx.settings_db).resolve(ctx.identity):
        authorized(ctx, domain)
        if body is not None:
            service.save_session(str(ctx.identity.user_id), value, context_key)
    return value
