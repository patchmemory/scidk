"""The FAIR check: the letters, the sample, the preview, and the zero writes.

Three things here are load-bearing beyond the obvious assertions:

* **Nothing writes.** The runner is handed a writer that fails the test if it is
  ever called, so "zero Neo4j writes" is enforced by the fixture rather than
  checked afterwards. A reader that counts its queries stands in for the graph.
* **The engine's wording is pinned.** ``fair_check`` splits a row's failures into
  transform failures and key failures by reading the messages
  :class:`~scidk.pipeline.mapping_engine.RowMapping` carries. If the engine
  rewords one, the tests below fail — which is the point: the alternative is the
  report quietly losing its "column" column.
* **Idempotence.** Running the check twice must produce the same document, with
  ``checked_at`` the only difference. That is what makes it safe to press the
  button, and it only holds because nothing in the path has side effects.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Set

from scidk.pipeline.fair_check import (
    DEFAULT_SAMPLE_SIZE,
    MAX_SAMPLE_SIZE,
    PriorRun,
    clamp_sample_size,
    neo4j_key_lookup,
    prior_run_for_source,
    run_fair_check,
)
from scidk.pipeline.plugin_base import DataSourcePlugin
from scidk.pipeline.runner import PipelineRunner
from scidk.pipeline.transforms import TransformError

#: Two complete rows: one Project and two Person roles each, everything keyed.
ROWS = [
    {"ID": "CAC-2024-0042", "PI": "jane@mit.edu", "Submitter": "bob@mit.edu"},
    {"ID": "CAC-2024-0043", "PI": "bob@mit.edu", "Submitter": "kim@mit.edu"},
]

#: Five rows, the third with no submitter. One row in five is exactly
#: KEY_FAILURE_FAIL_RATIO, and the rule is *more than* a fifth — so this is the
#: boundary case that must warn rather than fail.
GAPPY_ROWS = ROWS + [
    {"ID": "CAC-2024-0044", "PI": "amy@mit.edu", "Submitter": ""},
    {"ID": "CAC-2024-0045", "PI": "kim@mit.edu", "Submitter": "amy@mit.edu"},
    {"ID": "CAC-2024-0046", "PI": "lee@mit.edu", "Submitter": "lee@mit.edu"},
]

COLUMNS = ["ID", "PI", "Submitter"]

MAPPING = {
    "version": "1.0",
    "node_mappings": [
        {"id": "project", "label": "Project", "key_property": "code",
         "properties": [{"name": "code", "column": "ID"}]},
        {"id": "pi", "label": "Person", "key_property": "email",
         "properties": [{"name": "email", "column": "PI"}]},
        {"id": "submitter", "label": "Person", "key_property": "email",
         "properties": [{"name": "email", "column": "Submitter"}]},
    ],
    "relationship_mappings": [
        {"type": "PI_OF", "from": "pi", "to": "project"},
        {"type": "SUBMITTED", "from": "submitter", "to": "project"},
    ],
}


class FakePlugin(DataSourcePlugin):
    """Scriptable stand-in for a data source plugin."""

    name = "fake"
    display_name = "Fake source"
    source_types = ["fake"]

    def __init__(
        self,
        rows: Optional[List[Dict[str, Any]]] = None,
        columns: Optional[List[str]] = None,
        find_ok: bool = True,
        access_ok: bool = True,
        fetch_raises: bool = False,
        transforms: Optional[Dict[str, Any]] = None,
    ):
        self.rows = ROWS if rows is None else rows
        self.columns = COLUMNS if columns is None else columns
        self.find_ok = find_ok
        self.access_ok = access_ok
        self.fetch_raises = fetch_raises
        self.transforms = transforms or {}
        self.calls: List[str] = []

    def find(self, config):
        self.calls.append("find")
        return {
            "ok": self.find_ok,
            "columns": self.columns,
            "row_count": len(self.rows),
            "sample": self.rows[:3],
            "metadata": {},
            "error": None if self.find_ok else "source unreachable",
        }

    def access(self, config):
        self.calls.append("access")
        return {
            "ok": self.access_ok,
            "auth_method": "rclone_oauth",
            "error": None if self.access_ok else "credential rejected",
        }

    def fetch(self, config) -> Iterator[Dict[str, Any]]:
        self.calls.append("fetch")
        if self.fetch_raises:
            raise IOError("connection reset")
        return iter(self.rows)

    def transform_library(self):
        return dict(self.transforms)


class ForbiddenWriter:
    """A writer that fails the test if the FAIR check ever reaches it."""

    def write_declared_nodes(self, nodes, relationships):  # pragma: no cover
        raise AssertionError("the FAIR check wrote to Neo4j")


class FakeReader:
    """A ``Neo4jReader`` holding a fixed set of existing keys.

    Records every query, so a test can assert the lookup is grouped rather than
    one round trip per node — and that a check with nothing to look up makes no
    query at all.
    """

    def __init__(self, existing: Optional[Set[str]] = None, raises: bool = False):
        self.existing = existing or set()
        self.raises = raises
        self.queries: List[str] = []

    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        self.queries.append(query)
        if self.raises:
            raise RuntimeError("bolt connection closed")
        values = (parameters or {}).get("values") or []
        return [{"key": v} for v in values if str(v) in self.existing]


def make_runner(plugin: Optional[FakePlugin] = None, mapping: Any = None) -> PipelineRunner:
    return PipelineRunner(
        plugin or FakePlugin(),
        MAPPING if mapping is None else mapping,
        {"source_path": "fake:x"},
        # Present precisely so a stray write would be caught. The check must not
        # use it, and building the runner without one would hide a regression that
        # only bites the route, which does pass a real source config.
        writer=ForbiddenWriter(),
    )


def check(plugin=None, mapping=None, reader=None, **kwargs) -> Dict[str, Any]:
    lookup = neo4j_key_lookup(reader) if reader is not None else None
    return run_fair_check(make_runner(plugin, mapping), key_lookup=lookup, **kwargs)


# ------------------------------------------------------------- the sequence

def test_all_four_letters_pass_on_a_healthy_source():
    result = check(reader=FakeReader())
    assert [result[l]["result"] for l in "FAIR"] == ["pass", "pass", "pass", "pass"]
    assert result["overall"] == "pass"
    assert result["fair_ok"] is True


def test_an_unfindable_source_fails_F_and_stops():
    plugin = FakePlugin(find_ok=False)
    result = check(plugin)

    assert result["F"]["result"] == "fail"
    assert "unreachable" in result["F"]["error"]
    assert result["A"]["result"] == "skipped"
    assert result["I"]["result"] == "skipped"
    assert plugin.calls == ["find"], "A and I ran after F failed"


def test_a_rejected_credential_fails_A_and_stops_before_the_mapping():
    plugin = FakePlugin(access_ok=False)
    result = check(plugin)

    assert result["F"]["result"] == "pass"
    assert result["A"]["result"] == "fail"
    assert "credential rejected" in result["A"]["error"]
    assert result["I"]["result"] == "skipped"
    assert "fetch" not in plugin.calls


def test_A_does_not_depend_on_the_mapping():
    """Whether a credential works is not a question about which columns are mapped."""
    result = check(mapping={}, mapping_problem="this source has no mapping config")

    assert result["F"]["result"] == "pass"
    assert result["A"]["result"] == "pass"
    assert result["A"]["auth_method"] == "rclone_oauth"
    assert result["I"]["result"] == "fail"
    assert result["I"]["errors"] == ["this source has no mapping config"]


def test_a_letter_never_reached_is_skipped_not_failed():
    """"The mapping was never checked" and "the mapping is broken" differ."""
    result = check(FakePlugin(access_ok=False))
    assert result["I"]["result"] == "skipped"
    assert result["I"] != {"result": "fail"}


# ------------------------------------------------------------- I: the config

def test_a_malformed_config_is_reported_before_any_row_is_read():
    plugin = FakePlugin()
    mapping = {"version": "1.0", "node_mappings": [
        {"id": "p", "label": "Project", "key_property": "nope",
         "properties": [{"name": "code", "column": "ID"}]},
    ]}
    result = check(plugin, mapping)

    assert result["I"]["result"] == "fail"
    assert any("key_property 'nope'" in e for e in result["I"]["errors"])
    assert "fetch" not in plugin.calls, "rows were read despite an invalid config"


def test_an_unknown_transform_fails_I_because_the_config_does_not_validate():
    """``preflight()`` calls this R. Here R is drift, and the config check catches it."""
    mapping = {"version": "1.0", "node_mappings": [
        {"id": "p", "label": "Project", "key_property": "code",
         "properties": [{"name": "code", "column": "ID", "transform": "no_such"}]},
    ]}
    result = check(mapping=mapping)

    assert result["I"]["result"] == "fail"
    assert any("no_such" in e for e in result["I"]["errors"])


def test_a_broken_row_stream_is_reported_as_a_fetch_failure():
    result = check(FakePlugin(fetch_raises=True))
    assert result["I"]["result"] == "fail"
    assert any("connection reset" in e for e in result["I"]["errors"])


# ------------------------------------------------------- I: missing columns

def test_a_missing_key_column_fails_I_and_names_it():
    result = check(FakePlugin(columns=["PI", "Submitter"]))

    assert result["I"]["result"] == "fail"
    assert result["I"]["missing_columns"] == ["ID"]
    assert any("project" in e and "merge key" in e for e in result["I"]["errors"])


def test_a_missing_property_column_only_warns():
    """A config broader than one export still runs; the property is just omitted."""
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project", "key_property": "code",
             "properties": [{"name": "code", "column": "ID"},
                            {"name": "archived", "column": "PI Archived"}]},
        ],
    }
    result = check(mapping=mapping, reader=FakeReader())

    assert result["I"]["result"] == "warn"
    assert result["I"]["missing_columns"] == ["PI Archived"]
    assert any("'PI Archived'" in w for w in result["I"]["warnings"])
    assert result["I"]["rows_resolved"] == 2, "the run was refused over a warning"


def test_a_missing_column_is_reported_by_name_and_not_as_a_crash():
    result = check(FakePlugin(columns=[]))
    assert result["I"]["missing_columns"] == ["ID", "PI", "Submitter"]


# -------------------------------------------------------------- I: the sample

def test_the_sample_is_capped_and_defaults_to_ten():
    plugin = FakePlugin(rows=[{"ID": f"P-{i}", "PI": "a@b.c"} for i in range(80)])
    assert check(plugin, reader=FakeReader())["I"]["sample_size"] == DEFAULT_SAMPLE_SIZE
    assert check(plugin, reader=FakeReader(), sample_size=999)["I"]["sample_size"] \
        == MAX_SAMPLE_SIZE


def test_clamp_sample_size_takes_junk_as_the_default():
    assert clamp_sample_size(None) == DEFAULT_SAMPLE_SIZE
    assert clamp_sample_size("lots") == DEFAULT_SAMPLE_SIZE
    assert clamp_sample_size("25") == 25
    assert clamp_sample_size(0) == 1
    assert clamp_sample_size(1000) == MAX_SAMPLE_SIZE


def test_a_source_with_no_rows_warns_rather_than_passing_silently():
    result = check(FakePlugin(rows=[]))
    assert result["I"]["result"] == "warn"
    assert result["I"]["sample_size"] == 0
    assert any("no rows" in w for w in result["I"]["warnings"])


def test_key_resolution_failures_are_counted_and_attributed_to_their_row():
    """Row 3's submitter column is empty, so that Person cannot be keyed."""
    result = check(FakePlugin(rows=GAPPY_ROWS), reader=FakeReader())

    assert result["I"]["rows_with_key_failure"] == 1
    failure = result["I"]["key_failures"][0]
    assert failure["row"] == 3, "row numbers in the report are 1-based"
    assert "submitter" in failure["error"]
    assert "no non-empty key property" in failure["error"]
    # Row 3 still produced its Project and its PI, so it is resolved, not skipped.
    assert result["I"]["rows_resolved"] == 5
    assert result["I"]["rows_skipped"] == 0
    assert result["I"]["result"] == "warn"


def test_key_failures_on_most_of_the_sample_fail_I():
    rows = [{"ID": f"P-{i}", "PI": "", "Submitter": ""} for i in range(4)]
    result = check(FakePlugin(rows=rows), reader=FakeReader())

    assert result["I"]["result"] == "fail"
    assert result["I"]["key_failure_ratio"] == 1.0
    assert any("could not resolve a merge key" in e for e in result["I"]["errors"])


def test_a_transform_failure_names_its_row_and_its_column():
    def explode(value):
        raise TransformError("not a date")

    mapping = {
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project", "key_property": "code",
             "properties": [{"name": "code", "column": "ID"},
                            {"name": "archived", "column": "PI",
                             "transform": "explode"}]},
        ],
    }
    result = check(FakePlugin(transforms={"explode": explode}), mapping,
                   reader=FakeReader())

    failures = result["I"]["transform_failures"]
    assert len(failures) == 2, failures
    assert failures[0] == {
        "row": 1,
        "column": "PI",
        "property": "project.archived",
        "error": "project.archived: not a date",
    }
    assert result["I"]["result"] == "warn"


def test_a_row_rejected_by_row_filter_is_reported_as_skipped():
    mapping = dict(MAPPING, row_filter={"require_any_non_empty": ["Submitter"],
                                        "on_reject": "skip_silently"})
    result = check(FakePlugin(rows=GAPPY_ROWS), mapping, reader=FakeReader())

    assert result["I"]["rows_skipped"] == 1
    assert result["I"]["rows_resolved"] == 4
    assert result["I"]["preview"][2].startswith("Row 3 → skipped: ")


# ------------------------------------------------- I: new versus merge, preview

def test_the_preview_distinguishes_new_from_merge():
    reader = FakeReader(existing={"CAC-2024-0042", "bob@mit.edu"})
    result = check(reader=reader)

    assert result["I"]["preview"] == [
        "Row 1 → Project(CAC-2024-0042) [merge], Person(jane@mit.edu) [new], "
        "Person(bob@mit.edu) [merge] → PI_OF, SUBMITTED",
        "Row 2 → Project(CAC-2024-0043) [new], Person(bob@mit.edu) [merge], "
        "Person(kim@mit.edu) [new] → PI_OF, SUBMITTED",
    ]
    assert result["I"]["nodes"] == {"total": 6, "new": 3, "merge": 3, "unknown": 0}
    assert result["I"]["relationships"] == 4


def test_the_lookup_is_grouped_by_label_not_one_query_per_node():
    reader = FakeReader()
    check(reader=reader)
    # Two labels, one key property each: Project.code and Person.email.
    assert len(reader.queries) == 2, reader.queries
    assert all(q.startswith("MATCH (n:") and " IN $values" in q for q in reader.queries)


def test_an_unreachable_graph_reports_unknown_rather_than_new():
    """Guessing "new" from a failed read would be a fabrication, not a default."""
    result = check(reader=FakeReader(raises=True))

    assert result["I"]["nodes"]["unknown"] == 6
    assert result["I"]["nodes"]["new"] == 0
    assert "[unknown]" in result["I"]["preview"][0]


def test_no_lookup_at_all_says_why():
    result = check(lookup_unavailable="Neo4j is not configured")

    assert result["I"]["nodes"]["unknown"] == 6
    assert any("Neo4j is not configured" in w for w in result["I"]["warnings"])
    assert result["I"]["result"] == "warn"


def test_a_hostile_label_is_never_interpolated_into_cypher():
    """The engine rejects it first; the lookup refuses it again regardless."""
    reader = FakeReader()
    lookup = neo4j_key_lookup(reader)
    assert lookup("Project) DETACH DELETE (n", "code", ["x"]) is None
    assert lookup("Project", "code) DETACH DELETE (n", ["x"]) is None
    assert reader.queries == []


# --------------------------------------------------------------- zero writes

def test_the_check_never_writes_even_with_a_writer_attached():
    runner = make_runner()  # ForbiddenWriter raises if it is ever called
    result = run_fair_check(runner, key_lookup=neo4j_key_lookup(FakeReader()))
    assert result["overall"] == "pass"


def test_the_graph_is_only_ever_read():
    reader = FakeReader()
    check(reader=reader)
    assert all("MATCH" in q for q in reader.queries)
    assert not any(word in q.upper() for q in reader.queries
                   for word in ("CREATE", "MERGE", "DELETE", "SET "))


def test_running_the_check_twice_produces_the_same_result():
    first = check(reader=FakeReader(existing={"CAC-2024-0042"}))
    second = check(reader=FakeReader(existing={"CAC-2024-0042"}))
    first.pop("checked_at")
    second.pop("checked_at")
    assert first == second


# ------------------------------------------------------------------------ R

class FakeHistory:
    """``RunHistory.list_runs`` over a fixed list of runs."""

    def __init__(self, runs: Sequence[Dict[str, Any]]):
        self.runs = list(runs)

    def list_runs(self, pipeline_id: Optional[str] = None, limit: int = 50):
        runs = [r for r in self.runs if pipeline_id is None
                or r.get("pipeline_id") == pipeline_id]
        return runs[:limit]


def a_run(source_id="s1", pipeline_id="src-s1", status="success", **summary):
    return {
        "pipeline_id": pipeline_id,
        "triggered_by": "manual",
        "in_flight": False,
        "completed_at": "2026-08-01T02:00:00Z",
        "steps": [{"source_id": source_id, "status": status, "summary": summary}],
    }


def test_R_passes_trivially_on_a_first_run():
    result = check(reader=FakeReader())
    assert result["R"]["result"] == "pass"
    assert result["R"]["note"] == "no prior run to compare"


def test_R_warns_on_a_row_count_that_moved_more_than_ten_percent():
    prior = PriorRun(ran_at="2026-08-01T02:00:00Z", summary={"row_count_estimate": 10})
    result = check(reader=FakeReader(), prior=prior)

    assert result["R"]["result"] == "warn"
    assert any("the source has 2 rows" in w for w in result["R"]["warnings"])
    assert result["overall"] == "warn"


def test_R_does_not_warn_when_the_row_count_barely_moved():
    rows = [{"ID": f"P-{i}", "PI": "a@b.c", "Submitter": "a@b.c"} for i in range(10)]
    prior = PriorRun(summary={"row_count_estimate": 10})
    result = check(FakePlugin(rows=rows), reader=FakeReader(), prior=prior)
    assert result["R"]["result"] == "pass"


def test_R_warns_when_a_mapped_column_has_disappeared_since_the_last_run():
    """A dropped *property* column: I warns about it, and R says it is new since
    the last run, which is the part that explains why this run will differ."""
    mapping = {"version": "1.0", "node_mappings": [
        {"id": "project", "label": "Project", "key_property": "code",
         "properties": [{"name": "code", "column": "ID"},
                        {"name": "pi", "column": "PI"}]},
    ]}
    prior = PriorRun(summary={"columns": ["ID", "PI"], "rows_read": 2})
    result = check(FakePlugin(columns=["ID"]), mapping, reader=FakeReader(),
                   prior=prior)

    assert result["R"]["result"] == "warn"
    assert any("'PI'" in w for w in result["R"]["warnings"])


def test_R_warns_when_key_resolution_got_worse():
    prior = PriorRun(summary={"rows_read": 100, "rows_skipped": 0, "rows_with_errors": 0})
    result = check(FakePlugin(rows=GAPPY_ROWS), reader=FakeReader(), prior=prior)

    assert result["R"]["result"] == "warn"
    assert any("fail key resolution" in w for w in result["R"]["warnings"])


def test_R_never_fails():
    """A drifted source is still ingestible; R's job is to say so, not to refuse."""
    prior = PriorRun(summary={"row_count_estimate": 10_000, "columns": ["ID", "Gone"],
                              "rows_read": 10_000})
    result = check(reader=FakeReader(), prior=prior)

    assert result["R"]["result"] == "warn"
    assert result["R"]["result"] != "fail"
    assert result["overall"] == "warn"


def test_R_is_not_reached_when_I_fails():
    result = check(FakePlugin(columns=["PI"]))
    assert result["I"]["result"] == "fail"
    assert result["R"] == {"result": "skipped"}


# ------------------------------------------------------- finding a prior run

def test_the_prior_run_is_the_latest_successful_one_for_this_source():
    history = FakeHistory([
        a_run(status="error", rows_read=1),
        a_run(status="success", rows_read=2),
        a_run(status="success", rows_read=3),
    ])
    prior = prior_run_for_source(history, "s1", pipeline_id="src-s1")
    assert prior is not None and prior.summary["rows_read"] == 2


def test_an_in_flight_run_is_not_a_baseline():
    run = a_run()
    run["in_flight"] = True
    assert prior_run_for_source(FakeHistory([run]), "s1") is None


def test_a_run_of_a_different_source_is_not_a_baseline():
    assert prior_run_for_source(FakeHistory([a_run(source_id="other")]), "s1") is None


def test_a_shared_pipeline_run_counts_when_the_implicit_one_has_none():
    """A source that has only ever run inside a DAG still has a baseline."""
    history = FakeHistory([a_run(pipeline_id="nightly", rows_read=7)])
    prior = prior_run_for_source(history, "s1", pipeline_id="src-s1")
    assert prior is not None
    assert prior.pipeline_id == "nightly"


def test_no_history_at_all_is_no_prior_run():
    assert prior_run_for_source(FakeHistory([]), "s1", pipeline_id="src-s1") is None
