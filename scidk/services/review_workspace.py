"""Bounded Review adapters over Stage 2 decisions and Stage 5 disclosure.

No graph client, new ledger, model tools, or materialization path.
"""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

from ..agent_tools.assertions import AssertionAccess
from ..agent_tools.registry import available_tool_definitions, run_tool
from ..agent_tools.security import DisclosureDenied, PolicyStore
from ..curation.auth import request_reviewer
from ..curation.review import ReviewService
from .overview_chat import context_turn


def authorized(ctx, tool='get_assertion'):
    ctx = replace(ctx, profile='review')
    if (not ctx.identity or ctx.identity.token_id or ctx.identity.channel != 'chat'
            or tool not in {d['name'] for d in available_tool_definitions(ctx)}
            or not isinstance(ctx.knowledge.assertions, AssertionAccess)
            or ctx.knowledge.assertions.facts.store.path != Path(ctx.settings_db).resolve()):
        raise DisclosureDenied()
    return ctx


def inspect(ctx, aid, *, history=False):
    ctx = authorized(ctx)
    if not isinstance(aid, str) or not 0 < len(aid) <= 256 or type(history) is not bool:
        raise DisclosureDenied()
    access = ctx.knowledge.assertions
    with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
        result = access.inspect(policy, aid, include_history=history)
        # Immutable source metadata is checked independently, never copied from
        # candidate identity claims, source locators or raw source payloads.
        with closing(sqlite3.connect(access.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
            claim = json.loads(conn.execute('SELECT body FROM assertions WHERE assertion_id=?', (aid,)).fetchone()[0])
            policy.property('Assertion', 'source_scope')
            result['source_scope'] = claim['source_scope']
            for evidence in result['evidence']:
                source = json.loads(conn.execute('SELECT body FROM evidence WHERE evidence_id=?',
                                                (evidence['evidence_id'],)).fetchone()[0])
                policy.property('EvidenceSource', 'accessed_at')
                evidence['accessed_at'] = source['accessed_at']
    return result


def queue(ctx, args):
    ctx = authorized(ctx)
    allowed = {'kind', 'domain', 'status', 'source', 'offset', 'context_id'}
    if set(args) - allowed:
        raise DisclosureDenied()
    for key in allowed - {'offset'}:
        if not isinstance(args.get(key, ''), str) or len(args.get(key, '')) > 256:
            raise DisclosureDenied()
    if args.get('kind', '') not in {'', 'node', 'property', 'relationship'} or args.get('domain', '') not in {'', 'research', 'ontology', 'system'} or args.get('status', '') not in {'', 'proposed', 'accepted', 'rejected', 'superseded'}:
        raise DisclosureDenied()
    offset = args.get('offset', 0)
    if type(offset) is not int or not 0 <= offset <= 500:
        raise DisclosureDenied()
    with closing(sqlite3.connect(ctx.knowledge.assertions.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
        ids = conn.execute('SELECT assertion_id FROM assertions ORDER BY assertion_id LIMIT 501').fetchall()
    if len(ids) > 500:
        raise ValueError('Bound exceeded')
    permitted, size = [], 0
    for (aid,) in ids:
        try:
            item = inspect(ctx, aid)
        except DisclosureDenied:
            continue
        size += len(json.dumps(item).encode())
        if size > 2 * 1024 * 1024:
            raise ValueError('Bound exceeded')
        claim = item['claim']
        # Filters and pagination operate on disclosed records only.
        if any(args.get(k) and args[k] != value for k, value in (
                ('kind', claim['target_kind']), ('domain', claim['domain']), ('status', item['curation_status']),
                ('source', item['source_scope']['resource_id']))):
            continue
        context_id = args.get('context_id')
        if context_id and context_id not in {aid, item['fact_id'], *(claim.get(k) for k in
                ('entity_ref', 'target_ref', 'subject_ref', 'object_ref'))}:
            continue
        permitted.append(item)
    return {'items': permitted[offset:offset + 20],
            'next_offset': offset + 20 if len(permitted) > offset + 20 else None,
            'limitations': ['Reviewer assignment is unavailable: the ledger has no assignment contract.',
                            'Search is bounded to 500 candidates; no inaccessible counts are returned.']}


def preview(ctx, service, aid):
    ctx = authorized(ctx)
    reviewer = request_reviewer()
    if (str(ctx.identity.user_id) != reviewer or not isinstance(service, ReviewService)
            or service.ledger is not ctx.knowledge.assertions.ledger):
        raise DisclosureDenied()
    selected = inspect(ctx, aid)
    raw = service.preview(aid, reviewer=reviewer)
    # Preview includes dependency/conflict IDs. Authorize each before returning
    # even a digest. The raw claim/diff and unfiltered preview never reach UI.
    related = {s['assertion_id'] for s in raw['support']}
    related.update(raw['conflict_ids'])
    for dependency in raw['dependencies']:
        related.update(s['assertion_id'] for s in dependency['states'])
    for related_id in related:
        inspect(ctx, related_id)
    if selected['revision'] != raw['expected_revision']:
        raise DisclosureDenied()
    return {'expected_revision': raw['expected_revision'], 'preview_digest': raw['preview_digest'],
            'conflict_ids': raw['conflict_ids'], 'notice': 'Decision only; graph materialization remains pending.'}


def decide(ctx, service, body):
    if (set(body) - {'id', 'action', 'expected_revision', 'preview_digest', 'rationale', 'superseded_by', 'confirm'}
            or body.get('confirm') is not True):
        raise DisclosureDenied()
    checked = preview(ctx, service, body.get('id'))
    if body.get('superseded_by'):
        inspect(ctx, body['superseded_by'])
    if any(body.get(key) != checked[key] for key in ('expected_revision', 'preview_digest')):
        from ..curation.contracts import ConflictError
        raise ConflictError('Stale preview')
    reviewer = request_reviewer()
    result = service.review(body['id'], {k: v for k, v in body.items() if k not in {'id', 'confirm'}}, reviewer=reviewer)
    # Immutable decision provenance and outbox were committed atomically above.
    # Match the existing human route's additional best-effort account audit.
    from ..core.auth import get_auth_manager
    from flask import request
    auth = get_auth_manager(db_path=ctx.settings_db)
    try:
        user = auth.get_user(int(reviewer))
        auth.log_audit(user['username'], 'curation_review', details=result['decision_id'], ip_address=request.remote_addr)
    finally:
        auth.close()
    return result


def assistant(ctx, body):
    ctx = authorized(ctx)
    if not isinstance(body, dict) or set(body) != {'id', 'message', 'send_question'}:
        raise DisclosureDenied()
    inspect(ctx, body['id'])
    def related_context(current_ctx, selected):
        # Same-fact comparisons use only independently disclosed assertions.
        # This never exposes a count or identifier for inaccessible support.
        fact_id = selected['assertion']['fact_id']
        with closing(sqlite3.connect(current_ctx.knowledge.assertions.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
            ids = conn.execute('SELECT assertion_id FROM assertions WHERE fact_id=? ORDER BY assertion_id LIMIT 51',
                               (fact_id,)).fetchall()
        if len(ids) > 50:
            raise DisclosureDenied()
        with PolicyStore(current_ctx.settings_db).resolve(current_ctx.identity) as policy:
            policy.property('Assertion', 'related_assertions')
        permitted = []
        for (aid,) in ids:
            if aid == body['id']:
                continue
            try:
                permitted.append(inspect(current_ctx, aid))
            except DisclosureDenied:
                continue
        context = {**selected, 'related_assertions': permitted,
                   'comparison_notice': 'Only permitted same-fact assertions are supplied. This is not an exhaustive conflict report.'}
        if len(json.dumps(context).encode()) > 2 * 1024 * 1024:
            raise DisclosureDenied()
        return context
    # Server binds profile, selection and tool. No automatic proposal tools.
    return context_turn(ctx, {'message': body['message'], 'send_question': body['send_question'],
        'context': {'tool': 'get_assertion', 'arguments': {'assertion_id': body['id']}}},
        profile='review', allowed={'get_assertion'}, enrich=related_context)


def propose(ctx, body):
    ctx = authorized(ctx, 'submit_assertion')
    if set(body) != {'assertion', 'caller_key', 'confirm'} or body['confirm'] is not True:
        raise DisclosureDenied()
    result = run_tool('submit_assertion', {k: body[k] for k in ('assertion', 'caller_key')}, ctx)
    if result.get('status') != 'success':
        raise DisclosureDenied()
    return result
