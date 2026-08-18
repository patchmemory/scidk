"""Runner behaviour, with the emphasis on how it handles a failing write.

``write_declared_nodes`` never raises and has no transaction. Both facts have
teeth:

* A run that wrote nothing at all returns a normal-looking result with its
  failures in ``result['errors']``. A runner that only watches for exceptions
  reports success on total failure, so several tests here assert that the
  ``errors`` list is read and that "declared nodes, wrote zero" is escalated.
* A failure partway through leaves everything before it committed. The runner
  cannot roll that back, so what it owes the user is an accurate report:
  ``'partial'`` status and ``writes_committed`` set.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List

import pytest

from scidk.pipeline.plugin_base import DataSourcePlugin
from scidk.pipeline.runner import MAX_REPORTED_MESSAGES, PipelineRunner


class FakePlugin(DataSourcePlugin):
    """A plugin whose four contract methods are scripted by the test."""

    name = "fake"
    display_name = "Fake source"
    source_types = ["fake"]

    def __init__(
        self,
        rows: List[Dict[str, Any]] = None,
        columns: List[str] = None,
        find_ok: bool = True,
        access_ok: bool = True,
        find_raises: bool = False,
        fetch_raises_after: int = None,
        transforms: Dict[str, Any] = None,
    ):
        self.rows = rows if rows is not None else [{"ID": "p1"}]
        self.columns = columns if columns is not None else ["ID"]
        self.find_ok = find_ok
        self.access_ok = access_ok
        self.find_raises = find_raises
        self.fetch_raises_after = fetch_raises_after
        self.transforms = transforms or {}
        self.calls: List[str] = []

    def find(self, config):
        self.calls.append("find")
        if self.find_raises:
            raise RuntimeError("provider exploded")
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
            "auth_method": "fake",
            "error": None if self.access_ok else "credential rejected",
        }

    def fetch(self, config) -> Iterator[Dict[str, Any]]:
        self.calls.append("fetch")

        def stream():
            for index, row in enumerate(self.rows):
                if self.fetch_raises_after is not None and index == self.fetch_raises_after:
                    raise IOError("connection reset mid-stream")
                yield row

        return stream()

    def transform_library(self):
        return dict(self.transforms)


class FakeWriter:
    """A ``write_declared_nodes`` stand-in, scriptable per batch."""

    def __init__(self, results: List[Dict[str, Any]] = None, raises_on_batch: int = None):
        self.results = results or []
        self.raises_on_batch = raises_on_batch
        self.batches: List[tuple] = []

    def write_declared_nodes(self, nodes, relationships):
        index = len(self.batches)
        self.batches.append((list(nodes), list(relationships)))
        if self.raises_on_batch is not None and index == self.raises_on_batch:
            raise ConnectionError("bolt connection closed")
        if index < len(self.results):
            return self.results[index]
        # Default: everything written, nothing wrong.
        return {
            "written_nodes": len(nodes),
            "written_relationships": len(relationships),
            "errors": [],
        }


MAPPING = {
    "version": "1.0",
    "node_mappings": [
        {
            "id": "project",
            "label": "Project",
            "key_property": "pid",
            "properties": [{"name": "pid", "column": "ID"}],
        }
    ],
}


def runner(plugin=None, writer=None, mapping=None, **kwargs) -> PipelineRunner:
    return PipelineRunner(
        plugin or FakePlugin(),
        mapping or MAPPING,
        {"source_path": "fake:x"},
        writer=writer,
        **kwargs,
    )


# ----------------------------------------------------------------- ordering

def test_calls_find_then_access_then_fetch_in_that_order():
    plugin = FakePlugin()
    runner(plugin, FakeWriter()).run()
    assert plugin.calls == ["find", "access", "fetch"]


def test_preflight_never_fetches():
    plugin = FakePlugin()
    runner(plugin, FakeWriter()).preflight()
    assert plugin.calls == ["find", "access"]
    assert "fetch" not in plugin.calls


# --------------------------------------------------------------- FAIR gate

def test_all_four_letters_pass_on_a_healthy_source():
    report = runner(FakePlugin(), FakeWriter()).preflight()
    assert report.fair == {"F": True, "A": True, "I": True, "R": True}


def test_unreachable_source_fails_F_and_writes_nothing():
    writer = FakeWriter()
    report = runner(FakePlugin(find_ok=False), writer).run()

    assert report.fair["F"] is False
    assert report.status == "error"
    assert writer.batches == [], "a failed FAIR gate must not write"
    assert any("source unreachable" in e for e in report.errors)


def test_rejected_credential_fails_A_and_writes_nothing():
    writer = FakeWriter()
    report = runner(FakePlugin(access_ok=False), writer).run()

    assert report.fair["A"] is False
    assert report.status == "error"
    assert writer.batches == []
    assert any("credential rejected" in e for e in report.errors)


def test_missing_column_fails_I_and_names_the_column():
    plugin = FakePlugin(columns=["SomethingElse"])
    report = runner(plugin, FakeWriter()).run()

    assert report.fair["I"] is False
    assert report.missing_columns == ["ID"]
    assert any("'ID'" in e for e in report.errors)
    assert "fetch" not in plugin.calls


def test_unknown_transform_fails_R():
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [{"name": "pid", "column": "ID", "transform": "no_such"}],
            }
        ],
    }
    report = runner(FakePlugin(), FakeWriter(), mapping=mapping).preflight()
    assert report.fair["R"] is False
    assert any("no_such" in e for e in report.errors)


def test_a_plugin_that_raises_where_the_contract_forbids_it_is_reported_not_propagated():
    report = runner(FakePlugin(find_raises=True), FakeWriter()).run()
    assert report.status == "error"
    assert report.fair["F"] is False
    assert any("provider exploded" in e for e in report.errors)


# ------------------------------------------------------------ happy path

def test_successful_run_reports_what_it_wrote():
    writer = FakeWriter()
    report = runner(FakePlugin(rows=[{"ID": "a"}, {"ID": "b"}]), writer).run()

    assert report.status == "success"
    assert (report.rows_read, report.nodes_written) == (2, 2)
    assert report.writes_committed is True
    assert report.errors == []
    assert report.duration_sec is not None


def test_dry_run_declares_but_never_writes():
    writer = FakeWriter()
    report = runner(FakePlugin(rows=[{"ID": "a"}]), writer).run(dry_run=True)

    assert writer.batches == []
    assert report.nodes_declared == 1 and report.nodes_written == 0
    assert report.writes_committed is False
    assert report.status == "success"


def test_no_writer_is_treated_as_a_dry_run_rather_than_a_crash():
    report = runner(FakePlugin(), writer=None).run()
    assert report.dry_run is True and report.nodes_written == 0


def test_limit_stops_the_stream_early():
    report = runner(FakePlugin(rows=[{"ID": str(i)} for i in range(10)]), FakeWriter()).run(limit=3)
    assert report.rows_read == 3


def test_rows_are_written_in_batches_so_memory_stays_bounded():
    plugin = FakePlugin(rows=[{"ID": str(i)} for i in range(10)])
    writer = FakeWriter()
    report = runner(plugin, writer, batch_rows=4).run()

    assert len(writer.batches) == 3, "10 rows at 4 per batch is 3 writes"
    assert [len(nodes) for nodes, _ in writer.batches] == [4, 4, 2]
    assert report.nodes_written == 10


def test_a_relationship_and_its_endpoints_land_in_the_same_batch():
    """A relationship is MATCHed, so both endpoints must already exist."""
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "project",
                "label": "Project",
                "key_property": "pid",
                "properties": [{"name": "pid", "column": "ID"}],
            },
            {
                "id": "person",
                "label": "Person",
                "key_property": "email",
                "properties": [{"name": "email", "column": "Email"}],
            },
        ],
        "relationship_mappings": [{"type": "SUBMITTED", "from": "person", "to": "project"}],
    }
    plugin = FakePlugin(
        rows=[{"ID": f"p{i}", "Email": f"u{i}@mit.edu"} for i in range(4)],
        columns=["ID", "Email"],
    )
    writer = FakeWriter()
    runner(plugin, writer, mapping=mapping, batch_rows=2).run()

    for nodes, relationships in writer.batches:
        labelled = {(n["label"], n["properties"][n["key_property"]]) for n in nodes}
        for rel in relationships:
            assert (rel["from_label"], rel["from_match"]["email"]) in labelled
            assert (rel["to_label"], rel["to_match"]["pid"]) in labelled


# --------------------------------------------- the failing-write behaviours

def test_write_errors_are_surfaced_and_not_swallowed():
    writer = FakeWriter(results=[{
        "written_nodes": 1,
        "written_relationships": 0,
        "errors": ["Failed to write node Project: Neo.ClientError.Statement.SyntaxError"],
    }])
    report = runner(FakePlugin(rows=[{"ID": "a"}, {"ID": "b"}]), writer, batch_rows=99).run()

    assert report.write_error_count == 1
    assert any("SyntaxError" in e for e in report.errors)


def test_declaring_nodes_and_writing_zero_is_an_error_not_a_success():
    """The exact trap: a 200-level path returning written_nodes: 0."""
    writer = FakeWriter(results=[{"written_nodes": 0, "written_relationships": 0, "errors": []}])
    report = runner(FakePlugin(rows=[{"ID": "a"}]), writer).run()

    assert report.status == "error"
    assert report.nodes_declared == 1 and report.nodes_written == 0
    assert any("wrote 0" in e for e in report.errors)
    assert report.writes_committed is False


def test_a_failure_after_a_successful_batch_is_partial_and_says_writes_are_committed():
    """No transaction, so the first batch stands. The report has to admit that."""
    writer = FakeWriter(results=[
        {"written_nodes": 2, "written_relationships": 0, "errors": []},
        {"written_nodes": 0, "written_relationships": 0, "errors": ["deadlock detected"]},
    ])
    plugin = FakePlugin(rows=[{"ID": "a"}, {"ID": "b"}, {"ID": "c"}, {"ID": "d"}])
    report = runner(plugin, writer, batch_rows=2).run()

    assert report.status == "partial"
    assert report.writes_committed is True
    assert report.nodes_written == 2
    assert "writes already committed" in report.summary_line()


def test_a_writer_that_raises_mid_run_is_recorded_as_partial():
    writer = FakeWriter(raises_on_batch=1)
    plugin = FakePlugin(rows=[{"ID": str(i)} for i in range(4)])
    report = runner(plugin, writer, batch_rows=2).run()

    assert report.status == "partial"
    assert report.writes_committed is True
    assert any("bolt connection closed" in e for e in report.errors)


def test_a_stream_that_dies_mid_run_is_recorded_with_what_was_already_written():
    plugin = FakePlugin(rows=[{"ID": str(i)} for i in range(6)], fetch_raises_after=4)
    writer = FakeWriter()
    report = runner(plugin, writer, batch_rows=2).run()

    assert report.status == "partial"
    assert report.rows_read == 4
    assert report.writes_committed is True
    assert any("connection reset mid-stream" in e for e in report.errors)


# ------------------------------------------------------------- row errors

def test_a_bad_row_does_not_stop_the_run_by_default():
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [
                    {"name": "pid", "column": "ID"},
                    {"name": "count", "column": "Count", "transform": "integer_coerce"},
                ],
            }
        ],
    }
    plugin = FakePlugin(
        rows=[{"ID": "a", "Count": "1"}, {"ID": "b", "Count": "nope"}, {"ID": "c", "Count": "3"}],
        columns=["ID", "Count"],
    )
    report = runner(plugin, FakeWriter(), mapping=mapping).run()

    assert report.rows_read == 3
    assert report.rows_with_errors == 1
    assert report.nodes_written == 3, "the bad cell cost a property, not a node"
    assert report.status == "partial"


def test_on_row_error_abort_stops_at_the_first_bad_row():
    mapping = {
        "version": "1.0",
        "options": {"on_row_error": "abort"},
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [
                    {"name": "pid", "column": "ID"},
                    {"name": "count", "column": "Count", "transform": "integer_coerce"},
                ],
            }
        ],
    }
    plugin = FakePlugin(
        rows=[{"ID": "a", "Count": "1"}, {"ID": "b", "Count": "nope"}, {"ID": "c", "Count": "3"}],
        columns=["ID", "Count"],
    )
    report = runner(plugin, FakeWriter(), mapping=mapping).run()

    assert report.rows_read == 2, "stopped on the bad row, did not read the third"
    assert any("abort" in e for e in report.errors)


def test_skipped_rows_are_counted_separately_from_failed_ones():
    mapping = dict(MAPPING, row_filter={
        "require_any_non_empty": ["ID"], "on_reject": "skip_silently",
    })
    plugin = FakePlugin(rows=[{"ID": "a"}, {"ID": ""}, {"ID": "c"}])
    report = runner(plugin, FakeWriter(), mapping=mapping).run()

    assert (report.rows_read, report.rows_skipped, report.nodes_written) == (3, 1, 2)
    assert report.status == "success", "a filtered row is not an error"


def test_error_messages_are_capped_but_the_count_stays_exact():
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [
                    {"name": "pid", "column": "ID"},
                    {"name": "count", "column": "Count", "transform": "integer_coerce"},
                ],
            }
        ],
    }
    bad = MAX_REPORTED_MESSAGES + 50
    plugin = FakePlugin(
        rows=[{"ID": str(i), "Count": "nope"} for i in range(bad)], columns=["ID", "Count"]
    )
    report = runner(plugin, FakeWriter(), mapping=mapping).run()

    assert report.error_count == bad
    assert len(report.errors) == MAX_REPORTED_MESSAGES
    assert report.to_dict()["errors_truncated"] == 50


# ------------------------------------------------------------ reporting

def test_report_is_json_serializable():
    import json

    report = runner(FakePlugin(), FakeWriter()).run()
    assert json.loads(json.dumps(report.to_dict()))["status"] == "success"


def test_summary_line_reads_as_a_card_subtitle():
    report = runner(FakePlugin(rows=[{"ID": "a"}, {"ID": "b"}]), FakeWriter()).run()
    assert "2 nodes" in report.summary_line() and "0 errors" in report.summary_line()


def test_plugin_transforms_are_available_to_the_mapping():
    mapping = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [{"name": "pid", "column": "ID", "transform": "shout"}],
            }
        ],
    }
    plugin = FakePlugin(transforms={"shout": lambda v: str(v).upper()})
    report = runner(plugin, FakeWriter(), mapping=mapping).run()
    assert report.status == "success"


def test_a_plugin_whose_transform_library_raises_does_not_prevent_construction():
    class Broken(FakePlugin):
        def transform_library(self):
            raise RuntimeError("library is broken")

    report = runner(Broken(), FakeWriter()).run()
    assert report.status == "success", "the config names no plugin transforms"
