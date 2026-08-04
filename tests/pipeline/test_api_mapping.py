"""The Task D HTTP surface: a source's column mapping, and the columns it maps from.

Same app fixture discipline as ``test_api_pipeline.py`` — every Neo4j environment
variable is cleared, because ``scidk/app.py`` calls ``load_dotenv()`` at import and a
full-suite run would otherwise hand these routes real credentials for the developer's
dev graph. Nothing here should reach Neo4j at all: a mapping is a config, and Task E
is where a mapping first meets the graph.

The rule these tests pin, and the one thing that makes this route different from its
Task C neighbour: ``PUT .../schema`` *refuses* an unusable schema, and
``PUT .../mapping`` *accepts* an unusable mapping. A half-finished mapping is what a
user closing the browser mid-task should come back to, and the engine validates on
load, so nothing incomplete in that column can make a run write something wrong.
"""
from __future__ import annotations

import json

import pytest

# The app/client fixtures and the env-clearing rationale live next door.
from .test_api_pipeline import (  # noqa: F401 - fixtures used by name
    app,
    client,
    csv_path,
    fake_graph,
    make_source,
    post,
)

#: A schema over the columns of the ``csv_path`` fixture (Asset ID, Name).
SCHEMA = {
    "nodes": [
        {"id": "n0", "caption": "Asset", "labels": ["Asset"],
         "properties": [{"name": "asset_id"}, {"name": "name"}],
         "key_property": "asset_id"},
        {"id": "n1", "caption": "Site", "labels": ["Site"],
         "properties": [{"name": "code"}], "key_property": "code"},
    ],
    "relationships": [
        {"id": "r0", "type": "LOCATED_AT", "fromId": "n0", "toId": "n1",
         "properties": []},
    ],
}

MAPPING = {
    "version": "1.0",
    "node_mappings": [
        {"id": "asset", "label": "Asset", "key_property": "asset_id",
         "properties": [{"name": "asset_id", "column": "Asset ID"},
                        {"name": "name", "column": "Name"}]},
    ],
}


def put(client, path, payload):
    return client.put(path, data=json.dumps(payload), content_type="application/json")


def make_mapped_source(client, csv_path, mapping=MAPPING):
    source = make_source(client, csv_path)
    put(client, f"/api/pipeline/sources/{source['id']}/schema", {"schema": SCHEMA})
    if mapping is not None:
        response = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
                       {"mapping": mapping})
        assert response.status_code == 200, response.get_json()
    return source


# ------------------------------------------------------------------ GET / PUT

def test_a_new_source_has_no_mapping(client, csv_path):
    source = make_source(client, csv_path)
    body = client.get(f"/api/pipeline/sources/{source['id']}/mapping").get_json()

    assert body["mapping"] is None
    assert body["saved_at"] is None
    assert body["summary"]["defined"] is False
    # No mapping is "not started", not "broken" — so there is no verdict to report.
    assert body["validation"] is None


def test_saving_a_mapping_writes_mapping_json(client, csv_path):
    source = make_source(client, csv_path)

    saved = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
                {"mapping": MAPPING})
    assert saved.status_code == 200, saved.get_json()
    body = saved.get_json()
    assert body["summary"]["labels"] == ["Asset"]
    assert body["saved_at"]

    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["mapping_json"] == MAPPING
    assert stored["mapping_saved_at"]


def test_a_bare_config_is_accepted_as_the_body(client, csv_path):
    """The page posts {"mapping": ...}; a config posted directly works too."""
    source = make_source(client, csv_path)
    assert put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               MAPPING).status_code == 200


def test_a_version_is_filled_in_when_a_config_omits_it(client, csv_path):
    """The only version there is. Failing validation for its absence is noise."""
    source = make_source(client, csv_path)
    without = {k: v for k, v in MAPPING.items() if k != "version"}
    body = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               {"mapping": without}).get_json()
    assert body["mapping"]["version"] == "1.0"
    assert body["validation"]["ok"] is True


def test_a_body_that_is_not_a_config_at_all_is_refused(client, csv_path):
    """A client bug, as distinct from an unfinished mapping."""
    source = make_source(client, csv_path)
    response = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
                   {"mapping": ["node_mappings"]})
    assert response.status_code == 400
    assert "JSON object" in response.get_json()["error"]


def test_null_clears_the_mapping(client, csv_path):
    source = make_mapped_source(client, csv_path)
    body = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               {"mapping": None}).get_json()
    assert body["mapping"] is None
    assert body["saved_at"] is None

    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["mapping_json"] is None
    assert stored["mapping_saved_at"] is None


def test_a_mapping_for_a_source_that_does_not_exist_is_a_404(client):
    assert client.get("/api/pipeline/sources/nope/mapping").status_code == 404
    assert put(client, "/api/pipeline/sources/nope/mapping",
               {"mapping": MAPPING}).status_code == 404


def test_the_mapping_route_never_touches_the_schema(client, csv_path):
    """Two independent artefacts on one record; saving one must not disturb the other."""
    source = make_mapped_source(client, csv_path)
    schema = client.get(f"/api/pipeline/sources/{source['id']}/schema").get_json()
    assert schema["summary"]["labels"] == ["Asset", "Site"]
    assert schema["saved_at"]


# ------------------------------------------------------------ the verdict

def test_a_complete_mapping_reports_that_the_engine_accepts_it(client, csv_path):
    """The primary acceptance criterion, as the route reports it."""
    source = make_source(client, csv_path)
    body = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               {"mapping": MAPPING}).get_json()

    assert body["validation"] == {"ok": True, "errors": [], "warnings": []}


def test_a_partial_mapping_saves_and_says_what_is_missing(client, csv_path):
    """Save is available at any point; the report is where the holes are named."""
    source = make_source(client, csv_path)
    partial = {
        "version": "1.0",
        "node_mappings": [
            # Columns assigned, no key chosen yet: exactly what a half-finished role
            # in the UI produces.
            {"id": "asset", "label": "Asset",
             "properties": [{"name": "name", "column": "Name"}]},
        ],
    }
    response = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
                   {"mapping": partial})

    assert response.status_code == 200
    body = response.get_json()
    assert body["validation"]["ok"] is False
    assert any("key_property" in e for e in body["validation"]["errors"])
    # Stored anyway — the work is not thrown away for being unfinished.
    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["mapping_json"] == partial
    assert body["summary"]["unkeyed_roles"] == ["asset"]


def test_a_relationship_naming_a_role_that_is_not_declared_is_reported(client, csv_path):
    source = make_source(client, csv_path)
    broken = dict(MAPPING, relationship_mappings=[
        {"type": "LOCATED_AT", "from": "asset", "to": "site"},
    ])
    body = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               {"mapping": broken}).get_json()

    assert body["validation"]["ok"] is False
    assert any("'site'" in e and "not declared" in e for e in body["validation"]["errors"])


def test_a_property_name_cypher_cannot_address_is_refused_by_validation(client, csv_path):
    """The identifier guard, reported here rather than discovered at write time."""
    source = make_source(client, csv_path)
    unsafe = {
        "version": "1.0",
        "node_mappings": [{"id": "asset", "label": "Asset", "key_property": "asset_id",
                           "properties": [{"name": "asset_id", "column": "Asset ID"},
                                          {"name": "Sample ID", "column": "Name"}]}],
    }
    body = put(client, f"/api/pipeline/sources/{source['id']}/mapping",
               {"mapping": unsafe}).get_json()
    assert body["validation"]["ok"] is False
    assert any("Sample ID" in e for e in body["validation"]["errors"])


def test_a_plugin_transform_resolves_for_a_source_of_that_plugin(client, csv_path):
    """Which transform names are valid depends on which plugin serves the source.

    The same config is fine for a SharePoint source and unknown for a CSV one, so the
    route has to consult the plugin rather than a single global library.
    """
    using_plugin_transform = {
        "version": "1.0",
        "node_mappings": [{
            "id": "pi", "label": "Person", "key_property": "email",
            "source": {"column": "Name", "transform": "parse_rfc5322"},
            "property_map": {"name": "name", "email": "email"},
        }],
    }
    csv_source = make_source(client, csv_path)
    body = put(client, f"/api/pipeline/sources/{csv_source['id']}/mapping",
               {"mapping": using_plugin_transform}).get_json()
    assert body["validation"]["ok"] is False
    assert any("parse_rfc5322" in e for e in body["validation"]["errors"])

    sharepoint = make_source(client, csv_path, name="SP list",
                             plugin_type="sharepoint")
    body = put(client, f"/api/pipeline/sources/{sharepoint['id']}/mapping",
               {"mapping": using_plugin_transform}).get_json()
    assert body["validation"] == {"ok": True, "errors": [], "warnings": []}


# ----------------------------------------------------------------- columns

def test_the_columns_route_reads_the_source_live(client, csv_path):
    """Nothing stores the column list: Task B's preview lives in the browser."""
    source = make_source(client, csv_path)
    body = client.get(f"/api/pipeline/sources/{source['id']}/columns").get_json()

    assert body["ok"] is True
    assert body["columns"] == ["Asset ID", "Name"]
    # A sample, so the left panel can show what each column actually holds.
    assert body["sample"][0]["Asset ID"] == "A-1"
    assert body["missing_columns"] == []


def test_a_mapping_that_has_drifted_from_its_source_is_reported_by_name(client, csv_path):
    """A column the source dropped, named before a run rather than after one."""
    drifted = {
        "version": "1.0",
        "node_mappings": [{"id": "asset", "label": "Asset", "key_property": "asset_id",
                           "properties": [{"name": "asset_id", "column": "Asset ID"},
                                          {"name": "name", "column": "Gone Away"}]}],
    }
    source = make_mapped_source(client, csv_path, mapping=drifted)
    body = client.get(f"/api/pipeline/sources/{source['id']}/columns").get_json()

    assert body["ok"] is True
    assert body["missing_columns"] == ["Gone Away"]


def test_an_unreadable_source_reports_why_instead_of_failing(client, tmp_path):
    """The page has to stay usable: an existing mapping is still editable."""
    source = post(client, "/api/pipeline/sources", {
        "name": "Gone", "plugin_type": "csv",
        "config": {"source_path": str(tmp_path / "missing.csv")},
    }).get_json()["source"]

    response = client.get(f"/api/pipeline/sources/{source['id']}/columns")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]
    assert body["columns"] == []


def test_a_source_whose_plugin_is_unavailable_says_so(client, csv_path):
    """No plugin means no columns, and a message rather than a 500."""
    from scidk.pipeline.store import PipelineStore

    source = make_source(client, csv_path)
    store = PipelineStore(client.application.config["SCIDK_SETTINGS_DB"])
    store.update_source(source["id"], plugin_type="ilab_importer")

    body = client.get(f"/api/pipeline/sources/{source['id']}/columns").get_json()
    assert body["ok"] is False
    assert "ilab_importer" in body["error"]


# ------------------------------------------------------ the card and the flow

def test_the_source_card_reports_whether_its_mapping_is_defined(client, csv_path):
    source = make_source(client, csv_path)
    listed = client.get("/api/pipeline/sources").get_json()["sources"][0]
    assert listed["mapping_summary"]["defined"] is False

    put(client, f"/api/pipeline/sources/{source['id']}/mapping", {"mapping": MAPPING})
    listed = client.get("/api/pipeline/sources").get_json()["sources"][0]
    assert listed["mapping_summary"]["defined"] is True
    assert listed["mapping_summary"]["node_mapping_count"] == 1
    assert listed["mapping_summary"]["mapped_columns"] == ["Asset ID", "Name"]


def test_the_mapping_page_renders_with_both_panels(client, csv_path):
    source = make_mapped_source(client, csv_path)
    body = client.get(f"/pipeline/sources/{source['id']}/mapping").get_data(as_text=True)

    assert 'data-testid="mapping-page"' in body
    assert 'data-testid="columns-panel"' in body
    assert 'data-testid="targets-panel"' in body
    assert 'data-testid="save-mapping"' in body
    # The breadcrumb Task C established, one step further along.
    assert 'data-testid="mapping-breadcrumb"' in body
    # The transform catalogue is rendered inline so the dropdowns need no round trip.
    assert "lowercase_strip" in body


def test_the_page_offers_the_plugins_transforms_and_not_another_plugins(client, csv_path):
    csv_source = make_source(client, csv_path)
    body = client.get(
        f"/pipeline/sources/{csv_source['id']}/mapping").get_data(as_text=True)
    assert "parse_rfc5322" not in body

    sharepoint = make_source(client, csv_path, name="SP", plugin_type="sharepoint")
    body = client.get(
        f"/pipeline/sources/{sharepoint['id']}/mapping").get_data(as_text=True)
    assert "parse_rfc5322" in body
    # And the row-reading one is offered as unselectable rather than left out, so the
    # page can say why it has no field for it.
    assert '"sp_colresolution"' in body
    assert '"selectable": false' in body or '"selectable":false' in body


def test_the_mapping_page_for_a_source_that_does_not_exist_is_a_404(client):
    assert client.get("/pipeline/sources/nope/mapping").status_code == 404


def test_the_sources_page_no_longer_calls_step_3_unbuilt(client):
    body = client.get("/pipeline/sources").get_data(as_text=True)
    assert 'data-testid="step-dot-mapping"' in body
    assert 'data-testid="step-mapping"' in body
    assert 'data-testid="sheet-next-mapping"' in body
    assert 'data-testid="mapping-source-btn"' in body
    # Step 3 was greyed out and labelled as unbuilt while it was; it is not now.
    assert "Mapping is Cycle 3B Task D" not in body
    assert 'class="step future"' not in body


@pytest.mark.parametrize("page", ["/pipeline/sources", "MAPPING_PAGE"])
def test_the_rendered_page_javascript_parses(client, csv_path, tmp_path, page):
    """A syntax error in an inline template script is silent until someone opens it.

    Checked against the *rendered* page, so a Jinja expression that produces invalid
    JavaScript is caught too — including ``{{ mapping_json | tojson }}`` for a source
    whose mapping holds the awkward characters a hand-written config can carry.
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")

    awkward = dict(MAPPING, name="A </script> in a name & a 'quote'")
    source = make_mapped_source(client, csv_path, mapping=awkward)
    if page == "MAPPING_PAGE":
        page = f"/pipeline/sources/{source['id']}/mapping"
    html = client.get(page).get_data(as_text=True)

    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, f"no inline script found in {page}"
    for index, block in enumerate(blocks):
        path = tmp_path / f"block{index}.js"
        path.write_text(block, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr


def test_the_shared_model_script_parses(tmp_path):
    """pipeline_mapping.js is loaded by src, so it is not covered by the check above."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")

    model = (Path(__file__).resolve().parents[2] / "scidk" / "ui" / "static" / "js"
             / "pipeline_mapping.js")
    result = subprocess.run([node, "--check", str(model)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------- a real run

def test_a_mapping_saved_through_the_route_runs(client, csv_path, fake_graph):
    """The whole point: what the page saves is what the runner consumes.

    Uses the ``fake_graph`` fixture, so the write lands in memory and the request
    path — routing, RBAC, orchestration, the mapping engine — is exactly as in
    production.
    """
    source = make_mapped_source(client, csv_path)
    run = client.post(f"/api/pipeline/sources/{source['id']}/run").get_json()["run"]

    assert run["fair_ok"] is True, run["errors"]
    assert run["status"] == "success"
    assert run["nodes_written"] == 2
    assert {n["properties"]["asset_id"] for n in fake_graph.nodes} == {"A-1", "A-2"}


def test_a_source_with_no_mapping_fails_its_fair_check_rather_than_writing(
    client, csv_path, fake_graph
):
    source = make_source(client, csv_path)
    run = client.post(f"/api/pipeline/sources/{source['id']}/run").get_json()["run"]

    assert run["fair_ok"] is False
    assert fake_graph.nodes == []
