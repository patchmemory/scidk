"""Tests for post-commit :Dataset node creation.

These exercise ``write_dataset_nodes`` end-to-end against a temporary SQLite path
index (populated like a real scan) and a fake Neo4j client that records the
Cypher it would run, so no live Neo4j is required.
"""
import pathlib

import pytest

from scidk.core import path_index_sqlite as pix
from scidk.core.profile_registry import ProfileRegistry
from scidk.services.dataset_node_service import write_dataset_nodes

PROFILES_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scidk"
    / "interpreters"
    / "profiles"
)

HOST = "host-1"
SCAN_ID = "scan-123"


class FakeNeo4jClient:
    """Records execute_write calls; mimics a connected Neo4jClient."""

    def __init__(self):
        self._driver = object()  # truthy -> _is_connected() returns True
        self.calls = []

    def execute_write(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        # Emulate the dataset MERGE returning a freshly-created node.
        if "MERGE (d:Dataset" in query:
            return [{"created": True}]
        return []

    def close(self):
        pass


def _registry_from(*yaml_names):
    """Build a ProfileRegistry loaded only with the named profile YAMLs."""
    return _registry_with_files(
        [(name, (PROFILES_DIR / name).read_text()) for name in yaml_names]
    )


def _registry_with_files(name_content_pairs, tmp_path=None):
    import tempfile

    reg = ProfileRegistry()
    base = pathlib.Path(tempfile.mkdtemp())
    for name, content in name_content_pairs:
        (base / name).write_text(content)
    reg.load(base)
    return reg


def _seed_files(rows):
    conn = pix.connect()
    pix.init_db(conn)
    try:
        cur = conn.cursor()
        for r in rows:
            cur.execute(
                "INSERT INTO files(path, parent_path, name, depth, type, size, "
                "modified_time, file_extension, mime_type, etag, hash, remote, "
                "scan_id, extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r["path"], r["parent_path"], r["name"], r.get("depth", 1),
                    r["type"], r.get("size", 10), None, r.get("ext"), None,
                    None, None, None, SCAN_ID, None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIDK_DB_PATH", str(tmp_path / "files.db"))
    yield


def test_tiff_directory_writes_tiff_collection_dataset(temp_db):
    # A directory of .tif files whose names are NOT a numbered sequence, so the
    # most specific match is tiff_collection (TIFFCollection), not image_sequence.
    dir_path = "remote:bucket/scan"
    _seed_files([
        {"path": f"{dir_path}/alpha.tif", "parent_path": dir_path, "name": "alpha.tif", "type": "file", "ext": ".tif"},
        {"path": f"{dir_path}/beta.tif", "parent_path": dir_path, "name": "beta.tif", "type": "file", "ext": ".tif"},
        {"path": f"{dir_path}/notes.txt", "parent_path": dir_path, "name": "notes.txt", "type": "file", "ext": ".txt"},
    ])

    reg = ProfileRegistry()
    reg.load(PROFILES_DIR)  # real registry incl. file_collection catch-all
    client = FakeNeo4jClient()

    result = write_dataset_nodes(SCAN_ID, HOST, client, reg)

    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["errors"] == []

    # The Dataset MERGE must set type = "TIFFCollection".
    merge_calls = [c for c in client.calls if "MERGE (d:Dataset" in c[0]]
    assert len(merge_calls) == 1
    params = merge_calls[0][1]
    assert params["type"] == "TIFFCollection"
    assert params["profile_id"] == "tiff_collection"
    assert params["dir_path"] == dir_path
    assert params["host"] == HOST

    # Files are linked via (:Dataset)-[:CONTAINS]->(:File) matched on (path, host).
    link_calls = [c for c in client.calls if "[:CONTAINS]" in c[0]]
    assert len(link_calls) == 1
    link_params = link_calls[0][1]
    assert set(link_params["file_paths"]) == {f"{dir_path}/alpha.tif", f"{dir_path}/beta.tif", f"{dir_path}/notes.txt"}
    assert link_params["host"] == HOST


def test_no_matching_profile_writes_no_dataset(temp_db):
    # Registry without the file_collection catch-all; a directory of .txt files
    # matches nothing, so no Dataset node is written.
    dir_path = "remote:bucket/docs"
    _seed_files([
        {"path": f"{dir_path}/a.txt", "parent_path": dir_path, "name": "a.txt", "type": "file", "ext": ".txt"},
        {"path": f"{dir_path}/b.txt", "parent_path": dir_path, "name": "b.txt", "type": "file", "ext": ".txt"},
    ])

    reg = _registry_from("tiff_collection.yaml")  # no file_collection -> no catch-all
    client = FakeNeo4jClient()

    result = write_dataset_nodes(SCAN_ID, HOST, client, reg)

    assert result["created"] == 0
    assert result["updated"] == 0
    assert [c for c in client.calls if "MERGE (d:Dataset" in c[0]] == []


def test_disabled_profile_is_skipped(temp_db):
    # scidk_dataset is disabled by default; a directory with a .scidk.yaml
    # descriptor must not produce a Dataset node.
    dir_path = "remote:bucket/userds"
    _seed_files([
        {"path": f"{dir_path}/.scidk.yaml", "parent_path": dir_path, "name": ".scidk.yaml", "type": "file", "ext": ".yaml"},
        {"path": f"{dir_path}/data.bin", "parent_path": dir_path, "name": "data.bin", "type": "file", "ext": ".bin"},
    ])

    reg = ProfileRegistry()
    reg.load(PROFILES_DIR)  # full registry: file_collection abstract, scidk_dataset disabled
    client = FakeNeo4jClient()

    result = write_dataset_nodes(SCAN_ID, HOST, client, reg)

    assert result["created"] == 0
    assert [c for c in client.calls if "MERGE (d:Dataset" in c[0]] == []


def test_abstract_profile_never_emits_node(temp_db):
    # A directory that matches ONLY the abstract file_collection (no specific or
    # enabled profile applies) produces no Dataset node.
    dir_path = "remote:bucket/misc"
    _seed_files([
        {"path": f"{dir_path}/data.bin", "parent_path": dir_path, "name": "data.bin", "type": "file", "ext": ".bin"},
    ])

    reg = ProfileRegistry()
    reg.load(PROFILES_DIR)
    client = FakeNeo4jClient()

    result = write_dataset_nodes(SCAN_ID, HOST, client, reg)

    assert result["created"] == 0
    assert [c for c in client.calls if "MERGE (d:Dataset" in c[0]] == []


def test_sqlite_setting_enables_scidk_dataset(temp_db, monkeypatch):
    # The Settings-UI preference (profile_enabled_scidk_dataset=true in SQLite)
    # overrides the YAML default and turns on the otherwise-disabled profile.
    dir_path = "remote:bucket/userds"
    _seed_files([
        {"path": f"{dir_path}/dataset.scidk.yaml", "parent_path": dir_path, "name": "dataset.scidk.yaml", "type": "file", "ext": ".yaml"},
    ])

    # Override the settings lookup used inside _profile_enabled (imported lazily
    # from scidk.core.settings) to simulate the Settings-UI preference.
    from scidk.core import settings as settings_mod
    monkeypatch.setattr(
        settings_mod,
        "get_setting",
        lambda key, default=None: "true" if key == "profile_enabled_scidk_dataset" else default,
    )

    reg = ProfileRegistry()
    reg.load(PROFILES_DIR)
    client = FakeNeo4jClient()

    result = write_dataset_nodes(SCAN_ID, HOST, client, reg)

    assert result["created"] == 1
    merge_calls = [c for c in client.calls if "MERGE (d:Dataset" in c[0]]
    assert len(merge_calls) == 1
    assert merge_calls[0][1]["type"] == "UserDefinedDataset"
    assert merge_calls[0][1]["profile_id"] == "scidk_dataset"
