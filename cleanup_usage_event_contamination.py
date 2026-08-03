#!/usr/bin/env python3
"""One-time cleanup after the Cycle 1 Task B property-attribution fix.

Before the fix, ``extract_labels_and_properties`` attributed every property it
found to every label in the query, so

    MATCH (p:Project)-[:PI_OF]-(u:Person) RETURN p.cac_protocol, u.email

logged cac_protocol and email against *both* Project and Person. Those rows are
in ``usage_event``, and ``flush_rankings()`` has already folded them into
``property_ranking``, which shapes the chat schema context.

This script deletes them so rankings rebuild cleanly from new queries.

Scope — deliberately narrower than a blanket ``DELETE FROM usage_event``:

  * ``event_type = 'query_executed'`` rows are deleted. These are the only rows
    the buggy parser produced.
  * ``event_type = 'concept_graph_plan'`` rows are KEPT. They are written
    directly by api_chat.py with ``label_name = ''`` and
    ``property_name = NULL``, carry the Concept Graph traversal log in
    ``traversal_json``, and never went through the buggy parser. A blanket
    delete would throw them away for no benefit.
  * ``property_ranking`` is truncated. ``flush_rankings()`` upserts and never
    deletes, so a contaminated (label, property) pair would otherwise survive in
    the table that feeds chat context even after its source rows are gone.

Idempotent — safe to run twice; the second run reports zero rows.

Usage:
    python cleanup_usage_event_contamination.py [--db PATH] [--dry-run]

The database defaults to $SCIDK_SETTINGS_DB, then ./scidk_settings.db.
"""
import argparse
import os
import sqlite3
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--db',
        default=os.environ.get('SCIDK_SETTINGS_DB') or 'scidk_settings.db',
        help='Path to scidk_settings.db (default: $SCIDK_SETTINGS_DB or ./scidk_settings.db)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Report what would be deleted without changing anything',
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"error: no such database: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_event'"
        ).fetchone()
        if not table:
            print(f"{args.db}: no usage_event table — nothing to clean.")
            return 0

        contaminated = conn.execute(
            "SELECT COUNT(*) FROM usage_event WHERE event_type = 'query_executed'"
        ).fetchone()[0]
        kept = conn.execute(
            "SELECT COUNT(*) FROM usage_event WHERE event_type <> 'query_executed'"
        ).fetchone()[0]
        rankings = conn.execute(
            "SELECT COUNT(*) FROM property_ranking"
        ).fetchone()[0]

        print(f"{args.db}")
        print(f"  usage_event 'query_executed' rows to delete: {contaminated}")
        print(f"  usage_event other rows kept (traversal logs): {kept}")
        print(f"  property_ranking rows to clear:               {rankings}")

        if args.dry_run:
            print("  (dry run — nothing changed)")
            return 0

        conn.execute("DELETE FROM usage_event WHERE event_type = 'query_executed'")
        conn.execute("DELETE FROM property_ranking")
        conn.commit()
        print("  done — rankings will rebuild from new queries.")
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
