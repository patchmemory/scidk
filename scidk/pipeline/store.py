"""SQLite persistence for ``pipeline_source`` and ``pipeline``.

Both tables live in ``scidk_settings.db`` — the settings database, not the
~15GB path-index ``files.db`` that ``scidk/core/migrations.py`` targets. Schema
changes go through :meth:`PipelineStore._ensure_tables_exist` guarded by
``PRAGMA table_info``, the same pattern ``SavedMapsService`` and ``CanvasService``
use. ``migrations.py`` is the wrong tool here and would point at the wrong file.

Timestamps are ISO-8601 UTC strings (``2026-08-03T14:32:05Z``), matching the
``DATETIME`` columns the data model in ``dev/cycles.md`` specifies. Note this
differs from ``saved_maps`` and ``canvas_session``, which store REAL epoch
seconds — the two conventions coexist in one database because these tables are
specified as DATETIME and their values are read by humans in the run history.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["PipelineStore", "utc_now"]

#: Columns holding JSON. Decoded on read, encoded on write, so callers deal in
#: dicts and never in strings that happen to look like JSON.
_SOURCE_JSON_COLUMNS = ("source_path", "schema_json", "mapping_json", "last_run_summary", "fair_status")
_PIPELINE_JSON_COLUMNS = ("dag_json",)

#: Writable through :meth:`PipelineStore.update_source`. A whitelist and not a
#: filter on the incoming dict: column names cannot be parameterized in SQL, so
#: anything reaching the query string has to come from this tuple and not from a
#: request body.
_SOURCE_UPDATABLE = (
    "name", "plugin_type", "source_path", "schema_json", "schema_saved_at",
    "mapping_json", "mapping_saved_at", "last_run_at", "last_run_status",
    "last_run_summary", "fair_status", "fair_checked_at",
)

_PIPELINE_UPDATABLE = (
    "name", "description", "dag_json", "schedule", "schedule_paused",
    "last_run_at", "last_run_status",
)


def utc_now() -> str:
    """Current time as an ISO-8601 UTC string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PipelineStore:
    """CRUD for pipeline sources and pipelines.

    Args:
        db_path: Path to ``scidk_settings.db``. Defaults to the cwd-relative name,
            matching the other settings-DB services.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "scidk_settings.db"
        self._ensure_tables_exist()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables_exist(self) -> None:
        """Create both tables and add any missing columns. Idempotent."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_source (
                    id               TEXT PRIMARY KEY,
                    name             TEXT NOT NULL,
                    plugin_type      TEXT NOT NULL,
                    source_path      TEXT,
                    schema_json      TEXT,
                    schema_saved_at  DATETIME,
                    mapping_json     TEXT,
                    mapping_saved_at DATETIME,
                    last_run_at      DATETIME,
                    last_run_status  TEXT,
                    last_run_summary TEXT,
                    fair_status      TEXT,
                    fair_checked_at  DATETIME,
                    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    description     TEXT,
                    dag_json        TEXT NOT NULL,
                    schedule        TEXT,
                    schedule_paused INTEGER DEFAULT 0,
                    last_run_at     DATETIME,
                    last_run_status TEXT,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pipeline_source_updated "
                "ON pipeline_source(updated_at DESC)"
            )
            # Columns added after a deployment already has these tables go here,
            # guarded by PRAGMA table_info.
            self._add_missing_columns(conn, "pipeline_source", {
                # When the schema canvas last committed (Task C). Distinct from
                # updated_at, which any edit moves: the canvas compares its
                # working session against this to decide whether the session
                # holds unsaved work, and a rename must not look like a save.
                "schema_saved_at": "DATETIME",
                # When the column mapping was last committed (Task D). Same
                # reasoning: the mapping page shows when it last saved, and
                # updated_at moves for a rename.
                "mapping_saved_at": "DATETIME",
            })
            self._add_missing_columns(conn, "pipeline", {})
            conn.commit()
            logger.debug("Ensured pipeline_source and pipeline tables exist in %s", self.db_path)
        finally:
            conn.close()

    @staticmethod
    def _add_missing_columns(
        conn: sqlite3.Connection, table: str, columns: Dict[str, str]
    ) -> None:
        if not columns:
            return
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, sql_type in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    # ------------------------------------------------------ serialization

    @staticmethod
    def _decode(row: sqlite3.Row, json_columns: tuple) -> Dict[str, Any]:
        """Row → dict, decoding the JSON columns.

        A JSON column holding something unparseable is surfaced under
        ``<column>_raw`` rather than dropped or crashed on: a hand-edited row is
        a thing that happens, and losing the value silently would be worse than
        showing it.
        """
        data = dict(row)
        for column in json_columns:
            raw = data.get(column)
            if raw in (None, ""):
                data[column] = None
                continue
            try:
                data[column] = json.loads(raw)
            except (TypeError, ValueError):
                data[column] = None
                data[f"{column}_raw"] = raw
        return data

    @staticmethod
    def _encode(value: Any) -> Optional[str]:
        """Value → JSON text for storage. Strings already holding JSON pass through."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

    # ------------------------------------------------------------ sources

    def list_sources(self) -> List[Dict[str, Any]]:
        """Every configured source, newest activity first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM pipeline_source ORDER BY updated_at DESC, name ASC"
            ).fetchall()
            return [self._decode(r, _SOURCE_JSON_COLUMNS) for r in rows]
        finally:
            conn.close()

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline_source WHERE id = ?", (source_id,)
            ).fetchone()
            return self._decode(row, _SOURCE_JSON_COLUMNS) if row else None
        finally:
            conn.close()

    def create_source(
        self,
        name: str,
        plugin_type: str,
        source_path: Optional[Any] = None,
        schema_json: Optional[Any] = None,
        mapping_json: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Insert a source and return it as stored.

        Args:
            name: Display name.
            plugin_type: Resolvable by :mod:`scidk.pipeline.plugin_registry`.
            source_path: Plugin-specific connection config. A dict is stored as
                JSON; despite the column name it is a config object, not just a
                path (see the data model in ``dev/cycles.md``).
        """
        source_id = str(uuid.uuid4())
        now = utc_now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO pipeline_source
                    (id, name, plugin_type, source_path, schema_json, mapping_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id, name, plugin_type,
                    self._encode(source_path), self._encode(schema_json),
                    self._encode(mapping_json), now, now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_source(source_id) or {}

    def update_source(self, source_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        """Update the named columns. Unknown names are rejected, not ignored.

        Raises:
            ValueError: A field is not in :data:`_SOURCE_UPDATABLE`. Loud, because
                a silently dropped update looks to the user like a save that
                worked.
        """
        return self._update("pipeline_source", _SOURCE_UPDATABLE, _SOURCE_JSON_COLUMNS,
                            source_id, fields, self.get_source)

    def delete_source(self, source_id: str) -> bool:
        """Delete a source. Returns False when it did not exist.

        Does *not* clean up the source's ``canvas_session`` rows or remove it from
        pipelines — see ``api_pipeline.delete_source`` for the full teardown,
        which needs services this module deliberately does not import.
        """
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM pipeline_source WHERE id = ?", (source_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def record_source_run(
        self,
        source_id: str,
        status: str,
        summary: Optional[Dict[str, Any]] = None,
        ran_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Stamp the outcome of a real ingest run onto the source."""
        return self.update_source(
            source_id,
            last_run_at=ran_at or utc_now(),
            last_run_status=status,
            last_run_summary=summary,
        )

    def save_schema(self, source_id: str, schema: Optional[Any]) -> Optional[Dict[str, Any]]:
        """Commit the source's schema target (Task C).

        Stamps ``schema_saved_at`` alongside it. The schema canvas needs to know
        whether its working session is newer than the last save, and ``updated_at``
        cannot answer that — a rename moves it too.

        Args:
            schema: A validated Arrows document (see
                :func:`scidk.pipeline.schema_arrows.parse_arrows`), or None to
                clear the schema.
        """
        return self.update_source(
            source_id, schema_json=schema, schema_saved_at=utc_now() if schema else None
        )

    def save_mapping(self, source_id: str, mapping: Optional[Any]) -> Optional[Dict[str, Any]]:
        """Commit the source's column mapping (Task D).

        Deliberately stores whatever it is given, valid or not. The mapping page
        saves at any point — a half-finished mapping is worth keeping so the user
        can come back to it — and the engine validates on *load*, so an incomplete
        config in this column cannot cause a run to write something wrong. What it
        does cause is a failed FAIR check, which is where the user is told.

        Args:
            mapping: A mapping config (``mapping_schema.json`` format), or None to
                clear it.
        """
        return self.update_source(
            source_id, mapping_json=mapping, mapping_saved_at=utc_now() if mapping else None
        )

    def record_fair_check(
        self, source_id: str, fair_status: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Store a FAIR check result.

        Kept apart from ``last_run_*`` on purpose: a FAIR check writes nothing to
        Neo4j, so letting it overwrite the last *ingest* status would make the
        card claim a run happened that did not.
        """
        return self.update_source(
            source_id, fair_status=fair_status, fair_checked_at=utc_now()
        )

    # ---------------------------------------------------------- pipelines

    def list_pipelines(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM pipeline ORDER BY updated_at DESC, name ASC"
            ).fetchall()
            return [self._decode(r, _PIPELINE_JSON_COLUMNS) for r in rows]
        finally:
            conn.close()

    def get_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline WHERE id = ?", (pipeline_id,)
            ).fetchone()
            return self._decode(row, _PIPELINE_JSON_COLUMNS) if row else None
        finally:
            conn.close()

    def create_pipeline(
        self,
        name: str,
        dag: Optional[Any] = None,
        description: Optional[str] = None,
        schedule: Optional[str] = None,
        schedule_paused: bool = False,
        pipeline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a pipeline.

        Args:
            dag: ``{"steps": [{"source_id": ..., "depends_on": [...]}]}``. See
                :mod:`scidk.pipeline.orchestrator` for what the runner does with
                it. ``dag_json`` is NOT NULL, so an omitted DAG becomes an empty
                step list rather than failing the insert.
            pipeline_id: Supply to make creation idempotent, as the implicit
                single-source pipeline does.
        """
        pid = pipeline_id or str(uuid.uuid4())
        now = utc_now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO pipeline
                    (id, name, description, dag_json, schedule, schedule_paused,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid, name, description,
                    self._encode(dag if dag is not None else {"steps": []}),
                    schedule, 1 if schedule_paused else 0, now, now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_pipeline(pid) or {}

    def update_pipeline(self, pipeline_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        if "schedule_paused" in fields:
            fields["schedule_paused"] = 1 if fields["schedule_paused"] else 0
        if "dag" in fields:
            fields["dag_json"] = fields.pop("dag")
        return self._update("pipeline", _PIPELINE_UPDATABLE, _PIPELINE_JSON_COLUMNS,
                            pipeline_id, fields, self.get_pipeline)

    def delete_pipeline(self, pipeline_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM pipeline WHERE id = ?", (pipeline_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def record_pipeline_run(
        self, pipeline_id: str, status: str, ran_at: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return self.update_pipeline(
            pipeline_id, last_run_at=ran_at or utc_now(), last_run_status=status
        )

    def source_ids_in_dag(self, pipeline: Optional[Dict[str, Any]]) -> List[str]:
        """Source ids a pipeline's DAG references, in declaration order."""
        steps = ((pipeline or {}).get("dag_json") or {}).get("steps") or []
        return [str(s.get("source_id")) for s in steps if isinstance(s, dict) and s.get("source_id")]

    def pipelines_referencing_source(self, source_id: str) -> List[Dict[str, Any]]:
        """Pipelines whose DAG includes ``source_id``.

        A scan rather than a query: ``dag_json`` is a JSON blob, and the number of
        pipelines in a deployment is small enough that indexing it would be
        premature. Revisit if that stops being true.
        """
        return [
            p for p in self.list_pipelines()
            if source_id in self.source_ids_in_dag(p)
        ]

    def implicit_pipeline_id(self, source_id: str) -> str:
        """Deterministic id of the single-source pipeline wrapping ``source_id``.

        Derived rather than random so the shortcut is idempotent: scheduling the
        same source twice updates one pipeline instead of accumulating them.
        """
        return f"src-{source_id}"

    def ensure_single_source_pipeline(
        self, source_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get or create the implicit pipeline for a source-level schedule.

        Schedules live on the pipeline, never on the source. A source-level
        schedule is therefore sugar over a one-step pipeline, created here so the
        scheduler only ever has one kind of thing to run.
        """
        pipeline_id = self.implicit_pipeline_id(source_id)
        existing = self.get_pipeline(pipeline_id)
        if existing:
            return existing
        source = self.get_source(source_id)
        label = name or f"{(source or {}).get('name') or source_id} (single source)"
        return self.create_pipeline(
            name=label,
            dag={"steps": [{"source_id": source_id, "depends_on": []}]},
            description="Created automatically for a source-level schedule.",
            pipeline_id=pipeline_id,
        )

    # ------------------------------------------------------------ helpers

    def _update(
        self,
        table: str,
        updatable: tuple,
        json_columns: tuple,
        row_id: str,
        fields: Dict[str, Any],
        reader,
    ) -> Optional[Dict[str, Any]]:
        """Shared UPDATE path for both tables."""
        unknown = sorted(set(fields) - set(updatable))
        if unknown:
            raise ValueError(
                f"cannot update {table}.{unknown[0]!r}: not an updatable column "
                f"(allowed: {list(updatable)})"
            )
        if not fields:
            return reader(row_id)

        assignments = []
        values: List[Any] = []
        for column, value in fields.items():
            assignments.append(f"{column} = ?")
            values.append(self._encode(value) if column in json_columns else value)
        assignments.append("updated_at = ?")
        values.append(utc_now())
        values.append(row_id)

        conn = self._connect()
        try:
            cur = conn.execute(
                f"UPDATE {table} SET {', '.join(assignments)} WHERE id = ?", values
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        finally:
            conn.close()
        return reader(row_id)


_store: Optional[PipelineStore] = None


def get_pipeline_store(db_path: Optional[str] = None) -> PipelineStore:
    """Process-wide store, rebuilt when an explicit ``db_path`` is given.

    Same shape as ``get_canvas_service`` — tests pass a temp path and get a fresh
    instance; request handlers pass the app's configured path.
    """
    global _store
    if _store is None or (db_path is not None and db_path != _store.db_path):
        _store = PipelineStore(db_path)
    return _store
