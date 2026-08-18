"""
Tests for MCP tools.

These tests verify the core MCP tool implementations work correctly
with a live Neo4j database.
"""
import pytest
from neo4j import GraphDatabase
import os

pytestmark = pytest.mark.integration


@pytest.fixture
def neo4j_driver():
    """Create a Neo4j driver for testing."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USER', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')

    driver = GraphDatabase.driver(uri, auth=(user, password))
    yield driver
    driver.close()


def test_list_labels(neo4j_driver):
    """Test list_labels tool."""
    from scidk.ai import mcp_tools

    result = mcp_tools.list_labels(neo4j_driver, database="neo4j")

    assert result["status"] == "success"
    assert "labels" in result
    assert isinstance(result["labels"], list)
    assert result["error"] is None

    # Should have at least one label
    if len(result["labels"]) > 0:
        assert "name" in result["labels"][0]
        assert "count" in result["labels"][0]


def test_get_schema(neo4j_driver):
    """Test get_schema tool."""
    from scidk.ai import mcp_tools

    result = mcp_tools.get_schema(neo4j_driver, database="neo4j")

    assert result["status"] == "success"
    assert "schema" in result
    assert "labels" in result["schema"]
    assert "relationships" in result["schema"]
    assert "properties" in result["schema"]
    assert result["error"] is None


def test_query_knowledge_graph_safe(neo4j_driver):
    """Test query_knowledge_graph with a safe query."""
    from scidk.ai import mcp_tools

    # Simple count query
    result = mcp_tools.query_knowledge_graph(
        neo4j_driver,
        "MATCH (n) RETURN count(n) as total",
        database="neo4j"
    )

    assert result["status"] == "success"
    assert "rows" in result
    assert isinstance(result["rows"], list)
    assert result["error"] is None


def test_query_knowledge_graph_blocked_write(neo4j_driver):
    """Test that write operations are blocked."""
    from scidk.ai import mcp_tools

    # Try a CREATE query (should be blocked)
    result = mcp_tools.query_knowledge_graph(
        neo4j_driver,
        "CREATE (n:Test {name: 'test'}) RETURN n",
        database="neo4j"
    )

    assert result["status"] == "error"
    assert "Forbidden keyword" in result["error"]
    assert "CREATE" in result["error"]


def test_query_knowledge_graph_auto_limit(neo4j_driver):
    """Test that LIMIT is added automatically."""
    from scidk.ai import mcp_tools

    # Query without LIMIT should have one added
    result = mcp_tools.query_knowledge_graph(
        neo4j_driver,
        "MATCH (n) RETURN n",
        database="neo4j",
        limit=5
    )

    # Should succeed and return at most 5 rows
    assert result["status"] == "success"
    assert len(result["rows"]) <= 5


def test_get_label_profile(neo4j_driver):
    """Test get_label_profile tool."""
    from scidk.ai import mcp_tools

    # First, get a label name
    labels_result = mcp_tools.list_labels(neo4j_driver, database="neo4j")
    if len(labels_result["labels"]) == 0:
        pytest.skip("No labels in database")

    label_name = labels_result["labels"][0]["name"]

    # Get profile for that label
    result = mcp_tools.get_label_profile(neo4j_driver, label_name, database="neo4j")

    assert result["status"] == "success"
    assert "profile" in result
    assert result["profile"]["label"] == label_name
    assert "node_count" in result["profile"]
    assert "properties" in result["profile"]
    assert "relationships" in result["profile"]
    assert result["error"] is None


def test_summarize_dataset(neo4j_driver):
    """Test summarize_dataset tool."""
    from scidk.ai import mcp_tools

    # Test overall summary
    result = mcp_tools.summarize_dataset(neo4j_driver, database="neo4j")

    assert result["status"] == "success"
    assert "summary" in result
    assert result["error"] is None


def test_tool_definitions_complete():
    """Test that all tools have proper definitions."""
    from scidk.ai import mcp_tools

    assert len(mcp_tools.TOOL_DEFINITIONS) == 5

    for tool_def in mcp_tools.TOOL_DEFINITIONS:
        assert "name" in tool_def
        assert "description" in tool_def
        assert "inputSchema" in tool_def
        assert "type" in tool_def["inputSchema"]
        assert tool_def["inputSchema"]["type"] == "object"
        assert "properties" in tool_def["inputSchema"]
