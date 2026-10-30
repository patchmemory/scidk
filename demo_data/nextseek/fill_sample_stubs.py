#!/usr/bin/env python3
"""Fill :5010 Sample / SampleType stubs from NExtSEEK-dev (read-only source).

Source: NExtSEEK-dev through the Neo4j HTTP Query API (never written to).
Target: the local :5010 graph. Rules:
  * MATCH only: never creates nodes, never deletes, never touches relationships.
  * Never overwrites a local property that already has a value; differing
    values are reported as conflicts and left alone.
  * On filled nodes ``_imported_stub`` is removed; ``source`` = 'NExtSEEK-dev'
    and ``synced_at`` are set.
  * Dry run is the default and prints counts, property keys, conflicts and 3
    example rows. ``--apply`` writes.

Credentials: NEXTSEEK_HTTP_URL, NEXTSEEK_USER, NEXTSEEK_PASSWORD (optionally
NEXTSEEK_DATABASE) from the process environment or the private env file
(``--env-file``, default: repo-root ``.env``). Local graph: NEO4J_URI, NEO4J_USER,
NEO4J_PASSWORD from the same file. Nothing is printed or stored with secrets.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scidk.services.neo4j_http_client import (  # noqa: E402
    DEFAULT_BATCH_SIZE, Neo4jHttpClient, Neo4jHttpError, chunked,
)

SOURCE = 'NExtSEEK-dev'
STUB_FLAG = '_imported_stub'
RESERVED = {STUB_FLAG, 'source', 'synced_at'}
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
DEFAULT_TARGETS = (('Sample', 'uuid'), ('SampleType', 'id'))
KEY_HINTS = ('uuid', 'id', 'identifier', 'key', 'name', 'sample_id', 'title')
LOOKUP_LIMIT = 5000      # rows per 1,000-value batch; guards against duplicate blow-up
DISCOVERY_LIMIT = 1000
PROBE_VALUES = 200
PROBE_CANDIDATES = 8


def ident(name: str) -> str:
    if not IDENT.match(name or ''):
        raise ValueError(f'Unsafe identifier: {name!r}')
    return f'`{name}`'


def load_env(path: Optional[Path]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if path and path.exists():
        from dotenv import dotenv_values
        values.update({k: v for k, v in dotenv_values(path, interpolate=False).items() if v is not None})
    for key, value in os.environ.items():
        if key.startswith(('NEXTSEEK_', 'NEO4J_')):
            values[key] = value
    return values


def is_storable(value: Any) -> bool:
    """Neo4j property values: scalars, or homogeneous lists of scalars."""
    scalar = (str, int, float, bool)
    if isinstance(value, scalar):
        return True
    return isinstance(value, list) and all(isinstance(v, scalar) for v in value) \
        and len({type(v) for v in value}) <= 1


def short(value: Any, width: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= width else text[:width - 3] + '...'


# ----------------------------------------------------------------------------- remote reads


def lookup(client: Neo4jHttpClient, label: str, key: str, values: List[Any]) -> Dict[Any, List[Dict[str, Any]]]:
    statement = (f'MATCH (n:{ident(label)}) WHERE n.{ident(key)} IN $values '
                 f'RETURN properties(n) AS p LIMIT {LOOKUP_LIMIT}')
    found: Dict[Any, List[Dict[str, Any]]] = {}
    for batch in chunked(values, DEFAULT_BATCH_SIZE):
        for row in client.query(statement, {'values': batch}):
            found.setdefault(row['p'].get(key), []).append(row['p'])
    return found


def find_remote_key(client: Neo4jHttpClient, label: str, default_key: str, local_values: List[Any]
                    ) -> Tuple[str, List[Tuple[str, int]]]:
    """Return (key, probe_results). Default key wins when it matches anything."""
    probe = local_values[:PROBE_VALUES]
    tried: List[Tuple[str, int]] = []
    default_hits = len(lookup(client, label, default_key, probe))
    tried.append((default_key, default_hits))
    if default_hits:
        return default_key, tried
    kind = type(probe[0]) if probe else str
    sample = client.query(f'MATCH (n:{ident(label)}) RETURN properties(n) AS p LIMIT {DISCOVERY_LIMIT}')
    candidates = Counter()
    for row in sample:
        for k, v in row['p'].items():
            if k != default_key and isinstance(v, kind) and not isinstance(v, bool) and IDENT.match(k):
                candidates[k] += 1
    ranked = sorted(candidates, key=lambda k: (not any(h in k.lower() for h in KEY_HINTS), -candidates[k], k))
    for cand in ranked[:PROBE_CANDIDATES]:
        tried.append((cand, len(lookup(client, label, cand, probe))))
    best = max(tried, key=lambda t: t[1])
    return best[0], tried


# ----------------------------------------------------------------------------- planning
def plan_node(local: Dict[str, Any], remote: Dict[str, Any],
              conflicts: Counter, skipped: Counter) -> Dict[str, Any]:
    """Properties to set on ``local`` from ``remote``. Never overwrites existing values."""
    props: Dict[str, Any] = {}
    for key, value in remote.items():
        if key in RESERVED:
            skipped[f'{key} (reserved)'] += 1
            continue
        if not is_storable(value):
            skipped[f'{key} (not a storable type)'] += 1
            continue
        if key in local and local[key] is not None:
            if local[key] != value:
                conflicts[key] += 1
            continue
        props[key] = value
    if local.get('source') not in (None, SOURCE):
        conflicts['source'] += 1
    return props


def local_nodes(session, label: str, match_key: str) -> List[Dict[str, Any]]:
    result = session.run(f'MATCH (n:{ident(label)}) WHERE n.{ident(STUB_FLAG)} IS NOT NULL '
                         f'RETURN properties(n) AS p ORDER BY n.{ident(match_key)}')
    return [r['p'] for r in result]


def build_plan(client: Neo4jHttpClient, nodes: List[Dict[str, Any]], label: str, match_key: str,
               remote_key: Optional[str]) -> Dict[str, Any]:
    values = [n[match_key] for n in nodes if n.get(match_key) is not None]
    probes: List[Tuple[str, int]] = []
    if remote_key is None:
        remote_key, probes = find_remote_key(client, label, match_key, values)
    found = lookup(client, label, remote_key, values)
    conflicts: Counter = Counter()
    skipped: Counter = Counter()
    key_counts: Counter = Counter()
    updates: List[Dict[str, Any]] = []
    matched = ambiguous = 0
    examples: List[Dict[str, Any]] = []
    for node in nodes:
        remotes = found.get(node.get(match_key), [])
        if not remotes:
            continue
        if len(remotes) > 1:
            ambiguous += 1
            continue
        matched += 1
        props = plan_node(node, remotes[0], conflicts, skipped)
        key_counts.update(props.keys())
        updates.append({'key': node[match_key], 'props': props})
        if len(examples) < 3:
            examples.append({'key': node[match_key], 'props': props})
    return dict(label=label, match_key=match_key, remote_key=remote_key, probes=probes,
                local_stubs=len(nodes), matched=matched, ambiguous=ambiguous,
                unmatched=len(values) - matched - ambiguous, conflicts=conflicts,
                skipped=skipped, key_counts=key_counts, updates=updates, examples=examples)


def print_plan(plan: Dict[str, Any], applying: bool) -> None:
    print(f"\n== {plan['label']} (local key '{plan['match_key']}' <-> NExtSEEK key '{plan['remote_key']}') ==")
    if plan['probes']:
        print('key probe (hits in first %d values): %s' % (
            PROBE_VALUES, ', '.join(f'{k}={n}' for k, n in plan['probes'])))
    print(f"local stubs: {plan['local_stubs']}")
    print(f"matched in NExtSEEK: {plan['matched']}  unmatched: {plan['unmatched']}  "
          f"ambiguous (>1 remote, skipped): {plan['ambiguous']}")
    print(f"nodes {'filled' if applying else 'that would be filled'}: {plan['matched']}")
    print('property keys (nodes receiving each): ' +
          (', '.join(f'{k}={n}' for k, n in sorted(plan['key_counts'].items())) or 'none'))
    print('conflicts (kept local value): ' +
          (', '.join(f'{k}={n}' for k, n in sorted(plan['conflicts'].items())) or 'none'))
    if plan['skipped']:
        print('remote properties skipped: ' + ', '.join(f'{k}={n}' for k, n in sorted(plan['skipped'].items())))
    for row in plan['examples']:
        props = {k: short(v) for k, v in row['props'].items()}
        print(f"  example {plan['match_key']}={short(row['key'])}: {props}")


# ----------------------------------------------------------------------------- apply
def apply_plan(session, plan: Dict[str, Any], synced_at: str) -> int:
    label, key = plan['label'], plan['match_key']
    statement = (
        f'UNWIND $rows AS row '
        f'MATCH (n:{ident(label)} {{{ident(key)}: row.key}}) '
        f'WHERE n.{ident(STUB_FLAG)} IS NOT NULL '
        f'SET n += row.props '
        f'SET n.source = coalesce(n.source, $source) '
        f'SET n.synced_at = CASE WHEN n.source = $source THEN $synced_at ELSE n.synced_at END '
        f'REMOVE n.{ident(STUB_FLAG)} '
        f'RETURN count(n) AS filled')
    filled = 0
    for batch in chunked(plan['updates'], DEFAULT_BATCH_SIZE):
        record = session.run(statement, rows=batch, source=SOURCE, synced_at=synced_at).single()
        filled += record['filled']
    return filled


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='default: report only, write nothing')
    mode.add_argument('--apply', action='store_true', help='write to the local graph')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--sample-remote-key', help="NExtSEEK property matching local Sample.uuid (auto-probed if unset)")
    parser.add_argument('--sampletype-remote-key', help="NExtSEEK property matching local SampleType.id (auto-probed if unset)")
    args = parser.parse_args(argv)

    env = load_env(args.env_file)
    try:
        client = Neo4jHttpClient.from_env(env, database=env.get('NEXTSEEK_DATABASE', 'neo4j'))
    except Neo4jHttpError as exc:
        print(f'ERROR: {exc}. Add them to {args.env_file} or the environment.', file=sys.stderr)
        return 2
    if not env.get('NEO4J_URI'):
        print('ERROR: NEO4J_URI missing for the local graph', file=sys.stderr)
        return 2

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(env['NEO4J_URI'], auth=(env.get('NEO4J_USER'), env.get('NEO4J_PASSWORD')))
    remote_keys = {'Sample': args.sample_remote_key, 'SampleType': args.sampletype_remote_key}
    plans = []
    try:
        with driver.session(database=env.get('SCIDK_NEO4J_DATABASE', 'neo4j'), default_access_mode='READ') as session:
            for label, match_key in DEFAULT_TARGETS:
                nodes = local_nodes(session, label, match_key)
                plans.append(build_plan(client, nodes, label, match_key, remote_keys[label]))
    except Neo4jHttpError as exc:
        print(f'ERROR reading NExtSEEK: {exc}', file=sys.stderr)
        return 1

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN (nothing written)'}")
    for plan in plans:
        print_plan(plan, args.apply)

    if args.apply:
        synced_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with driver.session(database=env.get('SCIDK_NEO4J_DATABASE', 'neo4j')) as session:
            for plan in plans:
                print(f"{plan['label']}: filled {apply_plan(session, plan, synced_at)} of {plan['matched']} planned")
    else:
        print('\nDry run only. Re-run with --apply after approval.')
    driver.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
