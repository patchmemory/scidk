"""Run a scan as a child process instead of a daemon thread.

``api_tasks.py`` has always scanned inside ``threading.Thread(daemon=True)`` and
kept no handle to it (api_tasks.py:611). A thread like that cannot be cancelled,
cannot be observed once it stops updating, and dies silently with the
interpreter — which is how files.db ended up with rows stuck in 'running' since
August 13th. A child process fixes all three: it has a PID that can be signalled,
its exit code says what happened, and ``create_app()`` can tell on the next boot
that its writer is gone.

The child is ``tools/scidk_scanner_opt.py``, which writes a complete, private
scan database (scans + files + scan_items + scan_progress). It is polled for
progress while it runs and its results are merged into files.db when it finishes
cleanly. Nothing here touches files.db until the merge, so a scan that dies
half-way leaves the real index untouched.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from typing import Dict, Optional

# The scanner is a CLI tool at the repo root, not an importable module.
_SCANNER = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'scidk_scanner_opt.py')
)

_POLL_SECONDS = 5.0          # how often the child's progress table is read
_WAIT_SLICE_SECONDS = 0.25   # how quickly the child's exit is noticed
_MERGE_ATTEMPTS = 3
_MERGE_RETRY_SECONDS = 5.0
_BUSY_TIMEOUT_MS = 30000


def _persist(task: dict) -> None:
    """Write task state through api_tasks._persist_task.

    Imported at call time, not module scope: api_tasks imports this module from
    inside its request handlers, so a module-level import here would be a cycle.
    Reusing that function rather than writing our own INSERT keeps one owner of
    the payload shape — the queue fields only survive because _persist_task
    rewrites the whole payload column from the task dict.
    """
    try:
        from ..web.routes.api_tasks import _persist_task
        _persist_task(task)
    except Exception:
        pass


def _try_delete(path: str) -> None:
    for p in (path, f"{path}-wal", f"{path}-shm"):
        try:
            os.unlink(p)
        except Exception:
            pass


def _tmp_db_path(task_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f'scidk_scan_{task_id}.db')


def _read_tail(path: str, limit: int = 500) -> str:
    try:
        with open(path, 'rb') as fh:
            return fh.read().decode(errors='replace')[-limit:].strip()
    except Exception:
        return ''


def _scanner_scan_id(tmp_db: str) -> Optional[str]:
    """Newest scan id in the child's database, or None if it has not started."""
    try:
        conn = sqlite3.connect(tmp_db, timeout=5)
        try:
            row = conn.execute(
                "SELECT id FROM scans ORDER BY started DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None  # tmp_db may not exist yet at the first poll


def launch_scanner(task_id: str, task_dict: dict,
                   files_db_path: Optional[str] = None,
                   max_total_workers: int = 32,
                   max_concurrent: int = 4,
                   live_tasks: Optional[Dict[str, dict]] = None,
                   scans_registry: Optional[Dict[str, dict]] = None) -> None:
    """Start a scan subprocess and a monitor thread for it. Returns at once.

    ``task_dict`` is the live in-memory task dict when one exists, so the
    monitor's updates are visible to ``GET /api/tasks/<id>`` as well as to
    background_tasks.

    ``scans_registry`` is ``app.extensions['scidk']['scans']``. A completed scan
    is registered there because POST /api/tasks type=commit resolves a scan id
    through that registry and 404s otherwise. It is passed in rather than looked
    up because the monitor thread has no Flask app context.
    """
    if files_db_path is None:
        from .path_index_sqlite import _db_path
        files_db_path = str(_db_path())

    tmp_db = _tmp_db_path(task_id)
    log_path = f'{tmp_db}.log'
    # A previous attempt's leftovers would be merged as if they were ours.
    _try_delete(tmp_db)

    workers = int(task_dict.get('workers') or 8)
    cmd = [
        sys.executable, _SCANNER,
        str(task_dict.get('path') or ''),
        '--db', tmp_db,
        '--workers', str(workers),
        '--no-hash',
        '--magic-limit', '0',
        '--quiet',
    ]
    # TODO: expose --no-hash and --magic-limit as per-job payload options.
    # Note: --workers is capped internally to len(top_dirs) by the scanner
    # (scidk_scanner_opt.py:690). A root with fewer top-level dirs than
    # requested workers uses fewer.

    try:
        log_fh = open(log_path, 'wb')
    except Exception:
        log_fh = None
    try:
        # stderr goes to a file rather than subprocess.PIPE: nothing reads the
        # pipe until wait() returns, so a child that writes more than the 64KB
        # pipe buffer would block forever on its own error output.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=(log_fh or subprocess.DEVNULL),
        )
    except Exception as e:
        if log_fh is not None:
            log_fh.close()
        task_dict['status'] = 'error'
        task_dict['error'] = f'Could not start scanner: {e}'
        task_dict['status_message'] = f'Failed: {e}'
        task_dict['ended'] = time.time()
        _persist(task_dict)
        _try_delete(tmp_db)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return
    if log_fh is not None:
        log_fh.close()  # the child holds its own dup of the descriptor

    task_dict['status'] = 'running'
    task_dict['worker_pid'] = proc.pid
    task_dict['status_message'] = f'Scanning with {workers} workers...'
    task_dict.pop('queue_position', None)
    _persist(task_dict)

    threading.Thread(
        target=_monitor,
        args=(proc, task_id, task_dict, tmp_db, log_path, files_db_path,
              max_total_workers, max_concurrent, live_tasks, scans_registry),
        daemon=True,
        name=f'scan-monitor-{task_id}',
    ).start()


def _monitor(proc: subprocess.Popen, task_id: str, task_dict: dict, tmp_db: str,
             log_path: str, files_db_path: str, max_total_workers: int,
             max_concurrent: int, live_tasks: Optional[Dict[str, dict]],
             scans_registry: Optional[Dict[str, dict]] = None) -> None:
    """Poll the child for progress, then settle the task on its exit.

    Daemon thread — it dies with the process. Unlike the scan thread it
    replaces, the work it watches does not: the subprocess survives, and its
    PID is recorded in the payload, so the next start can see it is gone (or
    the cancel endpoint can signal it).
    """
    scanner_scan_id = None
    last_poll = 0.0
    while True:
        # Wait on the child in short slices rather than sleeping the poll
        # interval: a small scan can finish in well under a second, and sleeping
        # 5s before noticing would delay the merge — and so the scan's
        # appearance in /api/scans — by that long for no reason.
        try:
            proc.wait(timeout=_WAIT_SLICE_SECONDS)
            break
        except subprocess.TimeoutExpired:
            pass
        now = time.time()
        if now - last_poll < _POLL_SECONDS:
            continue
        last_poll = now
        try:
            if scanner_scan_id is None:
                scanner_scan_id = _scanner_scan_id(tmp_db)
            if not scanner_scan_id:
                continue
            conn_tmp = sqlite3.connect(tmp_db, timeout=5)
            try:
                rows = conn_tmp.execute(
                    "SELECT metric, value FROM scan_progress WHERE scan_id=?",
                    (scanner_scan_id,),
                ).fetchall()
            finally:
                conn_tmp.close()
            metrics = {r[0]: r[1] for r in rows}
            files_seen = int(metrics.get('files_scanned', 0) or 0)
            task_dict['status_message'] = (
                f"Scanning... {files_seen:,} files "
                f"/ {int(metrics.get('dirs_scanned', 0) or 0):,} dirs"
            )
            # processed is set so a task seeded with an estimated total does not
            # sit at 0 for hours; progress stays 0.0 until the merge, because
            # until then no total is actually known.
            task_dict['processed'] = files_seen
            _persist(task_dict)
        except Exception:
            pass  # a poll failure must never end the scan

    returncode = proc.wait()
    task_dict['ended'] = time.time()
    if scanner_scan_id is None:
        scanner_scan_id = _scanner_scan_id(tmp_db)

    # Cancel is checked first: a cancelled scan was killed on purpose and
    # should not be reported as a failure.
    if task_dict.get('cancel_requested'):
        task_dict['status'] = 'canceled'
        task_dict['status_message'] = 'Cancelled'
        _persist(task_dict)
        _try_delete(tmp_db)
        _try_delete(log_path)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return

    if returncode != 0:
        err = _read_tail(log_path) or f'scanner exited with code {returncode}'
        task_dict['status'] = 'error'
        task_dict['error'] = err
        task_dict['status_message'] = f'Failed: {err[:200]}'
        _persist(task_dict)
        _try_delete(tmp_db)
        _try_delete(log_path)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return

    scan_status = None
    if scanner_scan_id:
        try:
            conn_tmp = sqlite3.connect(tmp_db, timeout=5)
            try:
                row = conn_tmp.execute(
                    "SELECT status FROM scans WHERE id=?", (scanner_scan_id,)
                ).fetchone()
                scan_status = row[0] if row else None
            finally:
                conn_tmp.close()
        except Exception:
            scan_status = None

    if scan_status == 'interrupted':
        # The scanner caught SIGINT and saved partial results; they are not
        # merged, because a partial tree indexed as a complete scan is worse
        # than no scan.
        task_dict['status'] = 'error'
        task_dict['error'] = 'Scan interrupted by signal'
        task_dict['status_message'] = 'Scan interrupted by signal'
        _persist(task_dict)
        _try_delete(tmp_db)
        _try_delete(log_path)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return

    if scan_status != 'complete' or not scanner_scan_id:
        task_dict['status'] = 'error'
        task_dict['error'] = f'Scanner finished with scan status {scan_status!r}'
        task_dict['status_message'] = f'Failed: unexpected scan status {scan_status!r}'
        _persist(task_dict)
        _try_delete(tmp_db)
        _try_delete(log_path)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return

    task_dict['status_message'] = 'Merging results into the index...'
    _persist(task_dict)
    merged = None
    last_error = None
    for attempt in range(_MERGE_ATTEMPTS):
        try:
            merged = merge_scan_results(tmp_db, files_db_path, scanner_scan_id, task_dict)
            break
        except Exception as e:
            last_error = e
            if attempt + 1 < _MERGE_ATTEMPTS:
                time.sleep(_MERGE_RETRY_SECONDS)

    if merged is None:
        # The scan itself succeeded — only the merge failed, usually because
        # another writer holds files.db. Keep the child's database so the merge
        # can be retried by hand instead of throwing away hours of walking.
        task_dict['status'] = 'error'
        task_dict['error'] = (
            f'Scan completed but merge into the index failed: {last_error}. '
            f'Results kept at {tmp_db} (scan_id {scanner_scan_id}).'
        )
        task_dict['status_message'] = f'Merge failed: {last_error}'
        _persist(task_dict)
        _try_delete(log_path)
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)
        return

    _register_scan(scans_registry, task_dict, scanner_scan_id, merged)

    task_dict['status'] = 'completed'
    task_dict['scan_id'] = scanner_scan_id
    task_dict['total'] = merged['file_count']
    task_dict['total_is_estimate'] = False
    task_dict['processed'] = merged['file_count']
    task_dict['progress'] = 1.0
    task_dict['status_message'] = (
        f"Completed: {merged['file_count']:,} files, "
        f"{merged['folder_count']:,} folders"
    )
    _persist(task_dict)
    _try_delete(tmp_db)
    _try_delete(log_path)
    _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)


def merge_scan_results(tmp_db: str, files_db_path: str, scanner_scan_id: str,
                       task_dict: Optional[dict] = None) -> dict:
    """Copy one scan from the child's database into files.db.

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
    ``files`` has 18 columns (init_db adds interpreted_at and
    interpreter_version) and the child's has 16.
    """
    # files.db may never have been initialised on a fresh deployment:
    # migrations.migrate() creates scans/scan_items/background_tasks but the
    # files table belongs to init_db, beside the DDL that owns it. Idempotent,
    # and a no-op on an index that already exists.
    from .path_index_sqlite import init_db as _init_db
    _init_db()

    conn = sqlite3.connect(files_db_path, timeout=30, isolation_level=None)
    try:
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        conn.execute("ATTACH DATABASE ? AS scan_tmp", (tmp_db,))
        try:
            counts = conn.execute(
                "SELECT coalesce(sum(type='file'),0), coalesce(sum(type='folder'),0) "
                "FROM scan_tmp.files WHERE scan_id=?",
                (scanner_scan_id,),
            ).fetchone()
            file_count = int(counts[0] or 0)
            folder_count = int(counts[1] or 0)

            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM files WHERE scan_id=?", (scanner_scan_id,))
                conn.execute("DELETE FROM scan_items WHERE scan_id=?", (scanner_scan_id,))
                conn.execute("DELETE FROM scans WHERE id=?", (scanner_scan_id,))
                conn.execute(
                    """
                    INSERT INTO files(
                        path, parent_path, name, depth, type, size,
                        modified_time, file_extension, mime_type,
                        etag, hash, remote, scan_id, extra_json,
                        interpreted_as, interpretation_json)
                    SELECT path, parent_path, name, depth, type, size,
                           modified_time, file_extension, mime_type,
                           etag, hash, remote, scan_id, extra_json,
                           interpreted_as, interpretation_json
                      FROM scan_tmp.files WHERE scan_id=?
                    """,
                    (scanner_scan_id,),
                )
                conn.execute(
                    """
                    INSERT INTO scan_items(
                        scan_id, path, type, size, modified_time,
                        file_extension, mime_type, etag, hash, extra_json)
                    SELECT scan_id, path, type, size, modified_time,
                           file_extension, mime_type, etag, hash, extra_json
                      FROM scan_tmp.scan_items WHERE scan_id=?
                    """,
                    (scanner_scan_id,),
                )
                # The child writes status='complete'; every reader in this app
                # looks for 'completed' (api_tasks.py:38 filters
                # IN ('completed','committed')), so normalise on the way in.
                # extra_json is topped up with the keys /api/scans reads
                # (api_files.py:1497-1512) — without file_count the History
                # drawer shows a scan with no size.
                conn.execute(
                    """
                    INSERT INTO scans(id, root, started, completed, status, extra_json)
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
                    (
                        file_count, folder_count,
                        (task_dict or {}).get('provider_id') or 'local_fs',
                        (task_dict or {}).get('root_id') or '/',
                        scanner_scan_id,
                    ),
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
            'scan_id': scanner_scan_id}


def _register_scan(scans_registry: Optional[Dict[str, dict]], task_dict: dict,
                   scanner_scan_id: str, merged: dict) -> None:
    """Put a merged scan into the in-memory scans registry.

    POST /api/tasks type=commit resolves its scan_id there (api_tasks.py:616)
    and 404s on a miss, so without this a scan run out of process could never be
    committed to the graph. The shape mirrors what _worker() builds, with two
    deliberate absences: 'checksums' is empty because there are no in-memory
    Dataset objects for a scan this process never walked, and 'folders' is empty
    for the same reason. The commit path treats an empty 'checksums' as "build
    the rows from the index instead", which reads the merged rows straight out
    of files.db.
    """
    if scans_registry is None:
        return
    try:
        provider_id = task_dict.get('provider_id') or 'local_fs'
        root_id = task_dict.get('root_id') or '/'
        host_id = None
        try:
            if provider_id == 'local_fs':
                import socket as _sock
                host_id = f"local:{_sock.gethostname()}"
            elif provider_id == 'mounted_fs':
                host_id = f"mounted:{root_id}"
        except Exception:
            host_id = f"{provider_id}:{root_id}"
        started = task_dict.get('started') or 0.0
        ended = task_dict.get('ended') or time.time()
        from pathlib import Path as _Path
        scans_registry[scanner_scan_id] = {
            'id': scanner_scan_id,
            'path': task_dict.get('path'),
            'recursive': True,
            'started': started,
            'ended': ended,
            'duration_sec': (ended - started) if started else None,
            'file_count': int(merged.get('file_count') or 0),
            'folder_count': int(merged.get('folder_count') or 0),
            'checksums': [],
            'folders': [],
            'by_ext': {},
            'source': 'scidk_scanner_opt',
            'errors': [],
            'committed': False,
            'committed_at': None,
            'provider_id': provider_id,
            'host_type': provider_id,
            'host_id': host_id,
            'root_id': root_id,
            'root_label': _Path(root_id).name if root_id else None,
            'scan_source': f'provider:{provider_id}',
            'ingested_rows': int(merged.get('file_count') or 0)
                             + int(merged.get('folder_count') or 0),
            'rows_from_index': True,
        }
    except Exception:
        pass  # a registry miss must not fail an otherwise good scan


def _start_next(task_id: str, files_db_path: str, max_total_workers: int,
                max_concurrent: int, live_tasks: Optional[Dict[str, dict]],
                scans_registry: Optional[Dict[str, dict]] = None) -> None:
    """Hand the freed worker budget back to the queue."""
    try:
        from .path_index_sqlite import connect as _connect
        from .scan_queue import ScanQueue
        conn = _connect()
        try:
            ScanQueue.on_job_finished(
                conn, task_id, max_total_workers, max_concurrent,
                live_tasks=live_tasks, files_db_path=files_db_path,
                scans_registry=scans_registry,
            )
        finally:
            conn.close()
    except Exception:
        pass
