"""The Task C HTTP surface: a source's schema, and deriving one from the graph.

Same app fixture discipline as ``test_api_pipeline.py`` — every Neo4j environment
variable is cleared, because ``scidk/app.py`` calls ``load_dotenv()`` at import and
a full-suite run would otherwise give the derive route real credentials for the
developer's dev graph. The one test that needs a graph gets a fake client.
"""
from __future__ import annotations

import json

import pytest

# The app/client fixtures and the env-clearing rationale live next door; reusing
# them keeps one definition of "an app that cannot reach a real database".
from .test_api_pipeline import (  # noqa: F401 - fixtures used by name
    app,
    client,
    csv_path,
    make_source,
    post,
)

ARROWS = {
    "nodes": [
        {"id": "n0", "position": {"x": 0, "y": 0}, "caption": "Person",
         "labels": ["Person"], "properties": [{"name": "email"}, {"name": "name"}]},
        {"id": "n1", "position": {"x": 300, "y": 0}, "caption": "Project",
         "labels": ["Project"], "properties": [{"name": "code"}]},
    ],
    "relationships": [
        {"id": "r0", "type": "PI_OF", "fromId": "n1", "toId": "n0", "properties": []},
    ],
}


def put(client, path, payload):
    return client.put(path, data=json.dumps(payload), content_type="application/json")


# ------------------------------------------------------------------ GET / PUT

def test_a_new_source_has_no_schema(client, csv_path):
    source = make_source(client, csv_path)
    body = client.get(f"/api/pipeline/sources/{source['id']}/schema").get_json()

    assert body["schema"] is None
    assert body["saved_at"] is None
    assert body["summary"]["defined"] is False
    # The canvas is told its scope rather than constructing the string itself.
    assert body["context_id"] == f"pipeline_source:{source['id']}"


def test_saving_a_schema_writes_schema_json(client, csv_path):
    source = make_source(client, csv_path)

    saved = put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": ARROWS})
    assert saved.status_code == 200, saved.get_json()
    assert saved.get_json()["summary"]["labels"] == ["Person", "Project"]

    # Visible on the source record itself, which is what Task D will read.
    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert [n["labels"][0] for n in stored["schema_json"]["nodes"]] == ["Person", "Project"]
    assert stored["schema_saved_at"]


def test_a_bare_arrows_document_is_accepted_as_the_body(client, csv_path):
    """The canvas posts {"schema": ...}; an arrows.app file posted directly works too."""
    source = make_source(client, csv_path)
    assert put(client, f"/api/pipeline/sources/{source['id']}/schema", ARROWS).status_code == 200


def test_saved_at_moves_on_a_save_but_not_on_a_rename(client, csv_path):
    """The canvas decides whether its session holds unsaved work by this timestamp."""
    source = make_source(client, csv_path)
    put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": ARROWS})
    saved_at = client.get(f"/api/pipeline/sources/{source['id']}/schema") \
        .get_json()["saved_at"]

    put(client, f"/api/pipeline/sources/{source['id']}", {"name": "Renamed"})
    after_rename = client.get(f"/api/pipeline/sources/{source['id']}/schema") \
        .get_json()["saved_at"]

    assert after_rename == saved_at


def test_an_invalid_schema_is_refused_with_every_problem_named(client, csv_path):
    source = make_source(client, csv_path)
    response = put(client, f"/api/pipeline/sources/{source['id']}/schema", {
        "schema": {"nodes": [{"id": "n0", "caption": "Intake Form"},
                             {"id": "n1", "caption": "Fine", "properties": ["Sample ID"]}]},
    })

    assert response.status_code == 400
    body = response.get_json()
    assert len(body["problems"]) == 2
    assert "'Intake Form'" in body["error"]
    # Nothing was stored.
    assert client.get(f"/api/pipeline/sources/{source['id']}/schema") \
        .get_json()["schema"] is None


def test_a_missing_source_is_a_404_on_every_schema_route(client):
    assert client.get("/api/pipeline/sources/nope/schema").status_code == 404
    assert put(client, "/api/pipeline/sources/nope/schema", {"schema": ARROWS}) \
        .status_code == 404
    assert client.get("/api/pipeline/sources/nope/schema/export/arrows").status_code == 404
    assert client.post("/api/pipeline/sources/nope/schema/import/arrows",
                       data=json.dumps(ARROWS),
                       content_type="application/json").status_code == 404


# --------------------------------------------------------------- import gate

def test_import_validates_without_saving(client, csv_path):
    """Option A must not overwrite the previous schema just by being previewed."""
    source = make_source(client, csv_path)
    response = client.post(f"/api/pipeline/sources/{source['id']}/schema/import/arrows",
                           data=json.dumps(ARROWS), content_type="application/json")

    assert response.status_code == 200
    assert response.get_json()["summary"]["relationship_types"] == ["PI_OF"]
    assert client.get(f"/api/pipeline/sources/{source['id']}/schema") \
        .get_json()["schema"] is None


def test_import_reports_a_json_syntax_error_rather_than_a_missing_nodes_array(
    client, csv_path
):
    """The canvas must not open on this, so the message has to be about the JSON."""
    source = make_source(client, csv_path)
    response = client.post(f"/api/pipeline/sources/{source['id']}/schema/import/arrows",
                           data='{"nodes": [}', content_type="application/json")

    assert response.status_code == 400
    assert "not valid JSON" in response.get_json()["error"]


def test_import_normalizes_the_property_form(client, csv_path):
    source = make_source(client, csv_path)
    schema = client.post(f"/api/pipeline/sources/{source['id']}/schema/import/arrows",
                         data=json.dumps(ARROWS),
                         content_type="application/json").get_json()["schema"]
    assert schema["nodes"][0]["properties"] == {"email": "String", "name": "String"}


# --------------------------------------------------------------------- export

def test_export_round_trips_back_through_import(client, csv_path):
    source = make_source(client, csv_path)
    put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": ARROWS})

    exported = client.get(f"/api/pipeline/sources/{source['id']}/schema/export/arrows")
    assert exported.status_code == 200
    assert 'filename="schema.arrows.json"' in exported.headers["Content-Disposition"]

    document = json.loads(exported.get_data(as_text=True))
    reimported = client.post(
        f"/api/pipeline/sources/{source['id']}/schema/import/arrows",
        data=json.dumps(document), content_type="application/json",
    ).get_json()["schema"]

    # Identical element set: same labels, same properties, same triples.
    assert reimported == document


def test_exporting_a_source_with_no_schema_says_so(client, csv_path):
    source = make_source(client, csv_path)
    response = client.get(f"/api/pipeline/sources/{source['id']}/schema/export/arrows")
    assert response.status_code == 404
    assert "no schema" in response.get_json()["error"]


# --------------------------------------------------------------------- derive

def test_derive_without_a_configured_neo4j_says_what_to_do_instead(client):
    """The fixture clears every Neo4j variable, which is also a real deployment state."""
    response = client.get("/api/pipeline/schema/derive")
    assert response.status_code == 400
    assert "Arrows.app" in response.get_json()["error"]


@pytest.fixture
def fake_neo4j(monkeypatch):
    """A Neo4jClient whose reads are canned, so the derive route needs no database."""
    from scidk.web.routes import api_pipeline

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False

        def connect(self):
            return True

        def execute_read(self, cypher, params=None):
            if cypher.startswith("CALL db.schema.visualization"):
                raise RuntimeError("There is no procedure with the name")
            if cypher.startswith("CALL apoc.meta.schema"):
                raise RuntimeError("There is no procedure with the name")
            if cypher.startswith("MATCH (n)-[r]->(m)"):
                return [{"from_labels": ["Project"], "rel_type": "PI_OF",
                         "to_labels": ["Person"]}]
            if cypher.startswith("CALL db.labels"):
                return [{"label": "Person"}, {"label": "Project"}]
            raise RuntimeError("There is no procedure with the name")

        def close(self):
            self.closed = True

    import scidk.services.neo4j_client as neo4j_module

    monkeypatch.setattr(neo4j_module, "Neo4jClient", FakeClient)
    monkeypatch.setattr(
        neo4j_module, "get_neo4j_params",
        lambda app: ("bolt://fake:7687", "neo4j", "x", None, "basic"),
    )
    return api_pipeline


def test_derive_returns_labels_as_nodes_and_types_as_edges(client, fake_neo4j):
    response = client.get("/api/pipeline/schema/derive")
    assert response.status_code == 200, response.get_json()
    body = response.get_json()

    assert body["strategy"] == "relationship scan"
    by_id = {n["id"]: n["labels"][0] for n in body["schema"]["nodes"]}
    assert set(by_id.values()) == {"Person", "Project"}
    rel = body["schema"]["relationships"][0]
    assert (by_id[rel["fromId"]], rel["type"], by_id[rel["toId"]]) == \
        ("Project", "PI_OF", "Person")
    # Why the earlier strategies did not answer, so an empty result is explicable.
    assert any("db.schema.visualization" in note for note in body["notes"])


def test_a_derived_schema_saves_without_further_editing(client, csv_path, fake_neo4j):
    source = make_source(client, csv_path)
    derived = client.get("/api/pipeline/schema/derive").get_json()["schema"]
    assert put(client, f"/api/pipeline/sources/{source['id']}/schema",
               {"schema": derived}).status_code == 200


# ------------------------------------------------------- the canvas page itself

def test_the_schema_canvas_page_renders_for_a_source(client, csv_path):
    source = make_source(client, csv_path, name="AIPT Intake Form")
    response = client.get(f"/pipeline/sources/{source['id']}/schema")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-testid="schema-canvas-page"' in body
    # The breadcrumb Task C specifies: Data Sources -> [source name] -> Schema.
    assert "AIPT Intake Form" in body and "Schema" in body
    # Scoped to this source's canvas context, never the main Maps canvas.
    assert f"pipeline_source:{source['id']}" in body
    assert 'data-testid="schema-mode-indicator"' in body


def test_the_page_carries_the_committed_schema_so_it_paints_without_a_round_trip(
    client, csv_path
):
    source = make_source(client, csv_path)
    put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": ARROWS})

    body = client.get(f"/pipeline/sources/{source['id']}/schema").get_data(as_text=True)
    assert '"PI_OF"' in body


def test_the_three_entry_points_are_accepted_and_anything_else_ignored(client, csv_path):
    source = make_source(client, csv_path)
    for start in ("arrows", "neo4j", "blank"):
        body = client.get(
            f"/pipeline/sources/{source['id']}/schema?start={start}"
        ).get_data(as_text=True)
        assert f'data-start="{start}"' in body

    body = client.get(
        f"/pipeline/sources/{source['id']}/schema?start=../evil"
    ).get_data(as_text=True)
    assert 'data-start=""' in body


def test_the_schema_canvas_page_404s_for_an_unknown_source(client):
    assert client.get("/pipeline/sources/nope/schema").status_code == 404


def test_the_rendered_page_javascript_parses(client, csv_path, tmp_path):
    """A syntax error in an inline template script is silent until someone opens it.

    Checked against the *rendered* page, so a Jinja expression that produces
    invalid JavaScript is caught too. Skipped when node is unavailable.
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")

    source = make_source(client, csv_path)
    put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": ARROWS})
    html = client.get(f"/pipeline/sources/{source['id']}/schema").get_data(as_text=True)

    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline script found in the schema canvas page"
    for index, block in enumerate(blocks):
        path = tmp_path / f"block{index}.js"
        path.write_text(block, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr


# ----------------------------------------------- the scoped canvas session

def test_deleting_a_source_clears_its_schema_canvas_session(client, csv_path):
    """Task C relies on the cleanup a0583d8 added; this is the check that it fires."""
    source = make_source(client, csv_path)
    context_id = f"pipeline_source:{source['id']}"

    saved = client.post(
        "/api/canvas/session",
        data=json.dumps({"context_id": context_id,
                         "canvas": {"nodes": [{"id": "schema-Person", "label": "Person",
                                               "_space": "schema"}], "edges": []}}),
        content_type="application/json",
    )
    assert saved.status_code == 200
    assert client.get(f"/api/canvas/session?context_id={context_id}") \
        .get_json()["canvas"]["nodes"]

    removed = client.delete(f"/api/pipeline/sources/{source['id']}").get_json()["removed"]
    assert removed["canvas_sessions"] == 1
    assert client.get(f"/api/canvas/session?context_id={context_id}") \
        .get_json()["canvas"] is None


def test_a_source_schema_canvas_does_not_touch_the_main_maps_canvas(client, csv_path):
    """The main canvas is context_id '' and must be unaffected by anything scoped."""
    source = make_source(client, csv_path)
    main = {"nodes": [{"id": "1", "label": "Sample", "name": "S1"}], "edges": []}
    client.post("/api/canvas/session", data=json.dumps({"canvas": main}),
                content_type="application/json")

    client.post(
        "/api/canvas/session",
        data=json.dumps({"context_id": f"pipeline_source:{source['id']}",
                         "canvas": {"nodes": [], "edges": []}}),
        content_type="application/json",
    )
    client.delete(f"/api/pipeline/sources/{source['id']}")

    assert client.get("/api/canvas/session").get_json()["canvas"] == main
