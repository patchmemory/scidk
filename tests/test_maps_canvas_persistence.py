"""Maps canvas persistence: a loaded saved map or query result must not be replaced
by a late default-Schema render.

These tests drive the *real* Maps template (``_maps_app.html``, shared by direct
``/map`` and Knowledge -> Maps) in headless Chromium. The page and its static assets
come from the Flask app; only the data endpoints are mocked, so the default-schema
request can be held and released at will - which is the race that overwrote the
canvas. No graph, no network, no credentials.

Skipped when Playwright's Chromium is unavailable.
"""
import json
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ORIGIN = "http://scidk.test"

DEFAULT_SCHEMA = {
    "nodes": [
        {"label": "DefaultAlpha", "count": 3, "source": "graph"},
        {"label": "DefaultBeta", "count": 2, "source": "graph"},
    ],
    "edges": [{"start_label": "DefaultAlpha", "rel_type": "DEFAULT_REL",
               "end_label": "DefaultBeta", "count": 1, "source": "graph"}],
}

QUERY_ROWS = [{
    "n": {"id": 101, "labels": ["Sample"], "properties": {"name": "sample-one"}, "element_id": "e101"},
    "r": {"id": 900, "type": "HAS_PART", "start_node": 101, "end_node": 102, "properties": {}},
    "m": {"id": 102, "labels": ["Part"], "properties": {"name": "part-one"}, "element_id": "e102"},
}]

SAVED_MAP = {
    "id": "map-1", "name": "Persistence Map", "description": "", "tags": "",
    "created_at": 1.0, "updated_at": 1.0, "last_used_at": None,
    "query": "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 5",
    "filters": {},
    "visualization": {"mode": "instance"},
}


@pytest.fixture(scope="module")
def browser():
    # Chromium keeps a unix socket inside its profile dir; the suite's repo-local
    # TMPDIR is deep enough to exceed the 108-char socket path limit. Give the
    # Playwright driver (which creates the profile) a short, throwaway TMPDIR.
    short_tmp = tempfile.mkdtemp(prefix="pw-", dir="/tmp")
    saved = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = short_tmp
    try:
        pw = sync_api.sync_playwright().start()
    finally:
        if saved is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = saved
    b = None
    try:
        try:
            b = pw.chromium.launch(args=["--no-sandbox"])
        except Exception as default_exc:
            # The Python package may expect a newer Chromium build than the one
            # installed; fall back to any installed Playwright Chromium.
            candidates = sorted((Path.home() / ".cache" / "ms-playwright").glob(
                "chromium-*/chrome-linux*/chrome"), reverse=True)
            for exe in candidates:
                try:
                    b = pw.chromium.launch(executable_path=str(exe), args=["--no-sandbox"])
                    break
                except Exception:
                    continue
            if b is None:
                pytest.skip(f"Chromium unavailable: {default_exc}")
        yield b
    finally:
        if b is not None:
            b.close()
        pw.stop()
        shutil.rmtree(short_tmp, ignore_errors=True)


class MapsPage:
    """A Maps page whose default-schema responses are held until released."""

    def __init__(self, browser, app, html, saved_map):
        self.app = app
        self.saved_map = saved_map
        self.held_schema = []        # routes of default-schema requests not yet answered
        self.schema_requests = 0
        self.errors = []
        self.context = browser.new_context()
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("dialog", lambda d: d.accept())
        self.html = html
        self.page.route("**/*", self._route)

    # -- request handling ----------------------------------------------------
    def _json(self, route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _route(self, route):
        req = route.request
        url = urlparse(req.url)
        if url.hostname != "scidk.test":
            return route.abort()
        path = url.path
        if path.startswith("/static/"):
            f = Path(self.app.static_folder) / path[len("/static/"):]
            if f.is_file():
                ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return route.fulfill(status=200, content_type=ctype, body=f.read_bytes())
            return route.fulfill(status=404, body="")
        if path == "/api/graph/schema/combined":
            self.schema_requests += 1
            self.held_schema.append(route)      # answered later by release_schema()
            return
        if path == "/api/graph/management-connection":
            return self._json(route, {"connection": {
                "id": "conn-1", "display_name": "Test", "database": "neo4j",
                "connection_id": "0123456789abcdef0123"}})
        if path == "/api/maps/saved":
            return self._json(route, {"status": "ok", "maps": [self.saved_map]})
        if path.startswith("/api/maps/saved/"):
            if path.endswith("/use"):
                return self._json(route, {"status": "ok"})
            return self._json(route, {"status": "ok", "map": self.saved_map})
        if path == "/api/graph/query":
            return self._json(route, {"status": "ok", "results": QUERY_ROWS,
                                      "result_count": 1, "execution_time_ms": 1})
        if path.startswith("/api/"):
            return self._json(route, {"status": "ok", "layers": [], "maps": [], "queries": []})
        if path in ("/map", "/knowledge"):
            return route.fulfill(status=200, content_type="text/html", body=self.html)
        return route.fulfill(status=204, body="")

    def release_schema(self):
        """Resolve every held default-schema request (late, after the user acted)."""
        held, self.held_schema = self.held_schema, []
        for r in held:
            self._json(r, DEFAULT_SCHEMA)
        self.page.wait_for_timeout(700)     # let the stale continuation run

    # -- page helpers -------------------------------------------------------
    def open(self, path):
        self.page.goto(ORIGIN + path)
        self.page.wait_for_function(
            "window.cytoscapeInstances && window.cytoscapeInstances['tab-1']", timeout=15000)
        self.page.wait_for_selector("#neo4j-connection-select option[value='conn-1']",
                                    state="attached", timeout=15000)

    def node_ids(self, tab="tab-1"):
        return sorted(self.page.evaluate(
            "(t) => window.cytoscapeInstances[t].nodes().map(n => n.id())", tab))

    def node_labels(self, tab="tab-1"):
        return sorted(self.page.evaluate(
            "(t) => window.cytoscapeInstances[t].nodes().map(n => String(n.data('label')))", tab))

    def control_mode(self):
        return self.page.evaluate(
            "document.querySelector('input[name=\"viz-mode\"]:checked').value")

    def state(self, tab="tab-1"):
        return self.page.evaluate("(t) => JSON.parse(JSON.stringify(window.mapTabStore.get(t)))", tab)

    def start_default_schema_request(self):
        """A user toggles Instance -> Schema, issuing a (held) default-schema fetch."""
        self.page.locator("[data-testid=mode-instance]").check()
        self.page.locator("[data-testid=mode-schema]").check()
        self.page.wait_for_function("1", timeout=1000)
        assert self.schema_requests >= 1

    def load_saved_map(self):
        self.page.locator(".map-item .load-btn").first.click()

    def run_query(self, text="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 5"):
        self.page.evaluate("(q) => window.tabEditors['tab-1'].setValue(q)", text)
        self.page.locator(".run-query-tab-1").click()
        self.wait_for_result()

    def wait_for_result(self, tab="tab-1"):
        self.page.wait_for_function(
            "(t) => window.mapTabStore.get(t).renderKind === 'query-result'", arg=tab, timeout=10000)

    def close(self):
        self.context.close()


@pytest.fixture(params=["/map", "/knowledge?view=graph"], ids=["direct-map", "knowledge-maps"])
def maps(request, browser, app, client):
    # The routes only call render_template() after the graph-management access
    # gate (a named session + read grant). That gate is policy and is not what is
    # under test, so render the very templates the routes serve directly.
    from flask import render_template
    path = request.param
    with app.test_request_context(path.split("?")[0] if path == "/map" else path):
        if path == "/map":
            body = render_template("map.html", schema_summary={})
        else:
            body = render_template("gui/knowledge.html", view="maps")
    assert "map_tab_state.js" in body, f"{path} must load the per-tab state module"
    mp = MapsPage(browser, app, body, dict(SAVED_MAP))
    mp.open(path)
    yield mp
    assert mp.errors == [], f"page errors: {mp.errors}"
    mp.close()


INSTANCE_IDS = ["101", "102"]


def test_saved_map_survives_late_default_schema(maps):
    """Load a saved map, THEN resolve a delayed default-schema request."""
    maps.start_default_schema_request()
    maps.load_saved_map()
    maps.wait_for_result()
    assert maps.node_ids() == INSTANCE_IDS

    maps.release_schema()                       # the late default Schema response

    assert maps.node_ids() == INSTANCE_IDS, "late schema response replaced the loaded map"
    assert "DefaultAlpha" not in maps.node_labels()
    assert maps.control_mode() == "instance"
    st = maps.state()
    assert st["savedMapId"] == "map-1" and st["renderKind"] == "query-result"
    assert st["renderedMode"] == "instance"


def test_schema_mode_saved_map_issues_no_default_schema_request(maps):
    """A saved map in Schema mode must render its own result, not fetch the default."""
    maps.saved_map["visualization"] = {"mode": "schema"}
    before = maps.schema_requests
    maps.load_saved_map()
    maps.wait_for_result()
    labels = maps.node_labels()
    maps.release_schema()
    assert maps.schema_requests == before, "loading a saved map started a default-schema fetch"
    assert maps.node_labels() == labels
    assert "DefaultAlpha" not in labels
    assert maps.control_mode() == "schema"


def test_query_result_survives_late_initialization(maps):
    """Run a query, THEN resolve delayed initialization (Instance mode)."""
    maps.start_default_schema_request()                  # held fetch, Schema
    maps.page.locator("[data-testid=mode-instance]").check()   # deliberate change -> stale
    maps.run_query()
    assert maps.node_ids() == INSTANCE_IDS

    maps.release_schema()

    assert maps.node_ids() == INSTANCE_IDS
    assert maps.control_mode() == "instance"
    assert maps.state()["queryText"].startswith("MATCH")


def test_query_result_survives_late_schema_in_schema_mode(maps):
    maps.start_default_schema_request()
    maps.run_query()                                      # Schema control, result rendered
    labels = maps.node_labels()
    assert "DefaultAlpha" not in labels and labels
    maps.release_schema()
    assert maps.node_labels() == labels
    assert maps.control_mode() == "schema"


def test_switching_tabs_and_returning_keeps_state(maps):
    maps.page.locator("[data-testid=mode-instance]").check()
    maps.run_query()
    ids = maps.node_ids()
    assert ids == INSTANCE_IDS

    maps.page.locator("#add-tab-btn").click()
    maps.page.wait_for_function("window.cytoscapeInstances['tab-2']", timeout=10000)
    assert maps.node_ids("tab-2") == []
    assert maps.state("tab-2")["hasRender"] is False

    maps.page.locator(".map-tab[data-tab-id='tab-1'] .map-tab-title").click()
    maps.page.wait_for_timeout(500)
    assert maps.node_ids("tab-1") == INSTANCE_IDS
    assert maps.control_mode() == "instance"
    assert maps.state("tab-1")["renderKind"] == "query-result"
    assert maps.schema_requests == 0, "returning to a tab re-initialised it"


def test_late_schema_after_tab_switch_and_return(maps):
    maps.start_default_schema_request()
    maps.page.locator("[data-testid=mode-instance]").check()
    maps.run_query()
    maps.page.locator("#add-tab-btn").click()
    maps.page.wait_for_function("window.cytoscapeInstances['tab-2']", timeout=10000)
    maps.page.locator(".map-tab[data-tab-id='tab-1'] .map-tab-title").click()
    maps.release_schema()
    assert maps.node_ids("tab-1") == INSTANCE_IDS
    assert maps.node_ids("tab-2") == []
    assert maps.control_mode() == "instance"


def test_control_matches_displayed_graph_after_query(maps):
    """Run in Schema mode and in Instance mode; the control tracks what is drawn."""
    maps.run_query()
    assert maps.control_mode() == "schema" == maps.state()["renderedMode"]
    maps.page.locator("[data-testid=mode-instance]").check()
    maps.run_query()
    assert maps.control_mode() == "instance" == maps.state()["renderedMode"]
    assert maps.node_ids() == INSTANCE_IDS


def test_synthetic_change_event_never_renders(maps):
    """Script-dispatched change events only synchronise the control."""
    maps.run_query()
    labels = maps.node_labels()
    before = maps.schema_requests
    maps.page.evaluate(
        "() => { const r = document.querySelector('[data-testid=mode-schema]');"
        " r.checked = true; r.dispatchEvent(new Event('change')); }")
    maps.release_schema()
    assert maps.schema_requests == before
    assert maps.node_labels() == labels


def test_default_schema_only_for_pristine_tab(maps):
    """Background default rendering is refused once a tab holds content."""
    maps.run_query()
    labels = maps.node_labels()
    before = maps.schema_requests
    ok = maps.page.evaluate("() => window.renderSchemaVisualization('tab-1')")
    assert ok is False
    assert maps.schema_requests == before
    assert maps.node_labels() == labels

    # A genuinely new tab may still get the default schema.
    maps.page.locator("#add-tab-btn").click()
    maps.page.wait_for_function("window.cytoscapeInstances['tab-2']", timeout=10000)
    # Fire-and-forget: the call resolves only once the held request is released.
    maps.page.evaluate("() => { window.renderSchemaVisualization('tab-2'); }")
    maps.page.wait_for_function("1", timeout=500)
    assert maps.schema_requests == before + 1
    maps.release_schema()
    assert maps.node_ids("tab-2") == ["DefaultAlpha", "DefaultBeta"]
    assert maps.node_labels("tab-1") == labels


def test_loading_another_map_wins_over_pending_default(maps):
    """Superseded work never lands: a second user action invalidates the first."""
    maps.start_default_schema_request()
    maps.page.locator("[data-testid=mode-instance]").check()
    maps.run_query()
    first = maps.node_ids()
    maps.load_saved_map()
    maps.page.wait_for_timeout(1500)            # load + auto-run
    maps.release_schema()
    assert maps.node_ids() == first == INSTANCE_IDS
    assert maps.state()["savedMapId"] == "map-1"
