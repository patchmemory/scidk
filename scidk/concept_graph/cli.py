"""Command-line seeding for the Concept Graph.

    python -m scidk.concept_graph seed                # intents, tools, MCP tools
    python -m scidk.concept_graph seed --reset        # clear the graph first
    python -m scidk.concept_graph seed --with-labels  # also mirror the research schema
    python -m scidk.concept_graph status              # read-only: what is in there
    scidk-concept-graph seed                          # same, as an installed script

Cycle 8 Task C. Before this there were two ways to seed and neither was an entry
point: ``POST /api/chat/concept-graph/reseed``, which needs a running server, and
``seed_concept_graph.py`` at the repo root, which builds a whole Flask app to reach
one driver and resolves ``intents.yaml`` against the working directory. Neither
seeded the MCP tools from the canonical registry, and neither could clear first —
so "re-initialise this instance cleanly" had no answer.

This talks to the concept graph and nothing else. It reads its connection from the
same environment variables the app does (``SCIDK_CONCEPT_NEO4J_URI``,
``SCIDK_CONCEPT_NEO4J_AUTH``), so there is no app context and no settings database
in the way. ``--with-labels`` is the one exception: mirroring labels needs the
research graph, whose parameters come from ``NEO4J_URI``/``NEO4J_PASSWORD``.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from . import INTENTS_YAML

#: Every node label the concept graph owns starts with this. ``--reset`` deletes by
#: prefix rather than by an enumerated list, so a label added later is still cleared.
CONCEPT_LABEL_PREFIX = 'Concept_'

_MATCH_CONCEPT_NODES = (
    "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH $prefix) "
)

logger = logging.getLogger(__name__)


def _ollama_endpoint() -> str:
    return os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')


def _open_concept_driver():
    """The concept-graph driver, or None with the reason printed.

    ``get_concept_driver`` never raises and logs at WARNING; a CLI needs the
    configuration spelled out, because "unavailable" is almost always one of these
    three variables pointing somewhere else.
    """
    from ..services.concept_graph_service import get_concept_driver

    driver = get_concept_driver()
    if driver is None:
        uri = os.environ.get('SCIDK_CONCEPT_NEO4J_URI', 'bolt://localhost:7689')
        print(f"error: concept graph unreachable at {uri}", file=sys.stderr)
        print("Check:", file=sys.stderr)
        print("  SCIDK_CONCEPT_NEO4J_URI   (default bolt://localhost:7689)",
              file=sys.stderr)
        print("  SCIDK_CONCEPT_NEO4J_AUTH  (default neo4j/concept-graph-password)",
              file=sys.stderr)
        print("  SCIDK_CONCEPT_GRAPH_ENABLED", file=sys.stderr)
    return driver


def _confirm_reset(assume_yes: bool) -> bool:
    """Gate the destructive path. Non-interactive callers must pass ``--yes``."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("error: --reset deletes every Concept_* node. Re-run with --yes to "
              "confirm non-interactively.", file=sys.stderr)
        return False
    answer = input(
        f"Delete every {CONCEPT_LABEL_PREFIX}* node in the concept graph "
        "and re-seed? [y/N] "
    )
    return answer.strip().lower() in ('y', 'yes')


def _clear_concept_nodes(driver) -> int:
    """DETACH DELETE every Concept_* node. Returns how many were removed.

    Counted before the delete rather than aggregated after it: the count is for the
    operator's benefit, and a delete that reports a number it derived from its own
    result set is the kind of thing that reads as reassuring when it is wrong.
    """
    with driver.session() as session:
        record = session.run(
            _MATCH_CONCEPT_NODES + "RETURN count(n) AS total",
            prefix=CONCEPT_LABEL_PREFIX,
        ).single()
        total = record['total'] if record else 0

        session.run(_MATCH_CONCEPT_NODES + "DETACH DELETE n",
                    prefix=CONCEPT_LABEL_PREFIX)

    return total


def _seed(args: argparse.Namespace) -> int:
    from ..services.concept_graph_service import (
        seed_intents_from_yaml,
        seed_mcp_tools,
        seed_tools_from_yaml,
        sync_labels_from_schema,
    )

    if not INTENTS_YAML.exists():
        print(f"error: definitions not found at {INTENTS_YAML}", file=sys.stderr)
        return 1

    if args.reset and not _confirm_reset(args.yes):
        print("Aborted; nothing was changed.")
        return 1

    driver = _open_concept_driver()
    if driver is None:
        return 1

    ollama = _ollama_endpoint()
    failures = 0

    try:
        if args.reset:
            deleted = _clear_concept_nodes(driver)
            print(f"Cleared {deleted} {CONCEPT_LABEL_PREFIX}* nodes")

        print(f"Seeding from {INTENTS_YAML}")
        print(f"Embeddings via {ollama}")

        intents = seed_intents_from_yaml(driver, str(INTENTS_YAML), ollama)
        print(f"  intents:   {intents.get('embedded', 0)} embedded, "
              f"{intents.get('failed', 0)} failed")
        failures += intents.get('failed', 0)

        tools = seed_tools_from_yaml(driver, str(INTENTS_YAML), ollama)
        print(f"  tools:     {tools.get('embedded', 0)} embedded, "
              f"{tools.get('failed', 0)} failed")
        failures += tools.get('failed', 0)

        if args.skip_mcp_tools:
            print("  mcp tools: skipped")
        else:
            mcp = seed_mcp_tools(driver, ollama)
            print(f"  mcp tools: {mcp.get('seeded', 0)} seeded, "
                  f"{mcp.get('failed', 0)} failed, "
                  f"{mcp.get('edges_created', 0)} edges wired")
            failures += mcp.get('failed', 0)
            for error in mcp.get('errors', []):
                print(f"    ! {error}", file=sys.stderr)

        if args.with_labels:
            failures += _sync_labels(driver, sync_labels_from_schema)

        _print_totals(driver)
    except Exception as e:
        print(f"error: seeding failed: {e}", file=sys.stderr)
        logger.debug("Seeding failed", exc_info=True)
        return 1
    finally:
        driver.close()

    if failures:
        print(f"\nFinished with {failures} failure(s). Embeddings need Ollama at "
              f"{ollama}.", file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


def _sync_labels(concept_driver, sync_labels_from_schema) -> int:
    """Mirror the research graph's schema into :Concept_Label. Returns failure count.

    Parameters come from the environment rather than an app: ``get_neo4j_params``
    reads ``app.extensions`` first and falls back to ``NEO4J_URI`` and friends, and
    with no app there is only the fallback. A CLI that quietly built a Flask app to
    read the settings database would also inherit its scheduler and plugin loading.
    """
    from neo4j import GraphDatabase

    from ..services.neo4j_client import get_neo4j_params

    uri, user, pwd, _database, auth_mode = get_neo4j_params()
    if not uri:
        print("  labels:    skipped — research graph not configured "
              "(set NEO4J_URI)", file=sys.stderr)
        return 1

    auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
    research_driver = GraphDatabase.driver(uri, auth=auth)
    try:
        # sqlite_conn is accepted and unused by sync_labels_from_schema.
        result = sync_labels_from_schema(concept_driver, research_driver, None)
        print(f"  labels:    {result.get('labels', 0)} labels, "
              f"{result.get('relationships', 0)} relationships, "
              f"{result.get('edges', 0)} edges (from {uri})")
    finally:
        research_driver.close()
    return 0


def _print_totals(driver) -> None:
    """What is actually in the graph now, read back rather than accumulated."""
    with driver.session() as session:
        rows = session.run(
            _MATCH_CONCEPT_NODES + "RETURN labels(n)[0] AS label, count(n) AS total "
            "ORDER BY label",
            prefix=CONCEPT_LABEL_PREFIX,
        ).data()
        edges = session.run(
            "MATCH ()-[r:SATISFIES]->() RETURN count(r) AS total"
        ).single()

    print("\nGraph contents:")
    for row in rows:
        print(f"  {row['label']}: {row['total']}")
    print(f"  SATISFIES edges: {edges['total'] if edges else 0}")


def _status(args: argparse.Namespace) -> int:
    """Node and edge counts, and nothing else.

    Read-only on purpose: it is how you check a deployment's concept graph, and how
    ``seed`` itself can be pointed at an instance and verified without writing to it.
    """
    driver = _open_concept_driver()
    if driver is None:
        return 1

    try:
        print(f"Connected to "
              f"{os.environ.get('SCIDK_CONCEPT_NEO4J_URI', 'bolt://localhost:7689')}")
        _print_totals(driver)
    except Exception as e:
        print(f"error: could not read the concept graph: {e}", file=sys.stderr)
        logger.debug("Status failed", exc_info=True)
        return 1
    finally:
        driver.close()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='scidk-concept-graph',
        description='Seed and re-initialise the SciDK Concept Graph.',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    seed = subparsers.add_parser(
        'seed',
        help='seed intents and tools from intents.yaml plus MCP tools from the '
             'canonical registry',
        description='Seeding is idempotent — every write is a MERGE on the node '
                    'name — so this is safe to re-run without --reset.',
    )
    seed.add_argument(
        '--reset', action='store_true',
        help=f'DETACH DELETE every {CONCEPT_LABEL_PREFIX}* node before seeding',
    )
    seed.add_argument(
        '-y', '--yes', action='store_true',
        help='skip the --reset confirmation prompt (required when not on a tty)',
    )
    seed.add_argument(
        '--with-labels', action='store_true',
        help='also mirror the research graph schema into :Concept_Label '
             '(needs NEO4J_URI)',
    )
    seed.add_argument(
        '--skip-mcp-tools', action='store_true',
        help='seed only what intents.yaml declares, not the MCP tool registry',
    )
    seed.set_defaults(handler=_seed)

    status = subparsers.add_parser(
        'status',
        help='node and edge counts for the configured concept graph (read-only)',
    )
    status.set_defaults(handler=_status)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # WARNING, not INFO: the service layer logs one line per embedded intent and
    # per decayed edge, which would bury the summary this prints.
    logging.basicConfig(
        level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')

    return args.handler(args)
