"""
Tests for scheduled job registration.

Cycle 1, Task D (J7): flush_rankings() had zero callers, so property rankings
were never refreshed automatically.

Cycle 8, Task A: concept-graph weight decay moved here from BackupScheduler,
which registered it only when create_app() had already built a working driver and
then ran the job against that same driver across a fork.
"""
import sqlite3

import pytest

from scidk.core.app_scheduler import AppScheduler
from scidk.core.scheduled_jobs import (
    CONCEPT_DECAY_HOUR,
    CONCEPT_DECAY_TIMEZONE,
    DEFAULT_CONCEPT_WEIGHT_HALFLIFE_DAYS,
    DEFAULT_RANKING_FLUSH_INTERVAL_HOURS,
    RANKING_FLUSH_TIMEZONE,
    _concept_weight_halflife_days,
    _ranking_flush_interval_hours,
    concept_graph_weight_decay,
    flush_property_rankings,
    register_all,
)
from scidk.services.schema_intelligence import (
    ensure_schema_intelligence_tables,
    log_query_usage,
)

JOB_ID = 'schema_intelligence_ranking_flush'
DECAY_JOB_ID = 'concept_graph_weight_decay'


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


# ─────────────────────────────────────────────
# Concept Graph weight decay (Cycle 8, Task A)
# ─────────────────────────────────────────────

class _FakeConceptSession:
    """Returns one stale SATISFIES edge, then records the update."""

    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._driver.calls.append((query, params))
        self._driver.result = self._driver.edges
        return self

    def data(self):
        return self._driver.result


class _FakeConceptDriver:
    def __init__(self, edges=()):
        self.edges = list(edges)
        self.result = []
        self.calls = []
        self.closed = False

    def session(self):
        return _FakeConceptSession(self)

    def close(self):
        self.closed = True

    @property
    def weight_updates(self):
        """The (rel_id, new_weight) pairs written by the decay pass."""
        return [
            (params['rel_id'], params['new_weight'])
            for query, params in self.calls
            if 'SET r.weight' in query
        ]


def _stale_edge(days_old, weight):
    from datetime import datetime, timedelta

    return {
        'rel_id': 7,
        'weight': weight,
        'last_updated': (datetime.utcnow() - timedelta(days=days_old)).isoformat(),
        'intent': 'data_lookup',
        'tool': 'query_knowledge_graph',
    }


@pytest.fixture()
def concept_env(monkeypatch):
    """Concept graph enabled, half-life unset — the default deployment."""
    monkeypatch.setenv('SCIDK_CONCEPT_GRAPH_ENABLED', '1')
    monkeypatch.delenv('SCIDK_CONCEPT_WEIGHT_HALFLIFE_DAYS', raising=False)


def _install_driver(monkeypatch, driver):
    """Make the job's ``get_concept_driver()`` hand back ``driver``."""
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'get_concept_driver', lambda app=None: driver)
    return driver


# --- half-life configuration ---

def test_halflife_defaults_to_ninety_days(concept_env):
    assert _concept_weight_halflife_days() == 90
    assert DEFAULT_CONCEPT_WEIGHT_HALFLIFE_DAYS == 90


def test_halflife_is_configurable(monkeypatch):
    monkeypatch.setenv('SCIDK_CONCEPT_WEIGHT_HALFLIFE_DAYS', '30')
    assert _concept_weight_halflife_days() == 30


@pytest.mark.parametrize('value', ['nonsense', '', '0', '-5', '45.5'])
def test_unusable_halflife_falls_back_to_the_default(monkeypatch, value):
    """``apply_weight_decay`` divides by this — 0 raises, negatives invert decay."""
    monkeypatch.setenv('SCIDK_CONCEPT_WEIGHT_HALFLIFE_DAYS', value)
    assert _concept_weight_halflife_days() == DEFAULT_CONCEPT_WEIGHT_HALFLIFE_DAYS


# --- registration ---

def test_weight_decay_is_registered(concept_env, monkeypatch, settings_db):
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler()
    register_all(_FakeApp(settings_db), scheduler)

    jobs = {job['id']: job for job in scheduler.list_jobs()}
    assert DECAY_JOB_ID in jobs
    assert jobs[DECAY_JOB_ID]['name'] == 'Concept Graph Weight Decay'


def test_weight_decay_fires_at_three_in_a_stated_timezone(
        concept_env, monkeypatch, settings_db):
    """The BackupScheduler registration inherited an unstated system-local tz."""
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler(timezone='America/New_York')
    register_all(_FakeApp(settings_db), scheduler)

    job = scheduler.get_job(DECAY_JOB_ID)
    assert str(job.trigger.timezone) == CONCEPT_DECAY_TIMEZONE == 'UTC'
    assert f"hour='{CONCEPT_DECAY_HOUR}'" in str(job.trigger)
    assert "minute='0'" in str(job.trigger)


def test_registering_twice_does_not_duplicate_the_decay_job(
        concept_env, monkeypatch, settings_db):
    monkeypatch.delenv('SCIDK_RANKING_FLUSH_INTERVAL_HOURS', raising=False)
    scheduler = AppScheduler()
    app = _FakeApp(settings_db)

    register_all(app, scheduler)
    register_all(app, scheduler)

    assert [j['id'] for j in scheduler.list_jobs()].count(DECAY_JOB_ID) == 1


def test_decay_is_registered_even_when_the_graph_is_down(
        concept_env, monkeypatch, settings_db):
    """The old path skipped registration when create_app() got no driver, so a
    concept graph that came up later went undecayed until the next restart."""
    _install_driver(monkeypatch, None)
    scheduler = AppScheduler()
    register_all(_FakeApp(settings_db), scheduler)

    assert scheduler.get_job(DECAY_JOB_ID) is not None


def test_backup_scheduler_no_longer_owns_the_decay_job():
    """The concept_driver argument is gone, not just unused."""
    import inspect

    from scidk.core.backup_scheduler import BackupScheduler

    assert list(inspect.signature(BackupScheduler.start).parameters) == ['self']
    assert not hasattr(BackupScheduler, '_run_weight_decay')


# --- the job itself ---

def test_the_registered_job_decays_a_stale_high_weight_edge(
        concept_env, monkeypatch, settings_db):
    """Runs what the scheduler holds, not just the function by name.

    A 180-day-old edge at 0.95 is two half-lives stale, so it lands a quarter of
    the way from neutral: 0.5 + 0.45 * 0.25.
    """
    driver = _install_driver(monkeypatch, _FakeConceptDriver([_stale_edge(180, 0.95)]))

    scheduler = AppScheduler()
    register_all(_FakeApp(settings_db), scheduler)
    scheduler.get_job(DECAY_JOB_ID).func()

    assert driver.weight_updates == [(7, pytest.approx(0.6125, abs=1e-3))]
    assert driver.closed


def test_fresh_edges_are_left_alone(concept_env, monkeypatch):
    driver = _install_driver(monkeypatch, _FakeConceptDriver([_stale_edge(2, 0.95)]))

    concept_graph_weight_decay()

    assert driver.weight_updates == []


def test_the_configured_halflife_reaches_the_formula(monkeypatch):
    """A 30-day half-life decays a 90-day-old edge three half-lives, not one."""
    monkeypatch.setenv('SCIDK_CONCEPT_GRAPH_ENABLED', '1')
    monkeypatch.setenv('SCIDK_CONCEPT_WEIGHT_HALFLIFE_DAYS', '30')
    driver = _install_driver(monkeypatch, _FakeConceptDriver([_stale_edge(90, 0.9)]))

    concept_graph_weight_decay()

    # 0.5 + 0.4 * 0.5**3
    assert driver.weight_updates == [(7, pytest.approx(0.55, abs=1e-3))]


def test_job_closes_the_driver_it_opened(concept_env, monkeypatch):
    """It opens its own — capturing create_app()'s would cross a fork."""
    driver = _install_driver(monkeypatch, _FakeConceptDriver([_stale_edge(180, 0.95)]))

    concept_graph_weight_decay()

    assert driver.closed


def test_job_closes_the_driver_even_when_decay_fails(concept_env, monkeypatch):
    from scidk.services import concept_graph_service as cgs

    driver = _install_driver(monkeypatch, _FakeConceptDriver())
    monkeypatch.setattr(cgs, 'apply_weight_decay',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))

    concept_graph_weight_decay()     # must not raise

    assert driver.closed


def test_job_logs_and_returns_when_the_graph_is_unreachable(
        concept_env, monkeypatch, caplog):
    _install_driver(monkeypatch, None)

    with caplog.at_level('WARNING'):
        concept_graph_weight_decay()

    assert any('concept graph unreachable' in r.message.lower()
               for r in caplog.records)


def test_job_skips_when_the_concept_graph_is_disabled(monkeypatch):
    monkeypatch.setenv('SCIDK_CONCEPT_GRAPH_ENABLED', '0')
    driver = _install_driver(monkeypatch, _FakeConceptDriver([_stale_edge(180, 0.95)]))

    concept_graph_weight_decay()

    assert driver.calls == []


def test_job_swallows_and_logs_failures(concept_env, monkeypatch, caplog):
    """APScheduler discards exceptions, so a raising job fails invisibly."""
    from scidk.services import concept_graph_service as cgs

    def explode(app=None):
        raise RuntimeError('no route to host')

    monkeypatch.setattr(cgs, 'get_concept_driver', explode)

    with caplog.at_level('ERROR'):
        concept_graph_weight_decay()     # must not raise

    assert any('weight decay failed' in r.message.lower()
               for r in caplog.records)


def test_job_takes_no_arguments(concept_env):
    """Nothing to capture means nothing that can cross a fork."""
    import inspect

    assert list(inspect.signature(concept_graph_weight_decay).parameters) == []


def test_per_edge_errors_are_logged_not_swallowed(concept_env, monkeypatch, caplog):
    """apply_weight_decay returns errors rather than raising; the job must say so."""
    from scidk.services import concept_graph_service as cgs

    _install_driver(monkeypatch, _FakeConceptDriver())
    monkeypatch.setattr(cgs, 'apply_weight_decay', lambda *a, **k: {
        'edges_updated': 0, 'edges_skipped': 1, 'half_life_days': 90,
        'errors': ['Update error: data_lookup→query_knowledge_graph'],
    })

    with caplog.at_level('ERROR'):
        concept_graph_weight_decay()

    assert any('Update error' in r.message for r in caplog.records)
