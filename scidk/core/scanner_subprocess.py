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

import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# The scanner is a CLI tool at the repo root, not an importable module.
_SCANNER = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'scidk_scanner_opt.py')
)

_POLL_SECONDS = 5.0          # how often the child's progress table is read
_WAIT_SLICE_SECONDS = 0.25   # how quickly the child's exit is noticed
_MERGE_ATTEMPTS = 3
_MERGE_RETRY_SECONDS = 5.0

# The settings DB the scan-database Resource is recorded in. The monitor thread
# has no app context, so launch_scanner notes the path whenever it runs inside
# one (a request); a queued scan started later from a monitor thread reuses it.
# Not on task_dict, because GET /api/tasks/<id> returns that dict whole.
_settings_db_path: Optional[str] = None


def _settings_db() -> str:
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            global _settings_db_path
            _settings_db_path = current_app.config.get('SCIDK_SETTINGS_DB') or _settings_db_path
    except Exception:
        pass
    return _settings_db_path or os.environ.get('SCIDK_SETTINGS_DB') or 'scidk_settings.db'


# How long files_scanned may sit unchanged before the child is presumed hung.
# 30 min tolerates a slow NFS subtree; a deadlocked child never recovers.
STALE_THRESHOLD_SECONDS = 1800

# A scan database is proportional to the root, not to /tmp: a few million rows
# is several GB. Checked before launching rather than discovered as an sqlite
# "disk I/O error" from inside the child half an hour in.
_MIN_FREE_BYTES = 10 * 1024 ** 3


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


def _scan_db_dir() -> str:
    """Directory the child's private scan database is written to.

    Not tempfile.gettempdir(): /tmp is a small partition (tmpfs on some hosts),
    so a scan of a large root filled it and died. ~/.scidk/scans/ is a sibling
    of the ~/.scidk/db/ that holds files.db, which the results are merged into,
    so the scan database and its destination share one filesystem.

    ``SCIDK_SCAN_DB_DIR`` overrides it — a host whose home is on a small disk
    can point scans at the big one without a code change.
    """
    return os.path.expanduser(
        os.environ.get('SCIDK_SCAN_DB_DIR') or '~/.scidk/scans'
    )


def _tmp_db_path(task_id: str) -> str:
    return os.path.join(_scan_db_dir(), f'scidk_scan_{task_id}.db')


def _preflight_scan_dir(directory: str) -> Optional[str]:
    """None if ``directory`` can hold a scan database, else why it cannot.

    Returns the reason rather than raising so the caller can put it straight
    into the task row: a typo in SCIDK_SCAN_DB_DIR or a full disk should fail
    the task with something readable, not with a traceback from the child.
    """
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        return f'Scan database directory {directory} could not be created: {e}'
    if not os.path.isdir(directory):
        return f'Scan database directory {directory} is not a directory'
    if not os.access(directory, os.W_OK | os.X_OK):
        return f'Scan database directory {directory} is not writable'
    try:
        free = shutil.disk_usage(directory).free
    except Exception as e:
        return f'Could not check free space on {directory}: {e}'
    if free < _MIN_FREE_BYTES:
        return (
            f'Not enough free space for a scan database: '
            f'{free / 1024 ** 3:.1f} GB available on {directory}, '
            f'{_MIN_FREE_BYTES / 1024 ** 3:.0f} GB required'
        )
    return None


def _read_tail(path: str, limit: int = 500) -> str:
    try:
        with open(path, 'rb') as fh:
            return fh.read().decode(errors='replace')[-limit:].strip()
    except Exception:
        return ''


def _scanner_scan_id(tmp_db: str) -> Optional[str]:
    """Newest scan id in the child's database, or None if it has not started.

    The size check is not an optimisation. sqlite3.connect() *creates* a missing
    file, so polling a deleted tmp_db used to leave a 0-byte stub behind — after
    which "SELECT id FROM scans" raised forever, this returned None forever, and
    the monitor froze the task row with no error. The child writes to the
    unlinked inode, so that stub can never gain a scans table.
    """
    try:
        if not os.path.exists(tmp_db) or os.path.getsize(tmp_db) == 0:
            return None
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
    _settings_db()  # note it now, while a request's app context may exist
    if files_db_path is None:
        from .path_index_sqlite import _db_path
        files_db_path = str(_db_path())

    tmp_db = _tmp_db_path(task_id)
    log_path = f'{tmp_db}.log'

    problem = _preflight_scan_dir(os.path.dirname(tmp_db))
    if problem:
        task_dict['status'] = 'error'
        task_dict['error'] = problem
        task_dict['status_message'] = f'Failed: {problem}'
        task_dict['ended'] = time.time()
        _persist(task_dict)
        # The queue has already counted this job's workers as spent. Without
        # handing the budget back, a failed pre-flight leaves every later scan
        # queued forever.
        _start_next(task_id, files_db_path, max_total_workers, max_concurrent,
                    live_tasks, scans_registry)
        return

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
    # Consecutive polls that found no readable child database.
    _no_scan_id_misses = 0
    # Liveness: the child's own files_scanned counter must advance. None until
    # the first successful read, so a slow start on a huge tree is not killed
    # before it has walked anything.
    _last_files_scanned = None
    _last_progress_time = time.monotonic()
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
                _no_scan_id_misses += 1
                if _no_scan_id_misses > 60:   # 60 x 5s poll = 5 minutes
                    task_dict['status'] = 'error'
                    task_dict['status_message'] = (
                        'Scanner child DB missing after 5 min \u2014 '
                        'process may have crashed'
                    )
                    _persist(task_dict)
                    # on_job_finished() is deliberately NOT called: with no
                    # child database we can neither merge results nor confirm
                    # the child exited, and handing the worker budget back
                    # while a live process may still be walking would
                    # over-subscribe the queue. The row needs an operator.
                    return
                continue
            _no_scan_id_misses = 0
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

            # A deadlocked child keeps its last scan_progress row forever, so
            # re-persisting it every 5s makes updated_at look fresh while
            # nothing is happening. Advancement, not freshness, is the signal.
            if _last_files_scanned is None or files_seen != _last_files_scanned:
                _last_files_scanned = files_seen
                _last_progress_time = time.monotonic()
            else:
                elapsed = time.monotonic() - _last_progress_time
                if elapsed > STALE_THRESHOLD_SECONDS:
                    logger.warning(
                        "Scanner stale for %.0f s (task %s, pid %s, "
                        "files_scanned stuck at %s) \u2014 sending SIGTERM",
                        elapsed, task_id, proc.pid, files_seen,
                    )
                    proc.send_signal(signal.SIGTERM)
                    # The scanner installs no SIGTERM handler (it only catches
                    # KeyboardInterrupt, i.e. SIGINT), so this kills it
                    # outright: returncode becomes -15 and the returncode != 0
                    # branch below marks the task 'error' and calls
                    # _start_next(). Partial rows are never merged.
                    break
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
    _keep_as_resource(task_dict, tmp_db, scanner_scan_id, merged)
    _persist(task_dict)
    _try_delete(log_path)
    _start_next(task_id, files_db_path, max_total_workers, max_concurrent, live_tasks, scans_registry)


def _keep_as_resource(task_dict: dict, tmp_db: str, scan_id: str, merged: dict) -> None:
    """Keep the scan database as the Resource snapshot and record the Resource.

    Never fails the scan: the import already succeeded, so a problem here is
    reported in the task and the snapshot is dropped as before.
    """
    from ..pipeline.scan_resource import keep_snapshot, upsert_scan_resource
    from .host_id import host_id_for
    host = host_id_for(task_dict.get('provider_id') or 'local_fs', task_dict.get('root_id') or '/')
    root = str(task_dict.get('path') or '')
    try:
        snapshot = keep_snapshot(tmp_db, _scan_db_dir(), host, root)
        task_dict['snapshot_path'] = snapshot
    except Exception as e:
        task_dict['status_message'] += f' (snapshot not kept: {e})'
        _try_delete(tmp_db)
        return
    try:
        resource = upsert_scan_resource(_settings_db(), host, root, snapshot, scan_id,
                                        merged['file_count'], merged['folder_count'])
        task_dict['resource_id'] = resource.get('id')
    except Exception as e:
        task_dict['status_message'] += f' (Resource not recorded: {e})'


def merge_scan_results(tmp_db: str, files_db_path: str, scanner_scan_id: str,
                       task_dict: Optional[dict] = None) -> dict:
    """Import the child's scan into files.db: Pass 2, see pipeline.passes.import_scan."""
    from ..pipeline.passes.import_scan import import_scan
    return import_scan(tmp_db, files_db_path, scanner_scan_id,
                       provider_id=(task_dict or {}).get('provider_id') or 'local_fs',
                       root_id=(task_dict or {}).get('root_id') or '/')


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
        from .host_id import host_id_for
        host_id = host_id_for(provider_id, root_id)
        started = task_dict.get('started') or 0.0
        ended = task_dict.get('ended') or time.time()
        from pathlib import Path as _Path
        from . import scan_owner as _scan_owner
        _scan_owner.record(scanner_scan_id, task_dict.get('started_by'))
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
