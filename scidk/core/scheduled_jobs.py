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

logger = logging.getLogger(__name__)


def register_all(app, app_scheduler):
    """Register every recurring job with the process-wide scheduler.

    Args:
        app: Flask application, for config and logging. Do not capture live
            connections out of ``app.extensions`` into a job closure.
        app_scheduler: The process's :class:`~scidk.core.app_scheduler.AppScheduler`.
    """
    # Backup and concept-graph weight decay are registered by BackupScheduler
    # into this same scheduler; see create_app().
    return
