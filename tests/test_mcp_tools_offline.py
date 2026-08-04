"""Tests for MCP tools that do not need a live Neo4j.

`tests/test_mcp_tools.py` exercises the same module against a real database and
skips/fails without one. These tests use a fake driver so the safety filter and
the query construction are covered on every run.
"""
import pytest

from scidk.ai import mcp_tools


# ── Fakes ────────────────────────────────────────────────────────────────────

class _FakeResult:
    """Stands in for neo4j.Result — iterable of dict-like records."""

    def __init__(self, records=None):
        self._records = list(records or [])

    def single(self):
        return self._records[0] if self._records else None

    def __iter__(self):
        return iter(self._records)


class _FakeSession:
    def __init__(self, recorder, responses=None):
        self._recorder = recorder
        self._responses = responses or {}

    def run(self, cypher, parameters=None, **kwargs):
        params = dict(parameters or {})
        params.update(kwargs)
        self._recorder.append({'cypher': cypher, 'params': params})
        for needle, records in self._responses.items():
            if needle in cypher:
                return _FakeResult(records)
        return _FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def __init__(self, responses=None):
        self.calls = []
        self._responses = responses or {}

    def session(self, database=None):
        return _FakeSession(self.calls, self._responses)

    def close(self):
        pass


# ── Task A: write-keyword filter uses word boundaries ────────────────────────

READ_QUERIES_WITH_KEYWORD_SUBSTRINGS = [
    # `created_at` contains CREATE
    "MATCH (n:Sample) RETURN n.created_at ORDER BY n.created_at DESC",
    # `dataset` contains SET
    "MATCH (d:Dataset) RETURN d.dataset_id, d.name",
    # `OFFSET` contains SET
    "MATCH (n) RETURN n.offset, n.dataset LIMIT 10",
    # `n.merged` contains MERGE, `n.deleted` contains DELETE
    "MATCH (n) WHERE n.merged = true AND n.deleted IS NULL RETURN n",
    # `dropped_at` contains DROP, `removed_by` contains REMOVE
    "MATCH (n) RETURN n.dropped_at, n.removed_by",
    # Cypher operator spellings that must survive tokenization
    "MATCH (n) WHERE n.created_at IS NOT NULL AND n.name STARTS WITH 'x' RETURN n",
    "MATCH (a)-[r]->(b) WHERE a.dataset <> b.dataset RETURN a, b",
]

WRITE_QUERIES = [
    ("CREATE (n:Test {name: 'test'}) RETURN n", 'CREATE'),
    ("MERGE (n:Node {id: 1}) RETURN n", 'MERGE'),
    ("MATCH (n:Test) DELETE n", 'DELETE'),
    ("MATCH (n:Test) DETACH DELETE n", 'DELETE'),
    ("MATCH (n) SET n.flag = true", 'SET'),
    ("MATCH (n) REMOVE n:Test", 'REMOVE'),
    ("DROP INDEX ON :Test(name)", 'DROP'),
    # No whitespace between keyword and pattern
    ("CREATE(n:Test) RETURN n", 'CREATE'),
    # Lower case
    ("match (n) set n.x = 1", 'SET'),
    # Hidden after a comment / newline
    ("MATCH (n)\n// harmless\nDELETE n", 'DELETE'),
    # Second statement after a semicolon
    ("MATCH (n) RETURN n; CREATE (m:Test)", 'CREATE'),
    # Inside a CALL subquery
    ("MATCH (n) CALL { WITH n CREATE (m:Test) } RETURN n", 'CREATE'),
    # ON CREATE SET after a MERGE
    ("MERGE (n:Test) ON CREATE SET n.x = 1", 'CREATE'),
]


@pytest.mark.parametrize('cypher', READ_QUERIES_WITH_KEYWORD_SUBSTRINGS)
def test_read_query_with_keyword_substring_is_allowed(cypher):
    driver = _FakeDriver()
    result = mcp_tools.query_knowledge_graph(driver, cypher)

    assert result['status'] == 'success', result['error']
    assert result['error'] is None
    # The query actually reached the driver rather than being rejected.
    assert len(driver.calls) == 1


@pytest.mark.parametrize('cypher,keyword', WRITE_QUERIES)
def test_write_query_is_blocked(cypher, keyword):
    driver = _FakeDriver()
    result = mcp_tools.query_knowledge_graph(driver, cypher)

    assert result['status'] == 'error'
    assert 'Forbidden keyword' in result['error']
    assert keyword in result['error']
    assert result['rows'] is None
    assert result['row_count'] == 0
    # Rejected before any database round trip.
    assert driver.calls == []


def test_limit_appended_when_absent():
    driver = _FakeDriver()
    mcp_tools.query_knowledge_graph(driver, "MATCH (n) RETURN n", limit=7)

    assert driver.calls[0]['cypher'].endswith('LIMIT 7')


def test_limit_not_duplicated_when_present():
    driver = _FakeDriver()
    mcp_tools.query_knowledge_graph(driver, "MATCH (n) RETURN n LIMIT 3", limit=50)

    assert driver.calls[0]['cypher'].count('LIMIT') == 1


def test_limit_appended_for_property_named_like_the_clause():
    """`n.limit_value` is not a LIMIT clause, so a real one is still needed."""
    driver = _FakeDriver()
    mcp_tools.query_knowledge_graph(driver, "MATCH (n) RETURN n.limit_value", limit=5)

    assert driver.calls[0]['cypher'].endswith('LIMIT 5')


def test_trailing_semicolon_stripped_before_limit():
    driver = _FakeDriver()
    mcp_tools.query_knowledge_graph(driver, "MATCH (n) RETURN n;", limit=5)

    assert driver.calls[0]['cypher'] == 'MATCH (n) RETURN n LIMIT 5'
