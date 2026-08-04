"""The two things the mapping page asks of the backend that nothing else does.

``describe_transforms`` populates its dropdowns and ``mapping_summary`` its badges.
Both are deliberately opinion-free about whether a mapping can *run* — that is
``MappingEngine.validate``'s answer, and a second implementation of it here would be
something for the two to disagree about.
"""
from __future__ import annotations

import json
from pathlib import Path

from scidk.pipeline.mapping_ui import (
    RETURNS_LIST,
    RETURNS_OBJECT,
    RETURNS_OBJECT_LIST,
    RETURNS_SCALAR,
    RETURNS_UNKNOWN,
    describe_transforms,
    mapping_summary,
)
from scidk.pipeline.transforms import CORE_TRANSFORMS

AIPT = (Path(__file__).resolve().parents[2] / "plugins" / "sharepoint_intake"
        / "configs" / "aipt_intake_mapping.json")


def by_name(described):
    return {entry["name"]: entry for entry in described}


# ------------------------------------------------------- describe_transforms

def test_the_core_transforms_are_all_offered():
    described = describe_transforms()
    assert sorted(t["name"] for t in described) == sorted(CORE_TRANSFORMS)
    assert all(t["origin"] == "core" for t in described)


def test_a_plugin_library_is_layered_over_the_core_one():
    """Exactly as MappingEngine layers it, so the dropdown offers what will resolve."""
    from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

    described = by_name(describe_transforms(SHAREPOINT_TRANSFORMS))
    assert described["lowercase_strip"]["origin"] == "core"
    assert described["parse_rfc5322"]["origin"] == "plugin"
    assert len(described) == len(CORE_TRANSFORMS) + len(SHAREPOINT_TRANSFORMS)


def test_a_plugin_transform_shadowing_a_core_one_says_so():
    """The engine warns about this; the page has to say which one it is offering."""
    described = by_name(describe_transforms({"date_parse": lambda v: v}))
    assert described["date_parse"]["origin"] == "plugin"
    assert described["date_parse"]["shadows_core"] is True
    assert described["lowercase_strip"]["shadows_core"] is False


def test_a_transform_reading_the_whole_row_is_not_attachable_to_a_column():
    """The documented convention, and the reason column_resolution has no UI.

    ``sp_colresolution`` chooses *between* a _sp and an _orig column and takes no
    cell value at all, so there is no column dropdown that could express it. Saying
    that plainly beats offering it and producing a config that resolves nothing.
    """
    from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

    entry = by_name(describe_transforms(SHAREPOINT_TRANSFORMS))["sp_colresolution"]
    assert entry["takes_row"] is True
    assert entry["takes_value"] is False
    assert entry["selectable"] is False
    assert [a["name"] for a in entry["args"]] == ["prefer_col", "fallback_col"]
    assert all(a["required"] for a in entry["args"])


def test_an_optional_argument_does_not_make_a_transform_unselectable():
    """split_delimiter's delimiter has a default, so the dropdown can offer it."""
    entry = by_name(describe_transforms())["split_delimiter"]
    assert entry["selectable"] is True
    assert entry["args"] == [{"name": "delimiter", "required": False, "default": ";"}]


def test_the_return_kind_separates_object_transforms_from_scalar_ones():
    """The page needs it: an object cannot be written into one Neo4j property.

    A transform returning ``{"name", "email"}`` belongs in the source/property_map
    form and nowhere else; one returning a string fills a property directly.
    """
    from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

    described = by_name(describe_transforms(SHAREPOINT_TRANSFORMS))
    assert described["lowercase_strip"]["returns"] == RETURNS_SCALAR
    assert described["integer_coerce"]["returns"] == RETURNS_SCALAR
    assert described["sp_yesno"]["returns"] == RETURNS_SCALAR
    assert described["split_delimiter"]["returns"] == RETURNS_LIST
    assert described["sp_multiselect"]["returns"] == RETURNS_LIST
    assert described["parse_rfc5322"]["returns"] == RETURNS_OBJECT
    assert described["parse_rfc5322_list"]["returns"] == RETURNS_OBJECT_LIST


def test_an_unannotated_transform_is_reported_as_unknown_rather_than_guessed():
    described = by_name(describe_transforms({"mystery": lambda value: value}))
    assert described["mystery"]["returns"] == RETURNS_UNKNOWN
    # Still offerable: the engine will call it with a value and nothing else.
    assert described["mystery"]["selectable"] is True


def test_a_transform_with_no_signature_is_described_rather_than_crashed_on():
    """A C callable has no inspectable signature; the dropdown still has to render."""
    described = by_name(describe_transforms({"upper": str.upper}))
    assert described["upper"]["name"] == "upper"
    assert described["upper"]["takes_row"] is False


def test_the_summary_line_comes_from_the_docstring():
    entry = by_name(describe_transforms())["lowercase_strip"]
    assert entry["summary"] == "Strip surrounding whitespace and lowercase."


# ----------------------------------------------------------- mapping_summary

def test_no_mapping_is_reported_as_undefined():
    for value in (None, "", [], {}, "not a mapping"):
        summary = mapping_summary(value)
        assert summary["defined"] is False
        assert summary["node_mapping_count"] == 0


def test_the_summary_of_the_aipt_reference_config():
    """The one real instance of the format, so the numbers are checkable."""
    summary = mapping_summary(json.loads(AIPT.read_text(encoding="utf-8")))

    assert summary["defined"] is True
    assert summary["labels"] == ["Project", "Person", "Attachment"]
    assert summary["node_mapping_count"] == 5
    assert summary["relationship_mapping_count"] == 4
    # Three roles of Person: what the relationship panel's selectors are built from.
    assert summary["roles_by_label"]["Person"] == ["submitter", "pi", "collaborators"]
    assert summary["relationship_types"] == [
        "SUBMITTED", "PI_OF", "COLLABORATES_ON", "HAS_ATTACHMENT"]
    assert summary["unkeyed_roles"] == []
    # Column-per-property names plus the source-form columns; the ones named only
    # inside transform_args are MappingEngine.mapped_columns()' business.
    assert "CACProtocol" in summary["mapped_columns"]
    assert "PI Archived" in summary["mapped_columns"]
    assert "StudyType_sp" not in summary["mapped_columns"]


def test_a_role_with_no_key_is_named_so_the_card_can_say_incomplete():
    summary = mapping_summary({
        "version": "1.0",
        "node_mappings": [
            {"id": "project", "label": "Project",
             "properties": [{"name": "title", "column": "T"}]},
            {"id": "person", "label": "Person", "key_property": "email",
             "properties": [{"name": "email", "column": "E"}]},
        ],
    })
    assert summary["unkeyed_roles"] == ["project"]
    assert summary["property_count"] == 2


def test_a_malformed_entry_is_skipped_rather_than_raised_on():
    """This runs on whatever is in the column, including a hand-edited row."""
    summary = mapping_summary({
        "node_mappings": [None, "nonsense", {"id": "ok", "label": "Thing"}],
        "relationship_mappings": ["also nonsense", {"type": "REL"}],
    })
    assert summary["node_mapping_count"] == 1
    assert summary["labels"] == ["Thing"]
    assert summary["relationship_types"] == ["REL"]


def test_the_source_form_counts_its_property_map_as_properties():
    summary = mapping_summary({
        "node_mappings": [{
            "id": "pi", "label": "Person", "key_property": "email",
            "source": {"column": "PI", "transform": "parse_rfc5322"},
            "property_map": {"name": "name", "email": "email"},
        }],
    })
    assert summary["property_count"] == 2
    assert summary["mapped_columns"] == ["PI"]
