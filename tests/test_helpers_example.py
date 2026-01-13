"""
Example test demonstrating the tests.helpers package.

This file serves as documentation and verification that the helper modules
are correctly importable and usable in tests.
"""
import pytest
from tests.helpers.rclone import rclone_env
from tests.helpers.neo4j import inject_fake_neo4j, CypherRecorder
from tests.helpers.builders import build_tree, write_csv
from tests.helpers.asserts import assert_json, assert_error


def test_rclone_helper_example(monkeypatch):
    """Example usage of rclone test helper."""
    env_config = rclone_env(
        monkeypatch,
        listremotes=["local", "s3", "gdrive"],
        version="rclone v1.62.2"
    )
    assert env_config["version"] == "rclone v1.62.2"
    assert "s3" in env_config["listremotes"]


def test_neo4j_helper_example(monkeypatch):
    """Example usage of neo4j test helpers."""
    # Inject fake credentials to avoid connecting to real Neo4j
    inject_fake_neo4j(monkeypatch, uri="", user="", password="")

    # Use CypherRecorder to capture queries without executing them
    recorder = CypherRecorder()
    recorder.run("CREATE (n:Node {name: $name})", name="test")
    recorder.run("MATCH (n:Node) RETURN n")

    assert len(recorder.records) == 2
    assert recorder.last().query == "MATCH (n:Node) RETURN n"


def test_builders_helper_example(tmp_path):
    """Example usage of builders test helpers."""
    # Create a filesystem tree for testing
    build_tree(tmp_path, {
        'data': {
            'sample.txt': 'hello world',
            'nested': {
                'file.txt': 'nested content'
            }
        },
        'output.csv': [['id', 'name'], [1, 'Alice'], [2, 'Bob']]
    })

    assert (tmp_path / 'data' / 'sample.txt').read_text() == 'hello world'
    assert (tmp_path / 'data' / 'nested' / 'file.txt').exists()
    assert (tmp_path / 'output.csv').exists()

    # Write a standalone CSV
    write_csv(tmp_path / 'users.csv', [['id', 'email'], [1, 'test@example.com']])
    assert (tmp_path / 'users.csv').exists()


def test_asserts_helper_example(client):
    """Example usage of asserts test helpers."""
    # Test successful JSON response
    resp = client.get('/api/providers')
    data = assert_json(resp, shape=list)
    assert isinstance(data, list)

    # Test error response
    resp_err = client.get('/api/scans/nonexistent-id/status')
    error_data = assert_error(resp_err)
    assert isinstance(error_data, dict)
