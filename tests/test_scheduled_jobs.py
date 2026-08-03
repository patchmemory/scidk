"""
Tests for scheduled job registration.

Cycle 1, Task D (J7): flush_rankings() had zero callers, so property rankings
were never refreshed automatically.
"""
import sqlite3

import pytest

from scidk.core.app_scheduler import AppScheduler
from scidk.core.scheduled_jobs import (
    DEFAULT_RANKING_FLUSH_INTERVAL_HOURS,
    RANKING_FLUSH_TIMEZONE,
    _ranking_flush_interval_hours,
    flush_property_rankings,
    register_all,
)
from scidk.services.schema_intelligence import (
    ensure_schema_intelligence_tables,
    log_query_usage,
)

JOB_ID = 'schema_intelligence_ranking_flush'


class _FakeApp:
    """Minimal stand-in for the Flask app register_all() needs."""

    def __init__(self, settings_db):
        self.config = {'SCIDK_SETTINGS_DB': settings_db}

        import logging
        self.logger = logging.getLogger('test_scheduled_jobs')


@pytest.fixture()
def settings_db(tmp_path):
    """A settings database with the SI tables and some usage to aggregate."""
    path = str(tmp_path / 'settings.db')
    conn = sqlite3.connect(path)
    try:
        ensure_schema_intelligence_tables(conn)
    finally:
        conn.close()
    return path


# ─────────────────────────────────────────────
# Interval configuration
# ─────────────────────────────────────────────

def test_interval_defaults_to_six_hours(monkeypatch):
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    assert _ranking_flush_interval_hours() == 6
    assert DEFAULT_RANKING_FLUSH_INTERVAL_HOURS == 6


def test_interval_is_configurable(monkeypatch):
    monkeypatch.setenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', '3')
    assert _ranking_flush_interval_hours() == 3


@pytest.mark.parametrize('value', ['nonsense', '', '0', '-1', '25', '6.5'])
def test_unusable_interval_falls_back_to_the_default(monkeypatch, value):
    """A bad env var must not leave the job unregistered or the cron invalid."""
    monkeypatch.setenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', value)
    assert _ranking_flush_interval_hours() == DEFAULT_RANKING_FLUSH_INTERVAL_HOURS


# ─────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────

def test_ranking_flush_is_registered(monkeypatch, settings_db):
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler()
    register_all(_FakeApp(settings_db), scheduler)

    jobs = {job['id']: job for job in scheduler.list_jobs()}
    assert JOB_ID in jobs
    assert jobs[JOB_ID]['name'] == 'Schema Intelligence Ranking Flush'


def test_trigger_states_its_timezone_explicitly(monkeypatch, settings_db):
    """Existing jobs inherit an unstated system-local timezone; this one says UTC."""
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler(timezone='America/New_York')
    register_all(_FakeApp(settings_db), scheduler)

    job = scheduler.get_job(JOB_ID)
    assert str(job.trigger.timezone) == RANKING_FLUSH_TIMEZONE == 'UTC'
    assert str(job.trigger.timezone) != str(scheduler.scheduler.timezone)


def test_configured_interval_reaches_the_trigger(monkeypatch, settings_db):
    monkeypatch.setenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', '2')
    scheduler = AppScheduler()
    register_all(_FakeApp(settings_db), scheduler)

    assert "hour='*/2'" in str(scheduler.get_job(JOB_ID).trigger)


def test_registering_twice_does_not_duplicate_the_job(monkeypatch, settings_db):
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler()
    app = _FakeApp(settings_db)

    register_all(app, scheduler)
    register_all(app, scheduler)

    assert [j['id'] for j in scheduler.list_jobs()].count(JOB_ID) == 1


# ─────────────────────────────────────────────
# The job itself
# ─────────────────────────────────────────────

def test_job_populates_property_ranking(settings_db):
    """Verified with a direct query, as the definition of done asks."""
    conn = sqlite3.connect(settings_db)
    try:
        log_query_usage(
            "MATCH (p:Project)-[:PI_OF]-(u:Person) "
            "RETURN p.cac_protocol, u.email",
            session_id='s1', sqlite_conn=conn,
        )
        log_query_usage(
            "MATCH (p:Project) RETURN p.cac_protocol",
            session_id='s2', sqlite_conn=conn,
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM property_ranking").fetchone()[0] == 0
    finally:
        conn.close()

    flush_property_rankings(settings_db)

    conn = sqlite3.connect(settings_db)
    try:
        rows = conn.execute(
            "SELECT label_name, property_name, query_count, session_count, rank "
            "FROM property_ranking ORDER BY rank DESC"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    # cac_protocol: 2 queries across 2 sessions -> 2*1.0 + 2*2.0
    assert rows[0] == ('Project', 'cac_protocol', 2, 2, 6.0)
    # email: 1 query in 1 session -> 1*1.0 + 1*2.0
    assert rows[1] == ('Person', 'email', 1, 1, 3.0)


def test_job_is_idempotent(settings_db):
    conn = sqlite3.connect(settings_db)
    try:
        log_query_usage("MATCH (p:Project) RETURN p.name",
                        session_id='s1', sqlite_conn=conn)
    finally:
        conn.close()

    flush_property_rankings(settings_db)
    flush_property_rankings(settings_db)

    conn = sqlite3.connect(settings_db)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM property_ranking").fetchone()[0]
    finally:
        conn.close()
    assert rows == 1


def test_job_swallows_and_logs_failures(caplog, tmp_path):
    """APScheduler discards exceptions, so a raising job fails invisibly."""
    missing = str(tmp_path / 'no_such_dir' / 'settings.db')

    with caplog.at_level('ERROR'):
        flush_property_rankings(missing)   # must not raise

    assert any('ranking flush failed' in r.message.lower()
               for r in caplog.records)


def test_job_opens_its_own_connection(settings_db):
    """It takes a path, not a connection — a handle would have crossed a fork."""
    import inspect

    params = list(inspect.signature(flush_property_rankings).parameters)
    assert params == ['settings_db_path']

    # And it leaves nothing open.
    flush_property_rankings(settings_db)
    conn = sqlite3.connect(settings_db)
    try:
        conn.execute('PRAGMA locking_mode')     # would contend on a held handle
    finally:
        conn.close()
