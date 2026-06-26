import pathlib
import re

import pytest
import yaml

PROFILES_DIR = pathlib.Path(__file__).resolve().parents[1] / "scidk" / "interpreters" / "profiles"

PROFILE_FILES = [
    "file_collection.yaml",
    "tiff_collection.yaml",
    "csv_collection.yaml",
    "image_sequence.yaml",
    "scidk_dataset.yaml",
]


def _load(filename):
    path = PROFILES_DIR / filename
    assert path.exists(), f"Missing profile YAML: {path}"
    with path.open() as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("filename", PROFILE_FILES)
def test_profile_yaml_has_required_fields(filename):
    data = _load(filename)

    assert isinstance(data, dict), f"{filename} did not parse to a mapping"

    # profile_id present and non-empty
    assert data.get("profile_id"), f"{filename} missing profile_id"

    # graph.node_label present
    graph = data.get("graph")
    assert isinstance(graph, dict), f"{filename} missing graph section"
    assert graph.get("node_label"), f"{filename} missing graph.node_label"

    # graph.properties present and a mapping
    properties = graph.get("properties")
    assert isinstance(properties, dict) and properties, (
        f"{filename} missing graph.properties"
    )


@pytest.mark.parametrize("filename", PROFILE_FILES)
def test_profile_yaml_enabled_is_bool(filename):
    data = _load(filename)
    assert "enabled" in data, f"{filename} missing enabled field"
    assert isinstance(data["enabled"], bool), f"{filename} enabled must be a bool"


def test_specific_profiles_enabled_by_default():
    for filename in ("tiff_collection.yaml", "csv_collection.yaml", "image_sequence.yaml"):
        assert _load(filename)["enabled"] is True, f"{filename} should be enabled by default"


def test_file_collection_is_abstract():
    data = _load("file_collection.yaml")
    assert data.get("abstract") is True, "file_collection must be abstract"


def test_scidk_dataset_profile():
    data = _load("scidk_dataset.yaml")
    assert data["profile_id"] == "scidk_dataset"
    assert data["inherits"] == "file_collection"
    # Disabled by default — user opts in via Settings UI.
    assert data["enabled"] is False
    assert data["graph"]["properties"]["type"] == "UserDefinedDataset"
    assert data["graph"]["properties"]["profile"] == "scidk_dataset"
    # Triggers on the SciDK descriptor filenames.
    pattern = data["trigger"]["filename_pattern"]
    assert re.search(pattern, ".scidk.yaml")
    assert re.search(pattern, "dataset.scidk.yaml")
    assert not re.search(pattern, "notes.yaml")
