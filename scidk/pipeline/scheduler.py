"""Pipeline cron schedules that take effect without restarting the app.

The problem this solves
-----------------------
``restart_gunicorn.sh`` runs with ``--preload``, so ``create_app()`` executes once
in the master and the started scheduler is *inherited* by the 16 workers.
``fork()`` does not copy threads, so only the master's timer fires jobs — which is
exactly what stops the nightly backup running 16 times.

But it also means a worker cannot schedule anything. An API request runs in a
worker, and a worker's copy of the scheduler has no timer behind it;
``AppScheduler.is_owner()`` exists so callers can tell. ``BackupScheduler`` hit
this first and logs a warning that a schedule change needs a restart. Cycle 3B
Task F requires the opposite — "takes effect immediately, no app restart" — so it
needs a channel between the two processes.

That channel is a jobstore both processes open: an APScheduler
``SQLAlchemyJobStore`` on ``scidk_settings.db``.

* The **worker** opens the store through a short-lived scheduler started with
  ``paused=True``. Paused means no timer and no firing, but ``add_job`` still
  writes through to the store with a computed ``next_run_time`` — which is the
  documented way to enqueue work for a scheduler in another process.
* The **master** registers the same store on the process-wide
  :class:`~scidk.core.app_scheduler.AppScheduler` and fires from it.

The one thing a shared jobstore does not give you is a notification. APScheduler
sleeps until the next run time it knows about, and nothing tells it a *new* job
appeared; with no jobs at all it sleeps indefinitely. So :func:`attach` also
registers a heartbeat in the in-memory store. Every wakeup re-reads every
jobstore, so a schedule written by a worker is picked up within one heartbeat
interval — seconds, not a restart. The heartbeat itself does nothing; being woken
is the entire point of it.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_POLL_INTERVAL_SEC",
    "HEARTBEAT_JOB_ID",
    "PIPELINE_JOBSTORE_ALIAS",
    "PipelineScheduleStore",
    "attach",
    "get_schedule_store",
    "job_id_for",
    "run_scheduled_pipeline",
    "validate_cron",
]

#: Jobstore alias pipeline cron jobs live under.
PIPELINE_JOBSTORE_ALIAS = "pipeline"

#: Table the jobstore uses inside ``scidk_settings.db``. Prefixed so it is
#: obviously APScheduler's and not one of ours.
JOBSTORE_TABLE = "apscheduler_pipeline_jobs"

#: The do-nothing job whose only purpose is to wake the master so it re-reads the
#: shared jobstore. Lives in the in-memory store, so it is never persisted.
HEARTBEAT_JOB_ID = "pipeline_schedule_poll"

#: How often the master wakes to notice schedule changes. Overridable with
#: SCIDK_PIPELINE_POLL_INTERVAL_SEC. This is the worst-case delay between saving
#: a schedule and the master knowing about it.
DEFAULT_POLL_INTERVAL_SEC = 30

#: Timezone pipeline crons are interpreted in. Stated explicitly rather than
#: inherited: a cron whose meaning depends on the server's locale is a cron that
#: silently moves when the server does.
SCHEDULE_TIMEZONE = os.environ.get("SCIDK_PIPELINE_TIMEZONE") or "UTC"


def job_id_for(pipeline_id: str) -> str:
    """Stable APScheduler job id for a pipeline. One schedule per pipeline."""
    return f"pipeline:{pipeline_id}"


def validate_cron(expression: str) -> Optional[str]:
    """Return why a cron expression is unusable, or None if it is fine.

    Checked before storing, not at fire time: a malformed cron that APScheduler
    rejects inside the master would be a warning in a log nobody reads, and the
    user would see a schedule that looks saved and never runs.
    """
    from apscheduler.triggers.cron import CronTrigger

    text = str(expression or "").strip()
    if not text:
        return "cron expression is empty"
    fields = text.split()
    if len(fields) != 5:
        return (
            f"expected 5 fields (minute hour day-of-month month day-of-week), got "
            f"{len(fields)}"
        )
    try:
        _trigger_from_cron(text)
    except Exception as e:  # noqa: BLE001 - the parser's message is the useful part
        return f"{e}"
    return None


def _trigger_from_cron(expression: str):
    """Build a CronTrigger from a 5-field expression in :data:`SCHEDULE_TIMEZONE`."""
    from apscheduler.triggers.cron import CronTrigger

    minute, hour, day, month, day_of_week = str(expression).strip().split()
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
        timezone=SCHEDULE_TIMEZONE,
    )


def jobstore_url(settings_db_path: str) -> str:
    """SQLAlchemy URL for the settings database.

    Absolute, because the master and the workers do not reliably share a working
    directory, and ``scidk_settings.db`` is a cwd-relative default.
    """
    return f"sqlite:///{os.path.abspath(settings_db_path)}"


def build_jobstore(settings_db_path: str):
    """Construct the shared ``SQLAlchemyJobStore``.

    A fresh instance per caller: each holds its own SQLAlchemy engine, and an
    engine that crossed a ``fork()`` would have workers sharing one connection
    pool.
    """
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

    return SQLAlchemyJobStore(url=jobstore_url(settings_db_path), tablename=JOBSTORE_TABLE)


# --------------------------------------------------------------- the job

def run_scheduled_pipeline(pipeline_id: str, settings_db_path: str) -> None:
    """Run one pipeline on its schedule. Never raises.

    Module-level and taking only strings, because the jobstore persists this as a
    textual reference plus pickled arguments. A closure, a bound method, or an
    argument holding a live connection could not be stored — and under
    ``--preload`` anything captured at ``create_app()`` time crossed a fork to get
    here anyway.

    Opens and closes its own SQLite connections and Neo4j driver, per the rules in
    :mod:`scidk.core.scheduled_jobs`. Passes ``app=None``, so Neo4j settings come
    from the environment: there is no Flask app in the master's scheduler thread.
    """
    from .orchestrator import run_pipeline
    from .run_history import RunHistory
    from .store import PipelineStore

    try:
        store = PipelineStore(settings_db_path)
        pipeline = store.get_pipeline(pipeline_id)
        if pipeline is None:
            logger.warning(
                "Scheduled pipeline %s no longer exists; removing its schedule",
                pipeline_id,
            )
            try:
                get_schedule_store(settings_db_path).remove(pipeline_id)
            except Exception:  # noqa: BLE001
                pass
            return

        # Paused keeps the cron definition without running it. Checked here as
        # well as at write time so a pause takes effect even if the job in the
        # store was not rewritten.
        if pipeline.get("schedule_paused"):
            logger.info("Scheduled pipeline %s is paused; skipping", pipeline_id)
            return

        result = run_pipeline(
            pipeline_id,
            store,
            RunHistory(settings_db_path),
            app=None,
            triggered_by="schedule",
        )
        logger.info(
            "Scheduled pipeline %s (%s) finished: %s (%d step(s))",
            pipeline_id, pipeline.get("name"), result.get("status"),
            len(result.get("steps") or []),
        )
    except Exception as e:  # noqa: BLE001
        # An unhandled exception here is swallowed by APScheduler, which would
        # make the failure invisible. Log it instead.
        logger.error(
            "Scheduled pipeline %s failed: %s", pipeline_id, e, exc_info=True
        )


def _heartbeat() -> None:
    """Do nothing, on a timer.

    Its value is the wakeup, not the work: each wakeup makes the scheduler
    re-read every jobstore, which is how a schedule a worker wrote gets noticed
    without a restart.
    """
    logger.debug("Pipeline schedule poll tick")


# ------------------------------------------------------------ master side

def poll_interval_sec() -> int:
    """Heartbeat interval, clamped to something sane."""
    raw = os.environ.get("SCIDK_PIPELINE_POLL_INTERVAL_SEC")
    if not raw:
        return DEFAULT_POLL_INTERVAL_SEC
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "SCIDK_PIPELINE_POLL_INTERVAL_SEC=%r is not an integer; using %ds",
            raw, DEFAULT_POLL_INTERVAL_SEC,
        )
        return DEFAULT_POLL_INTERVAL_SEC
    if not 5 <= seconds <= 3600:
        logger.warning(
            "SCIDK_PIPELINE_POLL_INTERVAL_SEC=%d is outside 5-3600; using %ds",
            seconds, DEFAULT_POLL_INTERVAL_SEC,
        )
        return DEFAULT_POLL_INTERVAL_SEC
    return seconds


def attach(app_scheduler, settings_db_path: str) -> bool:
    """Register the shared jobstore and the heartbeat on the process's scheduler.

    Called once from ``create_app()``, in the process that owns the scheduler.
    Jobs already in the store — written by an earlier run or by a worker — become
    live as soon as the store is registered; nothing needs re-adding.

    Args:
        app_scheduler: The process's :class:`~scidk.core.app_scheduler.AppScheduler`.
        settings_db_path: Path to ``scidk_settings.db``.

    Returns:
        True when the jobstore is attached and the heartbeat registered. False if
        it could not be, in which case pipeline schedules simply do not fire —
        logged, and not fatal to startup.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    try:
        app_scheduler.add_jobstore(build_jobstore(settings_db_path), PIPELINE_JOBSTORE_ALIAS)
    except Exception as e:  # noqa: BLE001 - scheduling is not worth failing startup for
        logger.error(
            "Could not attach the pipeline jobstore (%s); pipeline schedules will "
            "not fire in this process: %s", settings_db_path, e, exc_info=True
        )
        return False

    interval = poll_interval_sec()
    app_scheduler.add_job(
        _heartbeat,
        IntervalTrigger(seconds=interval, timezone=SCHEDULE_TIMEZONE),
        id=HEARTBEAT_JOB_ID,
        name="Pipeline schedule poll",
    )
    existing = len(app_scheduler.scheduler.get_jobs(jobstore=PIPELINE_JOBSTORE_ALIAS))
    logger.info(
        "Pipeline scheduler attached: %d persisted schedule(s), polling every %ds "
        "(tz=%s, db=%s)", existing, interval, SCHEDULE_TIMEZONE, settings_db_path,
    )
    return True


# ------------------------------------------------------------ worker side

class PipelineScheduleStore:
    """Read and write pipeline schedules in the shared jobstore.

    Safe to use from a gunicorn worker, which is the whole point: it never touches
    the process's own scheduler (which has no timer behind it) and instead opens
    the jobstore directly through a short-lived paused scheduler.

    Args:
        settings_db_path: Path to ``scidk_settings.db``.
    """

    def __init__(self, settings_db_path: str):
        self.settings_db_path = settings_db_path

    def _client(self):
        """A started-but-paused scheduler wired to the shared jobstore.

        Paused, so it never fires anything — this process must not run pipelines
        out of a request handler. Started, because a stopped scheduler queues
        ``add_job`` into ``_pending_jobs`` in memory and never writes through.
        """
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(timezone=SCHEDULE_TIMEZONE)
        scheduler.add_jobstore(build_jobstore(self.settings_db_path), PIPELINE_JOBSTORE_ALIAS)
        scheduler.start(paused=True)
        return scheduler

    def upsert(self, pipeline_id: str, cron: str) -> Dict[str, Any]:
        """Create or replace a pipeline's cron job.

        Args:
            pipeline_id: The pipeline to schedule.
            cron: A 5-field cron expression, already validated.

        Returns:
            ``{"cron", "next_run_time", "job_id"}``.

        Raises:
            ValueError: ``cron`` is not a usable expression.
        """
        problem = validate_cron(cron)
        if problem:
            raise ValueError(f"invalid cron expression {cron!r}: {problem}")

        scheduler = self._client()
        try:
            job = scheduler.add_job(
                run_scheduled_pipeline,
                _trigger_from_cron(cron),
                id=job_id_for(pipeline_id),
                name=f"Pipeline {pipeline_id}",
                args=[pipeline_id, os.path.abspath(self.settings_db_path)],
                jobstore=PIPELINE_JOBSTORE_ALIAS,
                replace_existing=True,
                # A missed window should run once when noticed, not once per
                # window missed while the app was down.
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            next_run = getattr(job, "next_run_time", None)
        finally:
            scheduler.shutdown(wait=False)

        logger.info("Scheduled pipeline %s at %r (next: %s)", pipeline_id, cron, next_run)
        return {
            "cron": cron,
            "job_id": job_id_for(pipeline_id),
            "next_run_time": next_run.isoformat() if next_run else None,
        }

    def remove(self, pipeline_id: str) -> bool:
        """Delete a pipeline's cron job. False if there was none."""
        scheduler = self._client()
        try:
            scheduler.remove_job(job_id_for(pipeline_id), jobstore=PIPELINE_JOBSTORE_ALIAS)
            logger.info("Unscheduled pipeline %s", pipeline_id)
            return True
        except Exception:  # noqa: BLE001 - JobLookupError means nothing to remove
            return False
        finally:
            scheduler.shutdown(wait=False)

    def get(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Return ``{"job_id", "trigger", "next_run_time"}``, or None if unscheduled."""
        scheduler = self._client()
        try:
            job = scheduler.get_job(job_id_for(pipeline_id), jobstore=PIPELINE_JOBSTORE_ALIAS)
            if job is None:
                return None
            next_run = getattr(job, "next_run_time", None)
            return {
                "job_id": job.id,
                "trigger": str(job.trigger),
                "next_run_time": next_run.isoformat() if next_run else None,
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("Could not read schedule for %s: %s", pipeline_id, e)
            return None
        finally:
            scheduler.shutdown(wait=False)

    def list_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Every persisted pipeline schedule, keyed by pipeline id."""
        scheduler = self._client()
        try:
            jobs = {}
            for job in scheduler.get_jobs(jobstore=PIPELINE_JOBSTORE_ALIAS):
                if not job.id.startswith("pipeline:"):
                    continue
                next_run = getattr(job, "next_run_time", None)
                jobs[job.id.split(":", 1)[1]] = {
                    "job_id": job.id,
                    "trigger": str(job.trigger),
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            return jobs
        except Exception as e:  # noqa: BLE001
            logger.debug("Could not list pipeline schedules: %s", e)
            return {}
        finally:
            scheduler.shutdown(wait=False)


_schedule_stores: Dict[str, PipelineScheduleStore] = {}


def get_schedule_store(settings_db_path: str) -> PipelineScheduleStore:
    """Get the schedule store for a settings database.

    The object is stateless — every method opens and closes its own scheduler —
    so caching it costs nothing and keeps call sites short.
    """
    key = os.path.abspath(settings_db_path)
    if key not in _schedule_stores:
        _schedule_stores[key] = PipelineScheduleStore(settings_db_path)
    return _schedule_stores[key]
