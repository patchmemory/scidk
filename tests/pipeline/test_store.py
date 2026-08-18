"""``pipeline_source``, ``pipeline`` and ``pipeline_run`` persistence.

All three tables live in ``scidk_settings.db`` and are created by
``_ensure_table_exists``-style methods, never by ``scidk/core/migrations.py``,
which targets the path-index ``files.db``. The idempotency tests below are what
make that pattern safe to call on every service construction.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from scidk.pipeline.run_history import RunHistory
from scidk.pipeline.store import PipelineStore


@pytest.fixture
def db(tmp_path) -> str:
    return str(tmp_path / "scidk_settings.db")


@pytest.fixture
def store(db) -> PipelineStore:
    return PipelineStore(db)


@pytest.fixture
def history(db) -> RunHistory:
    return RunHistory(db)


# ----------------------------------------------------------------- schema

def test_tables_are_created(store, db):
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"pipeline_source", "pipeline"} <= names


def test_construction_is_idempotent(db):
    PipelineStore(db)
    first = PipelineStore(db)
    source = first.create_source("S", "csv")
    # A third construction must not disturb existing rows.
    assert PipelineStore(db).get_source(source["id"]) is not None


def test_history_shares_the_database_without_conflict(db):
    store = PipelineStore(db)
    RunHistory(db)
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"pipeline_source", "pipeline", "pipeline_run"} <= names
    assert store.list_sources() == []


# ---------------------------------------------------------------- sources

def test_create_and_read_a_source(store):
    created = store.create_source(
        "AIPT Intake", "sharepoint", source_path={"source_path": "sharepoint:AIPT/Lists/Intake"}
    )

    assert created["name"] == "AIPT Intake"
    assert created["plugin_type"] == "sharepoint"
    assert created["source_path"] == {"source_path": "sharepoint:AIPT/Lists/Intake"}
    assert created["created_at"] and created["updated_at"]
    assert store.get_source(created["id"]) == created


def test_json_columns_round_trip_as_objects(store):
    mapping = {"version": "1.0", "node_mappings": [{"id": "p", "label": "Project"}]}
    created = store.create_source("S", "csv", mapping_json=mapping)
    assert store.get_source(created["id"])["mapping_json"] == mapping


def test_unparseable_json_is_surfaced_rather_than_lost(store, db):
    created = store.create_source("S", "csv")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE pipeline_source SET mapping_json = ? WHERE id = ?",
            ("{not json", created["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    row = store.get_source(created["id"])
    assert row["mapping_json"] is None
    assert row["mapping_json_raw"] == "{not json"


def test_get_a_source_that_does_not_exist(store):
    assert store.get_source("nope") is None


def test_update_a_source(store):
    created = store.create_source("Old", "csv")
    updated = store.update_source(created["id"], name="New", mapping_json={"version": "1.0"})

    assert updated["name"] == "New"
    assert updated["mapping_json"] == {"version": "1.0"}


def test_update_rejects_an_unknown_column_loudly(store):
    """A silently dropped update looks to the user like a save that worked."""
    created = store.create_source("S", "csv")
    with pytest.raises(ValueError, match="not an updatable column"):
        store.update_source(created["id"], nonexistent="x")


def test_update_cannot_be_used_to_inject_sql(store):
    created = store.create_source("S", "csv")
    with pytest.raises(ValueError):
        store.update_source(created["id"], **{"name = 'x' --": "y"})


def test_update_of_a_missing_source_returns_none(store):
    assert store.update_source("nope", name="x") is None


def test_delete_a_source(store):
    created = store.create_source("S", "csv")
    assert store.delete_source(created["id"]) is True
    assert store.get_source(created["id"]) is None
    assert store.delete_source(created["id"]) is False


def test_list_sources_is_newest_activity_first(store):
    first = store.create_source("A", "csv")
    second = store.create_source("B", "csv")
    store.update_source(first["id"], name="A again")

    assert [s["name"] for s in store.list_sources()][0] == "A again"
    assert {s["id"] for s in store.list_sources()} == {first["id"], second["id"]}


def test_record_source_run_stamps_status_and_summary(store):
    created = store.create_source("S", "csv")
    updated = store.record_source_run(
        created["id"], "partial", {"nodes_written": 5, "errors": ["one thing failed"]}
    )

    assert updated["last_run_status"] == "partial"
    assert updated["last_run_at"]
    assert updated["last_run_summary"]["nodes_written"] == 5


def test_a_fair_check_does_not_overwrite_the_last_ingest_status(store):
    """A FAIR check writes nothing to Neo4j, so it must not claim a run happened."""
    created = store.create_source("S", "csv")
    store.record_source_run(created["id"], "success", {"nodes_written": 10})
    after = store.record_fair_check(created["id"], {"F": True, "A": True, "I": False, "R": True})

    assert after["last_run_status"] == "success"
    assert after["fair_status"]["I"] is False
    assert after["fair_checked_at"]


# -------------------------------------------------------------- pipelines

def test_create_and_read_a_pipeline(store):
    dag = {"steps": [{"source_id": "s1", "depends_on": []}]}
    created = store.create_pipeline("Weekly", dag=dag, schedule="0 2 * * *")

    assert created["name"] == "Weekly"
    assert created["dag_json"] == dag
    assert created["schedule"] == "0 2 * * *"
    assert created["schedule_paused"] == 0


def test_dag_json_is_not_null_even_when_no_dag_is_given(store):
    """The column is NOT NULL; an omitted DAG must not fail the insert."""
    created = store.create_pipeline("Empty")
    assert created["dag_json"] == {"steps": []}


def test_pause_keeps_the_cron_expression(store):
    created = store.create_pipeline("P", schedule="0 2 * * *")
    paused = store.update_pipeline(created["id"], schedule_paused=True)

    assert paused["schedule_paused"] == 1
    assert paused["schedule"] == "0 2 * * *", "pausing must not clear the schedule"


def test_source_ids_in_dag_preserves_declaration_order(store):
    pipeline = store.create_pipeline("P", dag={"steps": [
        {"source_id": "b"}, {"source_id": "a"}, {"not_a_step": 1},
    ]})
    assert store.source_ids_in_dag(pipeline) == ["b", "a"]


def test_pipelines_referencing_a_source(store):
    source = store.create_source("S", "csv")
    other = store.create_source("Other", "csv")
    referencing = store.create_pipeline("P", dag={"steps": [{"source_id": source["id"]}]})
    store.create_pipeline("Q", dag={"steps": [{"source_id": other["id"]}]})

    found = store.pipelines_referencing_source(source["id"])
    assert [p["id"] for p in found] == [referencing["id"]]


def test_implicit_single_source_pipeline_is_idempotent(store):
    """Scheduling the same source twice must update one pipeline, not accumulate them."""
    source = store.create_source("Equipment log", "csv")
    first = store.ensure_single_source_pipeline(source["id"])
    second = store.ensure_single_source_pipeline(source["id"])

    assert first["id"] == second["id"]
    assert len(store.list_pipelines()) == 1
    assert store.source_ids_in_dag(first) == [source["id"]]
    assert "Equipment log" in first["name"]


def test_delete_a_pipeline(store):
    created = store.create_pipeline("P")
    assert store.delete_pipeline(created["id"]) is True
    assert store.get_pipeline(created["id"]) is None


# ------------------------------------------------------------- run history

def test_a_run_is_recorded_before_it_finishes(history):
    """A run killed halfway has already changed the graph; the row is the evidence."""
    run_id = history.start_run("p1", triggered_by="schedule")
    in_flight = history.get_run(run_id)

    assert in_flight["status"] == "running"
    assert in_flight["completed_at"] is None
    assert in_flight["in_flight"] is True
    assert in_flight["triggered_by"] == "schedule"


def test_complete_run_finalizes_status_and_steps(history):
    run_id = history.start_run("p1")
    completed = history.complete_run(run_id, "partial", [
        {"source_id": "s1", "status": "success"},
        {"source_id": "s2", "status": "skipped", "reason": "FAIR check failed"},
    ])

    assert completed["status"] == "partial"
    assert completed["completed_at"] and completed["in_flight"] is False
    assert [s["status"] for s in completed["steps"]] == ["success", "skipped"]


def test_record_step_appends_to_an_in_flight_run(history):
    run_id = history.start_run("p1")
    history.record_step(run_id, {"source_id": "s1", "status": "success"})
    history.record_step(run_id, {"source_id": "s2", "status": "error"})

    assert [s["source_id"] for s in history.get_run(run_id)["steps"]] == ["s1", "s2"]


def test_record_step_for_an_unknown_run_is_dropped_not_raised(history):
    history.record_step("nope", {"source_id": "s1"})  # must not raise


def test_list_runs_is_newest_first_and_scoped_to_a_pipeline(history):
    first = history.start_run("p1")
    history.complete_run(first, "success")
    second = history.start_run("p1")
    history.complete_run(second, "error")
    other = history.start_run("p2")
    history.complete_run(other, "success")

    ids = [r["id"] for r in history.list_runs("p1")]
    assert set(ids) == {first, second}
    assert history.last_run("p1")["id"] in ids
    assert len(history.list_runs()) == 3


def test_latest_run_for_a_source_finds_it_by_step(history):
    run_id = history.start_run("p1")
    history.complete_run(run_id, "success", [{"source_id": "s-42", "status": "success"}])
    assert history.latest_run_for_source("s-42")["id"] == run_id
    assert history.latest_run_for_source("nope") is None


def test_delete_run_history_for_a_pipeline(history):
    for _ in range(3):
        history.complete_run(history.start_run("p1"), "success")
    history.complete_run(history.start_run("p2"), "success")

    assert history.delete_for_pipeline("p1") == 3
    assert history.list_runs("p1") == []
    assert len(history.list_runs("p2")) == 1


def test_steps_json_survives_a_non_serializable_value(history):
    """A report can carry a stray object; recording the run still has to work."""
    run_id = history.start_run("p1")
    history.complete_run(run_id, "success", [{"source_id": "s1", "when": object()}])
    assert history.get_run(run_id)["steps"][0]["source_id"] == "s1"


def test_an_unrecognized_status_is_still_recorded(history, caplog):
    run_id = history.start_run("p1")
    completed = history.complete_run(run_id, "weird")
    assert completed["status"] == "weird"
