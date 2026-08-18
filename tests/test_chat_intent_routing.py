"""Test intent classification and ReAct loop routing."""
import pytest
from scidk.services.graphrag.intent_classifier import classify, Intent
from scidk.ai.react_loop import (
    build_react_system_prompt,
    extract_action,
    is_safe_cypher,
    format_step_history
)


class TestIntentClassification:
    """Test intent routing for REACT path."""

    def test_react_intent_exploratory(self):
        """Test: Exploratory language routes to REACT."""
        queries = [
            "tell me about samples",
            "explore the relationships between treatments and samples",
            "investigate connections",
            "I'm curious about the data",
            "what can you tell me about this dataset"
        ]
        for query in queries:
            intent = classify(query)
            assert intent == Intent.REACT, f"'{query}' should route to REACT, got {intent}"

    def test_react_intent_conditional(self):
        """Test: Conditional queries route to REACT."""
        queries = ["are there any samples that have multiple treatments?"]
        for query in queries:
            intent = classify(query)
            assert intent == Intent.REACT, f"'{query}' should route to REACT, got {intent}"

    def test_lookup_still_works(self):
        """Test: LOOKUP queries don't accidentally route to REACT."""
        queries = ["how many samples are there?", "list all treatments", "count the datasets"]
        for query in queries:
            intent = classify(query)
            assert intent == Intent.LOOKUP, f"'{query}' should route to LOOKUP, got {intent}"

    def test_summarize_still_works(self):
        """Test: SUMMARIZE queries don't route to REACT."""
        queries = ["summarize the data", "what do we have?", "give me an overview of the graph"]
        for query in queries:
            intent = classify(query)
            assert intent == Intent.SUMMARIZE, f"'{query}' should route to SUMMARIZE, got {intent}"


class TestReActLoop:
    """Test ReAct loop components."""

    def test_extract_action_think(self):
        """Test: THINK action is parsed correctly."""
        response = "THINK: I need to find out how many samples there are first"
        action_type, content = extract_action(response)
        assert action_type == "THINK"
        assert "how many samples" in content

    def test_extract_action_query(self):
        """Test: QUERY action is parsed correctly."""
        response = "QUERY: MATCH (s:Sample) RETURN count(s)"
        action_type, content = extract_action(response)
        assert action_type == "QUERY"
        assert "MATCH" in content

    def test_is_safe_cypher_read_only(self):
        """Test: Read-only Cypher is allowed."""
        queries = [
            "MATCH (s:Sample) RETURN s",
            "MATCH (s:Sample)-[:HAS_TYPE]->(t:SampleType) RETURN t.name, count(s)",
        ]
        for query in queries:
            is_safe, error = is_safe_cypher(query)
            assert is_safe, f"Query should be safe: {query}, error: {error}"

    def test_is_safe_cypher_blocks_writes(self):
        """Test: Write operations are blocked."""
        dangerous_queries = [
            "CREATE (n:Sample {id: 'test'})",
            "MATCH (n:Sample) DELETE n",
            "MATCH (n:Sample) SET n.value = 100",
        ]
        for query in dangerous_queries:
            is_safe, error = is_safe_cypher(query)
            assert not is_safe, f"Query should be blocked: {query}"
            assert "Blocked" in error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
