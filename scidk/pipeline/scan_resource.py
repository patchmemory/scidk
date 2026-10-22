"""Files-page scans kept as scan-database Resources (option A, A3 + A5).

A scan from the Files page leaves its scanner database behind as a snapshot,
and gets a ``pipeline_source`` row of type ``scan_db`` pointing at it, so the
scan shows up under Resources ready for the Task 2 FAIR check and Review.

The ``scan_db`` plugin itself (its step cards) is Task 2; until it is
registered the Resources list shows these rows with ``plugin_available: false``
and no Run button, which is how it already treats an unknown type.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from typing import Any, Dict, Optional

PLUGIN_TYPE = 'scan_db'


def snapshot_path(scan_db_dir: str, host: str, root: str) -> str:
    """Where the latest snapshot for ``(host, root)`` lives. One per root: a new
    scan of the same root replaces the previous one."""
    slug = re.sub(r'[^A-Za-z0-9._-]+', '_', f"{host}_{os.path.basename(root.rstrip('/')) or 'root'}").strip('_')
    digest = hashlib.sha1(f'{host}\0{root}'.encode()).hexdigest()[:10]
    return os.path.join(scan_db_dir, f'snapshot_{slug}_{digest}.db')


def keep_snapshot(scan_db: str, scan_db_dir: str, host: str, root: str) -> str:
    """Move a finished scanner database to its snapshot path; returns that path.

    Checkpointed and switched out of WAL first, so the snapshot is one
    self-contained file (it gets copied, and the FAIR check opens it read-only).
    """
    conn = sqlite3.connect(scan_db)
    try:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.execute('PRAGMA journal_mode=DELETE')
    finally:
        conn.close()
    target = snapshot_path(scan_db_dir, host, root)
    for suffix in ('-wal', '-shm'):
        try:
            os.remove(target + suffix)
        except FileNotFoundError:
            pass
    os.replace(scan_db, target)
    return target


def upsert_scan_resource(settings_db: str, host: str, root: str, snapshot: str,
                         scan_id: str, file_count: int, folder_count: int) -> Dict[str, Any]:
    """Create, or update, the ``scan_db`` Resource for ``(host, root)``."""
    from .store import PipelineStore, utc_now

    store = PipelineStore(settings_db)
    config = {
        'source_path': snapshot,
        'host': host,
        'root': root,
        'scan_id': scan_id,
        'origin': 'files_page',
    }
    summary = {'scan_id': scan_id, 'file_count': int(file_count), 'folder_count': int(folder_count)}
    existing = _find(store, host, root)
    if existing is None:
        existing = store.create_source(f'{host} {root}', PLUGIN_TYPE, source_path=config)
    return store.update_source(existing['id'], source_path=config, last_run_at=utc_now(),
                               last_run_status='scanned', last_run_summary=summary) or existing


def _find(store, host: str, root: str) -> Optional[Dict[str, Any]]:
    for source in store.list_sources():
        cfg = source.get('source_path')
        if (source.get('plugin_type') == PLUGIN_TYPE and isinstance(cfg, dict)
                and cfg.get('host') == host and cfg.get('root') == root):
            return source
    return None
