"""
Tests for the process-wide scheduler and the fork-safety invariant --preload needs.

Cycle 1, Task C.
"""
import gc
import os
import sqlite3

import pytest
from apscheduler.triggers.cron import CronTrigger

from scidk.core.alert_manager import AlertManager
from scidk.core.app_scheduler import (
    AppScheduler,
    get_app_scheduler,
    reset_app_scheduler,
)
from scidk.core.backup_manager import BackupManager
from scidk.core.backup_scheduler import (
    BackupScheduler,
    get_backup_scheduler,
    reset_backup_scheduler,
)
from scidk.core.settings import InterpreterSettings


@pytest.fixture(autouse=True)
def _clean_singletons():
    """Each test gets fresh module-level singletons."""
    reset_app_scheduler()
    reset_backup_scheduler()
    yield
    reset_app_scheduler()
    reset_backup_scheduler()


# ─────────────────────────────────────────────
# AppScheduler
# ─────────────────────────────────────────────

def test_get_app_scheduler_returns_one_instance_per_process():
    """The duplication bug: a factory that builds a new scheduler every call."""
    assert get_app_scheduler() is get_app_scheduler() is get_app_scheduler()


def test_app_scheduler_defaults_to_utc():
    assert str(AppScheduler().timezone) == 'UTC'


def test_app_scheduler_timezone_is_configurable(monkeypatch):
    monkeypatch.setenv('SCIDK_SCHEDULER_TIMEZONE', 'America/New_York')
    assert AppScheduler().timezone == 'America/New_York'
    assert AppScheduler(timezone='UTC').timezone == 'UTC'


def test_start_is_idempotent():
    scheduler = AppScheduler()
    try:
        assert scheduler.start() is True
        assert scheduler.start() is False   # already running, not restarted
        assert scheduler.is_running()
    finally:
        scheduler.shutdown()


def test_owner_pid_and_is_owner():
    scheduler = AppScheduler()
    assert scheduler.owner_pid is None
    assert not scheduler.is_owner()
    try:
        scheduler.start()
        assert scheduler.owner_pid == os.getpid()
        assert scheduler.is_owner()
    finally:
        scheduler.shutdown()
    assert scheduler.owner_pid is None


def test_reused_job_id_replaces_rather_than_duplicates():
    scheduler = AppScheduler()
    scheduler.add_job(lambda: None, CronTrigger(hour=1, timezone='UTC'),
                      id='job_a', name='A')
    scheduler.add_job(lambda: None, CronTrigger(hour=2, timezone='UTC'),
                      id='job_a', name='A again')

    jobs = scheduler.list_jobs()
    assert [j['id'] for j in jobs] == ['job_a']
    assert 'hour=\'2\'' in jobs[0]['trigger']


def test_remove_job_reports_whether_it_existed():
    scheduler = AppScheduler()
    scheduler.add_job(lambda: None, CronTrigger(hour=1, timezone='UTC'), id='job_a')
    assert scheduler.remove_job('job_a') is True
    assert scheduler.remove_job('job_a') is False
    assert scheduler.list_jobs() == []


# ─────────────────────────────────────────────
# BackupScheduler singleton and shared scheduler
# ─────────────────────────────────────────────

@pytest.fixture()
def backup_manager(tmp_path):
    return BackupManager(backup_dir=str(tmp_path / 'backups'))


def test_get_backup_scheduler_returns_one_instance_per_process(backup_manager, tmp_path):
    """restart_gunicorn.sh -w 16 meant 16 schedulers; within a process, now one."""
    db = str(tmp_path / 'settings.db')
    first = get_backup_scheduler(backup_manager=backup_manager, settings_db_path=db)
    second = get_backup_scheduler(backup_manager=backup_manager, settings_db_path=db)
    assert first is second


def test_backup_scheduler_registers_into_an_injected_app_scheduler(
    backup_manager, tmp_path
):
    """Backup jobs and other features' jobs must land in one scheduler."""
    app_scheduler = get_app_scheduler()
    backup = BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=str(tmp_path / 'settings.db'),
        app_scheduler=app_scheduler,
    )
    try:
        backup.start()
        assert backup.scheduler is app_scheduler.scheduler
        assert 'daily_backup' in [j['id'] for j in app_scheduler.list_jobs()]
        # Ownership must be recorded on the AppScheduler too, not only on the
        # BackupScheduler that happened to start it.
        assert app_scheduler.is_owner()
        assert app_scheduler.owner_pid == os.getpid()
    finally:
        backup.stop()


def test_stopping_a_shared_scheduler_removes_only_its_own_jobs(
    backup_manager, tmp_path
):
    """stop() must not shut down a scheduler other features are using."""
    app_scheduler = get_app_scheduler()
    app_scheduler.add_job(lambda: None, CronTrigger(hour=6, timezone='UTC'),
                          id='someone_elses_job')
    backup = BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=str(tmp_path / 'settings.db'),
        app_scheduler=app_scheduler,
    )
    backup.start()
    assert app_scheduler.is_running()

    backup.stop()

    assert not backup.is_running()
    assert app_scheduler.is_running()
    assert [j['id'] for j in app_scheduler.list_jobs()] == ['someone_elses_job']


def test_backup_scheduler_without_injection_keeps_its_own_scheduler(
    backup_manager, tmp_path
):
    """Direct construction stays self-contained, as tests and scripts rely on."""
    backup = BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=str(tmp_path / 'settings.db'),
    )
    try:
        backup.start()
        assert backup.is_running()
        assert backup.scheduler is not get_app_scheduler().scheduler
    finally:
        backup.stop()
    assert not backup.is_running()


def test_is_owner_tracks_the_starting_process(backup_manager, tmp_path):
    backup = BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=str(tmp_path / 'settings.db'),
    )
    assert not backup.is_owner()
    try:
        backup.start()
        assert backup.is_owner()
    finally:
        backup.stop()


def test_next_backup_time_computed_without_touching_an_inherited_scheduler(
    backup_manager, tmp_path
):
    """A worker must not read the inherited jobstore — it may hold a locked mutex.

    gunicorn forks while the master's scheduler thread is running, so a child can
    inherit APScheduler's _jobstores_lock already held with no thread left to
    release it. The answer is recomputed from the persisted schedule instead.
    """
    backup = BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=str(tmp_path / 'settings.db'),
    )
    try:
        backup.start()

        owner_answer = backup.get_next_backup_time()
        assert owner_answer is not None

        backup._owner_pid = os.getpid() + 100000   # pretend to be a worker
        assert not backup.is_owner()

        # Poison the scheduler: any access raises. A correct implementation
        # never reaches it.
        class Exploding:
            def __getattr__(self, name):
                raise AssertionError(
                    "a non-owner process touched the inherited scheduler"
                )

        real_scheduler, backup.scheduler = backup.scheduler, Exploding()
        try:
            worker_answer = backup.get_next_backup_time()
        finally:
            backup.scheduler = real_scheduler

        assert worker_answer is not None
        assert worker_answer[:10] == owner_answer[:10]   # same scheduled day
    finally:
        backup._owner_pid = os.getpid()
        backup.stop()


def test_update_settings_on_an_inherited_copy_persists_without_rescheduling(
    backup_manager, tmp_path
):
    """Simulates a gunicorn worker: running, but not the process that started it."""
    db = str(tmp_path / 'settings.db')
    backup = BackupScheduler(backup_manager=backup_manager, settings_db_path=db)
    try:
        backup.start()
        backup._owner_pid = os.getpid() + 100000   # pretend the owner is elsewhere
        assert not backup.is_owner()

        assert backup.update_settings({'schedule_hour': 14}) is True
        assert backup.schedule_hour == 14           # persisted and reloaded

        conn = sqlite3.connect(db)
        try:
            stored = conn.execute(
                "SELECT value FROM backup_settings WHERE key = 'schedule_hour'"
            ).fetchone()
        finally:
            conn.close()
        assert stored[0] == '14'
    finally:
        backup._owner_pid = os.getpid()
        backup.stop()


# ─────────────────────────────────────────────
# Fork safety: nothing may hold a connection open at fork time
# ─────────────────────────────────────────────

def test_interpreter_settings_opens_no_connection_until_used(tmp_path):
    settings = InterpreterSettings(db_path=str(tmp_path / 'settings.db'))
    assert settings._db is None

    settings.save_enabled_interpreters({'python'})
    assert settings._db is not None
    assert settings.load_enabled_interpreters() == {'python'}

    settings.close()
    assert settings._db is None

    # Still usable — reopens lazily, as a forked worker would.
    assert settings.load_enabled_interpreters() == {'python'}
    settings.close()


def test_alert_manager_opens_no_connection_until_used(tmp_path):
    manager = AlertManager(db_path=str(tmp_path / 'settings.db'))
    assert manager._db is None

    alerts = manager.list_alerts()
    assert manager._db is not None
    assert len(alerts) > 0      # bootstrap_default_alerts ran on first access

    manager.close()
    assert manager._db is None

    assert len(manager.list_alerts()) == len(alerts)
    manager.close()


def _open_sqlite_connections():
    """Every live sqlite3.Connection in this process."""
    return [o for o in gc.get_objects() if isinstance(o, sqlite3.Connection)]


def test_create_app_leaves_no_sqlite_connection_open(monkeypatch, tmp_path):
    """The invariant --preload depends on.

    Anything still open when create_app() returns is inherited by all 16 forked
    workers as a shared file descriptor: interleaved writes and contended WAL
    locks on scidk_settings.db.
    """
    monkeypatch.setenv('SCIDK_SETTINGS_DB', str(tmp_path / 'settings.db'))
    monkeypatch.setenv('SCIDK_CONCEPT_GRAPH_ENABLED', '0')
    monkeypatch.setenv('SCIDK_DISABLE_SCHEDULER', '1')

    from scidk.app import create_app

    gc.collect()
    before = len(_open_sqlite_connections())

    app = create_app()

    gc.collect()
    leaked = [
        conn for conn in _open_sqlite_connections()
        # A closed connection raises on use; a live one answers.
        if _is_usable(conn)
    ]

    ext = app.extensions['scidk']
    for key in ('settings', 'alert_manager'):
        holder = ext.get(key)
        if holder is not None:
            assert getattr(holder, '_db', None) is None, (
                f"app.extensions['scidk']['{key}'] holds an open connection; "
                "it would be inherited by every gunicorn worker under --preload"
            )

    scheduler = ext.get('backup_scheduler')
    alert_manager = getattr(scheduler, 'alert_manager', None)
    if alert_manager is not None:
        assert getattr(alert_manager, '_db', None) is None, (
            "backup_scheduler.alert_manager holds an open connection"
        )

    # Guard against a future service reintroducing a held handle.
    assert len(leaked) <= before, (
        f"create_app() left {len(leaked) - before} extra SQLite connection(s) "
        "open; see _release_startup_connections() in scidk/app.py"
    )


def _is_usable(conn) -> bool:
    try:
        conn.execute('SELECT 1')
        return True
    except Exception:
        return False


def test_scheduler_skipped_in_the_werkzeug_reloader_parent(monkeypatch):
    """Debug mode runs the module twice; only the serving child owns the scheduler."""
    from scidk.app import _scheduler_should_start

    monkeypatch.delenv('SCIDK_DISABLE_SCHEDULER', raising=False)

    # Not under the reloader (gunicorn, tests): start.
    monkeypatch.delenv('SCIDK_RELOADER_ACTIVE', raising=False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    assert _scheduler_should_start() is True

    # Reloader parent: watches files, serves nothing.
    monkeypatch.setenv('SCIDK_RELOADER_ACTIVE', '1')
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    assert _scheduler_should_start() is False

    # Reloader child: the one that serves.
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true')
    assert _scheduler_should_start() is True


def test_scheduler_can_be_disabled_entirely(monkeypatch):
    from scidk.app import _scheduler_should_start

    monkeypatch.delenv('SCIDK_RELOADER_ACTIVE', raising=False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setenv('SCIDK_DISABLE_SCHEDULER', '1')
    assert _scheduler_should_start() is False
