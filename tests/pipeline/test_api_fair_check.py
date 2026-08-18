"""The Task E HTTP surface: ``POST /api/pipeline/sources/<id>/fair-check``.

Same app fixture discipline as ``test_api_pipeline.py`` — every Neo4j environment
variable is cleared, because ``scidk/app.py`` calls ``load_dotenv()`` at import and
a full-suite run would otherwise hand this route real credentials for the
developer's dev graph. The FAIR check only ever reads, but a test that silently
depends on whatever is in a local graph is not a test.

The claim these tests exist to hold up is "zero Neo4j writes". Two of them attack
it from the outside: one gives the app a working writer and asserts the route never
asks for it, and one counts the nodes in a fake graph before and after. The unit
tests in ``test_fair_check.py`` attack it from the inside, with a writer that fails
the test if it is ever called.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

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

MAPPING = {
    "version": "1.0",
    "node_mappings": [
        {"id": "asset", "label": "Asset", "key_property": "asset_id",
         "properties": [{"name": "asset_id", "column": "Asset ID"},
                        {"name": "name", "column": "Name"}]},
        {"id": "site", "label": "Site", "key_property": "code",
         "properties": [{"name": "code", "column": "Site"}]},
    ],
    "relationship_mappings": [{"type": "LOCATED_AT", "from": "asset", "to": "site"}],
}


class SpyReader:
    """A ``Neo4jReader`` over a fixed node set, recording every query it is asked.

    ``count`` answers the node-count probe the definition of done asks for, so a
    test can compare the graph before and after a check without a database.
    """

    def __init__(self, keys: Optional[List[str]] = None):
        self.keys = set(keys or [])
        self.queries: List[str] = []

    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        self.queries.append(query)
        if "count(n)" in query:
            return [{"total": len(self.keys)}]
        values = (parameters or {}).get("values") or []
        return [{"key": v} for v in values if str(v) in self.keys]

    def count(self) -> int:
        return self.execute_read("MATCH (n) RETURN count(n) AS total")[0]["total"]


@pytest.fixture
def graph_reader(monkeypatch):
    """Give the route a graph to read without touching a database."""
    from scidk.pipeline import runner as runner_module

    reader = SpyReader(keys=["A-1"])

    @contextmanager
    def fake_reader(app=None):
        yield reader, None

    monkeypatch.setattr(runner_module, "neo4j_reader", fake_reader)
    return reader


@pytest.fixture
def csv_with_sites(tmp_path):
    path = tmp_path / "equipment.csv"
    path.write_text(
        "Asset ID,Name,Site\n"
        "A-1,Microscope,BLD-1\n"
        "A-2,Centrifuge,BLD-1\n"
        "A-3,Freezer,BLD-2\n",
        encoding="utf-8",
    )
    return str(path)


def put(client, path, payload):
    return client.put(path, data=json.dumps(payload), content_type="application/json")


def mapped_source(client, csv_path, mapping=MAPPING):
    source = make_source(client, csv_path)
    if mapping is not None:
        assert put(client, f"/api/pipeline/sources/{source['id']}/mapping",
                   {"mapping": mapping}).status_code == 200
    return source


def fair_check(client, source_id, query=""):
    response = client.post(f"/api/pipeline/sources/{source_id}/fair-check{query}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["fair"]


# ---------------------------------------------------------------- the route

def test_a_healthy_source_passes_all_four_letters(client, csv_with_sites, graph_reader):
    source = mapped_source(client, csv_with_sites)
    fair = fair_check(client, source["id"])

    assert [fair[letter]["result"] for letter in "FAIR"] == ["pass"] * 4
    assert fair["overall"] == "pass"
    assert fair["F"]["columns"] == ["Asset ID", "Name", "Site"]
    assert fair["F"]["row_count"] == 3
    assert fair["A"]["auth_method"]
    assert fair["R"]["note"] == "no prior run to compare"


def test_the_preview_says_which_nodes_would_merge(client, csv_with_sites, graph_reader):
    """``A-1`` is already in the fake graph; the other two are not."""
    source = mapped_source(client, csv_with_sites)
    fair = fair_check(client, source["id"])

    assert fair["I"]["preview"] == [
        "Row 1 → Asset(A-1) [merge], Site(BLD-1) [new] → LOCATED_AT",
        "Row 2 → Asset(A-2) [new], Site(BLD-1) [new] → LOCATED_AT",
        "Row 3 → Asset(A-3) [new], Site(BLD-2) [new] → LOCATED_AT",
    ]
    assert fair["I"]["nodes"] == {"total": 6, "new": 5, "merge": 1, "unknown": 0}
    assert fair["I"]["relationships"] == 3


def test_an_unknown_source_is_a_404(client):
    assert client.post("/api/pipeline/sources/nope/fair-check").status_code == 404


def test_a_source_with_no_mapping_still_reports_F_and_A(client, csv_path, graph_reader):
    """F and A do not depend on a mapping, so they are still worth answering."""
    source = make_source(client, csv_path)
    fair = fair_check(client, source["id"])

    assert fair["F"]["result"] == "pass"
    assert fair["A"]["result"] == "pass"
    assert fair["I"]["result"] == "fail"
    assert any("no mapping config" in e for e in fair["I"]["errors"])
    assert fair["R"]["result"] == "skipped"
    assert fair["overall"] == "fail"


def test_an_unreadable_source_fails_F_by_name(client, tmp_path, graph_reader):
    source = make_source(client, str(tmp_path / "does-not-exist.csv"))
    fair = fair_check(client, source["id"])

    assert fair["F"]["result"] == "fail"
    assert fair["F"]["error"]
    assert fair["A"]["result"] == "skipped"


def test_a_mapping_naming_a_column_the_source_lost_reports_it_by_name(
    client, csv_path, graph_reader
):
    mapping = {"version": "1.0", "node_mappings": [
        {"id": "asset", "label": "Asset", "key_property": "asset_id",
         "properties": [{"name": "asset_id", "column": "Asset ID"},
                        {"name": "archived", "column": "PI Archived"}]},
    ]}
    fair = fair_check(client, mapped_source(client, csv_path, mapping)["id"])

    assert fair["I"]["result"] == "warn"
    assert fair["I"]["missing_columns"] == ["PI Archived"]
    assert fair["overall"] == "warn"


def test_sample_size_is_honoured_and_capped(client, csv_with_sites, graph_reader):
    source = mapped_source(client, csv_with_sites)

    assert fair_check(client, source["id"], "?sample_size=1")["I"]["sample_size"] == 1
    assert fair_check(client, source["id"], "?sample_size=999")["sample_size"] == 50
    # Junk is a request for a preview, not a reason to refuse one.
    assert fair_check(client, source["id"], "?sample_size=lots")["sample_size"] == 10


def test_neo4j_being_unconfigured_degrades_the_preview_rather_than_failing_it(
    client, csv_with_sites
):
    """No graph_reader fixture here: the app has no Neo4j at all."""
    source = mapped_source(client, csv_with_sites)
    fair = fair_check(client, source["id"])

    assert fair["I"]["result"] == "warn"
    assert fair["I"]["nodes"]["unknown"] == 6
    assert fair["I"]["nodes"]["new"] == 0
    assert any("not configured" in w for w in fair["I"]["warnings"])
    assert "[unknown]" in fair["I"]["preview"][0]


# ------------------------------------------------------------------ storage

def test_the_result_is_stored_under_fair_status_and_not_last_run(
    client, csv_with_sites, graph_reader
):
    source = mapped_source(client, csv_with_sites)
    fair_check(client, source["id"])

    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    assert stored["fair_status"]["overall"] == "pass"
    assert stored["fair_status"]["I"]["preview"]
    assert stored["fair_checked_at"]
    assert stored["last_run_status"] is None, "a FAIR check claimed a run happened"
    assert stored["last_run_at"] is None


def test_the_list_route_carries_the_status_for_the_card_badge(
    client, csv_with_sites, graph_reader
):
    source = mapped_source(client, csv_with_sites)
    fair_check(client, source["id"])

    listed = client.get("/api/pipeline/sources").get_json()["sources"]
    entry = next(s for s in listed if s["id"] == source["id"])
    assert entry["fair_status"]["overall"] == "pass"
    assert [entry["fair_status"][l]["result"] for l in "FAIR"] == ["pass"] * 4


def test_preflight_stores_the_same_shape_as_the_full_check(
    client, csv_with_sites, graph_reader
):
    """One column, one shape — otherwise the card's badge depends on which ran last."""
    source = mapped_source(client, csv_with_sites)
    client.post(f"/api/pipeline/sources/{source['id']}/preflight")

    stored = client.get(f"/api/pipeline/sources/{source['id']}").get_json()["source"]
    status = stored["fair_status"]
    assert status["check"] == "preflight"
    assert [status[l]["result"] for l in "FAIR"] == ["pass"] * 4
    assert status["overall"] == "pass"
    assert status["fair_ok"] is True


# -------------------------------------------------------------- zero writes

def test_the_check_writes_nothing_even_when_a_writer_is_available(
    client, csv_with_sites, graph_reader, fake_graph
):
    """``fake_graph`` is the writer a real run would use. It must stay untouched."""
    source = mapped_source(client, csv_with_sites)
    fair_check(client, source["id"])

    assert fake_graph.batches == 0
    assert fake_graph.nodes == []
    assert fake_graph.relationships == []


def test_the_node_count_is_unchanged_across_a_check(
    client, csv_with_sites, graph_reader
):
    source = mapped_source(client, csv_with_sites)
    before = graph_reader.count()
    fair = fair_check(client, source["id"])
    after = graph_reader.count()

    assert before == after == 1
    assert fair["I"]["nodes"]["total"] == 6, "the check did resolve nodes; it just kept them"
    written = [q for q in graph_reader.queries
               if any(w in q.upper() for w in ("CREATE", "MERGE", "DELETE", "SET "))]
    assert written == []


def test_running_the_check_twice_gives_the_same_answer(
    client, csv_with_sites, graph_reader
):
    """Idempotent, which is only true because nothing in the path has side effects."""
    source = mapped_source(client, csv_with_sites)
    first = fair_check(client, source["id"])
    second = fair_check(client, source["id"])

    first.pop("checked_at")
    second.pop("checked_at")
    assert first == second


# ------------------------------------------------------------------ the card

def test_the_card_has_a_fair_check_button_and_a_panel_to_render_into(client):
    body = client.get("/pipeline/sources").get_data(as_text=True)
    assert 'data-testid="fair-check-btn"' in body
    assert 'data-testid="fair-panel"' in body
    assert 'data-testid="fair-badge"' in body
    assert 'data-testid="fair-preview"' in body
    assert '/fair-check' in body
    # Updated in place from the response, not by reloading the list: the check
    # changes nothing else on the page, and a reload would discard the panel.
    assert 'badge.outerHTML = fairBadgeHtml(fair)' in body
