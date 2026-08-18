"""Worker-budget queue for scan tasks.

A scan launched through :mod:`scidk.core.scanner_subprocess` asks for N I/O
workers. Two scans of 32 workers each on the same CIFS mount do not go twice as
fast — they contend. So admission is governed by two caps: a total worker budget
across all running scans, and a hard limit on how many scans run at once.

Everything is stored in ``background_tasks``. That table has exactly six columns
(id, type, status, created, updated, payload) and gains no more, so ``workers``
and ``queue_position`` live inside the payload JSON and are read back with
``json_extract``.

Every function here takes an already-open connection to files.db and never
opens one of its own — the caller owns the connection's lifetime. Note that
``path_index_sqlite.connect()`` sets no ``row_factory``, so every row read here
is a plain tuple and is indexed positionally.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional

# Same value the merge path uses. files.db is a single writer with a multi-GB
# WAL and a stray long transaction elsewhere in the process can hold the lock
# for a while; without this, the queue's BEGIN IMMEDIATE fails instantly.
_BUSY_TIMEOUT_MS = 30000


def _prepare(conn: sqlite3.Connection) -> None:
    """Set the busy timeout on a caller-owned connection. Best-effort."""
    try:
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    except Exception:
        pass


class ScanQueue:
    """Admission control for scan tasks. All methods are stateless."""

    @staticmethod
    def used_workers(conn: sqlite3.Connection) -> int:
        """Sum of the worker budget held by currently running scans.

        Scans that predate the queue (or that run on the in-process fallback
        path) have no ``workers`` key and contribute 0 rather than NULL.
        """
        row = conn.execute(
            "SELECT coalesce(SUM(json_extract(payload,'$.workers')),0) "
            "FROM background_tasks WHERE status='running' AND type='scan'"
        ).fetchone()
        return int((row[0] if row else 0) or 0)

    @staticmethod
    def running_count(conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT count(*) FROM background_tasks "
            "WHERE status='running' AND type='scan'"
        ).fetchone()
        return int((row[0] if row else 0) or 0)

    @staticmethod
    def enqueue(conn: sqlite3.Connection, task_id: str,
                requested_workers: int, path: str) -> int:
        """Mark a task queued, record its worker request, assign a position.

        Returns the assigned queue position (1-based). Positions are relative
        to the tasks queued at the time — when the queue drains completely the
        next arrival starts again at 1.
        """
        _prepare(conn)
        # coalesce, because json_set() on a NULL payload returns NULL and would
        # blank the row rather than add to it.
        conn.execute(
            """
            UPDATE background_tasks
               SET status='queued',
                   payload=json_set(coalesce(payload,'{}'),
                     '$.workers', ?,
                     '$.path', ?,
                     '$.queue_position',
                       (SELECT coalesce(max(json_extract(payload,'$.queue_position')),0)+1
                          FROM background_tasks WHERE status='queued'))
             WHERE id=?
            """,
            (int(requested_workers), str(path), task_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT json_extract(payload,'$.queue_position') "
            "FROM background_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        return int((row[0] if row else 1) or 1)

    @staticmethod
    def try_start_next(conn: sqlite3.Connection, max_total_workers: int,
                       max_concurrent: int,
                       live_tasks: Optional[Dict[str, dict]] = None) -> Optional[str]:
        """Promote the head of the queue to 'running' if the caps allow it.

        BEGIN IMMEDIATE takes the write lock before reading the counts, so two
        gunicorn workers cannot both admit a task against the same budget.

        ``live_tasks`` is the in-memory task registry. When given, the promoted
        task's dict is flipped to 'running' too — the in-memory dict is what
        ``GET /api/tasks/<id>``, the cancel endpoint and the MAX_BG_TASKS
        admission guard all read, so leaving it at 'queued' would make a
        running scan invisible to every one of them.

        Returns the promoted task id, or None if nothing is startable.
        """
        _prepare(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            return None
        try:
            row = conn.execute(
                """
                SELECT id, coalesce(json_extract(payload,'$.workers'), 1)
                  FROM background_tasks
                 WHERE status='queued' AND type='scan'
                 ORDER BY coalesce(json_extract(payload,'$.queue_position'), created),
                          created
                 LIMIT 1
                """
            ).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                return None
            task_id, workers = row[0], int(row[1] or 1)
            if (ScanQueue.used_workers(conn) + workers > int(max_total_workers)
                    or ScanQueue.running_count(conn) >= int(max_concurrent)):
                conn.execute("ROLLBACK")
                return None
            conn.execute(
                "UPDATE background_tasks "
                "SET status='running', "
                "    payload=json_remove(coalesce(payload,'{}'),'$.queue_position') "
                "WHERE id=?",
                (task_id,),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            return None
        if live_tasks is not None:
            live = live_tasks.get(task_id)
            if live is not None:
                live['status'] = 'running'
                live.pop('queue_position', None)
        return task_id

    @staticmethod
    def on_job_finished(conn: sqlite3.Connection, task_id: str,
                        max_total_workers: int, max_concurrent: int,
                        live_tasks: Optional[Dict[str, dict]] = None,
                        files_db_path: Optional[str] = None,
                        scans_registry: Optional[Dict[str, dict]] = None) -> Optional[str]:
        """Called when a scan ends (any outcome). Starts the next queued scan.

        ``task_id`` is the job that just finished; it is not read, but it keeps
        the call site self-documenting and gives a hook for future accounting.

        The task dict handed to the launcher comes from ``live_tasks`` when the
        registry is available and is otherwise rebuilt from the persisted
        payload — the monitor thread that calls this has no Flask app context,
        so it cannot reach ``app.extensions`` itself.
        """
        started_id = ScanQueue.try_start_next(
            conn, max_total_workers, max_concurrent, live_tasks=live_tasks)
        if not started_id:
            return None
        task_dict = None
        if live_tasks is not None:
            task_dict = live_tasks.get(started_id)
        if task_dict is None:
            task_dict = ScanQueue.task_dict_from_db(conn, started_id)
        if task_dict is None:
            return None
        from .scanner_subprocess import launch_scanner
        launch_scanner(
            started_id, task_dict,
            files_db_path=files_db_path,
            max_total_workers=max_total_workers,
            max_concurrent=max_concurrent,
            live_tasks=live_tasks,
            scans_registry=scans_registry,
        )
        return started_id

    @staticmethod
    def task_dict_from_db(conn: sqlite3.Connection, task_id: str) -> Optional[dict]:
        """Rebuild the minimum task dict a launch needs from its stored row."""
        import json as _json
        row = conn.execute(
            "SELECT id, type, status, created, updated, payload "
            "FROM background_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = _json.loads(row[5] or '{}')
        except Exception:
            payload = {}
        task = {
            'id': row[0],
            'type': row[1],
            'status': row[2],
            'started': row[3],
            'ended': None,
        }
        task.update(payload)
        return task

    @staticmethod
    def current_state(conn: sqlite3.Connection, max_total_workers: int,
                      max_concurrent: int) -> dict:
        """Queue snapshot for the UI: what is running, what is waiting, caps."""
        running = []
        for row in conn.execute(
            """
            SELECT id,
                   json_extract(payload,'$.path'),
                   coalesce(json_extract(payload,'$.workers'), 0),
                   json_extract(payload,'$.status_message'),
                   coalesce(json_extract(payload,'$.progress'), 0.0)
              FROM background_tasks
             WHERE status='running' AND type='scan'
             ORDER BY created
            """
        ).fetchall() or []:
            running.append({
                'id': row[0],
                'path': row[1],
                'workers': int(row[2] or 0),
                'status_message': row[3],
                'progress': float(row[4] or 0.0),
            })
        queued = []
        for row in conn.execute(
            """
            SELECT id,
                   json_extract(payload,'$.path'),
                   coalesce(json_extract(payload,'$.workers'), 0),
                   json_extract(payload,'$.queue_position')
              FROM background_tasks
             WHERE status='queued' AND type='scan'
             ORDER BY coalesce(json_extract(payload,'$.queue_position'), created),
                      created
            """
        ).fetchall() or []:
            queued.append({
                'id': row[0],
                'path': row[1],
                'workers': int(row[2] or 0),
                'queue_position': row[3],
            })
        used = ScanQueue.used_workers(conn)
        return {
            'running': running,
            'queued': queued,
            'caps': {
                'max_total_workers': int(max_total_workers),
                'max_concurrent': int(max_concurrent),
                'used_workers': used,
                'available_workers': max(0, int(max_total_workers) - used),
                'running_count': len(running),
                'queued_count': len(queued),
            },
        }
