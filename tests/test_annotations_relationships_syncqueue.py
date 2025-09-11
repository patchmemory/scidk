import os
import sqlite3
from pathlib import Path

import time

from scidk.app import create_app
from scidk.core import path_index_sqlite as pix
from scidk.core import annotations_sqlite as ann


def test_migrations_add_relationships_and_syncqueue(monkeypatch, tmp_path):
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    # Boot app to trigger migrations
    app = create_app()
    assert app is not None

    # Ensure schema version >= 3
    conn = pix.connect()
    try:
        row = conn.execute('SELECT version FROM schema_migrations LIMIT 1').fetchone()
        assert row is not None
        assert int(row[0]) >= 3

        def has_table(name: str) -> bool:
            r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            return r is not None

        assert has_table('relationships')
        assert has_table('sync_queue')
    finally:
        conn.close()

    # CRUD: relationships
    ts = time.time()
    r = ann.create_relationship(from_id='file:A', to_id='file:B', rel_type='DERIVED_FROM', properties_json='{"w":1}', created_ts=ts)
    assert r['id'] > 0
    rels_a = ann.list_relationships('file:A')
    rels_b = ann.list_relationships('file:B')
    assert any(rr['id'] == r['id'] for rr in rels_a)
    assert any(rr['id'] == r['id'] for rr in rels_b)
    # delete
    ok = ann.delete_relationship(r['id'])
    assert ok is True
    rels_a2 = ann.list_relationships('file:A')
    assert not any(rr['id'] == r['id'] for rr in rels_a2)

    # CRUD: sync queue
    qid = ann.enqueue_sync(entity_type='file', entity_id='file:Z', action='upsert', payload='{}', created_ts=ts)
    assert qid > 0
    items = ann.dequeue_unprocessed(limit=10)
    assert any(it['id'] == qid for it in items)
    # mark processed
    ok2 = ann.mark_processed(qid, processed_ts=time.time())
    assert ok2 is True
    items2 = ann.dequeue_unprocessed(limit=10)
    assert not any(it['id'] == qid for it in items2)

    # DB file wrote
    assert Path(db_path).exists()
