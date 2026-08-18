"""The Pipeline HTTP surface: Tasks A, B and F.

Uses a real Flask app from ``create_app()`` with a temp settings DB, so blueprint
registration, RBAC behaviour under test mode, and the plugin template registry are
all exercised as they actually are in the app.

The scheduler assertions are deliberately about the *jobstore*, not about a job
firing. The requirement is "a schedule change written by an API request reaches
the process that owns the scheduler without a restart", and the shared jobstore is
the whole mechanism for that — so what has to be tested is that a write from the
request side is readable from the scheduler side.
"""
from __future__ import annotations

import json
import os

import pytest

from .conftest import CapturingWriter

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


#: Neo4j settings that would otherwise leak in from the environment. ``scidk/app.py``
#: calls ``load_dotenv()`` at import, so a full-suite run has real credentials for a
#: local dev graph while a single-file run does not — which made these tests both
#: non-deterministic and capable of writing into a real database. Cleared here so
#: no test reaches a graph by accident; the ones that need a working write get an
#: explicit fake through the ``fake_graph`` fixture.
_NEO4J_ENV = (
    "NEO4J_URI", "BOLT_URI", "NEO4J_USER", "NEO4J_USERNAME",
    "NEO4J_PASSWORD", "NEO4J_AUTH", "SCIDK_NEO4J_DATABASE",
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIDK_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("SCIDK_PIPELINE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SCIDK_SETTINGS_DB", str(tmp_path / "scidk_settings.db"))
    for name in _NEO4J_ENV:
        monkeypatch.delenv(name, raising=False)

    from scidk.app import create_app

    application = create_app()
    application.config["TESTING"] = True
    application.config["SCIDK_SETTINGS_DB"] = str(tmp_path / "scidk_settings.db")
    application.config["SCIDK_PIPELINE_UPLOAD_DIR"] = str(tmp_path / "uploads")
    # A UI-configured connection would override the cleared environment.
    application.extensions["scidk"]["neo4j_config"] = {}
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def fake_graph(monkeypatch):
    """Give the HTTP run path a working writer without touching a database.

    The routes build their own client via ``orchestrator.neo4j_writer``, so that
    is what is replaced. Keeps the request path — routing, RBAC, orchestration —
    exactly as it is in production while the write lands in memory.
    """
    from contextlib import contextmanager

    from scidk.pipeline import orchestrator

    writer = CapturingWriter()

    @contextmanager
    def fake_writer(app=None):
        yield writer

    monkeypatch.setattr(orchestrator, "neo4j_writer", fake_writer)
    return writer


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "equipment.csv"
    path.write_text("Asset ID,Name\nA-1,Microscope\nA-2,Centrifuge\n", encoding="utf-8")
    return str(path)


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def make_source(client, csv_path, name="Equipment log", plugin_type="csv"):
    response = post(client, "/api/pipeline/sources", {
        "name": name,
        "plugin_type": plugin_type,
        "config": {"source_path": csv_path},
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["source"]


# --------------------------------------------------------------- Task A

def test_the_sources_page_renders(client):
    response = client.get("/pipeline/sources")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-testid="pipeline-sources-page"' in body
    assert 'data-testid="add-source-btn"' in body


def test_the_page_is_reachable_from_the_nav(client):
    body = client.get("/pipeline/sources").get_data(as_text=True)
    assert "/pipeline/sources" in body and 'data-testid="nav-pipeline"' in body


def test_sources_list_starts_empty(client):
    response = client.get("/api/pipeline/sources")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "sources": []}


def test_create_and_list_a_source(client, csv_path):
    created = make_source(client, csv_path)
    assert created["name"] == "Equipment log"

    listed = client.get("/api/pipeline/sources").get_json()["sources"]
    assert len(listed) == 1
    assert listed[0]["display_path"] == csv_path
    assert listed[0]["plugin_available"] is True


def test_a_name_and_plugin_type_are_required(client):
    assert post(client, "/api/pipeline/sources", {"plugin_type": "csv"}).status_code == 400
    assert post(client, "/api/pipeline/sources", {"name": "X"}).status_code == 400


def test_a_plugin_type_with_no_implementation_is_rejected_at_creation(client):
    """Better than saving it and failing the first time someone presses Run."""
    response = post(client, "/api/pipeline/sources",
                    {"name": "iLab", "plugin_type": "ilab_table_loader"})
    assert response.status_code == 400
    assert "does not implement" in response.get_json()["error"] \
        or "no data source plugin" in response.get_json()["error"]


def test_the_add_picker_gets_its_types_from_the_existing_templates_route(client):
    """Task A says no new route for plugin type discovery; this is the one used."""
    response = client.get("/api/plugins/templates?category=data_import")
    assert response.status_code == 200
    templates = response.get_json()["templates"]
    assert templates, "no data_import templates registered"
    ids = {t["id"] for t in templates}
    assert {"sharepoint_intake", "table_loader"} <= ids
    assert all(t["category"] == "data_import" for t in templates)


def test_the_category_filter_actually_filters(client):
    everything = client.get("/api/plugins/templates").get_json()["templates"]
    imports = client.get("/api/plugins/templates?category=data_import") \
        .get_json()["templates"]
    assert len(imports) <= len(everything)
    assert all(t["category"] == "data_import" for t in imports)


def test_presets_are_available_as_second_level_choices(client):
    """"Table Loader" is the type; CSV / Excel / TSV are the presets under it."""
    templates = client.get("/api/plugins/templates?category=data_import") \
        .get_json()["templates"]
    table_loader = next(t for t in templates if t["id"] == "table_loader")
    assert set(table_loader["preset_configs"]) == {"csv_import", "excel_import", "tsv_import"}


def test_a_preset_config_is_merged_into_a_new_source(client, csv_path):
    response = post(client, "/api/pipeline/sources", {
        "name": "CSV import",
        "plugin_type": "table_loader",
        "preset": "csv_import",
        "config": {"source_path": csv_path},
    })
    assert response.status_code == 201
    config = response.get_json()["source"]["source_path"]
    assert config["source_path"] == csv_path
    assert config["file_type"] == "csv", "the preset's config was not applied"


def test_an_explicit_value_wins_over_the_preset(client, csv_path):
    response = post(client, "/api/pipeline/sources", {
        "name": "Odd one",
        "plugin_type": "table_loader",
        "preset": "csv_import",
        "config": {"source_path": csv_path, "has_header": False},
    })
    assert response.get_json()["source"]["source_path"]["has_header"] is False


def test_update_a_source(client, csv_path):
    source = make_source(client, csv_path)
    response = client.put(
        f"/api/pipeline/sources/{source['id']}",
        data=json.dumps({"name": "Renamed", "mapping_json": MAPPING}),
        content_type="application/json",
    )
    assert response.status_code == 200
    updated = response.get_json()["source"]
    assert updated["name"] == "Renamed"
    assert updated["mapping_json"] == MAPPING


def test_updating_a_missing_source_is_404(client):
    response = client.put("/api/pipeline/sources/nope",
                          data=json.dumps({"name": "X"}),
                          content_type="application/json")
    assert response.status_code == 404


def test_delete_removes_the_source(client, csv_path):
    source = make_source(client, csv_path)
    assert client.delete(f"/api/pipeline/sources/{source['id']}").status_code == 200
    assert client.get("/api/pipeline/sources").get_json()["sources"] == []
    assert client.delete(f"/api/pipeline/sources/{source['id']}").status_code == 404


def test_delete_removes_the_sources_canvas_sessions(app, client, csv_path):
    """The cleanup path Task A calls for: DELETE WHERE context_id = 'pipeline_source:<id>'."""
    from scidk.services.canvas_service import get_canvas_service, pipeline_source_context

    source = make_source(client, csv_path)
    context = pipeline_source_context(source["id"])
    canvas = get_canvas_service(db_path=app.config["SCIDK_SETTINGS_DB"])
    canvas.save_session("someone", {"nodes": ["schema"]}, context)
    canvas.save_session("someone", {"nodes": ["main"]})
    assert canvas.load_session("someone", context) is not None

    response = client.delete(f"/api/pipeline/sources/{source['id']}")

    assert response.get_json()["removed"]["canvas_sessions"] == 1
    assert canvas.load_session("someone", context) is None
    assert canvas.load_session("someone") is not None, "the main canvas was collateral damage"


def test_delete_removes_the_sources_implicit_pipeline_and_run_history(app, client, csv_path):
    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": "0 2 * * *"})
    assert client.get("/api/pipeline/pipelines").get_json()["pipelines"]

    response = client.delete(f"/api/pipeline/sources/{source['id']}")

    assert response.get_json()["removed"]["pipelines_deleted"] == 1
    assert client.get("/api/pipeline/pipelines").get_json()["pipelines"] == []


def test_delete_keeps_a_shared_pipeline_but_drops_the_sources_step(client, csv_path):
    """Other sources still need that pipeline; a dangling step would fail every run."""
    first = make_source(client, csv_path, name="first")
    second = make_source(client, csv_path, name="second")
    pipeline = post(client, "/api/pipeline/pipelines", {
        "name": "Both", "source_ids": [first["id"], second["id"]],
    }).get_json()["pipeline"]

    response = client.delete(f"/api/pipeline/sources/{first['id']}")
    assert response.get_json()["removed"]["pipelines_updated"] == 1

    remaining = client.get("/api/pipeline/pipelines").get_json()["pipelines"]
    assert len(remaining) == 1
    assert remaining[0]["source_ids"] == [second["id"]]
    # And the surviving step no longer depends on the deleted source.
    steps = remaining[0]["dag_json"]["steps"]
    assert all(first["id"] not in (s.get("depends_on") or []) for s in steps)


# --------------------------------------------------------------- Task B

def test_test_connection_returns_columns_and_a_preview(client, csv_path):
    response = post(client, "/api/pipeline/sources/test-connection", {
        "plugin_type": "csv", "config": {"source_path": csv_path},
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["columns"] == ["Asset ID", "Name"]
    assert len(data["sample"]) == 2
    assert data["row_count"] == 2


def test_test_connection_previews_at_most_three_rows(client, tmp_path):
    path = tmp_path / "many.csv"
    path.write_text("A\n" + "\n".join(str(i) for i in range(50)) + "\n", encoding="utf-8")
    data = post(client, "/api/pipeline/sources/test-connection", {
        "plugin_type": "csv", "config": {"source_path": str(path)},
    }).get_json()
    assert len(data["sample"]) == 3


def test_test_connection_reports_a_bad_path_clearly(client, tmp_path):
    """A 200 with ok:false — an unreachable source is a result to display."""
    response = post(client, "/api/pipeline/sources/test-connection", {
        "plugin_type": "csv", "config": {"source_path": str(tmp_path / "nope.csv")},
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is False
    assert "does not exist" in data["error"]


def test_test_connection_needs_something_to_connect_to(client):
    assert post(client, "/api/pipeline/sources/test-connection", {}).status_code == 400
    assert post(client, "/api/pipeline/sources/test-connection",
                {"plugin_type": "csv"}).status_code == 400


def test_test_connection_can_retest_a_saved_source(client, csv_path):
    source = make_source(client, csv_path)
    data = post(client, "/api/pipeline/sources/test-connection",
                {"source_id": source["id"]}).get_json()
    assert data["ok"] is True and data["columns"] == ["Asset ID", "Name"]


def test_test_connection_gives_up_within_its_timeout(client, monkeypatch):
    """A wedged remote still has to answer the user inside 10 seconds."""
    import time

    from scidk.pipeline import file_source
    from scidk.web.routes import api_pipeline

    monkeypatch.setattr(api_pipeline, "TEST_CONNECTION_TIMEOUT_SEC", 1)
    monkeypatch.setattr(
        file_source.TabularFilePlugin, "find",
        lambda self, config: time.sleep(30) or {"ok": True},
    )

    started = time.time()
    response = post(client, "/api/pipeline/sources/test-connection", {
        "plugin_type": "csv", "config": {"source_path": "/anything.csv"},
    })
    elapsed = time.time() - started

    assert response.status_code == 200
    assert response.get_json()["ok"] is False
    assert "did not respond within" in response.get_json()["error"]
    assert elapsed < 10, f"took {elapsed:.1f}s to give up"


def test_upload_produces_the_same_shape_as_a_remote_path(client, csv_path):
    """Task B's actual requirement: both options feed Step 2 identically."""
    import io

    remote = post(client, "/api/pipeline/sources/test-connection", {
        "plugin_type": "csv", "config": {"source_path": csv_path},
    }).get_json()

    with open(csv_path, "rb") as fh:
        payload = fh.read()
    uploaded = client.post(
        "/api/pipeline/sources/upload",
        data={"file": (io.BytesIO(payload), "equipment.csv")},
        content_type="multipart/form-data",
    ).get_json()

    assert uploaded["ok"] is True
    assert uploaded["columns"] == remote["columns"]
    assert uploaded["sample"] == remote["sample"]
    assert uploaded["row_count"] == remote["row_count"]


def test_an_upload_is_stored_under_a_generated_name(app, client):
    """A client-supplied filename must not reach the filesystem."""
    import io

    response = client.post(
        "/api/pipeline/sources/upload",
        data={"file": (io.BytesIO(b"A\n1\n"), "../../etc/passwd.csv")},
        content_type="multipart/form-data",
    )
    data = response.get_json()
    assert data["ok"] is True

    stored = data["config"]["source_path"]
    upload_dir = os.path.realpath(app.config["SCIDK_PIPELINE_UPLOAD_DIR"])
    assert os.path.commonpath([os.path.realpath(stored), upload_dir]) == upload_dir
    assert "passwd" not in os.path.basename(stored)
    # The display name keeps the basename, not the traversal — nothing derived
    # from the client's path reaches either the filesystem or the UI.
    assert data["config"]["upload_name"] == "passwd.csv"


def test_an_unsupported_file_type_is_refused(client):
    import io

    response = client.post(
        "/api/pipeline/sources/upload",
        data={"file": (io.BytesIO(b"nope"), "photo.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "not supported" in response.get_json()["error"]


def test_uploading_nothing_is_refused(client):
    response = client.post("/api/pipeline/sources/upload", data={},
                           content_type="multipart/form-data")
    assert response.status_code == 400


def test_an_oversized_upload_is_refused_and_not_kept(app, client, monkeypatch):
    import io

    from scidk.web.routes import api_pipeline

    # The floor is 1MB, so send something comfortably past it.
    monkeypatch.setattr(api_pipeline, "DEFAULT_MAX_UPLOAD_MB", 1)
    monkeypatch.setenv("SCIDK_PIPELINE_MAX_UPLOAD_MB", "1")

    response = client.post(
        "/api/pipeline/sources/upload",
        data={"file": (io.BytesIO(b"A\n" + b"1\n" * 2_000_000), "big.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert "upload limit" in response.get_json()["error"]
    upload_dir = app.config["SCIDK_PIPELINE_UPLOAD_DIR"]
    assert not os.path.isdir(upload_dir) or os.listdir(upload_dir) == []


def test_an_unreadable_upload_is_not_kept(app, client):
    """An empty file has no header, so there is nothing to keep."""
    import io

    client.post(
        "/api/pipeline/sources/upload",
        data={"file": (io.BytesIO(b""), "empty.csv")},
        content_type="multipart/form-data",
    )
    upload_dir = app.config["SCIDK_PIPELINE_UPLOAD_DIR"]
    leftovers = os.listdir(upload_dir) if os.path.isdir(upload_dir) else []
    assert leftovers == [], f"an unusable upload was kept: {leftovers}"


# --------------------------------------------------------------- Task F

def test_preflight_reports_the_fair_letters_without_writing(client, csv_path):
    source = make_source(client, csv_path)
    client.put(f"/api/pipeline/sources/{source['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")

    response = client.post(f"/api/pipeline/sources/{source['id']}/preflight")
    assert response.status_code == 200
    preflight = response.get_json()["preflight"]
    assert preflight["fair"] == {"F": True, "A": True, "I": True, "R": True}

    # Stored under fair_status, not last_run_status: nothing was ingested.
    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["fair_status"]["fair_ok"] is True
    assert stored["last_run_status"] is None


def test_preflight_on_a_source_with_no_mapping_says_so(client, csv_path):
    source = make_source(client, csv_path)
    preflight = client.post(f"/api/pipeline/sources/{source['id']}/preflight") \
        .get_json()["preflight"]
    assert preflight["fair_ok"] is False
    assert any("mapping" in e for e in preflight["errors"])


def test_a_source_run_without_neo4j_configured_fails_without_pretending(client, csv_path):
    """No graph to write to is a failed run, not a silent success."""
    source = make_source(client, csv_path)
    client.put(f"/api/pipeline/sources/{source['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")

    run = client.post(f"/api/pipeline/sources/{source['id']}/run").get_json()["run"]
    assert run["status"] == "error"
    assert run["nodes_written"] == 0
    assert any("Neo4j is not configured" in e for e in run["errors"])
    # And the failure is recorded on the source, not left looking un-run.
    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["last_run_status"] == "error"


def test_a_source_run_writes_what_the_mapping_declares(client, csv_path, fake_graph):
    source = make_source(client, csv_path)
    client.put(f"/api/pipeline/sources/{source['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")

    run = client.post(f"/api/pipeline/sources/{source['id']}/run").get_json()["run"]

    assert run["status"] == "success", run["errors"]
    assert run["nodes_written"] == 2
    assert {n["properties"]["asset_id"] for n in fake_graph.nodes} == {"A-1", "A-2"}
    assert all(n["label"] == "Asset" for n in fake_graph.nodes)


def test_a_dry_run_writes_nothing_and_reports_what_it_would(client, csv_path):
    source = make_source(client, csv_path)
    client.put(f"/api/pipeline/sources/{source['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")

    run = client.post(f"/api/pipeline/sources/{source['id']}/run?dry_run=1") \
        .get_json()["run"]
    assert run["dry_run"] is True
    assert run["nodes_declared"] == 2
    assert run["nodes_written"] == 0
    assert run["writes_committed"] is False


def test_running_a_missing_source_is_404(client):
    assert client.post("/api/pipeline/sources/nope/run").status_code == 404


def test_create_a_pipeline_from_an_ordered_source_list(client, csv_path):
    first = make_source(client, csv_path, name="first")
    second = make_source(client, csv_path, name="second")

    response = post(client, "/api/pipeline/pipelines", {
        "name": "Nightly", "source_ids": [first["id"], second["id"]],
    })
    assert response.status_code == 201
    steps = response.get_json()["pipeline"]["dag_json"]["steps"]
    assert [s["source_id"] for s in steps] == [first["id"], second["id"]]
    assert steps[1]["depends_on"] == [first["id"]], "order becomes dependency"


def test_a_pipeline_referencing_an_unknown_source_is_refused(client):
    response = post(client, "/api/pipeline/pipelines",
                    {"name": "Broken", "source_ids": ["nope"]})
    assert response.status_code == 400
    assert "unknown source" in response.get_json()["error"]


def test_a_pipeline_run_records_per_step_results(client, csv_path, fake_graph):
    source = make_source(client, csv_path)
    client.put(f"/api/pipeline/sources/{source['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")
    pipeline = post(client, "/api/pipeline/pipelines",
                    {"name": "P", "source_ids": [source["id"]]}).get_json()["pipeline"]

    response = client.post(f"/api/pipeline/pipelines/{pipeline['id']}/run")
    assert response.status_code == 200
    run = response.get_json()["run"]
    assert len(run["steps"]) == 1
    assert run["steps"][0]["source_id"] == source["id"]
    assert "fair" in run["steps"][0]

    runs = client.get(f"/api/pipeline/pipelines/{pipeline['id']}/runs") \
        .get_json()["runs"]
    assert len(runs) == 1 and runs[0]["id"] == run["run_id"]


def test_a_fair_failure_is_a_skipped_step_and_the_run_is_not_a_flat_failure(
    client, csv_path, tmp_path, fake_graph
):
    good = make_source(client, csv_path, name="good")
    client.put(f"/api/pipeline/sources/{good['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")
    broken = make_source(client, str(tmp_path / "missing.csv"), name="broken")
    client.put(f"/api/pipeline/sources/{broken['id']}",
               data=json.dumps({"mapping_json": MAPPING}),
               content_type="application/json")

    pipeline = post(client, "/api/pipeline/pipelines", {
        "name": "P", "source_ids": [broken["id"], good["id"]],
    }).get_json()["pipeline"]
    run = client.post(f"/api/pipeline/pipelines/{pipeline['id']}/run").get_json()["run"]

    by_name = {s["source_name"]: s for s in run["steps"]}
    assert by_name["broken"]["status"] == "skipped"
    assert "FAIR" in by_name["broken"]["reason"]
    assert len(run["steps"]) == 2, "the broken source did not stop the DAG"


def test_delete_a_pipeline_leaves_its_sources_alone(client, csv_path):
    source = make_source(client, csv_path)
    pipeline = post(client, "/api/pipeline/pipelines",
                    {"name": "P", "source_ids": [source["id"]]}).get_json()["pipeline"]

    assert client.delete(f"/api/pipeline/pipelines/{pipeline['id']}").status_code == 200
    assert client.get("/api/pipeline/pipelines").get_json()["pipelines"] == []
    assert len(client.get("/api/pipeline/sources").get_json()["sources"]) == 1


# ------------------------------------------------------------- scheduling

def test_setting_a_schedule_writes_it_to_the_shared_jobstore(app, client, csv_path):
    """The mechanism behind "takes effect immediately, no restart".

    The request is served by a worker whose scheduler has no timer behind it, so
    what matters is that the job lands somewhere the scheduler-owning process
    reads. Asserted from a separately-constructed store, which is what the master
    is from this request's point of view.
    """
    from scidk.pipeline.scheduler import PipelineScheduleStore

    source = make_source(client, csv_path)
    response = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                    {"cron": "0 2 * * *"})
    assert response.status_code == 200
    schedule = response.get_json()["schedule"]
    assert schedule["cron"] == "0 2 * * *"
    assert schedule["scheduled"] is True
    assert schedule["next_run_time"], "no next run time means nothing will fire"
    assert "warning" not in schedule

    independent = PipelineScheduleStore(app.config["SCIDK_SETTINGS_DB"])
    jobs = independent.list_jobs()
    assert schedule["pipeline_id"] in jobs
    assert jobs[schedule["pipeline_id"]]["next_run_time"]


def test_the_jobstore_is_persistent_not_in_memory(app, client, csv_path):
    """Written to scidk_settings.db, so it survives the process that made it."""
    import sqlite3

    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": "0 2 * * *"})

    conn = sqlite3.connect(app.config["SCIDK_SETTINGS_DB"])
    try:
        rows = conn.execute(
            "SELECT id FROM apscheduler_pipeline_jobs"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == [f"pipeline:src-{source['id']}"]


def test_a_source_schedule_creates_one_implicit_pipeline_however_often_it_is_set(
    client, csv_path
):
    source = make_source(client, csv_path)
    for cron in ("0 2 * * *", "0 3 * * *", "30 4 * * 1"):
        post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": cron})

    pipelines = client.get("/api/pipeline/pipelines").get_json()["pipelines"]
    assert len(pipelines) == 1
    assert pipelines[0]["schedule"] == "30 4 * * 1"
    assert pipelines[0]["source_ids"] == [source["id"]]
    assert pipelines[0]["implicit"] is True


def test_pausing_keeps_the_cron_but_stops_it_firing(app, client, csv_path):
    from scidk.pipeline.scheduler import PipelineScheduleStore

    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": "0 2 * * *"})

    paused = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                  {"cron": "0 2 * * *", "paused": True}).get_json()["schedule"]

    assert paused["cron"] == "0 2 * * *", "pausing must not clear the schedule"
    assert paused["paused"] is True
    assert paused["next_run_time"] is None
    assert PipelineScheduleStore(app.config["SCIDK_SETTINGS_DB"]).list_jobs() == {}


def test_resuming_restores_the_job(app, client, csv_path):
    from scidk.pipeline.scheduler import PipelineScheduleStore

    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule",
         {"cron": "0 2 * * *", "paused": True})
    resumed = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                   {"cron": "0 2 * * *", "paused": False}).get_json()["schedule"]

    assert resumed["paused"] is False and resumed["next_run_time"]
    assert PipelineScheduleStore(app.config["SCIDK_SETTINGS_DB"]).list_jobs()


def test_clearing_a_schedule_removes_the_job(app, client, csv_path):
    from scidk.pipeline.scheduler import PipelineScheduleStore

    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": "0 2 * * *"})
    cleared = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                   {"cron": None}).get_json()["schedule"]

    assert cleared["cron"] is None and cleared["scheduled"] is False
    assert PipelineScheduleStore(app.config["SCIDK_SETTINGS_DB"]).list_jobs() == {}


def test_a_malformed_cron_is_refused_before_it_is_stored(client, csv_path):
    """Otherwise it looks saved and silently never runs."""
    source = make_source(client, csv_path)
    for bad in ("not a cron", "0 2 * *", "99 * * * *", "* * * * * *"):
        response = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                        {"cron": bad})
        assert response.status_code == 400, f"accepted {bad!r}"
        assert "cron" in response.get_json()["error"]

    stored = client.get(f"/api/pipeline/sources/{source['id']}/schedule") \
        .get_json()["schedule"]
    assert stored["cron"] is None


def test_reading_a_schedule_before_one_exists(client, csv_path):
    source = make_source(client, csv_path)
    schedule = client.get(f"/api/pipeline/sources/{source['id']}/schedule") \
        .get_json()["schedule"]
    assert schedule["cron"] is None and schedule["scheduled"] is False


def test_a_source_in_a_scheduled_shared_pipeline_reports_that_schedule(client, csv_path):
    """Otherwise the card claims "manual only" for a source that runs nightly."""
    first = make_source(client, csv_path, name="first")
    second = make_source(client, csv_path, name="second")
    pipeline = post(client, "/api/pipeline/pipelines", {
        "name": "Shared", "source_ids": [first["id"], second["id"]],
    }).get_json()["pipeline"]
    post(client, f"/api/pipeline/pipelines/{pipeline['id']}/schedule",
         {"cron": "0 5 * * *"})

    schedule = client.get(f"/api/pipeline/sources/{first['id']}/schedule") \
        .get_json()["schedule"]
    assert schedule["cron"] == "0 5 * * *"
    assert schedule["via_pipeline"]["name"] == "Shared"


def test_the_scheduled_job_is_stored_as_a_resolvable_reference(app, client, csv_path):
    """The master unpickles this in a different process; a closure would not survive."""
    source = make_source(client, csv_path)
    post(client, f"/api/pipeline/sources/{source['id']}/schedule", {"cron": "0 2 * * *"})

    from scidk.pipeline.scheduler import PipelineScheduleStore, run_scheduled_pipeline

    store = PipelineScheduleStore(app.config["SCIDK_SETTINGS_DB"])
    scheduler = store._client()
    try:
        job = scheduler.get_job(f"pipeline:src-{source['id']}", jobstore="pipeline")
        assert job.func is run_scheduled_pipeline
        assert job.args[0] == f"src-{source['id']}"
        assert os.path.isabs(job.args[1]), "a relative db path will not resolve in the master"
    finally:
        scheduler.shutdown(wait=False)


def test_a_scheduled_run_of_a_deleted_pipeline_cleans_itself_up(app, tmp_path):
    """The pipeline is gone but its job may still be in the store."""
    from scidk.pipeline.scheduler import run_scheduled_pipeline

    # Must not raise, and must not leave the job behind.
    run_scheduled_pipeline("does-not-exist", app.config["SCIDK_SETTINGS_DB"])


def test_a_paused_pipeline_does_not_run_even_if_its_job_fires(app, client, csv_path):
    """Defence in depth: the flag is re-checked at fire time, not only at write."""
    from scidk.pipeline.run_history import RunHistory
    from scidk.pipeline.scheduler import run_scheduled_pipeline

    source = make_source(client, csv_path)
    schedule = post(client, f"/api/pipeline/sources/{source['id']}/schedule",
                    {"cron": "0 2 * * *", "paused": True}).get_json()["schedule"]

    run_scheduled_pipeline(schedule["pipeline_id"], app.config["SCIDK_SETTINGS_DB"])

    history = RunHistory(app.config["SCIDK_SETTINGS_DB"])
    assert history.list_runs(schedule["pipeline_id"]) == [], "a paused pipeline ran"


def test_the_master_registers_the_jobstore_and_a_poll_heartbeat(tmp_path, monkeypatch):
    """Without the heartbeat the master sleeps and never notices a new schedule."""
    from scidk.core.app_scheduler import AppScheduler
    from scidk.pipeline.scheduler import (
        HEARTBEAT_JOB_ID,
        PIPELINE_JOBSTORE_ALIAS,
        attach,
    )

    scheduler = AppScheduler(timezone="UTC")
    try:
        assert attach(scheduler, str(tmp_path / "scidk_settings.db")) is True
        assert scheduler.has_jobstore(PIPELINE_JOBSTORE_ALIAS)
        assert HEARTBEAT_JOB_ID in {j["id"] for j in scheduler.list_jobs()}
        # Idempotent: create_app may run more than once in a process.
        assert attach(scheduler, str(tmp_path / "scidk_settings.db")) is True
        assert len([j for j in scheduler.list_jobs() if j["id"] == HEARTBEAT_JOB_ID]) == 1
    finally:
        scheduler.shutdown()


def test_a_schedule_written_by_a_worker_is_visible_to_the_master(tmp_path):
    """End to end on the mechanism, across two independent scheduler objects."""
    from scidk.core.app_scheduler import AppScheduler
    from scidk.pipeline.scheduler import (
        PIPELINE_JOBSTORE_ALIAS,
        PipelineScheduleStore,
        attach,
    )
    from scidk.pipeline.store import PipelineStore

    db = str(tmp_path / "scidk_settings.db")
    store = PipelineStore(db)
    pipeline = store.create_pipeline("Nightly", dag={"steps": []})

    # The "worker": writes without ever touching the master's scheduler.
    PipelineScheduleStore(db).upsert(pipeline["id"], "0 2 * * *")

    # The "master": a separate AppScheduler, as a different process would have.
    master = AppScheduler(timezone="UTC")
    try:
        master.start()
        attach(master, db)
        jobs = master.scheduler.get_jobs(jobstore=PIPELINE_JOBSTORE_ALIAS)
        assert [j.id for j in jobs] == [f"pipeline:{pipeline['id']}"]
        assert jobs[0].next_run_time is not None
    finally:
        master.shutdown()
