"""Pass 2: import one scan from a scanner snapshot database into ``files.db``.

The shared import (option A in ``dev/SCANNER_SWITCH.md``): the Files page's
subprocess scan calls it after the child exits, and a scan-database Resource's
sync will call it on its snapshot. It was ``scanner_subprocess.merge_scan_results``,
which is now a wrapper over this.

Values are normalised on the way in rather than in the scanner, so the scanner
stays a single stdlib-only file that can be copied to a storage host.
"""
from __future__ import annotations

import sqlite3

from ...core.host_id import host_id_for

_BUSY_TIMEOUT_MS = 30000


def import_scan(snapshot_db: str, files_db_path: str, scan_id: str,
                provider_id: str = 'local_fs', root_id: str = '/') -> dict:
    """Pass 2: copy one scan from a scanner snapshot db into files.db.

    ATTACH is safe here: files.db is WAL (path_index_sqlite.py:28) and nothing
    else in the codebase attaches anything.

    Idempotent by delete-then-insert, not by INSERT OR IGNORE: files.db's
    ``files`` table has no PRIMARY KEY and no unique index, so OR IGNORE has no
    conflict target there and a retried merge would duplicate every row. The
    three DELETEs are scoped to this scan id, which is a uuid4 the child just
    minted, so they can only remove rows left by an earlier attempt at this
    same merge. Cross-file atomicity is not guaranteed in WAL mode; being
    re-runnable is what makes a partial failure recoverable.

    Column lists are explicit because ``SELECT *`` does not line up: files.db's
    ``files`` has 19 columns (init_db adds interpreted_at,
    interpreter_version and interpreter_hint) and the child's has 16.
    """
    # files.db may never have been initialised on a fresh deployment:
    # migrations.migrate() creates scans/scan_items/background_tasks but the
    # files table belongs to init_db, beside the DDL that owns it. Idempotent,
    # and a no-op on an index that already exists.
    from ...core.path_index_sqlite import init_db as _init_db
    _init_db()
    host_id = host_id_for(provider_id, root_id)

    conn = sqlite3.connect(files_db_path, timeout=30, isolation_level=None)
    try:
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        # scans / scan_items belong to migrations.py, which a fresh files.db may
        # not have run yet. Without them, the unqualified names below resolved to
        # the attached snapshot's own tables: the import deleted the snapshot's
        # scan rows and never wrote one to files.db. Hence migrate() first, and
        # main. / scan_tmp. on every table.
        from ...core import migrations as _migs
        _migs.migrate(conn)
        conn.execute("ATTACH DATABASE ? AS scan_tmp", (snapshot_db,))
        try:
            counts = conn.execute(
                "SELECT coalesce(sum(type='file'),0), coalesce(sum(type='folder'),0) "
                "FROM scan_tmp.files WHERE scan_id=?",
                (scan_id,),
            ).fetchone()
            file_count = int(counts[0] or 0)
            folder_count = int(counts[1] or 0)

            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM main.files WHERE scan_id=?", (scan_id,))
                conn.execute("DELETE FROM main.scan_items WHERE scan_id=?", (scan_id,))
                conn.execute("DELETE FROM main.scans WHERE id=?", (scan_id,))
                # Normalised on the way in:
                # - the scanner's interpreted_as is a routing hint, not a run, so
                #   it goes to interpreter_hint, and interpreted_as /
                #   interpretation_json stay NULL until an interpreter runs.
                #   Otherwise commit writes an empty :Interpretation per hinted
                #   row and Interpret shows every hint as a failed run.
                # - remote is the host label commit keys File nodes on; the
                #   scanner leaves it NULL.
                conn.execute(
                    """
                    INSERT INTO main.files(
                        path, parent_path, name, depth, type, size,
                        modified_time, file_extension, mime_type,
                        etag, hash, remote, scan_id, extra_json,
                        interpreter_hint)
                    SELECT path, parent_path, name, depth, type, size,
                           modified_time, file_extension, mime_type,
                           etag, hash, coalesce(remote, ?), scan_id, extra_json,
                           interpreted_as
                      FROM scan_tmp.files WHERE scan_id=?
                    """,
                    (host_id, scan_id),
                )
                conn.execute(
                    """
                    INSERT INTO main.scan_items(
                        scan_id, path, type, size, modified_time,
                        file_extension, mime_type, etag, hash, extra_json)
                    SELECT scan_id, path, type, size, modified_time,
                           file_extension, mime_type, etag, hash, extra_json
                      FROM scan_tmp.scan_items WHERE scan_id=?
                    """,
                    (scan_id,),
                )
                # The child writes status='complete'; every reader in this app
                # looks for 'completed' (api_tasks.py:38 filters
                # IN ('completed','committed')), so normalise on the way in.
                # extra_json is topped up with the keys /api/scans reads
                # (api_files.py:1497-1512) — without file_count the History
                # drawer shows a scan with no size.
                conn.execute(
                    """
                    INSERT INTO main.scans(id, root, started, completed, status, extra_json)
                    SELECT id, root, started, completed, 'completed',
                           json_set(coalesce(extra_json,'{}'),
                             '$.file_count', ?,
                             '$.folder_count', ?,
                             '$.recursive', json('true'),
                             '$.duration_sec', coalesce(completed,0) - coalesce(started,0),
                             '$.source', 'scidk_scanner_opt',
                             '$.provider_id', ?,
                             '$.root_id', ?)
                      FROM scan_tmp.scans WHERE id=?
                    """,
                    (file_count, folder_count, provider_id, root_id, scan_id),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        finally:
            try:
                conn.execute("DETACH DATABASE scan_tmp")
            except Exception:
                pass
    finally:
        conn.close()
    return {'file_count': file_count, 'folder_count': folder_count,
            'scan_id': scan_id}


