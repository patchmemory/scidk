"""Registration point for recurring jobs.

``register_all()`` is called once from ``create_app()``, in the single process
that owns the scheduler, with the process-wide :class:`AppScheduler`. Features
add their jobs here instead of constructing a scheduler of their own.

Writing a job function
----------------------
Under ``gunicorn --preload`` these functions run in the master process, and
everything reachable from ``create_app()`` got there by crossing a ``fork()``.
So:

* Open SQLite connections and Neo4j drivers *inside* the job and close them
  before returning. Do not capture a connection from ``app.extensions``.
* Read configuration inside the job too, so a settings change is picked up
  without a restart.
* Never let a job raise. An unhandled exception is swallowed by APScheduler and
  the failure becomes invisible; log it instead.
* State the timezone on the trigger explicitly. A bare ``CronTrigger(hour=6)``
  inherits the scheduler's timezone, which is not obvious at the call site.
"""

import logging
import os

from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

#: How often property rankings are recomputed, in hours.
#: Override with SCIDK_RANKING_FLUSH_INTERVAL_HOURS.
DEFAULT_RANKING_FLUSH_INTERVAL_HOURS = 6

#: Timezone the ranking flush cron is stated in. The existing backup and
#: weight-decay jobs use an unstated system-local timezone while their comments
#: say UTC; new jobs say what they mean.
RANKING_FLUSH_TIMEZONE = 'UTC'


def _ranking_flush_interval_hours() -> int:
    """Read the flush interval, clamped to something a cron hour field accepts."""
    raw = os.environ.get('SCIDK_RANKING_FLUSH_INTERVAL_HOURS')
    if not raw:
        return DEFAULT_RANKING_FLUSH_INTERVAL_HOURS
    try:
        hours = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            f"SCIDK_RANKING_FLUSH_INTERVAL_HOURS={raw!r} is not an integer; "
            f"using {DEFAULT_RANKING_FLUSH_INTERVAL_HOURS}h"
        )
        return DEFAULT_RANKING_FLUSH_INTERVAL_HOURS

    if not 1 <= hours <= 24:
        logger.warning(
            f"SCIDK_RANKING_FLUSH_INTERVAL_HOURS={hours} is outside 1-24; "
            f"using {DEFAULT_RANKING_FLUSH_INTERVAL_HOURS}h"
        )
        return DEFAULT_RANKING_FLUSH_INTERVAL_HOURS

    return hours


def flush_property_rankings(settings_db_path: str) -> None:
    """Recompute property_ranking from usage_event.

    Aggregates the usage events that have accumulated since the last run into the
    rankings that shape the chat schema context. Before this job existed,
    ``flush_rankings()`` had no callers at all and rankings were never refreshed.

    Opens and closes its own connection: under ``gunicorn --preload`` this runs in
    the master process, so a handle captured at ``create_app()`` time would have
    crossed a fork. Never raises — a scheduled job that throws is swallowed by
    APScheduler, so failures are logged here instead.
    """
    import sqlite3

    from ..services.schema_intelligence import flush_rankings

    try:
        conn = sqlite3.connect(settings_db_path)
        try:
            result = flush_rankings(conn)
            logger.info(
                f"Scheduled ranking flush: updated {result.get('updated', 0)} "
                f"property rankings in {settings_db_path}"
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Scheduled ranking flush failed: {e}", exc_info=True)


def register_all(app, app_scheduler):
    """Register every recurring job with the process-wide scheduler.

    Args:
        app: Flask application, for config and logging. Do not capture live
            connections out of ``app.extensions`` into a job closure.
        app_scheduler: The process's :class:`~scidk.core.app_scheduler.AppScheduler`.
    """
    # Backup and concept-graph weight decay are registered by BackupScheduler
    # into this same scheduler; see create_app().

    settings_db = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')

    # Pipeline schedules (Cycle 3B Task F). Unlike every other job here, these are
    # created by API requests in worker processes, so they live in a persistent
    # jobstore this process shares with the workers rather than being registered
    # from code. attach() also adds the heartbeat that makes this process notice a
    # schedule a worker wrote, without a restart.
    try:
        from ..pipeline.scheduler import attach as attach_pipeline_scheduler

        attach_pipeline_scheduler(app_scheduler, settings_db)
    except Exception as e:
        logger.error(f"Could not attach the pipeline scheduler: {e}", exc_info=True)

    # Schema Intelligence: recompute property rankings (J7).
    interval = _ranking_flush_interval_hours()

    app_scheduler.add_job(
        lambda: flush_property_rankings(settings_db),
        CronTrigger(hour=f'*/{interval}', minute=17,
                    timezone=RANKING_FLUSH_TIMEZONE),
        id='schema_intelligence_ranking_flush',
        name='Schema Intelligence Ranking Flush',
    )
    logger.info(
        f"Registered ranking flush every {interval}h at :17 "
        f"{RANKING_FLUSH_TIMEZONE} (db={settings_db})"
    )
