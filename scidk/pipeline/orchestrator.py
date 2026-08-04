"""Run a source, or a whole pipeline of sources in dependency order.

:mod:`scidk.pipeline.runner` executes *one* source. This module is the level
above: it assembles a runner from a stored ``pipeline_source`` row, and walks a
``pipeline``'s DAG running each source in turn.

Two levels of run, as specified in Cycle 3B Task F:

* :func:`run_source` — one source, ad-hoc refresh. Preflight, then ingest if the
  FAIR gate passes. A FAIR failure writes nothing.
* :func:`run_pipeline` — the named DAG, and the unit of scheduling in production.
  Every source is preflighted; the ones that fail become recorded skipped steps
  and the rest still run, because one broken source should not stop a nightly
  refresh of the other five.

Both are callable with no Flask request context, because the scheduler calls
:func:`run_pipeline` from the gunicorn master where there isn't one.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .plugin_registry import PluginNotAvailable, resolve_plugin
from .run_history import RunHistory
from .runner import PipelineRunner, RunReport, neo4j_writer
from .store import PipelineStore

logger = logging.getLogger(__name__)

__all__ = [
    "DagError",
    "build_runner",
    "run_pipeline",
    "run_source",
    "source_config_of",
    "topological_order",
]


class DagError(ValueError):
    """A pipeline's ``dag_json`` cannot be ordered — a cycle or a dangling id."""


def topological_order(steps: Sequence[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Order DAG steps so every dependency precedes its dependents.

    Args:
        steps: ``[{"source_id": ..., "depends_on": [source_id, ...]}, ...]`` from
            ``pipeline.dag_json``.

    Returns:
        ``(ordered_source_ids, problems)``. ``problems`` names dependencies on
        sources not in the DAG, and any cycle. Steps caught in a cycle are left
        out of the order rather than run in an arbitrary one — a guessed order
        would write to the graph in a sequence nobody chose.

    Ties break on declaration order, so a DAG with no dependencies at all runs
    top to bottom as it reads on screen.
    """
    problems: List[str] = []
    declared: List[str] = []
    dependencies: Dict[str, List[str]] = {}

    for index, step in enumerate(steps or ()):
        if not isinstance(step, dict):
            problems.append(f"dag step {index} is not an object")
            continue
        source_id = step.get("source_id")
        if not source_id:
            problems.append(f"dag step {index} has no source_id")
            continue
        source_id = str(source_id)
        if source_id in dependencies:
            problems.append(f"dag lists source {source_id} more than once")
            continue
        declared.append(source_id)
        dependencies[source_id] = [str(d) for d in (step.get("depends_on") or [])]

    known = set(declared)
    for source_id, deps in dependencies.items():
        unknown = [d for d in deps if d not in known]
        for missing in unknown:
            problems.append(
                f"source {source_id} depends on {missing}, which the DAG does not include"
            )
        dependencies[source_id] = [d for d in deps if d in known]

    # Kahn's algorithm over declaration order, so the result is deterministic.
    order: List[str] = []
    remaining = dict(dependencies)
    while remaining:
        ready = [s for s in declared if s in remaining and not remaining[s]]
        if not ready:
            problems.append(
                "dag has a dependency cycle among "
                f"{sorted(remaining)}; those sources were not run"
            )
            break
        for source_id in ready:
            order.append(source_id)
            del remaining[source_id]
        for deps in remaining.values():
            deps[:] = [d for d in deps if d not in order]

    return order, problems


def source_config_of(source: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a plugin instance config from a stored source row.

    ``pipeline_source.source_path`` holds a JSON config object despite its name.
    A bare string is accepted too and treated as the path, so a hand-written row
    and an early record still run.
    """
    stored = (source or {}).get("source_path")
    if isinstance(stored, dict):
        config = dict(stored)
    elif isinstance(stored, str) and stored.strip():
        config = {"source_path": stored.strip()}
    else:
        config = {}
    raw = (source or {}).get("source_path_raw")
    if not config and isinstance(raw, str) and raw.strip():
        config = {"source_path": raw.strip()}
    return config


def build_runner(
    source: Dict[str, Any],
    writer: Optional[Any] = None,
    upload_dir: Optional[str] = None,
) -> PipelineRunner:
    """Assemble a runner for one stored source.

    Args:
        source: A ``pipeline_source`` row as :class:`PipelineStore` returns it.
        writer: Something with ``write_declared_nodes``, or None to map only.
        upload_dir: Directory uploads live in. Passed to the built-in file source
            as ``base_dir`` *only* for sources that came from an upload, so a
            crafted ``source_path`` on an uploaded source cannot read arbitrary
            files, while an admin who configured ``/data/exports/x.csv`` by hand
            is still trusted — that path came from a setting, not from a browser.

    Raises:
        PluginNotAvailable: No plugin implements this source's ``plugin_type``.
        ValueError: The source has no mapping config, so there is nothing to run.
    """
    config = source_config_of(source)
    mapping = source.get("mapping_json")
    if not mapping:
        raise ValueError(
            f"source {source.get('name') or source.get('id')!r} has no mapping "
            "config; define the column mapping before running it"
        )

    kwargs: Dict[str, Any] = {}
    if config.get("upload_name") and upload_dir:
        kwargs["base_dir"] = upload_dir
    plugin = resolve_plugin(source.get("plugin_type") or "", **kwargs)
    return PipelineRunner(plugin, mapping, config, writer=writer)


def run_source(
    source_id: str,
    store: PipelineStore,
    app: Optional[Any] = None,
    dry_run: bool = False,
    upload_dir: Optional[str] = None,
    writer: Optional[Any] = None,
) -> RunReport:
    """Run one source end to end and stamp the outcome onto its record.

    Args:
        source_id: ``pipeline_source.id``.
        store: Where the source lives and where the outcome is written back.
        app: Flask app supplying Neo4j settings. None in a scheduled job, where
            the environment is the only available source of them.
        dry_run: Map and report, write nothing.
        upload_dir: See :func:`build_runner`.
        writer: Override the Neo4j client — for tests, and for a pipeline run
            that keeps one connection open across all its sources.

    Returns:
        RunReport: never raises. A missing source, an unavailable plugin and an
        absent mapping config are all reported as a failed run, because that is
        what the caller has to display either way.
    """
    source = store.get_source(source_id)
    if source is None:
        report = RunReport(status="error")
        report.add_error(f"source {source_id!r} does not exist")
        return report

    try:
        runner = build_runner(source, writer=writer, upload_dir=upload_dir)
    except (PluginNotAvailable, ValueError) as e:
        report = RunReport(status="error")
        report.add_error(str(e))
        store.record_source_run(source_id, "error", report.to_dict())
        return report

    if writer is not None or dry_run:
        report = runner.run(dry_run=dry_run)
    else:
        with neo4j_writer(app) as client:
            if client is None:
                report = RunReport(status="error")
                report.add_error(
                    "Neo4j is not configured; configure a connection in Settings "
                    "before running a pipeline source"
                )
                store.record_source_run(source_id, "error", report.to_dict())
                return report
            runner.writer = client
            report = runner.run(dry_run=False)

    if not dry_run:
        store.record_source_run(source_id, report.status, report.to_dict())
    return report


def run_pipeline(
    pipeline_id: str,
    store: PipelineStore,
    history: RunHistory,
    app: Optional[Any] = None,
    triggered_by: str = "manual",
    upload_dir: Optional[str] = None,
    writer: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute a pipeline's DAG, recording a ``pipeline_run`` row.

    Args:
        pipeline_id: ``pipeline.id``.
        store: Source and pipeline records.
        history: Where the run row is written.
        app: Flask app for Neo4j settings, or None under the scheduler.
        triggered_by: ``'manual'``, ``'schedule'`` or ``'api'``.
        upload_dir: See :func:`build_runner`.
        writer: Override the Neo4j client, for tests.

    Returns:
        ``{"run_id", "pipeline_id", "status", "steps", "errors"}``. ``status`` is
        ``'success'`` when every step succeeded, ``'error'`` when none did, and
        ``'partial'`` otherwise — recorded as itself, not merged into either.
    """
    pipeline = store.get_pipeline(pipeline_id)
    if pipeline is None:
        return {
            "run_id": None,
            "pipeline_id": pipeline_id,
            "status": "error",
            "steps": [],
            "errors": [f"pipeline {pipeline_id!r} does not exist"],
        }

    steps_spec = (pipeline.get("dag_json") or {}).get("steps") or []
    order, problems = topological_order(steps_spec)
    errors = list(problems)

    run_id = history.start_run(pipeline_id, triggered_by=triggered_by)
    steps: List[Dict[str, Any]] = []

    # One connection for the whole DAG rather than one per source. Opened here so
    # it is closed even when a source raises, and skipped entirely for a DAG that
    # turned out to have nothing runnable in it.
    if writer is not None or not order:
        steps = _execute(order, store, history, run_id, app, upload_dir, writer, errors)
    else:
        with neo4j_writer(app) as client:
            if client is None:
                errors.append(
                    "Neo4j is not configured; configure a connection in Settings "
                    "before running a pipeline"
                )
            else:
                steps = _execute(order, store, history, run_id, app, upload_dir, client, errors)

    status = _pipeline_status(steps, errors)
    history.complete_run(run_id, status, steps)
    store.record_pipeline_run(pipeline_id, status)

    return {
        "run_id": run_id,
        "pipeline_id": pipeline_id,
        "status": status,
        "steps": steps,
        "errors": errors,
    }


def _execute(
    order: Sequence[str],
    store: PipelineStore,
    history: RunHistory,
    run_id: str,
    app: Optional[Any],
    upload_dir: Optional[str],
    writer: Optional[Any],
    errors: List[str],
) -> List[Dict[str, Any]]:
    """Run each source in ``order``, recording every step as it finishes."""
    steps: List[Dict[str, Any]] = []
    for source_id in order:
        source = store.get_source(source_id)
        name = (source or {}).get("name") or source_id
        try:
            report = run_source(
                source_id, store, app=app, upload_dir=upload_dir, writer=writer
            )
        except Exception as e:  # noqa: BLE001 - one bad source must not end the DAG
            logger.error("Pipeline step %s (%s) raised: %s", source_id, name, e, exc_info=True)
            errors.append(f"{name}: {type(e).__name__}: {e}")
            step = {
                "source_id": source_id,
                "source_name": name,
                "status": "error",
                "fair": {"F": False, "A": False, "I": False, "R": False},
                "summary": {"errors": [f"{type(e).__name__}: {e}"]},
            }
        else:
            step = {
                "source_id": source_id,
                "source_name": name,
                # A source whose FAIR gate failed wrote nothing. Recorded as
                # 'skipped' rather than 'error' so the report distinguishes
                # "never attempted" from "attempted and broke partway".
                "status": "skipped" if not report.fair_ok else report.status,
                "fair": dict(report.fair),
                "summary": report.to_dict(),
            }
            if not report.fair_ok:
                step["reason"] = "FAIR check failed; source not ingested"
        steps.append(step)
        history.record_step(run_id, step)
    return steps


def _pipeline_status(steps: Sequence[Dict[str, Any]], errors: Sequence[str]) -> str:
    """Aggregate step outcomes into the run's status."""
    if not steps:
        return "error"
    succeeded = sum(1 for s in steps if s.get("status") == "success")
    if succeeded == len(steps) and not errors:
        return "success"
    if succeeded == 0:
        return "error"
    return "partial"
