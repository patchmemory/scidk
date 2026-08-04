"""The whole backend against the real plugin and the real reference config.

Every other test in this directory uses a fake plugin or a hand-written config.
This one wires the actual :class:`SharePointPlugin` to the actual
``aipt_intake_mapping.json`` over the existing SharePoint test fixture, because
the note in ``dev/cycles.md`` is explicit that between Cycle 3 and Cycle 3B *no
code path writes AIPT intake rows to Neo4j* — this is the test that the path now
exists and produces what the config claims.

The writer is a fake. Nothing here needs a live Neo4j, and the declarations it
captures are asserted against the shape ``write_declared_nodes`` requires.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.sharepoint_intake import get_plugin
from scidk.pipeline.identifiers import check_identifier
from scidk.pipeline.plugin_registry import resolve_plugin
from scidk.pipeline.runner import PipelineRunner

REPO = Path(__file__).resolve().parents[2]
REFERENCE_CONFIG = REPO / "plugins/sharepoint_intake/configs/aipt_intake_mapping.json"
FIXTURE = REPO / "tests/plugins/fixtures/sharepoint_intake_sample.csv"


class CapturingWriter:
    """Records what would be written and reports it as fully written."""

    def __init__(self):
        self.nodes = []
        self.relationships = []

    def write_declared_nodes(self, nodes, relationships):
        self.nodes.extend(nodes)
        self.relationships.extend(relationships)
        return {
            "written_nodes": len(nodes),
            "written_relationships": len(relationships),
            "errors": [],
        }


@pytest.fixture(scope="module")
def mapping() -> dict:
    with REFERENCE_CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def result(mapping):
    writer = CapturingWriter()
    runner = PipelineRunner(get_plugin(), mapping, {"source_path": str(FIXTURE)}, writer=writer)
    return runner.run(), writer


def test_the_reference_config_runs_against_the_reference_fixture(result):
    report, _writer = result

    assert report.fair == {"F": True, "A": True, "I": True, "R": True}, report.errors
    assert report.rows_read == 4
    assert report.nodes_written > 0
    assert report.writes_committed is True


def test_the_fixtures_deliberately_unusable_row_is_rejected_and_named(result):
    """The fixture's last row has neither CACProtocol nor ShortDescription, and the
    config's row_filter sets on_reject to record_error — so the run is 'partial'
    and says which row and why, rather than quietly ingesting 3 of 4 rows."""
    report, _writer = result

    assert report.status == "partial"
    assert report.rows_skipped == 1
    assert report.errors == ["row 3: row has neither CACProtocol nor ShortDescription"]


def test_absent_optional_columns_are_warnings_not_a_refusal_to_run(mapping, result):
    """The fixture has 17 of the config's 31 columns. That is a narrower export,
    not a broken config: the 14 absent columns all feed optional Project
    properties, so the run proceeds and names each one."""
    report, _writer = result

    assert len(report.missing_columns) == 14, report.missing_columns
    assert report.fair["I"] is True
    for column in report.missing_columns:
        assert any(column in w for w in report.warnings), f"{column} was not reported"


def test_losing_only_cacprotocol_does_not_break_the_config(mapping, result):
    """Because the config's project_id fallback is deliberately built for that case.

    ``project_id`` falls back to ``{ShortDescription}|{RecordSource}|{__row_index__}``,
    so a source without CACProtocol still produces deterministic Project nodes.
    The column-criticality check has to know that, or it would refuse a run the
    config was explicitly written to survive.
    """
    report, _writer = result
    engine = PipelineRunner(get_plugin(), mapping, {}).engine

    blocking, _informational = engine.column_problems(
        [c for c in report.columns if c != "CACProtocol"]
    )
    assert blocking == []


def test_losing_every_column_feeding_the_project_key_does_block(mapping, result):
    """One Project per row keyed '||0', '||1' is not a run worth doing."""
    report, _writer = result
    engine = PipelineRunner(get_plugin(), mapping, {}).engine

    starved = [
        c for c in report.columns
        if c not in ("CACProtocol", "ShortDescription", "RecordSource")
    ]
    blocking, _informational = engine.column_problems(starved)
    assert any("project" in b for b in blocking), blocking


def test_it_produces_the_labels_and_relationship_types_the_config_declares(result):
    _report, writer = result

    assert {n["label"] for n in writer.nodes} <= {"Project", "Person", "Attachment"}
    assert "Project" in {n["label"] for n in writer.nodes}
    assert {r["type"] for r in writer.relationships} <= {
        "SUBMITTED", "PI_OF", "COLLABORATES_ON", "HAS_ATTACHMENT"
    }


def test_every_declaration_satisfies_write_declared_nodes(result):
    """key_property's value must also be a key inside properties or the decl is rejected."""
    _report, writer = result

    for node in writer.nodes:
        assert set(node) == {"label", "key_property", "properties"}
        assert node["key_property"] in node["properties"]
        assert node["properties"][node["key_property"]] not in (None, "")

    for rel in writer.relationships:
        assert set(rel) == {"type", "from_label", "from_match", "to_label", "to_match"}
        assert rel["from_match"] and rel["to_match"]


def test_nothing_reaching_cypher_is_an_unsafe_identifier(result):
    """The guarantee the whole identifiers module exists for, checked on real output."""
    _report, writer = result

    for node in writer.nodes:
        assert check_identifier(node["label"], "label") is None
        for name in node["properties"]:
            assert check_identifier(name, "property name") is None
    for rel in writer.relationships:
        assert check_identifier(rel["type"], "relationship type") is None


def test_a_person_appearing_in_two_roles_is_one_node(result):
    _report, writer = result
    people = [n for n in writer.nodes if n["label"] == "Person"]
    keys = [(n["key_property"], n["properties"][n["key_property"]]) for n in people]
    assert len(keys) == len(set(keys)), f"duplicate Person declarations: {keys}"


def test_the_sharepoint_plugin_resolves_by_every_alias_the_ui_might_store():
    for alias in ("sharepoint", "sharepoint_intake", "sharepoint_list"):
        assert type(resolve_plugin(alias)).__name__ == "SharePointPlugin"


def test_sharepoint_transforms_are_reachable_from_the_mapping(mapping):
    """sp_colresolution is a plugin transform; the run is only reproducible if it resolves."""
    runner = PipelineRunner(get_plugin(), mapping, {"source_path": str(FIXTURE)})
    assert runner.engine.unknown_transforms() == []
    assert "sp_colresolution" in runner.engine.transforms


def test_a_dry_run_over_the_reference_config_writes_nothing(mapping):
    writer = CapturingWriter()
    report = PipelineRunner(
        get_plugin(), mapping, {"source_path": str(FIXTURE)}, writer=writer
    ).run(dry_run=True)

    assert writer.nodes == [] and writer.relationships == []
    assert report.nodes_declared > 0
