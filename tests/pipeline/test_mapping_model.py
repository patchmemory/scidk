"""The mapping page's format layer, run as the browser runs it.

Task D's acceptance criterion is that the page's output passes
:meth:`MappingEngine.validate` without modification. That is a property of
``scidk/ui/static/js/pipeline_mapping.js``, so these tests execute *that file* under
Node and hand what it produces to the real engine. A Python reimplementation of
``buildConfig`` would be able to agree with itself while disagreeing with the page,
which is exactly the failure this arrangement prevents — the same reasoning behind
``schema_space_harness.js`` in Task C.

Skipped when node is not on PATH. The engine-side assertions are the point, so the
skip is per-test rather than a silent pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scidk.pipeline.mapping_engine import MappingEngine

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("mapping_model_harness.js")
MODEL = REPO / "scidk" / "ui" / "static" / "js" / "pipeline_mapping.js"
AIPT = REPO / "plugins" / "sharepoint_intake" / "configs" / "aipt_intake_mapping.json"


def run_model(
    schema: Dict[str, Any],
    mapping: Optional[Dict[str, Any]] = None,
    edits: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the edit state, apply ``edits``, and return what the page would save."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH; the page's own format layer is untested here")
    payload = json.dumps({"schema": schema, "mapping": mapping, "edits": edits or []})
    result = subprocess.run(
        [node, str(HARNESS), str(MODEL)],
        input=payload, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def validate(config: Dict[str, Any], transforms=None):
    """The engine's verdict on a config, with the SharePoint library available."""
    if transforms is None:
        from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

        transforms = SHAREPOINT_TRANSFORMS
    return MappingEngine(config, transform_library=transforms).validate()


#: A schema of the shape Task C produces: two labels, one relationship, key
#: properties declared on the nodes.
SCHEMA = {
    "nodes": [
        {"id": "n0", "caption": "Project", "labels": ["Project"],
         "properties": {"project_id": "String", "title": "String", "status": "String"},
         "key_property": "project_id"},
        {"id": "n1", "caption": "Person", "labels": ["Person"],
         "properties": {"email": "String", "name": "String"},
         "key_property": "email"},
    ],
    "relationships": [
        {"id": "r0", "type": "PI_OF", "fromId": "n1", "toId": "n0", "properties": {}},
    ],
}


# --------------------------------------------------- the empty starting point

def test_a_schema_with_no_mapping_offers_one_role_per_label():
    """Every label the schema declares is a target to map, not one to discover."""
    out = run_model(SCHEMA, None)

    assert [r["label"] for r in out["roles"]] == ["Project", "Person"]
    # The first role of a label is named after it, lowercased — that name is what a
    # relationship endpoint refers to.
    assert [r["id"] for r in out["roles"]] == ["project", "person"]
    # The schema's key_property is the default, so the common case needs no choosing.
    assert out["roles"][0]["keys"] == ["project_id"]
    assert out["roles"][1]["keys"] == ["email"]
    # Nothing is assigned yet, so nothing is emitted.
    assert out["config"]["node_mappings"] == []
    assert all(r["hasContent"] is False for r in out["roles"])


def test_the_one_role_at_each_end_is_selected_without_being_asked():
    out = run_model(SCHEMA, None)
    rel = out["rels"][0]
    assert (rel["type"], rel["fromLabel"], rel["toLabel"]) == ("PI_OF", "Person", "Project")
    assert (rel["from"], rel["to"]) == ("person", "project")


# ------------------------------------------------ the primary acceptance test

def test_a_mapping_built_in_the_ui_passes_engine_validation():
    """The definition of done, checked end to end through the page's own code."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id",
         "column": "CACProtocol"},
        {"op": "assign", "role": "project", "property": "title",
         "column": "ShortDescription"},
        {"op": "assign", "role": "project", "property": "status", "column": "StudyStatus"},
        {"op": "assign", "role": "person", "property": "email",
         "column": "UserEmail_orig", "transform": "lowercase_strip"},
        {"op": "assign", "role": "person", "property": "name", "column": "UserName_orig"},
        {"op": "rel", "type": "PI_OF", "from": "person", "to": "project"},
    ])
    config = out["config"]

    report = validate(config)
    assert report.errors == []
    assert report.ok is True

    # And it says what the user asked it to say.
    assert config["version"] == "1.0"
    project = config["node_mappings"][0]
    assert project["id"] == "project" and project["label"] == "Project"
    assert project["key_property"] == "project_id"
    assert project["properties"] == [
        {"name": "project_id", "column": "CACProtocol"},
        {"name": "title", "column": "ShortDescription"},
        {"name": "status", "column": "StudyStatus"},
    ]
    assert config["node_mappings"][1]["properties"][0] == {
        "name": "email", "column": "UserEmail_orig", "transform": "lowercase_strip",
    }
    assert config["relationship_mappings"] == [
        {"type": "PI_OF", "from": "person", "to": "project"},
    ]


def test_the_mapping_it_produces_actually_maps_a_row():
    """Validation is necessary, not sufficient: the config has to do the job too."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id",
         "column": "CACProtocol"},
        {"op": "assign", "role": "person", "property": "email", "column": "PI Email",
         "transform": "lowercase_strip"},
        {"op": "rel", "type": "PI_OF", "from": "person", "to": "project"},
    ])
    engine = MappingEngine(out["config"])
    mapped = engine.map_row({"CACProtocol": "CAC-2024-0042", "PI Email": " Jane@MIT.edu "})

    assert mapped.errors == []
    assert {(n.label, n.key_value) for n in mapped.nodes} == {
        ("Project", "CAC-2024-0042"), ("Person", "jane@mit.edu"),
    }
    assert mapped.relationships == [{
        "type": "PI_OF", "from_label": "Person", "from_match": {"email": "jane@mit.edu"},
        "to_label": "Project", "to_match": {"project_id": "CAC-2024-0042"},
    }]


# ------------------------------------------------------- two roles, one label

def test_two_roles_of_one_label_get_their_own_relationships():
    """The multi-node-same-label case: one row, a PI Person and a submitter Person."""
    schema = {
        "nodes": SCHEMA["nodes"],
        "relationships": [
            {"id": "r0", "type": "PI_OF", "fromId": "n1", "toId": "n0", "properties": {}},
            {"id": "r1", "type": "SUBMITTED", "fromId": "n1", "toId": "n0",
             "properties": {}},
        ],
    }
    out = run_model(schema, None, [
        {"op": "assign", "role": "project", "property": "project_id",
         "column": "CACProtocol"},
        {"op": "assign", "role": "person", "property": "email", "column": "PI Email"},
        {"op": "rename", "role": "person", "name": "pi"},
        # The name "person" is free again once the first role took "pi", so the
        # second role gets it — and is then named for what it represents.
        {"op": "addRole", "label": "Person"},
        {"op": "rename", "role": "person", "name": "submitter"},
        {"op": "assign", "role": "submitter", "property": "email",
         "column": "UserEmail_orig"},
        {"op": "rel", "type": "PI_OF", "from": "pi", "to": "project"},
        {"op": "rel", "type": "SUBMITTED", "from": "submitter", "to": "project"},
    ])
    assert out["problems"] == []
    config = out["config"]
    assert validate(config).errors == []

    # Two node mappings sharing a label is how the format expresses two roles.
    assert [(m["id"], m["label"]) for m in config["node_mappings"]] == [
        ("project", "Project"), ("pi", "Person"), ("submitter", "Person"),
    ]
    assert config["relationship_mappings"] == [
        {"type": "PI_OF", "from": "pi", "to": "project"},
        {"type": "SUBMITTED", "from": "submitter", "to": "project"},
    ]

    # And one row produces both Persons, each with its own relationship.
    mapped = MappingEngine(config).map_row({
        "CACProtocol": "CAC-1", "PI Email": "pi@mit.edu",
        "UserEmail_orig": "sub@mit.edu",
    })
    assert mapped.errors == []
    assert sorted(r["type"] for r in mapped.relationships) == ["PI_OF", "SUBMITTED"]


def test_renaming_a_role_carries_the_relationships_that_point_at_it():
    """Endpoints are ids, so a rename that did not move them would break them."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
        {"op": "assign", "role": "person", "property": "email", "column": "E"},
        {"op": "rel", "type": "PI_OF", "from": "person", "to": "project"},
        {"op": "rename", "role": "person", "name": "pi"},
    ])
    assert out["config"]["relationship_mappings"] == [
        {"type": "PI_OF", "from": "pi", "to": "project"},
    ]
    assert validate(out["config"]).errors == []


def test_two_roles_cannot_share_a_name():
    out = run_model(SCHEMA, None, [
        {"op": "addRole", "label": "Person"},
        {"op": "rename", "role": "person_2", "name": "person"},
    ])
    assert len(out["problems"]) == 1
    assert "already called" in out["problems"][0]
    assert [r["id"] for r in out["roles"]] == ["project", "person", "person_2"]


def test_a_role_name_that_could_not_be_referenced_is_refused():
    out = run_model(SCHEMA, None, [{"op": "rename", "role": "person", "name": "a person"}])
    assert out["problems"] and "not a usable role name" in out["problems"][0]


def test_removing_a_role_unhooks_the_relationships_that_used_it():
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
        {"op": "addRole", "label": "Person"},
        {"op": "assign", "role": "person_2", "property": "email", "column": "E2"},
        {"op": "rel", "type": "PI_OF", "from": "person_2", "to": "project"},
        {"op": "removeRole", "role": "person_2"},
    ])
    assert [r["id"] for r in out["roles"]] == ["project", "person"]
    # The relationship is not left pointing at a node mapping that no longer exists.
    assert "relationship_mappings" not in out["config"]


# ----------------------------------------- one column, several properties

def test_a_transform_returning_an_object_uses_the_source_form():
    """`"Jane Smith <j@mit.edu>"` is a name *and* an address: one column, two properties."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
        {"op": "form", "role": "person", "value": "source"},
        {"op": "source", "role": "person", "column": "PI Archived",
         "transform": "parse_rfc5322"},
        {"op": "map", "role": "person",
         "entries": [{"from": "name", "to": "name"}, {"from": "email", "to": "email"}]},
        {"op": "rel", "type": "PI_OF", "from": "person", "to": "project"},
    ])
    config = out["config"]
    assert validate(config).errors == []

    person = config["node_mappings"][1]
    assert person["source"] == {"column": "PI Archived", "transform": "parse_rfc5322"}
    assert person["property_map"] == {"name": "name", "email": "email"}
    # 'one' is the default and is left unwritten, so reopening and saving a stored
    # mapping stays a no-op.
    assert "cardinality" not in person
    assert "properties" not in person  # the two forms are mutually exclusive

    mapped = MappingEngine(
        config, transform_library=_sharepoint()
    ).map_row({"C": "CAC-1", "PI Archived": "Jane Smith <j@mit.edu>"})
    assert mapped.errors == []
    person_node = [n for n in mapped.nodes if n.label == "Person"][0]
    assert person_node.properties == {"name": "Jane Smith", "email": "j@mit.edu"}


def test_cardinality_many_produces_a_node_per_value():
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
        {"op": "form", "role": "person", "value": "source"},
        {"op": "source", "role": "person", "column": "Collaborators",
         "transform": "parse_rfc5322_list", "cardinality": "many"},
        {"op": "map", "role": "person",
         "entries": [{"from": "name", "to": "name"}, {"from": "email", "to": "email"}]},
    ])
    config = out["config"]
    assert validate(config).errors == []
    assert config["node_mappings"][1]["cardinality"] == "many"

    mapped = MappingEngine(config, transform_library=_sharepoint()).map_row(
        {"C": "CAC-1", "Collaborators": "A One <a@mit.edu>; B Two <b@mit.edu>"})
    assert mapped.errors == []
    assert sorted(n.key_value for n in mapped.nodes if n.label == "Person") == [
        "a@mit.edu", "b@mit.edu"]


def test_switching_back_to_the_column_form_drops_cardinality_many():
    """'many' requires the source form — the schema rejects the combination."""
    out = run_model(SCHEMA, None, [
        {"op": "form", "role": "person", "value": "source"},
        {"op": "source", "role": "person", "column": "X", "transform": "parse_rfc5322",
         "cardinality": "many"},
        {"op": "form", "role": "person", "value": "properties"},
        {"op": "assign", "role": "person", "property": "email", "column": "E"},
    ])
    person = [m for m in out["config"]["node_mappings"] if m["id"] == "person"][0]
    assert person.get("cardinality") != "many"
    assert "source" not in person and "property_map" not in person
    assert validate(out["config"]).errors == []


# ------------------------------------------------------- partial mappings

def test_a_role_with_columns_but_no_key_is_stored_and_reported():
    """Saving is allowed at any point; the engine is what says it cannot run yet."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "title", "column": "Desc"},
        {"op": "key", "role": "project", "property": ""},
    ])
    config = out["config"]
    assert len(config["node_mappings"]) == 1  # the work is kept, not discarded

    report = validate(config)
    assert report.ok is False
    assert any("key_property" in e for e in report.errors)


def test_an_untouched_role_is_not_emitted_at_all():
    """A role with nothing assigned is not a mapping, and not an error either."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
    ])
    assert [m["id"] for m in out["config"]["node_mappings"]] == ["project"]
    # The Person end is gone, so the relationship is not emitted pointing at nothing.
    assert "relationship_mappings" not in out["config"]
    assert validate(out["config"]).errors == []


def test_unassigning_a_property_takes_the_key_with_it():
    """Otherwise key_property names a property the mapping no longer declares."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "C"},
        {"op": "assign", "role": "project", "property": "title", "column": "T"},
        {"op": "assign", "role": "project", "property": "project_id", "column": ""},
    ])
    project = out["config"]["node_mappings"][0]
    assert [p["name"] for p in project["properties"]] == ["title"]
    assert "key_property" not in project
    # Reported as the missing key it is, not as a dangling reference.
    assert any("key_property" in e for e in validate(out["config"]).errors)


# ------------------------------------- reopening what was saved (round trip)

def test_reopening_a_saved_mapping_repopulates_every_selection():
    """The last item in the definition of done, checked field by field."""
    saved = {
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project", "key_property": "project_id",
             "properties": [
                 {"name": "project_id", "column": "CACProtocol"},
                 {"name": "title", "column": "ShortDescription"},
             ]},
            {"id": "pi", "label": "Person", "key_property": ["email", "name"],
             "optional": True, "source": {"column": "PI Archived",
                                          "transform": "parse_rfc5322"},
             "property_map": {"name": "name", "email": "email"}},
        ],
        "relationship_mappings": [{"type": "PI_OF", "from": "pi", "to": "project"}],
    }
    out = run_model(SCHEMA, saved)

    project, pi = out["roles"]
    assert project["keys"] == ["project_id"]
    assert {p["name"]: p["column"] for p in project["props"]} == {
        "project_id": "CACProtocol", "title": "ShortDescription", "status": "",
    }
    assert pi["id"] == "pi" and pi["form"] == "source"
    # A preference-order key survives as the list it is.
    assert pi["keys"] == ["email", "name"]

    # The relationship row is matched to its schema edge by (from label, type, to
    # label), so the role selectors come back set rather than empty.
    assert out["rels"] == [{"type": "PI_OF", "fromLabel": "Person", "toLabel": "Project",
                            "from": "pi", "to": "project", "include": True}]

    # And saving it straight back is a no-op.
    assert out["config"] == saved


def test_the_aipt_reference_config_survives_a_round_trip_untouched():
    """The one real-world instance of the format. Opening it must not damage it.

    Its schema is derived from itself, so every label and property the config names
    is declared — the state a user would be in after Step 2. Nothing is edited, so
    everything the page has no field for (`row_filter`, `options`,
    `vocabulary_check`, the `sp_colresolution` properties, the project-id template
    fallback, the attachment `condition`) has to come back exactly as it went in.
    """
    config = json.loads(AIPT.read_text(encoding="utf-8"))
    out = run_model(_schema_for(config), config)

    assert out["config"] == config
    assert validate(out["config"]).errors == []
    # The three roles of Person are three roles, not one.
    assert [r["id"] for r in out["roles"] if r["label"] == "Person"] == [
        "submitter", "pi", "collaborators"]
    # Its `sp_colresolution` properties are the out-of-scope form, shown as such.
    project = [r for r in out["roles"] if r["id"] == "project"][0]
    advanced = [p["name"] for p in project["props"] if p["advanced"]]
    assert advanced == ["study_type", "cell_toxicity", "measurements"]


def test_editing_one_property_of_the_aipt_config_changes_only_that():
    config = json.loads(AIPT.read_text(encoding="utf-8"))
    out = run_model(_schema_for(config), config, [
        {"op": "assign", "role": "project", "property": "study_status",
         "column": "StudyStatus_v2"},
    ])
    saved = out["config"]
    assert validate(saved).errors == []

    # Everything else is byte-identical, including the blocks with no UI at all.
    for key in ("options", "row_filter", "vocabulary_check", "source", "conventions"):
        assert saved[key] == config[key]
    project = saved["node_mappings"][0]
    changed = [p for p in project["properties"] if p["name"] == "study_status"]
    assert changed == [{"name": "study_status", "column": "StudyStatus_v2"}]
    # The template fallback on project_id is untouched.
    assert project["properties"][0]["fallback"]["template"] == \
        "{ShortDescription}|{RecordSource}|{__row_index__}"


# ------------------------------------------------------ schema drift

def test_a_mapping_naming_a_label_the_schema_dropped_is_kept_and_flagged():
    """A schema edited after the mapping was written must not delete work silently."""
    saved = {
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project", "key_property": "project_id",
             "properties": [{"name": "project_id", "column": "C"}]},
            {"id": "sample", "label": "Sample", "key_property": "sample_id",
             "properties": [{"name": "sample_id", "column": "S"}]},
        ],
    }
    out = run_model(SCHEMA, saved)

    sample = [r for r in out["roles"] if r["id"] == "sample"][0]
    assert sample["inSchema"] is False
    # Kept, so a run still produces it; the page shows it under "not in the schema".
    assert [m["id"] for m in out["config"]["node_mappings"]] == ["project", "sample"]
    assert validate(out["config"]).errors == []


def test_an_assignment_to_a_property_the_schema_dropped_is_still_editable():
    saved = {
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project", "key_property": "project_id",
             "properties": [{"name": "project_id", "column": "C"},
                            {"name": "legacy_code", "column": "OldCode"}]},
        ],
    }
    out = run_model(SCHEMA, saved)
    project = out["roles"][0]
    # The schema declares three properties; the mapping adds a fourth it dropped.
    assert [p["name"] for p in project["props"]] == [
        "project_id", "title", "status", "legacy_code"]
    assert out["config"]["node_mappings"][0] == saved["node_mappings"][0]


def test_column_usage_names_where_each_column_is_used():
    """What the left panel's "assigned" indicator reads."""
    out = run_model(SCHEMA, None, [
        {"op": "assign", "role": "project", "property": "project_id", "column": "Code"},
        {"op": "assign", "role": "project", "property": "title", "column": "Code"},
        {"op": "form", "role": "person", "value": "source"},
        {"op": "source", "role": "person", "column": "PI", "transform": "parse_rfc5322"},
    ])
    assert out["usage"] == {
        "Code": ["project.project_id", "project.title"],
        "PI": ["person (source)"],
    }


# ----------------------------------------------------------------- helpers

def _sharepoint():
    from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

    return SHAREPOINT_TRANSFORMS


def _schema_for(config: Dict[str, Any]) -> Dict[str, Any]:
    """An Arrows document declaring exactly what a mapping config names.

    Stands in for the schema a user would have drawn in Step 2 before writing this
    mapping. Built from the config rather than hand-written so the two cannot drift.
    """
    from scidk.pipeline.mapping_ui import mapping_summary

    summary = mapping_summary(config)
    by_label: Dict[str, List[str]] = {}
    for entry in config["node_mappings"]:
        names = by_label.setdefault(entry["label"], [])
        for spec in entry.get("properties") or []:
            if spec.get("name") and spec["name"] not in names:
                names.append(spec["name"])
        for target in (entry.get("property_map") or {}).values():
            if target not in names:
                names.append(target)

    nodes = [
        {"id": f"n{index}", "caption": label, "labels": [label],
         "properties": {name: "String" for name in names}}
        for index, (label, names) in enumerate(by_label.items())
    ]
    node_id = {node["labels"][0]: node["id"] for node in nodes}
    roles = {entry["id"]: entry["label"] for entry in config["node_mappings"]}
    relationships = [
        {"id": f"r{index}", "type": rel["type"], "properties": {},
         "fromId": node_id[roles[rel["from"]]], "toId": node_id[roles[rel["to"]]]}
        for index, rel in enumerate(config.get("relationship_mappings") or [])
    ]
    assert summary["defined"]
    return {"nodes": nodes, "relationships": relationships}
