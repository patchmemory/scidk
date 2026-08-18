"""The Arrows.app schema format: parsing, summarizing, and deriving from Neo4j.

Cycle 3B Task C. No database — :func:`derive_from_graph` takes its query runner as
an argument precisely so these tests can hand it canned rows, including the
failures that make it fall through to its next strategy.
"""
from __future__ import annotations

import json

import pytest

from scidk.pipeline.schema_arrows import (
    STRATEGY_APOC,
    STRATEGY_SCAN,
    STRATEGY_VISUALIZATION,
    SchemaError,
    derive_from_graph,
    parse_arrows,
    schema_summary,
)

# The format as the Cycle 3B task block documents it: properties as a list of
# {"name": ...}. arrows.app itself writes an object. Both have to work.
TASK_BLOCK_FORM = {
    "nodes": [
        {"id": "n0", "position": {"x": 100, "y": 150}, "caption": "Person",
         "labels": ["Person"], "properties": [{"name": "email"}, {"name": "name"}]},
        {"id": "n1", "position": {"x": 400, "y": 150}, "caption": "Project",
         "labels": ["Project"], "properties": [{"name": "code"}]},
    ],
    "relationships": [
        {"id": "r0", "fromId": "n1", "toId": "n0", "type": "PI_OF", "properties": []},
    ],
}

ARROWS_APP_FORM = {
    "style": {"node-color": "#4C8EDA"},
    "nodes": [
        {"id": "n0", "position": {"x": -100.5, "y": 0}, "caption": "Sample",
         "labels": ["Sample"], "properties": {"uuid": "String", "treatment": "String"},
         "style": {}},
        {"id": "n1", "position": {"x": 200, "y": 0}, "caption": "SampleType",
         "labels": ["SampleType"], "properties": {"name": "String"}, "style": {}},
    ],
    "relationships": [
        {"id": "r0", "type": "OF_TYPE", "fromId": "n0", "toId": "n1",
         "properties": {}, "style": {}},
    ],
}


# --------------------------------------------------------------------- parsing

def test_parses_the_task_block_property_form():
    schema = parse_arrows(TASK_BLOCK_FORM)

    assert [n["labels"][0] for n in schema["nodes"]] == ["Person", "Project"]
    # Normalized to the object form arrows.app writes, with a default type.
    assert schema["nodes"][0]["properties"] == {"email": "String", "name": "String"}
    assert schema["relationships"][0]["type"] == "PI_OF"


def test_parses_the_arrows_app_property_form_and_keeps_positions():
    schema = parse_arrows(ARROWS_APP_FORM)

    assert schema["nodes"][0]["position"] == {"x": -100.5, "y": 0.0}
    assert schema["nodes"][0]["properties"]["treatment"] == "String"
    assert schema["style"] == {"node-color": "#4C8EDA"}


def test_accepts_raw_json_text():
    schema = parse_arrows(json.dumps(TASK_BLOCK_FORM))
    assert len(schema["nodes"]) == 2


def test_parse_is_idempotent_so_import_export_round_trips():
    once = parse_arrows(TASK_BLOCK_FORM)
    twice = parse_arrows(json.dumps(once))
    assert once == twice


def test_bare_string_property_list_is_accepted():
    schema = parse_arrows({"nodes": [{"id": "n0", "caption": "Person",
                                     "properties": ["email"]}]})
    assert schema["nodes"][0]["properties"] == {"email": "String"}


def test_caption_is_used_when_labels_is_absent():
    schema = parse_arrows({"nodes": [{"id": "n0", "caption": "Person"}]})
    assert schema["nodes"][0]["labels"] == ["Person"]


def test_missing_positions_get_distinct_grid_slots():
    schema = parse_arrows({"nodes": [
        {"id": f"n{i}", "caption": f"L{i}"} for i in range(7)
    ]})
    positions = {(n["position"]["x"], n["position"]["y"]) for n in schema["nodes"]}
    assert len(positions) == 7


def test_non_finite_position_falls_back_to_the_grid():
    schema = parse_arrows({"nodes": [
        {"id": "n0", "caption": "Person", "position": {"x": float("nan"), "y": 1}},
    ]})
    assert schema["nodes"][0]["position"] == {"x": 0.0, "y": 0.0}


def test_key_property_must_be_one_of_the_properties():
    with pytest.raises(SchemaError) as excinfo:
        parse_arrows({"nodes": [{"id": "n0", "caption": "Sample",
                                 "properties": ["uuid"], "key_property": "missing"}]})
    assert "key_property" in str(excinfo.value)


def test_key_property_survives_a_round_trip():
    schema = parse_arrows({"nodes": [{"id": "n0", "caption": "Sample",
                                     "properties": ["uuid"], "key_property": "uuid"}]})
    assert schema["nodes"][0]["key_property"] == "uuid"
    assert parse_arrows(schema)["nodes"][0]["key_property"] == "uuid"


# ------------------------------------------------------------------ rejections

def test_invalid_json_names_the_line_and_column():
    with pytest.raises(SchemaError) as excinfo:
        parse_arrows('{"nodes": [}')
    message = str(excinfo.value)
    assert "not valid JSON" in message and "line 1" in message


def test_empty_paste_is_rejected():
    with pytest.raises(SchemaError, match="Nothing to import"):
        parse_arrows("   ")


def test_json_without_nodes_is_rejected():
    with pytest.raises(SchemaError, match="Arrows.app export"):
        parse_arrows({"relationships": []})


def test_json_array_is_rejected():
    with pytest.raises(SchemaError, match="JSON object"):
        parse_arrows("[1, 2, 3]")


def test_a_label_cypher_cannot_address_is_rejected_by_name():
    with pytest.raises(SchemaError) as excinfo:
        parse_arrows({"nodes": [{"id": "n0", "caption": "Intake Form"}]})
    assert "'Intake Form'" in str(excinfo.value)


def test_a_property_name_cypher_cannot_address_is_rejected_by_name():
    with pytest.raises(SchemaError) as excinfo:
        parse_arrows({"nodes": [{"id": "n0", "caption": "Sample",
                                 "properties": ["Sample ID"]}]})
    assert "'Sample ID'" in str(excinfo.value)


def test_a_relationship_type_with_a_space_is_rejected():
    document = {
        "nodes": [{"id": "n0", "caption": "A"}, {"id": "n1", "caption": "B"}],
        "relationships": [{"id": "r0", "type": "PI OF", "fromId": "n0", "toId": "n1"}],
    }
    with pytest.raises(SchemaError, match="PI OF"):
        parse_arrows(document)


def test_a_dangling_relationship_endpoint_is_rejected():
    document = {
        "nodes": [{"id": "n0", "caption": "A"}],
        "relationships": [{"id": "r0", "type": "REL", "fromId": "n0", "toId": "n9"}],
    }
    with pytest.raises(SchemaError, match="'n9'"):
        parse_arrows(document)


def test_a_node_without_a_label_or_caption_is_rejected():
    with pytest.raises(SchemaError, match="no label or caption"):
        parse_arrows({"nodes": [{"id": "n0", "properties": ["x"]}]})


def test_duplicate_node_ids_are_rejected():
    with pytest.raises(SchemaError, match="duplicate node id"):
        parse_arrows({"nodes": [{"id": "n0", "caption": "A"},
                                {"id": "n0", "caption": "B"}]})


def test_every_problem_is_reported_not_just_the_first():
    document = {"nodes": [
        {"id": "n0", "caption": "Bad Label"},
        {"id": "n1", "caption": "Also Bad"},
        {"id": "n2", "caption": "Fine", "properties": ["Bad Prop"]},
    ]}
    with pytest.raises(SchemaError) as excinfo:
        parse_arrows(document)
    assert len(excinfo.value.problems) == 3
    assert "'Also Bad'" in str(excinfo.value)


def test_an_absurdly_large_document_is_refused_as_a_data_export():
    document = {"nodes": [{"id": f"n{i}", "caption": "Row"} for i in range(2001)]}
    with pytest.raises(SchemaError, match="data export"):
        parse_arrows(document)


def test_an_empty_schema_is_valid():
    # Option C — build from scratch — saves this on the way to its first label.
    assert parse_arrows({"nodes": []}) == {"style": {}, "nodes": [], "relationships": []}


# --------------------------------------------------------------------- summary

def test_summary_counts_what_the_card_shows():
    summary = schema_summary(parse_arrows(TASK_BLOCK_FORM))
    assert summary == {
        "defined": True,
        "labels": ["Person", "Project"],
        "relationship_types": ["PI_OF"],
        "node_count": 2,
        "relationship_count": 1,
        "property_count": 3,
    }


@pytest.mark.parametrize("value", [None, {}, "not a schema", {"nodes": []}])
def test_summary_reports_undefined_rather_than_raising(value):
    assert schema_summary(value)["defined"] is False


# ------------------------------------------------------- derive from the graph

class FakeNode:
    """A ``db.schema.visualization()`` virtual node."""

    def __init__(self, element_id: str, name: str):
        self.element_id = element_id
        self._props = {"name": name}
        self.labels = frozenset({name})

    def get(self, key, default=None):
        return self._props.get(key, default)


class FakeRel:
    def __init__(self, rel_type: str, start: FakeNode, end: FakeNode):
        self.type = rel_type
        self.start_node = start
        self.end_node = end


def make_reader(responses):
    """A query runner that answers by Cypher prefix, raising for the rest.

    Raising is the point: an unavailable procedure is how Neo4j reports one, and
    the fallback chain only means anything if it is exercised that way.
    """
    def read(cypher, params=None):
        for prefix, response in responses.items():
            if cypher.startswith(prefix):
                if isinstance(response, Exception):
                    raise response
                return response
        raise RuntimeError(f"There is no procedure with the name `{cypher}`")

    return read


def test_derives_from_db_schema_visualization():
    project, person = FakeNode("-1", "Project"), FakeNode("-2", "Person")
    read = make_reader({
        "CALL db.schema.visualization": [
            {"nodes": [project, person],
             "relationships": [FakeRel("PI_OF", project, person)]},
        ],
        "CALL db.schema.nodeTypeProperties": [
            {"nodeLabels": ["Person"], "propertyName": "email",
             "propertyTypes": ["String"]},
        ],
    })

    result = derive_from_graph(read)

    assert result["strategy"] == STRATEGY_VISUALIZATION
    labels = [n["labels"][0] for n in result["schema"]["nodes"]]
    assert labels == ["Project", "Person"]
    # The triple is preserved as an edge between the two label nodes.
    rel = result["schema"]["relationships"][0]
    by_id = {n["id"]: n["labels"][0] for n in result["schema"]["nodes"]}
    assert (by_id[rel["fromId"]], rel["type"], by_id[rel["toId"]]) == \
        ("Project", "PI_OF", "Person")
    assert result["schema"]["nodes"][1]["properties"] == {"email": "String"}


def test_falls_back_to_apoc_when_visualization_is_unavailable():
    read = make_reader({
        "CALL db.schema.visualization": RuntimeError("Unknown procedure"),
        "CALL apoc.meta.schema": [{"value": {
            "Person": {"type": "node", "properties": {"email": {"type": "STRING"}},
                       "relationships": {}},
            "Project": {"type": "node", "properties": {},
                        "relationships": {"PI_OF": {"direction": "out",
                                                    "labels": ["Person"]}}},
        }}],
    })

    result = derive_from_graph(read)

    assert result["strategy"] == STRATEGY_APOC
    assert {n["labels"][0] for n in result["schema"]["nodes"]} == {"Person", "Project"}
    assert result["schema"]["relationships"][0]["type"] == "PI_OF"


def test_falls_back_to_a_relationship_scan_when_neither_procedure_exists():
    read = make_reader({
        "CALL db.schema.visualization": RuntimeError("Unknown procedure"),
        "CALL apoc.meta.schema": RuntimeError("Unknown procedure"),
        "MATCH (n)-[r]->(m)": [
            {"from_labels": ["Project"], "rel_type": "PI_OF", "to_labels": ["Person"]},
            {"from_labels": ["Project"], "rel_type": "PI_OF", "to_labels": ["Person"]},
        ],
        "CALL db.labels": [{"label": "Project"}, {"label": "Person"},
                           {"label": "Orphan"}],
        "CALL db.schema.nodeTypeProperties": RuntimeError("Unknown procedure"),
    })

    result = derive_from_graph(read)

    assert result["strategy"] == STRATEGY_SCAN
    # db.labels() contributes the label no relationship touches.
    assert {n["labels"][0] for n in result["schema"]["nodes"]} == \
        {"Project", "Person", "Orphan"}
    # The duplicate triple collapses to one edge.
    assert len(result["schema"]["relationships"]) == 1


def test_the_scan_is_bounded():
    seen = []

    def read(cypher, params=None):
        seen.append(cypher)
        if cypher.startswith("MATCH (n)-[r]->(m)"):
            return []
        raise RuntimeError("Unknown procedure")

    derive_from_graph(read)
    scan = next(c for c in seen if c.startswith("MATCH (n)-[r]->(m)"))
    assert "LIMIT 1000" in scan


def test_an_empty_graph_derives_an_empty_schema_with_an_explanation():
    read = make_reader({
        "CALL db.schema.visualization": [{"nodes": [], "relationships": []}],
        "CALL apoc.meta.schema": [{"value": {}}],
        "MATCH (n)-[r]->(m)": [],
        "CALL db.labels": [],
    })

    result = derive_from_graph(read)

    assert result["strategy"] is None
    assert result["schema"]["nodes"] == []
    assert any("no labels yet" in note for note in result["notes"])


def test_a_label_cypher_cannot_address_is_dropped_rather_than_failing_the_derive():
    # A live graph can hold labels created by another tool. Refusing to derive
    # anything because one of them is unusable would be the wrong trade.
    good, bad = FakeNode("-1", "Person"), FakeNode("-2", "Sample ID")
    read = make_reader({
        "CALL db.schema.visualization": [
            {"nodes": [good, bad], "relationships": [FakeRel("HAS", good, bad)]},
        ],
        "CALL db.schema.nodeTypeProperties": [],
    })

    result = derive_from_graph(read)

    assert [n["labels"][0] for n in result["schema"]["nodes"]] == ["Person"]
    assert result["schema"]["relationships"] == []


def test_a_derived_schema_is_valid_input_to_parse_arrows():
    project, person = FakeNode("-1", "Project"), FakeNode("-2", "Person")
    read = make_reader({
        "CALL db.schema.visualization": [
            {"nodes": [project, person],
             "relationships": [FakeRel("PI_OF", project, person)]},
        ],
        "CALL db.schema.nodeTypeProperties": [],
    })

    derived = derive_from_graph(read)["schema"]
    assert parse_arrows(derived) == derived
