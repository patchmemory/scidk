"""Read-only summary of the relationships present in the primary graph.

Feeds the Knowledge -> Relationships catalog. It answers one question - which relationship types exist, how many
edges each has, and which source/target labels they connect - with a single aggregation over the PRIMARY graph.
It never touches external profiles, never writes, and returns no per-edge detail (examples are fetched on demand
by the UI once a relationship is selected).

A short-lived in-process cache avoids re-running the aggregation on every page load. ``refresh=True`` always
re-queries, and a successful write through the links API invalidates the cache (see ``api_links``).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

TTL_SECONDS = 120

# One pass over the edges. Grouping on the first label of each endpoint matches the long-standing discovery
# convention; unlabelled endpoints are dropped below.
SUMMARY_QUERY = (
    "MATCH (a)-[r]->(b) "
    "RETURN head(labels(a)) AS source_label, type(r) AS rel_type, head(labels(b)) AS target_label, count(*) AS edge_count"
)

_lock = threading.Lock()
_cache: Dict[Any, Dict[str, Any]] = {}


def invalidate() -> None:
    """Drop every cached summary (called after writes, and by tests)."""
    with _lock:
        _cache.clear()


def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate (source_label, rel_type, target_label, edge_count) rows into per-type entries."""
    by_type: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        source, rel_type, target = row.get('source_label'), row.get('rel_type'), row.get('target_label')
        count = int(row.get('edge_count') or 0)
        if not rel_type or not source or not target or count <= 0:
            continue
        entry = by_type.setdefault(rel_type, {'rel_type': rel_type, 'edge_count': 0, 'sources': {}, 'targets': {}, 'patterns': []})
        entry['edge_count'] += count
        entry['sources'][source] = entry['sources'].get(source, 0) + count
        entry['targets'][target] = entry['targets'].get(target, 0) + count
        entry['patterns'].append({'source_label': source, 'target_label': target, 'edge_count': count})
    types = []
    for entry in by_type.values():
        entry['patterns'].sort(key=lambda p: (-p['edge_count'], p['source_label'], p['target_label']))
        entry['sources'] = [{'label': k, 'edge_count': v} for k, v in sorted(entry['sources'].items(), key=lambda kv: (-kv[1], kv[0]))]
        entry['targets'] = [{'label': k, 'edge_count': v} for k, v in sorted(entry['targets'].items(), key=lambda kv: (-kv[1], kv[0]))]
        types.append(entry)
    types.sort(key=lambda t: (-t['edge_count'], t['rel_type']))
    return {
        'types': types,
        'type_count': len(types),
        'pattern_count': sum(len(t['patterns']) for t in types),
        'total_edges': sum(t['edge_count'] for t in types),
    }


def _primary_key(app: Any) -> tuple:
    from .neo4j_client import get_neo4j_params
    uri, user, _pwd, database, _auth = get_neo4j_params(app)
    return (uri, user, database)


def _query_primary() -> List[Dict[str, Any]]:
    from .neo4j_client import get_neo4j_client
    client = get_neo4j_client()
    if not client:
        raise RuntimeError('Primary graph is not configured')
    try:
        return client.execute_read(SUMMARY_QUERY)
    finally:
        client.close()


def get_summary(app: Any = None, refresh: bool = False, ttl: Optional[float] = None,
                query: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                clock: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Return the primary-graph relationship summary, from cache when it is still fresh.

    Concurrent callers share one query: the first runs it while the rest wait on the lock and then read the
    result. ``refresh=True`` bypasses the cache, unless another request already refreshed it after this one began.
    """
    ttl = TTL_SECONDS if ttl is None else ttl
    started = clock()
    key = _primary_key(app)
    with _lock:
        hit = _cache.get(key)
        if hit and (not refresh or hit['generated_at'] >= started) and clock() - hit['generated_at'] <= ttl:
            return _present(hit, cached=True, now=clock(), ttl=ttl)
        t0 = time.perf_counter()
        rows = (query or _query_primary)()
        entry = dict(build_summary(rows), generated_at=clock(), elapsed_ms=round((time.perf_counter() - t0) * 1000))
        _cache[key] = entry
        return _present(entry, cached=False, now=clock(), ttl=ttl)


def _present(entry: Dict[str, Any], cached: bool, now: float, ttl: float) -> Dict[str, Any]:
    out = dict(entry)
    out.update(cached=cached, age_seconds=round(max(0.0, now - entry['generated_at']), 1), ttl_seconds=ttl, scope='primary')
    return out
