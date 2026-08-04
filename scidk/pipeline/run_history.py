"""Persistence for ``pipeline_run`` — what every pipeline execution did.

A run is recorded in two steps rather than one. :meth:`RunHistory.start_run`
inserts a row with ``started_at`` set and ``completed_at`` NULL *before* the first
source is touched; :meth:`RunHistory.complete_run` fills in the outcome. That is
deliberate: with no transaction over the Neo4j writes, a run killed halfway
through (a restart, an OOM, a lost connection) has already changed the graph, and
a history that only records completed runs would show no trace of it. An
in-flight row with no ``completed_at`` is the evidence that something started and
never finished.

Same database and same conventions as :mod:`scidk.pipeline.store`:
``scidk_settings.db``, ``_ensure_table_exists()`` rather than
``scidk/core/migrations.py``, timestamps as ISO-8601 UTC strings.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from .store import utc_now

logger = logging.getLogger(__name__)

__all__ = ["RunHistory", "get_run_history"]

#: Statuses a finished run may have. ``'partial'`` is first-class — some steps
#: succeeded and some did not, which is neither of its neighbours.
RUN_STATUSES = ("success", "partial", "error")

#: Reasons a run was started, for the history view.
TRIGGERS = ("manual", "schedule", "api")


class RunHistory:
    """Read and write ``pipeline_run`` rows.

    Args:
        db_path: Path to ``scidk_settings.db``.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "scidk_settings.db"
        self._ensure_table_exists()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table_exists(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_run (
                    id           TEXT PRIMARY KEY,
                    pipeline_id  TEXT NOT NULL,
                    started_at   DATETIME,
                    completed_at DATETIME,
                    status       TEXT,
                    triggered_by TEXT,
                    steps_json   TEXT
                )
                """
            )
            # History is always read per pipeline, newest first.
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pipeline_run_pipeline "
                "ON pipeline_run(pipeline_id, started_at DESC)"
            )
            conn.commit()
            logger.debug("Ensured pipeline_run table exists in %s", self.db_path)
        finally:
            conn.close()

    # -------------------------------------------------------------- write

    def start_run(
        self,
        pipeline_id: str,
        triggered_by: str = "manual",
        run_id: Optional[str] = None,
    ) -> str:
        """Record that a run has begun and return its id.

        Called before the first source runs, so a crashed run leaves a row with
        ``completed_at`` NULL instead of leaving no row at all.
        """
        rid = run_id or str(uuid.uuid4())
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO pipeline_run
                    (id, pipeline_id, started_at, completed_at, status, triggered_by, steps_json)
                VALUES (?, ?, ?, NULL, 'running', ?, ?)
                """,
                (rid, pipeline_id, utc_now(), triggered_by, json.dumps([])),
            )
            conn.commit()
        finally:
            conn.close()
        return rid

    def record_step(self, run_id: str, step: Dict[str, Any]) -> None:
        """Append one step's result to an in-flight run.

        Read-modify-write on the JSON column. Safe here because one run is
        executed by one thread in sequence; do not call it concurrently for the
        same run without adding locking.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT steps_json FROM pipeline_run WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                logger.warning("record_step for unknown run %r; dropped", run_id)
                return
            steps = _decode_steps(row["steps_json"])
            steps.append(step)
            conn.execute(
                "UPDATE pipeline_run SET steps_json = ? WHERE id = ?",
                (json.dumps(steps, default=str), run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_run(
        self,
        run_id: str,
        status: str,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Finalize a run.

        Args:
            run_id: From :meth:`start_run`.
            status: One of :data:`RUN_STATUSES`. An unrecognized value is stored
                as given and logged — refusing to record the outcome of a run
                that already happened would lose more than it protects.
            steps: Per-step results, replacing anything :meth:`record_step`
                accumulated. Omit to keep those.
        """
        if status not in RUN_STATUSES:
            logger.warning("Unrecognized pipeline run status %r for run %s", status, run_id)

        conn = self._connect()
        try:
            if steps is None:
                conn.execute(
                    "UPDATE pipeline_run SET completed_at = ?, status = ? WHERE id = ?",
                    (utc_now(), status, run_id),
                )
            else:
                conn.execute(
                    "UPDATE pipeline_run SET completed_at = ?, status = ?, steps_json = ? "
                    "WHERE id = ?",
                    (utc_now(), status, json.dumps(steps, default=str), run_id),
                )
            conn.commit()
        finally:
            conn.close()
        return self.get_run(run_id)

    # --------------------------------------------------------------- read

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline_run WHERE id = ?", (run_id,)
            ).fetchone()
            return _decode_run(row) if row else None
        finally:
            conn.close()

    def list_runs(
        self, pipeline_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Runs newest first, for one pipeline or across all of them."""
        conn = self._connect()
        try:
            if pipeline_id:
                rows = conn.execute(
                    "SELECT * FROM pipeline_run WHERE pipeline_id = ? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (pipeline_id, max(1, int(limit))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM pipeline_run ORDER BY started_at DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
            return [_decode_run(r) for r in rows]
        finally:
            conn.close()

    def last_run(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        runs = self.list_runs(pipeline_id, limit=1)
        return runs[0] if runs else None

    def latest_run_for_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Most recent run containing a step for ``source_id``.

        Scans recent runs rather than indexing ``steps_json``: a source's own
        ``last_run_*`` columns are the fast path for the card, and this exists for
        the detail view, where a bounded scan is cheap enough.
        """
        for run in self.list_runs(limit=200):
            for step in run.get("steps") or []:
                if step.get("source_id") == source_id:
                    return run
        return None

    def delete_for_pipeline(self, pipeline_id: str) -> int:
        """Delete a pipeline's run history. Returns rows removed."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM pipeline_run WHERE pipeline_id = ?", (pipeline_id,)
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def _decode_steps(raw: Any) -> List[Dict[str, Any]]:
    """Parse ``steps_json``, tolerating a row that predates or corrupts it."""
    if not raw:
        return []
    try:
        steps = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return steps if isinstance(steps, list) else []


def _decode_run(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["steps"] = _decode_steps(data.pop("steps_json", None))
    #: A row with no completed_at is a run that started and never reported back.
    data["in_flight"] = data.get("completed_at") in (None, "")
    return data


_history: Optional[RunHistory] = None


def get_run_history(db_path: Optional[str] = None) -> RunHistory:
    """Process-wide history, rebuilt when an explicit ``db_path`` is given."""
    global _history
    if _history is None or (db_path is not None and db_path != _history.db_path):
        _history = RunHistory(db_path)
    return _history
