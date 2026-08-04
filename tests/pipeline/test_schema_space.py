"""Schema-space elements on a canvas: never instance data, and they round-trip.

Two halves, both about the same invariant — a ``_space: "schema"`` element
describes a label *type* and must never be treated as an entity:

* The Python half covers every consumer of a canvas snapshot. This is not
  hypothetical tidiness: a schema node's ``properties`` is a list of property
  names, so ``generate_cypher`` and the RO-Crate export used to raise
  ``AttributeError`` on the first ``.items()`` if one reached them.
* The JavaScript half runs the real ``graph_utils.js`` under Node, because the
  Arrows <-> Cytoscape conversion is where the import/export round trip lives and
  a Python reimplementation of it could agree with itself while disagreeing with
  the page. Skipped, not faked, when Node is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scidk.pipeline.schema_arrows import parse_arrows
from scidk.services.canvas_service import (
    build_commit_plan,
    generate_cypher,
    generate_python_fs,
    generate_rocrate_export,
    instance_elements,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_UTILS = REPO_ROOT / "scidk" / "ui" / "static" / "js" / "graph_utils.js"
HARNESS = Path(__file__).with_name("schema_space_harness.js")

#: A canvas holding both spaces at once, which the vision explicitly allows: a
#: schema rule sitting above the instances it describes.
MIXED_SNAPSHOT = {
    "nodes": [
        {"id": "schema-Sample", "label": "Sample", "_space": "schema",
         "provisional": True, "properties": ["uuid", "treatment"],
         "key_property": "uuid"},
        {"id": "prov-1", "label": "Sample", "name": "S1", "provisional": True,
         "properties": {"name": "S1"}},
        {"id": "42", "label": "Sample", "name": "S0", "provisional": False,
         "properties": {"name": "S0"}, "element_id": "4:abc:42"},
    ],
    "edges": [
        {"source": "schema-Sample", "target": "schema-Sample", "_space": "schema",
         "relationship": "DERIVED_FROM", "provisional": True},
        {"source": "prov-1", "target": "42", "relationship": "DERIVED_FROM",
         "provisional": True},
    ],
}


# --------------------------------------------------- nothing schema-shaped commits

def test_a_schema_element_is_never_committed_to_neo4j():
    plan = build_commit_plan(MIXED_SNAPSHOT)

    # The instance element still commits; the schema one does not.
    assert [d["properties"]["name"] for d in plan["node_decls"]] == ["S1"]
    assert len(plan["rels"]) == 1


def test_a_skipped_schema_element_says_why():
    """A mixed canvas has to explain itself; a silent drop looks like a bug."""
    plan = build_commit_plan(MIXED_SNAPSHOT)
    reasons = " ".join(plan["skipped"])
    assert "schema element" in reasons
    assert "not instance data" in reasons


def test_a_schema_only_canvas_commits_nothing():
    snapshot = {"nodes": [MIXED_SNAPSHOT["nodes"][0]],
                "edges": [MIXED_SNAPSHOT["edges"][0]]}
    plan = build_commit_plan(snapshot)
    assert plan["node_decls"] == [] and plan["rels"] == []
    assert len(plan["skipped"]) == 2


@pytest.mark.parametrize(
    "generate", [generate_cypher, generate_python_fs, generate_rocrate_export]
)
def test_every_export_ignores_schema_elements(generate):
    text = generate(MIXED_SNAPSHOT, "mixed")

    # Ran at all: a schema node's property *list* used to reach .items().
    assert text
    # The label type does not appear as an entity. "Sample" itself does (the
    # instance nodes carry that label), so the schema node's id is the tell.
    assert "schema-Sample" not in text


def test_the_filter_keeps_element_order_and_leaves_instances_alone():
    kept = instance_elements(MIXED_SNAPSHOT["nodes"])
    assert [n["id"] for n in kept] == ["prov-1", "42"]
    assert instance_elements(None) == []


# ------------------------------------------------ the browser-side conversion

ARROWS = {
    "nodes": [
        {"id": "n0", "position": {"x": 100, "y": 150}, "caption": "Person",
         "labels": ["Person"], "properties": [{"name": "email"}, {"name": "name"}]},
        {"id": "n1", "position": {"x": 400, "y": 150}, "caption": "Project",
         "labels": ["Project"], "properties": [{"name": "code"}],
         "key_property": "code"},
    ],
    "relationships": [
        {"id": "r0", "fromId": "n1", "toId": "n0", "type": "PI_OF", "properties": []},
    ],
}


def run_harness(arrows, options=None):
    """Convert an Arrows document through the real graph_utils.js."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH; the browser-side conversion is untested here")
    payload = json.dumps({"arrows": arrows, "options": options or {}})
    result = subprocess.run(
        [node, str(HARNESS), str(GRAPH_UTILS)],
        input=payload, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_arrows_becomes_schema_space_elements():
    out = run_harness(parse_arrows(ARROWS))
    nodes = [e for e in out["elements"] if e["group"] == "nodes"]
    edges = [e for e in out["elements"] if e["group"] == "edges"]

    assert all(n["data"]["_space"] == "schema" for n in nodes)
    assert all(e["data"]["_space"] == "schema" for e in edges)
    # Label-keyed ids, per the element conventions in the Maps Canvas vision.
    assert [n["data"]["id"] for n in nodes] == ["schema-Person", "schema-Project"]
    # Properties are names, not values, and the key property is marked.
    assert nodes[0]["data"]["properties"] == ["email", "name"]
    assert nodes[1]["data"]["key_property"] == "code"
    assert nodes[1]["data"]["schemaLabel"] == ":Project\n🔑 code"
    assert edges[0]["data"]["type"] == "PI_OF"


def test_positions_from_arrows_are_preserved_when_not_normalized():
    out = run_harness(parse_arrows(ARROWS))
    positions = [e["position"] for e in out["elements"] if e["group"] == "nodes"]
    assert positions == [{"x": 100, "y": 150}, {"x": 400, "y": 150}]


def test_positions_are_normalized_into_the_viewport_on_import():
    """Arrows coordinates can be anywhere; every node has to land on screen."""
    far_away = {
        "nodes": [
            {"id": "n0", "caption": "A", "position": {"x": -48000, "y": -31000}},
            {"id": "n1", "caption": "B", "position": {"x": 52000, "y": 29000}},
        ],
        "relationships": [],
    }
    out = run_harness(parse_arrows(far_away), {"width": 1000, "height": 700})
    for element in out["elements"]:
        x, y = element["position"]["x"], element["position"]["y"]
        assert 0 <= x <= 1000 and 0 <= y <= 700, element


def test_a_compact_design_is_not_blown_up():
    close_together = {
        "nodes": [{"id": "n0", "caption": "A", "position": {"x": 0, "y": 0}},
                  {"id": "n1", "caption": "B", "position": {"x": 40, "y": 0}}],
        "relationships": [],
    }
    out = run_harness(parse_arrows(close_together), {"width": 1000, "height": 700})
    xs = [e["position"]["x"] for e in out["elements"]]
    assert abs(xs[1] - xs[0]) <= 40 * 1.5 + 0.001


def test_two_nodes_with_one_label_merge_and_say_so():
    """In schema space the label is the identity; two "Person" nodes are one type."""
    duplicated = {
        "nodes": [
            {"id": "n0", "caption": "Person", "properties": ["email"]},
            {"id": "n1", "caption": "Person", "properties": ["orcid"]},
        ],
        "relationships": [],
    }
    out = run_harness(parse_arrows(duplicated))
    nodes = [e for e in out["elements"] if e["group"] == "nodes"]

    assert len(nodes) == 1
    assert nodes[0]["data"]["properties"] == ["email", "orcid"]
    assert any("merged" in w for w in out["warnings"])


def test_the_same_triple_twice_is_one_edge():
    document = {
        "nodes": [{"id": "n0", "caption": "A"}, {"id": "n1", "caption": "B"}],
        "relationships": [
            {"id": "r0", "type": "REL", "fromId": "n0", "toId": "n1"},
            {"id": "r1", "type": "REL", "fromId": "n0", "toId": "n1"},
        ],
    }
    out = run_harness(parse_arrows(document))
    assert len([e for e in out["elements"] if e["group"] == "edges"]) == 1


def test_the_round_trip_preserves_the_element_set():
    """The Definition of Done: export, import, identical elements."""
    original = parse_arrows(ARROWS)
    exported = parse_arrows(run_harness(original)["arrows"])

    def element_set(document):
        by_id = {n["id"]: n["labels"][0] for n in document["nodes"]}
        return (
            sorted((n["labels"][0], tuple(sorted(n["properties"])),
                    n.get("key_property")) for n in document["nodes"]),
            sorted((by_id[r["fromId"]], r["type"], by_id[r["toId"]])
                   for r in document["relationships"]),
        )

    assert element_set(exported) == element_set(original)


def test_the_export_is_valid_input_to_the_python_validator():
    """Whatever the canvas produces has to survive the PUT it is sent to."""
    exported = run_harness(parse_arrows(ARROWS))["arrows"]
    assert parse_arrows(exported)["nodes"][0]["labels"] == ["Person"]


def test_arrows_property_types_survive_the_canvas():
    typed = {"nodes": [{"id": "n0", "caption": "Sample",
                        "properties": {"count": "Integer"}}], "relationships": []}
    exported = run_harness(parse_arrows(typed))["arrows"]
    assert exported["nodes"][0]["properties"] == {"count": "Integer"}
