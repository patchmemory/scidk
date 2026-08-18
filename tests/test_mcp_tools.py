"""
Tests for MCP tools.

These tests verify the core MCP tool implementations work correctly
with a live Neo4j database.
"""
import pytest
from neo4j import GraphDatabase
import os


@pytest.fixture
def neo4j_driver():
    """A live Neo4j driver, or skip the test that asked for it.

    Skipped rather than marked ``integration`` at module scope: half of this
    file needs no database at all (the registry tests below assert on
    TOOL_DEFINITIONS, which is pure data), and deselecting those along with
    these would quietly drop the guard on the canonical tool list.

    verify_connectivity() before yielding, so "no graph here" reports as a
    skip naming the URI instead of six assert 'error' == 'success' failures
    that read like the tools are broken.
    """
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USER', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception as e:
        driver.close()
        pytest.skip(f"live Neo4j required at {uri}: {type(e).__name__}: {e}")
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
        assert "input_schema" in tool_def
        assert "type" in tool_def["input_schema"]
        assert tool_def["input_schema"]["type"] == "object"
        assert "properties" in tool_def["input_schema"]
        assert tool_def["category"] in mcp_tools.TOOL_CATEGORIES


def test_registry_is_the_only_tool_list():
    """The pre-Cycle-6 second list is gone, not merely unused.

    Both the MCP server and Concept Graph seeding read TOOL_DEFINITIONS now.
    A reintroduced MCP_TOOL_DEFINITIONS would silently take one of them back.
    """
    from scidk.ai import mcp_tools

    assert not hasattr(mcp_tools, 'MCP_TOOL_DEFINITIONS')


def test_every_category_is_used():
    """No declared category is dead, and every tool's category is declared."""
    from scidk.ai import mcp_tools

    declared = set(mcp_tools.TOOL_CATEGORIES)
    used = {t['category'] for t in mcp_tools.TOOL_DEFINITIONS}

    assert used == declared


def test_get_tool_definitions_unfiltered_returns_whole_registry():
    from scidk.ai import mcp_tools

    tools = mcp_tools.get_tool_definitions()

    assert [t['name'] for t in tools] == [
        t['name'] for t in mcp_tools.TOOL_DEFINITIONS
    ]
    # A new list, so a caller appending to it cannot corrupt the registry.
    assert tools is not mcp_tools.TOOL_DEFINITIONS


def test_get_tool_definitions_filters_by_category():
    from scidk.ai import mcp_tools

    schema_tools = mcp_tools.get_tool_definitions('schema')

    assert {t['name'] for t in schema_tools} == {
        'get_schema', 'get_label_profile', 'list_labels'
    }
    assert [t['name'] for t in mcp_tools.get_tool_definitions('data_query')] == [
        'query_knowledge_graph'
    ]
    assert [t['name'] for t in mcp_tools.get_tool_definitions('summarization')] == [
        'summarize_dataset'
    ]


def test_get_tool_definitions_rejects_unknown_category():
    """An unknown category raises rather than answering with an empty list."""
    from scidk.ai import mcp_tools

    with pytest.raises(ValueError, match='Unknown category'):
        mcp_tools.get_tool_definitions('nonexistent')


def test_mcp_list_tools_shape_matches_registry():
    """The MCP boundary maps input_schema → inputSchema for every entry.

    Asserted against the registry rather than the running server: importing
    scidk.mcp_server needs the `mcp` package, which is not a test dependency.
    What can break here is a registry entry missing the key the handler reads.
    """
    from scidk.ai import mcp_tools

    for tool_def in mcp_tools.TOOL_DEFINITIONS:
        # The three keys scidk/mcp_server.py:list_tools subscripts directly.
        assert isinstance(tool_def['name'], str) and tool_def['name']
        assert isinstance(tool_def['description'], str) and tool_def['description']
        assert isinstance(tool_def['input_schema'], dict)
