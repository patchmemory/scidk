"""Explicit v1 → v2 migration. Never called by application startup."""
from .contracts import CONTRACT, ConflictError

EXTRA_TABLES = {'outbox', 'receipts', 'graph_binding'}
DDL = '''
CREATE TABLE graph_binding (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), graph_target TEXT NOT NULL
);
CREATE TABLE outbox (
 operation_id TEXT PRIMARY KEY, operation_hash TEXT NOT NULL,
 body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE receipts (
 operation_id TEXT PRIMARY KEY REFERENCES outbox,
 operation_hash TEXT NOT NULL, graph_target TEXT NOT NULL,
 outcome TEXT NOT NULL CHECK(outcome IN ('applied', 'obsolete')),
 applied_at TEXT NOT NULL
);
'''


def upgrade(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    base = {'curation_schema', 'evidence', 'assertions', 'decisions', 'submissions'}
    versions = conn.execute('SELECT version, contract FROM curation_schema ORDER BY version').fetchall()
    if tables == base | EXTRA_TABLES and versions == [(1, CONTRACT), (2, CONTRACT)]:
        return
    if tables != base or versions != [(1, CONTRACT)]:
        raise ConflictError('Unsupported curation schema; migration refused')
    triggers = '\n'.join(
        f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'append-only curation ledger'); END;"
        for table in EXTRA_TABLES for action in ('UPDATE', 'DELETE'))
    conn.executescript('BEGIN IMMEDIATE;\n' + DDL + triggers +
                       f"\nINSERT INTO curation_schema VALUES (2, '{CONTRACT}');\nCOMMIT;")
