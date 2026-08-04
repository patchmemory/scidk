"""The mapping config schema, and the reference config it exists to validate.

The AIPT config is the only instance of this format, and until this schema landed
a typo in it was a runtime surprise: a misspelled ``colunm`` silently mapped
nothing, and a property named with a space became a swallowed Cypher syntax
error. Every negative case below is one of those surprises, asserted to fail
validation now.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scidk.pipeline.mapping_engine import (
    MappingEngine,
    load_mapping_schema,
    validate_against_schema,
)

REFERENCE_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "plugins/sharepoint_intake/configs/aipt_intake_mapping.json"
)


@pytest.fixture(scope="module")
def reference() -> dict:
    with REFERENCE_CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_is_itself_a_valid_json_schema():
    import jsonschema

    jsonschema.Draft202012Validator.check_schema(load_mapping_schema())


def test_reference_config_validates(reference):
    """The load-bearing assertion: the deployment's real config is legal."""
    assert validate_against_schema(reference) == []


def test_reference_config_passes_full_semantic_validation(reference):
    """Structural validity is not enough — endpoints and transforms must resolve."""
    from plugins.sharepoint_intake.transforms import SHAREPOINT_TRANSFORMS

    report = MappingEngine(reference, transform_library=SHAREPOINT_TRANSFORMS).validate()
    assert report.errors == []
    assert report.warnings == []


def mutated(reference: dict, mutate) -> dict:
    config = copy.deepcopy(reference)
    mutate(config)
    return config


@pytest.mark.parametrize(
    "description,mutate",
    [
        (
            "node_mappings misspelled as the singular",
            lambda c: c.update({"node_mapping": c.pop("node_mappings")}),
        ),
        (
            "relationship_mappings misspelled as the singular",
            lambda c: c.update({"relationship_mapping": c.pop("relationship_mappings")}),
        ),
        (
            "'column' misspelled as 'colunm'",
            lambda c: c["node_mappings"][0]["properties"][1].update({"colunm": "X"}),
        ),
        (
            "property name with a space would be a Cypher syntax error",
            lambda c: c["node_mappings"][0]["properties"].append(
                {"name": "Sample ID", "column": "X"}
            ),
        ),
        (
            "label with a space",
            lambda c: c["node_mappings"][0].update({"label": "My Project"}),
        ),
        (
            "relationship type with a dash",
            lambda c: c["relationship_mappings"][0].update({"type": "PI-OF"}),
        ),
        (
            "property naming neither a column nor a transform",
            lambda c: c["node_mappings"][0]["properties"].append({"name": "orphan"}),
        ),
        (
            "both mapping forms at once",
            lambda c: c["node_mappings"][0].update(
                {"source": {"column": "X", "transform": "lowercase_strip"}}
            ),
        ),
        (
            "missing key_property",
            lambda c: c["node_mappings"][0].pop("key_property"),
        ),
        (
            "unrecognized cardinality",
            lambda c: c["node_mappings"][0].update({"cardinality": "several"}),
        ),
        (
            "write_mode that write_declared_nodes cannot honour",
            lambda c: c["options"].update({"write_mode": "replace"}),
        ),
        (
            "no node_mappings at all",
            lambda c: c.update({"node_mappings": []}),
        ),
        (
            "missing version",
            lambda c: c.pop("version"),
        ),
    ],
)
def test_schema_rejects(reference, description, mutate):
    assert validate_against_schema(mutated(reference, mutate)), (
        f"schema accepted a config it should reject: {description}"
    )


def test_error_messages_name_the_failing_path(reference):
    broken = mutated(
        reference,
        lambda c: c["node_mappings"][0]["properties"].append({"name": "Sample ID", "column": "X"}),
    )
    errors = validate_against_schema(broken)
    assert any("node_mappings/0/properties" in e for e in errors), errors
