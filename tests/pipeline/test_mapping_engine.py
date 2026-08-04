"""Mapping engine behaviour: resolution, sanitization, dedup, error attribution.

Two things are worth stating about what is asserted here.

*Sanitization is a write-path safety property, not a style check.*
``write_declared_nodes`` interpolates labels, relationship types and property
names into Cypher unquoted, so a config that names ``Sample ID`` or
``Project) DETACH DELETE n //`` has to be stopped by the engine. The tests below
check it is stopped at validate() time *and* at map time, because the second is
what holds when a caller skipped the first.

*Dedup is a data-model requirement.* Cycle 3B Task D describes one row producing
two Person nodes that turn out to be the same person. Merging them into one node
with two relationships is the specified behaviour, not an optimization.
"""
from __future__ import annotations

import pytest

from scidk.pipeline.mapping_engine import DeclarationCollector, MappingEngine
from scidk.pipeline.transforms import TransformError


def config(**overrides) -> dict:
    """A minimal two-node config: a Project and an optional Person who submitted it."""
    base = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "project",
                "label": "Project",
                "key_property": "project_id",
                "properties": [
                    {"name": "project_id", "column": "Protocol", "required": True},
                    {"name": "title", "column": "Title"},
                ],
            },
            {
                "id": "person",
                "label": "Person",
                "key_property": ["email", "name"],
                "optional": True,
                "properties": [
                    {"name": "email", "column": "Email", "transform": "lowercase_strip"},
                    {"name": "name", "column": "Name"},
                ],
                "skip_when_all_empty": ["email", "name"],
            },
        ],
        "relationship_mappings": [{"type": "SUBMITTED", "from": "person", "to": "project"}],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- resolution

def test_maps_a_row_onto_nodes_and_a_relationship():
    engine = MappingEngine(config())
    result = engine.map_row({"Protocol": "P-1", "Title": "Study", "Email": "A@MIT.EDU"}, 0)

    assert result.errors == []
    labels = {(n.label, n.key_property, n.key_value) for n in result.nodes}
    assert labels == {("Project", "project_id", "P-1"), ("Person", "email", "a@mit.edu")}
    assert result.relationships == [
        {
            "type": "SUBMITTED",
            "from_label": "Person",
            "from_match": {"email": "a@mit.edu"},
            "to_label": "Project",
            "to_match": {"project_id": "P-1"},
        }
    ]


def test_declaration_shape_satisfies_write_declared_nodes():
    """key_property's value must also appear inside properties or the decl is rejected."""
    engine = MappingEngine(config())
    decl = engine.map_row({"Protocol": "P-1"}, 0).nodes[0].to_decl()

    assert set(decl) == {"label", "key_property", "properties"}
    assert decl["key_property"] in decl["properties"]


def test_whitespace_is_stripped_so_a_merge_key_does_not_split_a_node():
    engine = MappingEngine(config())
    padded = engine.map_row({"Protocol": " P-1 "}, 0).nodes[0]
    clean = engine.map_row({"Protocol": "P-1"}, 1).nodes[0]
    assert padded.identity() == clean.identity()


def test_key_property_list_is_a_preference_order():
    """A Person keys on email when known and falls back to display name."""
    engine = MappingEngine(config())

    with_email = engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "A"}, 0)
    assert [n.key_property for n in with_email.nodes if n.label == "Person"] == ["email"]

    without = engine.map_row({"Protocol": "P", "Name": "Name Only"}, 1)
    person = next(n for n in without.nodes if n.label == "Person")
    assert (person.key_property, person.key_value) == ("name", "Name Only")


def test_optional_node_absent_takes_its_relationship_with_it():
    engine = MappingEngine(config())
    result = engine.map_row({"Protocol": "P-1"}, 0)

    assert [n.label for n in result.nodes] == ["Project"]
    assert result.relationships == []
    assert result.errors == []


def test_required_property_empty_produces_no_node_and_an_error_naming_it():
    engine = MappingEngine(config())
    result = engine.map_row({"Title": "No protocol"}, 7)

    assert result.nodes == []
    assert len(result.errors) == 1
    assert "row 7" in result.errors[0] and "project_id" in result.errors[0]


def test_empty_properties_are_omitted_rather_than_written_blank():
    engine = MappingEngine(config())
    project = engine.map_row({"Protocol": "P-1", "Title": ""}, 0).nodes[0]
    assert "title" not in project.properties


def test_zero_and_false_are_values_not_absences():
    engine = MappingEngine(
        config(
            node_mappings=[
                {
                    "id": "m",
                    "label": "Measurement",
                    "key_property": "mid",
                    "properties": [
                        {"name": "mid", "column": "ID"},
                        {"name": "count", "column": "Count", "transform": "integer_coerce"},
                        {"name": "flag", "column": "Flag", "transform": "boolean_coerce"},
                    ],
                }
            ],
            relationship_mappings=[],
        )
    )
    node = engine.map_row({"ID": "m1", "Count": "0", "Flag": "No"}, 0).nodes[0]
    assert node.properties["count"] == 0
    assert node.properties["flag"] is False


# ----------------------------------------------------------------- fallback

def test_template_fallback_synthesizes_a_deterministic_key():
    engine = MappingEngine(
        config(
            node_mappings=[
                {
                    "id": "project",
                    "label": "Project",
                    "key_property": "project_id",
                    "properties": [
                        {
                            "name": "project_id",
                            "column": "Protocol",
                            "required": True,
                            "fallback": {"template": "{Title}|{Source}|{__row_index__}"},
                        }
                    ],
                }
            ],
            relationship_mappings=[],
        )
    )
    row = {"Protocol": "", "Title": "Study", "Source": "drupal"}
    first = engine.map_row(row, 4).nodes[0]
    assert first.key_value == "Study|drupal|4"
    # Deterministic: the same row at the same index converges on the same node.
    assert engine.map_row(dict(row), 4).nodes[0].identity() == first.identity()


def test_template_placeholder_for_a_missing_column_interpolates_empty():
    engine = MappingEngine(
        config(
            node_mappings=[
                {
                    "id": "p",
                    "label": "Project",
                    "key_property": "pid",
                    "properties": [
                        {
                            "name": "pid",
                            "column": "Missing",
                            "fallback": {"template": "x-{Nope}-{__row_index__}"},
                        }
                    ],
                }
            ],
            relationship_mappings=[],
        )
    )
    assert engine.map_row({}, 2).nodes[0].key_value == "x--2"


# ------------------------------------------------------- transform dispatch

def test_transform_declaring_a_row_parameter_receives_the_whole_row():
    """The convention that makes a two-column choice like sp_colresolution expressible."""
    def pick_first(prefer_col, fallback_col, row):
        return (row.get(prefer_col) or row.get(fallback_col) or "").strip() or None

    engine = MappingEngine(
        config(
            node_mappings=[
                {
                    "id": "p",
                    "label": "Project",
                    "key_property": "pid",
                    "properties": [
                        {"name": "pid", "column": "ID"},
                        {
                            "name": "study_type",
                            "transform": "pick_first",
                            "transform_args": {"prefer_col": "T_sp", "fallback_col": "T_orig"},
                        },
                    ],
                }
            ],
            relationship_mappings=[],
        ),
        transform_library={"pick_first": pick_first},
    )
    node = engine.map_row({"ID": "p1", "T_sp": "", "T_orig": "Legacy"}, 0).nodes[0]
    assert node.properties["study_type"] == "Legacy"


def test_transform_failure_is_attributed_to_row_and_property_and_does_not_abort():
    engine = MappingEngine(
        config(
            node_mappings=[
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
            relationship_mappings=[],
        )
    )
    result = engine.map_row({"ID": "p1", "Count": "not a number"}, 12)

    assert len(result.nodes) == 1, "a bad cell must not cost us the node"
    assert len(result.errors) == 1
    assert "row 12" in result.errors[0] and "count" in result.errors[0]


def test_unknown_transform_is_reported_by_validate_not_discovered_mid_run():
    engine = MappingEngine(
        config(
            node_mappings=[
                {
                    "id": "p",
                    "label": "Project",
                    "key_property": "pid",
                    "properties": [{"name": "pid", "column": "ID", "transform": "no_such"}],
                }
            ],
            relationship_mappings=[],
        )
    )
    assert engine.unknown_transforms() == [("no_such", "p.properties[0].transform")]
    assert any("no_such" in e for e in engine.validate().errors)


# ------------------------------------------------------ source/property_map

def source_form_config() -> dict:
    return {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "project",
                "label": "Project",
                "key_property": "pid",
                "properties": [{"name": "pid", "column": "ID"}],
            },
            {
                "id": "collaborators",
                "label": "Person",
                "key_property": ["email", "name"],
                "cardinality": "many",
                "optional": True,
                "source": {"column": "Collaborators", "transform": "split_people"},
                "property_map": {"name": "name", "email": "email"},
                "skip_when_all_empty": ["email", "name"],
            },
        ],
        "relationship_mappings": [
            {"type": "COLLABORATES_ON", "from": "collaborators", "to": "project"}
        ],
    }


def split_people(value):
    people = []
    for chunk in str(value or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, email = chunk.partition("<")
        people.append({"name": name.strip() or None, "email": email.rstrip(">").strip() or None})
    return people


def test_cardinality_many_emits_one_node_per_element_each_with_a_relationship():
    engine = MappingEngine(source_form_config(), transform_library={"split_people": split_people})
    result = engine.map_row(
        {"ID": "p1", "Collaborators": "Bo <bo@mit.edu>; Cy <cy@mit.edu>"}, 0
    )

    people = [n for n in result.nodes if n.label == "Person"]
    assert {p.key_value for p in people} == {"bo@mit.edu", "cy@mit.edu"}
    assert len(result.relationships) == 2


def test_cardinality_one_receiving_a_list_is_an_error_not_a_silent_first_element():
    cfg = source_form_config()
    cfg["node_mappings"][1]["cardinality"] = "one"
    engine = MappingEngine(cfg, transform_library={"split_people": split_people})

    result = engine.map_row({"ID": "p1", "Collaborators": "Bo <bo@mit.edu>; Cy <cy@mit.edu>"}, 3)
    assert [n.label for n in result.nodes] == ["Project"]
    assert any("cardinality is 'one'" in e for e in result.errors)


# --------------------------------------------------------------- conditions

def test_condition_gates_a_node_on_a_column_value():
    cfg = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "attachment",
                "label": "Attachment",
                "key_property": "path",
                "optional": True,
                "condition": {"column": "Status", "equals": "available"},
                "properties": [{"name": "path", "column": "Path"}],
            }
        ],
    }
    engine = MappingEngine(cfg)
    assert engine.map_row({"Status": "available", "Path": "/a.pdf"}, 0).nodes
    assert engine.map_row({"Status": "not_copied", "Path": "/a.pdf"}, 1).nodes == []


def test_row_filter_rejection_is_recorded_and_produces_nothing():
    cfg = config(row_filter={
        "require_any_non_empty": ["Protocol", "Title"],
        "on_reject": "record_error",
        "error_message": "row has neither Protocol nor Title",
    })
    result = MappingEngine(cfg).map_row({"Protocol": "", "Title": "  "}, 5)

    assert result.skipped is True
    assert result.nodes == [] and result.relationships == []
    assert "row has neither Protocol nor Title" in result.errors[0]


def test_row_filter_can_reject_silently():
    cfg = config(row_filter={"require_any_non_empty": ["Protocol"], "on_reject": "skip_silently"})
    result = MappingEngine(cfg).map_row({"Protocol": ""}, 5)
    assert result.skipped is True and result.errors == []


# ------------------------------------------------------------ sanitization

@pytest.mark.parametrize(
    "field,value",
    [
        ("label", "My Project"),
        ("label", "Project) DETACH DELETE n //"),
        ("label", "1Project"),
    ],
)
def test_validate_rejects_an_unsafe_label(field, value):
    cfg = config()
    cfg["node_mappings"][0][field] = value
    errors = MappingEngine(cfg).validate().errors
    assert any(value in e for e in errors), errors


def test_map_row_refuses_an_unsafe_identifier_even_when_validate_was_skipped():
    """The write path enforces this itself; it does not trust that validate() ran."""
    cfg = config()
    cfg["node_mappings"][0]["label"] = "Project) DETACH DELETE n //"
    result = MappingEngine(cfg).map_row({"Protocol": "P-1"}, 0)

    assert [n.label for n in result.nodes] == ["Person"] or result.nodes == []
    assert not any(n.label.startswith("Project)") for n in result.nodes)
    assert any("DETACH DELETE" in e for e in result.errors)


def test_map_row_refuses_an_unsafe_property_name():
    cfg = config()
    cfg["node_mappings"][0]["properties"].append({"name": "Sample ID", "column": "S"})
    result = MappingEngine(cfg).map_row({"Protocol": "P-1", "S": "s1"}, 0)

    assert not any("Sample ID" in n.properties for n in result.nodes)
    assert any("Sample ID" in e for e in result.errors)


def test_validate_rejects_a_relationship_endpoint_that_does_not_exist():
    cfg = config(relationship_mappings=[{"type": "SUBMITTED", "from": "ghost", "to": "project"}])
    errors = MappingEngine(cfg).validate().errors
    assert any("ghost" in e for e in errors), errors


def test_validate_rejects_a_key_property_the_mapping_does_not_declare():
    cfg = config()
    cfg["node_mappings"][0]["key_property"] = "not_declared"
    errors = MappingEngine(cfg).validate().errors
    assert any("not_declared" in e for e in errors), errors


def test_validate_rejects_duplicate_node_mapping_ids():
    cfg = config()
    cfg["node_mappings"][1]["id"] = "project"
    errors = MappingEngine(cfg).validate().errors
    assert any("duplicate id" in e for e in errors), errors


def test_a_list_valued_merge_key_is_refused():
    cfg = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "tags",
                "properties": [
                    {"name": "tags", "column": "Tags", "transform": "split_delimiter"}
                ],
            }
        ],
    }
    result = MappingEngine(cfg).map_row({"Tags": "a;b"}, 0)
    assert result.nodes == []
    assert any("must be a scalar" in e for e in result.errors)


# --------------------------------------------------------------- columns

def test_mapped_columns_includes_columns_named_through_transform_args():
    """A column named in transform_args is still a column the source must have."""
    cfg = config(
        node_mappings=[
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [
                    {"name": "pid", "column": "ID"},
                    {
                        "name": "study_type",
                        "transform": "lowercase_strip",
                        "transform_args": {"prefer_col": "T_sp", "fallback_col": "T_orig"},
                    },
                ],
            }
        ],
        relationship_mappings=[],
    )
    assert MappingEngine(cfg).mapped_columns() == {"ID", "T_sp", "T_orig"}


def test_missing_columns_are_reported_by_name():
    engine = MappingEngine(config())
    assert engine.missing_columns(["Protocol", "Title", "Email", "Name"]) == []
    assert engine.missing_columns(["Protocol", "Title"]) == ["Email", "Name"]


def test_a_missing_optional_property_column_is_informational_not_blocking():
    """A config broader than one export is not a broken config."""
    blocking, informational = MappingEngine(config()).column_problems(
        ["Protocol", "Email", "Name"]
    )
    assert blocking == []
    assert any("'Title'" in m for m in informational)


def test_a_missing_required_property_column_blocks():
    blocking, _ = MappingEngine(config()).column_problems(["Title", "Email", "Name"])
    assert any("project_id is required" in m and "Protocol" in m for m in blocking)


def test_losing_every_key_column_of_an_optional_node_is_informational():
    """The Person simply never appears; the Project run is still worth doing."""
    blocking, informational = MappingEngine(config()).column_problems(["Protocol", "Title"])
    assert blocking == []
    assert any("can never resolve a merge key" in m for m in informational)


def test_losing_every_key_column_of_a_required_node_blocks():
    cfg = config()
    cfg["node_mappings"][1].pop("optional")
    blocking, _ = MappingEngine(cfg).column_problems(["Protocol", "Title"])
    assert any("person can never resolve a merge key" in m for m in blocking)


def test_a_template_fallback_keeps_a_required_property_satisfiable():
    cfg = config()
    cfg["node_mappings"][0]["properties"][0]["fallback"] = {"template": "{Title}|{__row_index__}"}
    blocking, _ = MappingEngine(cfg).column_problems(["Title", "Email", "Name"])
    assert blocking == []


def test_losing_every_row_filter_column_blocks_because_every_row_would_be_rejected():
    cfg = config(row_filter={"require_any_non_empty": ["Protocol", "Title"]})
    blocking, _ = MappingEngine(cfg).column_problems(["Email", "Name"])
    assert any("row_filter" in m for m in blocking)


def test_no_missing_columns_means_no_problems():
    assert MappingEngine(config()).column_problems(
        ["Protocol", "Title", "Email", "Name"]
    ) == ([], [])


# ------------------------------------------------------------------ dedup

def test_two_roles_resolving_to_one_person_become_one_node_with_two_relationships():
    """Cycle 3B Task D's multi-node-same-label case: submitter and PI are the same person."""
    cfg = {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "project",
                "label": "Project",
                "key_property": "pid",
                "properties": [{"name": "pid", "column": "ID"}],
            },
            {
                "id": "submitter",
                "label": "Person",
                "key_property": "email",
                "optional": True,
                "properties": [
                    {"name": "email", "column": "Submitter", "transform": "lowercase_strip"}
                ],
            },
            {
                "id": "pi",
                "label": "Person",
                "key_property": "email",
                "optional": True,
                "properties": [{"name": "email", "column": "PI", "transform": "lowercase_strip"}],
            },
        ],
        "relationship_mappings": [
            {"type": "SUBMITTED", "from": "submitter", "to": "project"},
            {"type": "PI_OF", "from": "pi", "to": "project"},
        ],
    }
    collector = DeclarationCollector()
    engine = MappingEngine(cfg)
    collector.add_row(engine.map_row({"ID": "p1", "Submitter": "A@mit.edu", "PI": "a@MIT.edu"}, 0))

    people = [n for n in collector.node_decls() if n["label"] == "Person"]
    assert len(people) == 1, "one address is one Person"
    assert {r["type"] for r in collector.relationship_decls()} == {"SUBMITTED", "PI_OF"}


def test_dedup_merges_properties_across_rows_without_overwriting():
    cfg = config()
    engine = MappingEngine(cfg)
    collector = DeclarationCollector()
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu"}, 0))
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "Ada"}, 1))

    person = next(n for n in collector.node_decls() if n["label"] == "Person")
    assert person["properties"] == {"email": "a@mit.edu", "name": "Ada"}


def test_conflicting_values_for_one_key_are_reported_not_silently_resolved():
    engine = MappingEngine(config())
    collector = DeclarationCollector()
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "Ada"}, 0))
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "Ada L"}, 1))

    assert any("'name'" in c for c in collector.conflicts), collector.conflicts


def test_relationships_are_deduplicated():
    engine = MappingEngine(config())
    collector = DeclarationCollector()
    for index in range(3):
        collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu"}, index))
    assert len(collector.relationship_decls()) == 1


def test_drain_empties_the_collector_but_keeps_conflicts():
    engine = MappingEngine(config())
    collector = DeclarationCollector()
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "Ada"}, 0))
    collector.add_row(engine.map_row({"Protocol": "P", "Email": "a@mit.edu", "Name": "Ada L"}, 1))

    nodes, rels = collector.drain()
    assert nodes and rels
    assert collector.drain() == ([], [])
    assert collector.conflicts, "conflicts survive a drain so the report keeps them"


# ------------------------------------------------------------ vocabulary

def vocabulary_config() -> dict:
    return {
        "version": "1.0",
        "node_mappings": [
            {
                "id": "p",
                "label": "Project",
                "key_property": "pid",
                "properties": [
                    {"name": "pid", "column": "ID"},
                    {"name": "modality", "column": "Modality"},
                ],
            }
        ],
        "vocabulary_check": {
            "enabled": True,
            "severity": "warning",
            "match": "case_insensitive",
            "multi_value_transform": "split_delimiter",
            "fields": ["modality"],
            "default_vocabulary": {"modality": ["MRI", "PET"]},
        },
    }


def test_out_of_vocabulary_value_warns_and_still_produces_the_node():
    result = MappingEngine(vocabulary_config()).map_row({"ID": "p1", "Modality": "Telepathy"}, 3)

    assert len(result.nodes) == 1, "a soft check must not block the row"
    assert result.errors == []
    assert any("Telepathy" in w for w in result.warnings)


def test_vocabulary_match_is_case_insensitive_by_default():
    result = MappingEngine(vocabulary_config()).map_row({"ID": "p1", "Modality": "mri"}, 0)
    assert result.warnings == []


def test_multi_value_cell_is_split_before_each_value_is_checked():
    result = MappingEngine(vocabulary_config()).map_row({"ID": "p1", "Modality": "MRI;Nope"}, 0)
    assert len(result.warnings) == 1 and "Nope" in result.warnings[0]


def test_injected_vocabulary_overrides_the_config_default():
    engine = MappingEngine(vocabulary_config(), vocabulary={"modality": ["Telepathy"]})
    assert engine.map_row({"ID": "p1", "Modality": "Telepathy"}, 0).warnings == []
    assert engine.map_row({"ID": "p1", "Modality": "MRI"}, 1).warnings


def test_severity_error_promotes_a_vocabulary_miss():
    cfg = vocabulary_config()
    cfg["vocabulary_check"]["severity"] = "error"
    result = MappingEngine(cfg).map_row({"ID": "p1", "Modality": "Nope"}, 0)
    assert result.errors and not result.warnings


def test_disabled_vocabulary_check_does_nothing():
    cfg = vocabulary_config()
    cfg["vocabulary_check"]["enabled"] = False
    assert MappingEngine(cfg).map_row({"ID": "p1", "Modality": "Nope"}, 0).warnings == []


# ------------------------------------------------------------------ misc

def test_config_must_be_an_object():
    with pytest.raises(Exception):
        MappingEngine(["not", "a", "config"])  # type: ignore[arg-type]


def test_map_rows_is_lazy():
    """A source larger than memory is only ingestible if nothing materializes it."""
    engine = MappingEngine(config())
    consumed = []

    def rows():
        for index in range(5):
            consumed.append(index)
            yield {"Protocol": f"P-{index}"}

    stream = engine.map_rows(rows())
    next(stream)
    assert consumed == [0], "map_rows read ahead of what was asked for"


def test_a_plugin_transform_shadowing_a_core_one_warns():
    engine = MappingEngine(config(), transform_library={"lowercase_strip": lambda v: v})
    assert any("shadows" in w for w in engine.validate().warnings)
