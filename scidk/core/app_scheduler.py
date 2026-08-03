"""Process-wide APScheduler owner.

One :class:`~apscheduler.schedulers.background.BackgroundScheduler` per process,
reached through :func:`get_app_scheduler`. Features register jobs into it instead
of standing up their own scheduler:

    from ..core.app_scheduler import get_app_scheduler
    from apscheduler.triggers.cron import CronTrigger

    get_app_scheduler().add_job(
        my_job, CronTrigger(hour=6, timezone=utc), id='my_job', name='My Job',
    )

Why this exists
---------------
``get_backup_scheduler()`` used to construct a new ``BackupScheduler`` on every
call, and ``create_app()`` calls it. ``restart_gunicorn.sh`` runs ``-w 16``, so
each of the 16 workers built its own ``BackgroundScheduler`` with its own
in-memory jobstore: ``daily_backup`` and the concept-graph weight decay fired 16
times a night. ``replace_existing=True`` deduplicates within one jobstore and does
nothing across 16 independent ones.

Two things fix that, and both are needed:

1. ``--preload`` in ``restart_gunicorn.sh``, so ``create_app()`` runs once in the
   gunicorn master and the started scheduler is inherited, not re-created, by
   workers. APScheduler's timer lives in a thread, and ``fork()`` does not copy
   threads — so only the master actually fires jobs.
2. This module-level singleton, so repeated ``create_app()`` calls within one
   process (tests, the Werkzeug reloader, an embedded second app) share one
   scheduler rather than stacking them up.

Ownership and process boundaries
--------------------------------
The process that calls :meth:`AppScheduler.start` owns the scheduler; its pid is
recorded in :attr:`AppScheduler.owner_pid`. After a fork the child inherits an
object that reports ``STATE_RUNNING`` but has no timer thread behind it, which is
exactly the intent — one firing process. :meth:`is_owner` exists so callers that
*mutate* the schedule can tell whether they are talking to the live scheduler or
to an inherited copy; see ``BackupScheduler.update_settings``.
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

#: Timezone new jobs are scheduled in when they do not state their own.
#: Override with SCIDK_SCHEDULER_TIMEZONE.
DEFAULT_TIMEZONE = 'UTC'


class AppScheduler:
    """A thin, feature-neutral wrapper around one BackgroundScheduler."""

    def __init__(self, timezone: Optional[str] = None):
        """
        Args:
            timezone: Olson name the scheduler defaults to. Falls back to
                SCIDK_SCHEDULER_TIMEZONE, then DEFAULT_TIMEZONE ('UTC').
                Triggers that state their own timezone are unaffected.
        """
        self.timezone = (
            timezone
            or os.environ.get('SCIDK_SCHEDULER_TIMEZONE')
            or DEFAULT_TIMEZONE
        )
        self._scheduler = BackgroundScheduler(timezone=self.timezone)
        self._owner_pid: Optional[int] = None

    @property
    def scheduler(self) -> BackgroundScheduler:
        """The underlying APScheduler instance, for features that need it directly."""
        return self._scheduler

    @property
    def owner_pid(self) -> Optional[int]:
        """Pid of the process that started this scheduler, or None if not started."""
        return self._owner_pid

    def is_owner(self) -> bool:
        """True if this process is the one whose timer thread is running.

        False in a forked worker that inherited a started scheduler. Callers that
        add, remove, or reschedule jobs should check this — mutating an inherited
        copy changes nothing that will ever fire.
        """
        return self._owner_pid is not None and self._owner_pid == os.getpid()

    def start(self) -> bool:
        """Start the scheduler if it is not already running in this process.

        Returns:
            True if this call started it, False if it was already running.
        """
        if self._scheduler.running:
            # Already running. If no owner is recorded, the underlying
            # BackgroundScheduler was started through some other path in this
            # same process — claim it, so is_owner() does not report False in
            # the process that holds the timer thread. A forked worker inherits
            # a non-None owner_pid and so never reaches this.
            if self._owner_pid is None:
                self._owner_pid = os.getpid()
            return False
        self._scheduler.start()
        self._owner_pid = os.getpid()
        logger.info(
            f"AppScheduler started (pid={self._owner_pid}, tz={self.timezone})"
        )
        return True

    def shutdown(self, wait: bool = False):
        """Stop the scheduler if it is running in this process."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
        self._owner_pid = None

    def is_running(self) -> bool:
        return bool(self._scheduler.running)

    def add_job(self, func, trigger, id: str, name: Optional[str] = None,
                replace_existing: bool = True, **kwargs):
        """Register a job. Jobs may be added before or after start().

        Args:
            func: Callable to run. Open database connections and drivers inside
                it rather than capturing them — under --preload the job runs in
                the gunicorn master, and anything captured at create_app() time
                crossed a fork to get there.
            trigger: An APScheduler trigger. State its timezone explicitly.
            id: Stable job id; reused ids replace rather than duplicate.
            name: Human-readable name for logs and introspection.
        """
        # APScheduler only applies replace_existing when the scheduler is
        # running; before start() it appends to _pending_jobs, where two calls
        # with the same id stack up and both appear in get_jobs(). Registration
        # happens during create_app(), which may be either side of start(), so
        # drop any existing job first and behave the same way in both states.
        if replace_existing:
            self.remove_job(id)

        job = self._scheduler.add_job(
            func, trigger, id=id, name=name or id,
            replace_existing=replace_existing, **kwargs
        )
        logger.info(f"AppScheduler: registered job '{id}' ({trigger})")
        return job

    def remove_job(self, id: str) -> bool:
        """Remove a job by id. Returns False if it was not registered."""
        try:
            self._scheduler.remove_job(id)
            return True
        except Exception:
            return False

    def get_job(self, id: str):
        try:
            return self._scheduler.get_job(id)
        except Exception:
            return None

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Summarise registered jobs for health endpoints and debugging."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = getattr(job, 'next_run_time', None)
            jobs.append({
                'id': job.id,
                'name': job.name,
                'trigger': str(job.trigger),
                'next_run_time': next_run.isoformat() if next_run else None,
            })
        return jobs


_app_scheduler: Optional[AppScheduler] = None
_app_scheduler_lock = threading.Lock()


def get_app_scheduler(timezone: Optional[str] = None) -> AppScheduler:
    """Get or create this process's AppScheduler.

    Returns the same instance for the life of the process. ``timezone`` only
    applies to the first call that creates it; later calls ignore it rather than
    silently rebuilding a scheduler that already has jobs registered.
    """
    global _app_scheduler
    if _app_scheduler is None:
        with _app_scheduler_lock:
            if _app_scheduler is None:
                _app_scheduler = AppScheduler(timezone=timezone)
    return _app_scheduler


def reset_app_scheduler():
    """Drop the singleton, shutting it down first. For tests only."""
    global _app_scheduler
    with _app_scheduler_lock:
        if _app_scheduler is not None:
            try:
                _app_scheduler.shutdown()
            except Exception:
                pass
            _app_scheduler = None
