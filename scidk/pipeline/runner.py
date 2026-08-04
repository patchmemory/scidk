"""Execute one source: discover, verify, validate, map, write.

The runner is the only thing that calls both a plugin and Neo4j. It fixes the
order of operations — :meth:`~scidk.pipeline.plugin_base.DataSourcePlugin.find`,
then ``access``, then mapping validation, and only then ``fetch`` — so an
unreachable source, a rejected credential, and a broken config are each reported
as themselves instead of as a failure halfway through an ingest.

Why the reporting is as detailed as it is
-----------------------------------------
``write_declared_nodes`` has two properties that make naive error handling wrong:

1. **It never raises.** A failed statement appends to ``result['errors']`` and the
   loop continues, so a run that wrote nothing at all returns normally. A caller
   that checks only for an exception reports success on a total failure. Every
   batch's ``errors`` is inspected here, and a batch that declared nodes but
   wrote none is escalated rather than logged.

2. **There is no transaction.** Each statement autocommits, so a failure partway
   through leaves everything before it committed. The runner therefore cannot
   offer all-or-nothing semantics and does not pretend to: it reports
   :attr:`RunReport.writes_committed`, and a non-success run that has it set says
   so in the summary. Rolling this back would mean wrapping the whole write in an
   explicit Neo4j transaction, which ``write_declared_nodes`` does not currently
   provide.

The FAIR letters
----------------
======= ============================================================
``F``   ``find()`` succeeded — the source is there and describable.
``A``   ``access()`` succeeded — credentials permit a real read.
``I``   The mapping config validates *and* every column it maps
        exists in the source. Interoperable in the sense that
        matters: this config can actually translate this source.
``R``   Every transform the config names resolves, so the run is
        reproducible from config plus transform library alone.
======= ============================================================

Task E builds the full FAIR check — the sampled row-by-row preview with
merge-vs-create lookups against live Neo4j. :meth:`PipelineRunner.preflight` is
the gate that check will sit on top of: same four letters, no Neo4j reads, no
sample preview.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional, Protocol, Sequence

from .mapping_engine import DeclarationCollector, MappingEngine, RowMapping
from .plugin_base import DataSourcePlugin
from .plugin_registry import transform_library_for

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_WRITE_BATCH_ROWS",
    "MAX_REPORTED_MESSAGES",
    "Neo4jWriter",
    "PipelineRunner",
    "RunReport",
    "neo4j_writer",
]

#: Rows mapped before the accumulated declarations are written. Bounds memory on
#: a source larger than RAM. Nodes and relationships from one row always land in
#: the same batch, so a relationship's endpoints exist by the time it is matched.
DEFAULT_WRITE_BATCH_ROWS = 500

#: Individual error/warning strings kept in a report. A source with one bad
#: column produces one message per row; keeping 100k of them would make the
#: report unreadable and the ``pipeline_run`` row enormous. Counts are always
#: exact — only the message list is capped, and the report says by how much.
MAX_REPORTED_MESSAGES = 200


class Neo4jWriter(Protocol):
    """The only thing the runner needs from Neo4j.

    :class:`~scidk.services.neo4j_client.Neo4jClient` satisfies it. So does a
    fake, which is how the runner is tested without a database.
    """

    def write_declared_nodes(
        self, nodes: List[Dict[str, Any]], relationships: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ...


@dataclass
class RunReport:
    """Everything one run did, succeeded at, and failed at.

    ``status`` is three-valued on purpose. ``'partial'`` is not a softened
    failure: it is the accurate description of an autocommitting write that got
    some of the way through, and merging it into either neighbour would hide the
    case where the graph is now half-updated.
    """

    status: str = "error"
    fair: Dict[str, bool] = field(default_factory=lambda: {"F": False, "A": False, "I": False, "R": False})
    rows_read: int = 0
    rows_skipped: int = 0
    rows_with_errors: int = 0
    nodes_declared: int = 0
    relationships_declared: int = 0
    nodes_written: int = 0
    relationships_written: int = 0
    write_error_count: int = 0
    #: True once any statement has been committed. With no transaction available,
    #: this is what tells a reader of a failed run whether the graph was touched.
    writes_committed: bool = False
    dry_run: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    started_at: float = 0.0
    completed_at: Optional[float] = None
    columns: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)
    row_count_estimate: Optional[int] = None

    @property
    def fair_ok(self) -> bool:
        return all(self.fair.values())

    @property
    def duration_sec(self) -> Optional[float]:
        if not self.started_at or self.completed_at is None:
            return None
        return round(self.completed_at - self.started_at, 3)

    def add_error(self, message: str) -> None:
        """Record an error, keeping at most :data:`MAX_REPORTED_MESSAGES` texts."""
        self.error_count += 1
        if len(self.errors) < MAX_REPORTED_MESSAGES:
            self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warning_count += 1
        if len(self.warnings) < MAX_REPORTED_MESSAGES:
            self.warnings.append(message)

    def summary_line(self) -> str:
        """One-line human summary, for the source card and the log."""
        if self.dry_run:
            return (
                f"{self.rows_read} rows -> {self.nodes_declared} nodes, "
                f"{self.relationships_declared} relationships (no writes); "
                f"{self.error_count} errors"
            )
        parts = [
            f"{self.nodes_written} nodes",
            f"{self.relationships_written} relationships",
            f"{self.rows_read} rows read",
        ]
        if self.rows_skipped:
            parts.append(f"{self.rows_skipped} skipped")
        parts.append(f"{self.error_count} errors")
        line = " · ".join(parts)
        if self.status != "success" and self.writes_committed:
            line += " · writes already committed (no rollback available)"
        return line

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable form, stored in ``pipeline_source.last_run_summary``."""
        data = {
            "status": self.status,
            "fair": dict(self.fair),
            "fair_ok": self.fair_ok,
            "rows_read": self.rows_read,
            "rows_skipped": self.rows_skipped,
            "rows_with_errors": self.rows_with_errors,
            "nodes_declared": self.nodes_declared,
            "relationships_declared": self.relationships_declared,
            "nodes_written": self.nodes_written,
            "relationships_written": self.relationships_written,
            "write_error_count": self.write_error_count,
            "writes_committed": self.writes_committed,
            "dry_run": self.dry_run,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_sec": self.duration_sec,
            "columns": list(self.columns),
            "missing_columns": list(self.missing_columns),
            "row_count_estimate": self.row_count_estimate,
            "summary": self.summary_line(),
        }
        if self.error_count > len(self.errors):
            data["errors_truncated"] = self.error_count - len(self.errors)
        if self.warning_count > len(self.warnings):
            data["warnings_truncated"] = self.warning_count - len(self.warnings)
        return data


class PipelineRunner:
    """Runs one source's mapping config against one plugin.

    Args:
        plugin: The resolved data source plugin.
        mapping_config: Parsed mapping config (``mapping_schema.json`` format).
        source_config: The plugin's instance config — ``source_path`` and
            whatever else that plugin reads.
        writer: Something with ``write_declared_nodes``. None means map but never
            write, which is what :meth:`run` with ``dry_run=True`` does anyway;
            passing None makes it impossible to write by accident.
        vocabulary: Allowed terms per field, overriding the config's
            ``default_vocabulary``.
        batch_rows: Rows mapped per write. Lower it for a very wide source.
    """

    def __init__(
        self,
        plugin: DataSourcePlugin,
        mapping_config: Mapping[str, Any],
        source_config: Optional[Mapping[str, Any]] = None,
        writer: Optional[Neo4jWriter] = None,
        vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
        batch_rows: int = DEFAULT_WRITE_BATCH_ROWS,
    ) -> None:
        self.plugin = plugin
        self.source_config: Dict[str, Any] = dict(source_config or {})
        self.writer = writer
        self.batch_rows = max(1, int(batch_rows))
        self.engine = MappingEngine(
            mapping_config,
            transform_library=transform_library_for(plugin),
            vocabulary=vocabulary,
        )

    # ---------------------------------------------------------- preflight

    def preflight(self, report: Optional[RunReport] = None) -> RunReport:
        """Run F, A, I and R without fetching a single data row.

        Args:
            report: Report to fill in. A fresh one is created when omitted.

        Returns:
            RunReport: ``fair`` populated and ``status`` set to ``'error'`` when
            any letter failed. Never raises — a plugin that raises where the
            contract says it should not is recorded as a failed letter.
        """
        report = report or RunReport(started_at=time.time())

        # F — Findable.
        find = self._safe_call("find", lambda: self.plugin.find(self.source_config))
        if isinstance(find, dict):
            report.fair["F"] = bool(find.get("ok"))
            report.columns = list(find.get("columns") or [])
            report.row_count_estimate = find.get("row_count")
            if not find.get("ok"):
                report.add_error(f"find: {find.get('error') or 'source not found'}")
        else:
            report.add_error(f"find: {find}")

        # A — Accessible.
        access = self._safe_call("access", lambda: self.plugin.access(self.source_config))
        if isinstance(access, dict):
            report.fair["A"] = bool(access.get("ok"))
            if not access.get("ok"):
                report.add_error(f"access: {access.get('error') or 'access denied'}")
        else:
            report.add_error(f"access: {access}")

        # R — Reproducible. Computed before I so an unknown transform is named as
        # a reproducibility failure and not only as a config error.
        unknown = self.engine.unknown_transforms()
        report.fair["R"] = not unknown
        for name, where in unknown:
            report.add_error(f"mapping: unknown transform {name!r} at {where}")

        # I — Interoperable: the config is valid and its columns exist.
        validation = self.engine.validate()
        for message in validation.errors:
            report.add_error(f"mapping: {message}")
        for message in validation.warnings:
            report.add_warning(f"mapping: {message}")

        # A missing column is only fatal when it makes a node impossible rather
        # than incomplete — see MappingEngine.column_problems. Reporting every
        # absent column as an error would refuse to run a config that is simply
        # broader than one particular export.
        blocking: List[str] = []
        if report.fair["F"]:
            report.missing_columns = self.engine.missing_columns(report.columns)
            blocking, informational = self.engine.column_problems(report.columns)
            for message in blocking:
                report.add_error(f"mapping: {message}")
            for message in informational:
                report.add_warning(f"mapping: {message}")
        report.fair["I"] = validation.ok and not blocking and report.fair["F"]

        if not report.fair_ok:
            report.status = "error"
        return report

    @staticmethod
    def _safe_call(stage: str, call) -> Any:
        """Call a plugin method, turning a contract violation into a message.

        The contract says ``find()`` and ``access()`` report failure through their
        return value and never raise. A plugin that raises anyway must not take
        the run down with a traceback the user cannot read.
        """
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            logger.warning("plugin %s() raised: %s", stage, e, exc_info=True)
            return f"plugin raised {type(e).__name__}: {e}"

    # --------------------------------------------------------------- run

    def run(self, dry_run: bool = False, limit: Optional[int] = None) -> RunReport:
        """Preflight, then map and write every row.

        Args:
            dry_run: Map everything and write nothing. Declaration counts are
                still reported, so this answers "what would this produce".
            limit: Stop after this many rows. For sampling a large source.

        Returns:
            RunReport: ``status`` is ``'success'``, ``'partial'`` or ``'error'``.
            Never raises: a failure mid-stream is recorded, with
            ``writes_committed`` saying whether the graph was already changed.
        """
        report = RunReport(started_at=time.time())
        report.dry_run = bool(dry_run) or self.writer is None

        self.preflight(report)
        if not report.fair_ok:
            report.completed_at = time.time()
            report.status = "error"
            return report

        collector = DeclarationCollector()
        aborted = False
        try:
            rows = self.plugin.fetch(self.source_config)
            for mapping in self.engine.map_rows(rows):
                report.rows_read += 1
                self._absorb(mapping, report)
                collector.add_row(mapping)

                if mapping.errors and self.engine.abort_on_row_error:
                    report.add_error(
                        f"row {mapping.row_index}: on_row_error is 'abort'; "
                        "stopping before the rest of the source"
                    )
                    aborted = True
                    break
                if report.rows_read % self.batch_rows == 0:
                    self._flush(collector, report)
                if limit is not None and report.rows_read >= limit:
                    break
        except Exception as e:  # noqa: BLE001 - a broken stream is a run outcome
            logger.error("Pipeline run failed while streaming rows: %s", e, exc_info=True)
            report.add_error(f"fetch: {type(e).__name__}: {e}")
            aborted = True

        self._flush(collector, report)
        for conflict in collector.conflicts[:MAX_REPORTED_MESSAGES]:
            report.add_warning(f"merge: {conflict}")

        report.completed_at = time.time()
        report.status = self._status(report, aborted)
        return report

    def _absorb(self, mapping: RowMapping, report: RunReport) -> None:
        """Fold one row's outcome into the report."""
        if mapping.skipped:
            report.rows_skipped += 1
        if mapping.errors:
            report.rows_with_errors += 1
        for message in mapping.errors:
            report.add_error(message)
        for message in mapping.warnings:
            report.add_warning(message)

    def _flush(self, collector: DeclarationCollector, report: RunReport) -> None:
        """Write one batch, then inspect what the write actually did."""
        nodes, relationships = collector.drain()
        if not nodes and not relationships:
            return
        report.nodes_declared += len(nodes)
        report.relationships_declared += len(relationships)

        if report.dry_run or self.writer is None:
            return

        try:
            result = self.writer.write_declared_nodes(nodes, relationships) or {}
        except Exception as e:  # noqa: BLE001 - a dropped connection mid-run
            logger.error("write_declared_nodes raised: %s", e, exc_info=True)
            report.add_error(f"write: {type(e).__name__}: {e}")
            report.write_error_count += 1
            return

        written_nodes = int(result.get("written_nodes") or 0)
        written_relationships = int(result.get("written_relationships") or 0)
        report.nodes_written += written_nodes
        report.relationships_written += written_relationships
        if written_nodes or written_relationships:
            report.writes_committed = True

        write_errors = list(result.get("errors") or [])
        report.write_error_count += len(write_errors)
        for message in write_errors:
            report.add_error(f"write: {message}")

        # The specific trap: write_declared_nodes returns normally having written
        # nothing. Without this the run looks fine and the graph is untouched.
        if nodes and written_nodes == 0:
            report.add_error(
                f"write: declared {len(nodes)} nodes and wrote 0. "
                "write_declared_nodes reports failures in its 'errors' list and "
                "never raises, so this is a failed write, not an empty batch."
            )

    @staticmethod
    def _status(report: RunReport, aborted: bool) -> str:
        """Classify the run. ``'partial'`` is a real outcome, not a rounding."""
        if report.dry_run:
            return "success" if report.error_count == 0 else "partial"
        if report.nodes_declared and report.nodes_written == 0:
            # Nothing landed. Whether the cause was the write or the stream, the
            # graph did not change, so this is a failure and not a partial.
            return "error"
        if aborted or report.error_count:
            return "partial" if report.writes_committed else "error"
        return "success"


@contextmanager
def neo4j_writer(app: Optional[Any] = None) -> Iterator[Optional[Neo4jWriter]]:
    """Yield a connected Neo4j client, or None when Neo4j is not configured.

    Opens and closes the driver inside the ``with`` block rather than reusing a
    long-lived one. Scheduled pipeline runs execute in the gunicorn master under
    ``--preload``, where a connection pool captured at ``create_app()`` time has
    crossed a ``fork()`` and is shared with every worker.

    Args:
        app: Flask app whose settings supply the connection. Omit it in a
            scheduled job — ``get_neo4j_params(None)`` falls back to the
            environment, which is the only source available there.
    """
    from ..services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(app)
    if not uri:
        yield None
        return

    client = Neo4jClient(uri, user, password, database, auth_mode)
    client.connect()
    try:
        yield client
    finally:
        try:
            client.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to close Neo4j client after run: %s", e)
