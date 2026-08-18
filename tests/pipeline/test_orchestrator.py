"""DAG ordering, source runs, and pipeline runs.

The behaviour Cycle 3B Task F is specific about, and which is asserted here:
sources that fail their FAIR check become recorded *skipped* steps and the rest
of the DAG still runs, and ``'partial'`` is recorded as itself rather than
rounded to success or failure.
"""
from __future__ import annotations

import pytest

from scidk.pipeline.orchestrator import (
    build_runner,
    run_pipeline,
    run_source,
    source_config_of,
    topological_order,
)
from scidk.pipeline.plugin_registry import PluginNotAvailable
from scidk.pipeline.run_history import RunHistory
from scidk.pipeline.store import PipelineStore

MAPPING = {
    "version": "1.0",
    "node_mappings": [
        {
            "id": "asset",
            "label": "Asset",
            "key_property": "asset_id",
            "properties": [
                {"name": "asset_id", "column": "Asset ID"},
                {"name": "name", "column": "Name"},
            ],
        }
    ],
}


class FakeWriter:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def write_declared_nodes(self, nodes, relationships):
        self.calls += 1
        if self.fail:
            return {"written_nodes": 0, "written_relationships": 0,
                    "errors": ["Neo.ClientError: rejected"]}
        return {"written_nodes": len(nodes),
                "written_relationships": len(relationships), "errors": []}


@pytest.fixture
def db(tmp_path) -> str:
    return str(tmp_path / "scidk_settings.db")


@pytest.fixture
def store(db) -> PipelineStore:
    return PipelineStore(db)


@pytest.fixture
def history(db) -> RunHistory:
    return RunHistory(db)


@pytest.fixture
def csv_source(tmp_path, store):
    path = tmp_path / "equipment.csv"
    path.write_text("Asset ID,Name\nA-1,Microscope\nA-2,Centrifuge\n", encoding="utf-8")
    return store.create_source(
        "Equipment log", "csv",
        source_path={"source_path": str(path)},
        mapping_json=MAPPING,
    )


# ------------------------------------------------------------ DAG ordering

def test_dependencies_precede_their_dependents():
    order, problems = topological_order([
        {"source_id": "c", "depends_on": ["b"]},
        {"source_id": "a", "depends_on": []},
        {"source_id": "b", "depends_on": ["a"]},
    ])
    assert order == ["a", "b", "c"]
    assert problems == []


def test_independent_steps_keep_declaration_order():
    order, problems = topological_order([{"source_id": "b"}, {"source_id": "a"}])
    assert order == ["b", "a"]
    assert problems == []


def test_a_cycle_is_reported_and_its_members_are_not_run():
    """Guessing an order would write to the graph in a sequence nobody chose."""
    order, problems = topological_order([
        {"source_id": "a", "depends_on": ["b"]},
        {"source_id": "b", "depends_on": ["a"]},
    ])
    assert order == []
    assert any("cycle" in p for p in problems)


def test_a_partial_cycle_still_runs_the_steps_outside_it():
    order, problems = topological_order([
        {"source_id": "ok", "depends_on": []},
        {"source_id": "a", "depends_on": ["b"]},
        {"source_id": "b", "depends_on": ["a"]},
    ])
    assert order == ["ok"]
    assert any("cycle" in p for p in problems)


def test_a_dependency_outside_the_dag_is_reported_and_ignored():
    order, problems = topological_order([{"source_id": "a", "depends_on": ["elsewhere"]}])
    assert order == ["a"]
    assert any("elsewhere" in p for p in problems)


def test_a_duplicate_source_in_the_dag_is_reported():
    order, problems = topological_order([{"source_id": "a"}, {"source_id": "a"}])
    assert order == ["a"]
    assert any("more than once" in p for p in problems)


def test_a_malformed_step_is_reported():
    _order, problems = topological_order([{"depends_on": []}, "not a dict"])
    assert len(problems) == 2


def test_an_empty_dag_orders_to_nothing():
    assert topological_order([]) == ([], [])


# --------------------------------------------------------- source config

def test_source_config_accepts_a_config_object():
    assert source_config_of({"source_path": {"source_path": "x", "sheet": "S"}}) == {
        "source_path": "x", "sheet": "S"
    }


def test_source_config_accepts_a_bare_string_for_a_hand_written_row():
    assert source_config_of({"source_path": "remote:Site/List"}) == {
        "source_path": "remote:Site/List"
    }


def test_source_config_of_an_unconfigured_source_is_empty():
    assert source_config_of({}) == {}


# ------------------------------------------------------------ build_runner

def test_a_source_with_no_mapping_config_cannot_be_built(store):
    source = store.create_source("S", "csv", source_path={"source_path": "/x.csv"})
    with pytest.raises(ValueError, match="no mapping config"):
        build_runner(source)


def test_a_plugin_type_nothing_implements_is_named_plainly(store):
    """ilab_importer registers a UI template but has no DataSourcePlugin."""
    source = store.create_source("S", "ilab_table_loader", mapping_json=MAPPING)
    with pytest.raises(PluginNotAvailable, match="does not implement"):
        build_runner(source)


def test_table_loader_is_served_by_the_builtin_reader(tmp_path, store):
    """The picker's "Table Loader -> CSV" has to actually run, not fail at save."""
    path = tmp_path / "x.csv"
    path.write_text("Asset ID,Name\nA-1,X\n", encoding="utf-8")
    source = store.create_source(
        "S", "table_loader", source_path={"source_path": str(path)}, mapping_json=MAPPING
    )
    report = build_runner(source, writer=FakeWriter()).preflight()
    assert report.fair_ok is True


def test_an_unknown_plugin_type_lists_what_is_known(store):
    source = store.create_source("S", "no_such_plugin", mapping_json=MAPPING)
    with pytest.raises(PluginNotAvailable, match="Known types"):
        build_runner(source)


def test_base_dir_is_applied_only_to_an_uploaded_source(tmp_path, store):
    outside = tmp_path / "outside.csv"
    outside.write_text("Asset ID,Name\nA-1,X\n", encoding="utf-8")
    uploads = str(tmp_path / "uploads")

    uploaded = store.create_source(
        "Uploaded", "csv",
        source_path={"source_path": str(outside), "upload_name": "outside.csv"},
        mapping_json=MAPPING,
    )
    report = build_runner(uploaded, writer=FakeWriter(), upload_dir=uploads).preflight()
    assert report.fair["F"] is False, "an uploaded source is confined to the upload dir"

    configured = store.create_source(
        "Admin configured", "csv",
        source_path={"source_path": str(outside)},
        mapping_json=MAPPING,
    )
    report = build_runner(configured, writer=FakeWriter(), upload_dir=uploads).preflight()
    assert report.fair["F"] is True, "a path from a setting is trusted like any other setting"


# -------------------------------------------------------------- run_source

def test_run_source_writes_and_stamps_the_source_record(store, csv_source):
    writer = FakeWriter()
    report = run_source(csv_source["id"], store, writer=writer)

    assert report.status == "success"
    assert report.nodes_written == 2
    stored = store.get_source(csv_source["id"])
    assert stored["last_run_status"] == "success"
    assert stored["last_run_at"]
    assert stored["last_run_summary"]["nodes_written"] == 2


def test_run_source_records_a_failure_on_the_source_record(store, csv_source):
    report = run_source(csv_source["id"], store, writer=FakeWriter(fail=True))

    assert report.status == "error"
    assert store.get_source(csv_source["id"])["last_run_status"] == "error"


def test_a_missing_source_is_reported_not_raised(store):
    report = run_source("nope", store, writer=FakeWriter())
    assert report.status == "error"
    assert any("does not exist" in e for e in report.errors)


def test_a_source_with_no_mapping_records_an_error_run(store):
    source = store.create_source("S", "csv", source_path={"source_path": "/x.csv"})
    report = run_source(source["id"], store, writer=FakeWriter())

    assert report.status == "error"
    assert store.get_source(source["id"])["last_run_status"] == "error"
    assert any("no mapping config" in e for e in report.errors)


def test_a_dry_run_does_not_stamp_the_source_record(store, csv_source):
    report = run_source(csv_source["id"], store, dry_run=True)
    assert report.nodes_declared == 2 and report.nodes_written == 0
    assert store.get_source(csv_source["id"])["last_run_status"] is None


# ------------------------------------------------------------ run_pipeline

def test_a_pipeline_run_executes_its_sources_and_records_the_run(store, history, csv_source):
    pipeline = store.create_pipeline(
        "Nightly", dag={"steps": [{"source_id": csv_source["id"], "depends_on": []}]}
    )
    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())

    assert result["status"] == "success"
    assert [s["source_id"] for s in result["steps"]] == [csv_source["id"]]
    assert result["steps"][0]["fair"] == {"F": True, "A": True, "I": True, "R": True}

    recorded = history.get_run(result["run_id"])
    assert recorded["status"] == "success"
    assert recorded["in_flight"] is False
    assert recorded["triggered_by"] == "manual"
    assert store.get_pipeline(pipeline["id"])["last_run_status"] == "success"


def test_sources_run_in_dag_order(tmp_path, store, history):
    order = []

    def make(name):
        path = tmp_path / f"{name}.csv"
        path.write_text("Asset ID,Name\nA-1,X\n", encoding="utf-8")
        return store.create_source(
            name, "csv", source_path={"source_path": str(path)}, mapping_json=MAPPING
        )

    first, second = make("first"), make("second")
    pipeline = store.create_pipeline("P", dag={"steps": [
        {"source_id": second["id"], "depends_on": [first["id"]]},
        {"source_id": first["id"], "depends_on": []},
    ]})

    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())
    assert [s["source_name"] for s in result["steps"]] == ["first", "second"]


def test_a_fair_failure_is_a_skipped_step_and_the_rest_still_run(tmp_path, store, history):
    """One broken source must not stop the nightly refresh of the others."""
    good_path = tmp_path / "good.csv"
    good_path.write_text("Asset ID,Name\nA-1,X\n", encoding="utf-8")
    good = store.create_source(
        "good", "csv", source_path={"source_path": str(good_path)}, mapping_json=MAPPING
    )
    broken = store.create_source(
        "broken", "csv",
        source_path={"source_path": str(tmp_path / "missing.csv")},
        mapping_json=MAPPING,
    )
    pipeline = store.create_pipeline("P", dag={"steps": [
        {"source_id": broken["id"]}, {"source_id": good["id"]},
    ]})

    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())

    by_name = {s["source_name"]: s for s in result["steps"]}
    assert by_name["broken"]["status"] == "skipped"
    assert "FAIR check failed" in by_name["broken"]["reason"]
    assert by_name["good"]["status"] == "success"
    assert result["status"] == "partial", "partial is recorded as itself"


def test_a_pipeline_whose_every_step_fails_is_an_error(store, history):
    broken = store.create_source("broken", "csv", source_path={"source_path": "/nope.csv"},
                                 mapping_json=MAPPING)
    pipeline = store.create_pipeline("P", dag={"steps": [{"source_id": broken["id"]}]})

    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())
    assert result["status"] == "error"


def test_an_empty_pipeline_is_an_error_rather_than_a_vacuous_success(store, history):
    pipeline = store.create_pipeline("Empty")
    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())
    assert result["status"] == "error" and result["steps"] == []


def test_a_missing_pipeline_is_reported_without_recording_a_run(store, history):
    result = run_pipeline("nope", store, history, writer=FakeWriter())
    assert result["status"] == "error" and result["run_id"] is None
    assert history.list_runs() == []


def test_a_dag_cycle_is_reported_on_the_run(store, history):
    a = store.create_source("a", "csv", mapping_json=MAPPING)
    b = store.create_source("b", "csv", mapping_json=MAPPING)
    pipeline = store.create_pipeline("P", dag={"steps": [
        {"source_id": a["id"], "depends_on": [b["id"]]},
        {"source_id": b["id"], "depends_on": [a["id"]]},
    ]})

    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())
    assert result["status"] == "error"
    assert any("cycle" in e for e in result["errors"])


def test_each_step_is_recorded_as_it_finishes_not_only_at_the_end(store, history, csv_source):
    """So a run killed mid-DAG still shows which sources had already been written."""
    pipeline = store.create_pipeline("P", dag={"steps": [{"source_id": csv_source["id"]}]})
    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())

    steps = history.get_run(result["run_id"])["steps"]
    assert len(steps) == 1 and steps[0]["source_id"] == csv_source["id"]


def test_triggered_by_is_recorded(store, history, csv_source):
    pipeline = store.create_pipeline("P", dag={"steps": [{"source_id": csv_source["id"]}]})
    result = run_pipeline(
        pipeline["id"], store, history, triggered_by="schedule", writer=FakeWriter()
    )
    assert history.get_run(result["run_id"])["triggered_by"] == "schedule"


def test_a_source_that_raises_unexpectedly_does_not_end_the_dag(
    monkeypatch, tmp_path, store, history
):
    good_path = tmp_path / "good.csv"
    good_path.write_text("Asset ID,Name\nA-1,X\n", encoding="utf-8")
    boom = store.create_source("boom", "csv", source_path={"source_path": str(good_path)},
                               mapping_json=MAPPING)
    good = store.create_source("good", "csv", source_path={"source_path": str(good_path)},
                               mapping_json=MAPPING)
    pipeline = store.create_pipeline("P", dag={"steps": [
        {"source_id": boom["id"]}, {"source_id": good["id"]},
    ]})

    from scidk.pipeline import orchestrator

    real = orchestrator.run_source

    def explode(source_id, *args, **kwargs):
        if source_id == boom["id"]:
            raise RuntimeError("something unforeseen")
        return real(source_id, *args, **kwargs)

    monkeypatch.setattr(orchestrator, "run_source", explode)
    result = run_pipeline(pipeline["id"], store, history, writer=FakeWriter())

    by_name = {s["source_name"]: s["status"] for s in result["steps"]}
    assert by_name == {"boom": "error", "good": "success"}
    assert result["status"] == "partial"
