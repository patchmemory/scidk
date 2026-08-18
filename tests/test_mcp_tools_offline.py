"""Tests for MCP tools that do not need a live Neo4j.

`tests/test_mcp_tools.py` exercises the same module against a real database and
skips/fails without one. These tests use a fake driver so the safety filter, the
query construction, and the Schema Intelligence routing are covered on every run.
"""
import sqlite3

import pytest

from scidk.ai import mcp_tools
from scidk.services.schema_intelligence import ensure_schema_intelligence_tables


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


# ── Task B: label is guarded before it reaches Cypher ────────────────────────

MALFORMED_LABELS = [
    # Backtick escapes the quoting and appends a clause.
    'Sample` ) DETACH DELETE (n) //',
    '`',
    # Whitespace / punctuation / operators.
    'Sample Type',
    'Sample-Type',
    'Sample:Type',
    'Sample(n)',
    'Sample;MATCH',
    'Sample\nMATCH',
    # Leading digit is not a valid identifier.
    '1Sample',
    # Non-string.
    42,
    ['Sample'],
]

# Falsy values are a missing label rather than a malformed one. get_label_profile
# requires a label so they are still an error there; summarize_dataset treats a
# falsy label as "summarize the whole dataset", so it is not passed them.
UNSAFE_LABELS = MALFORMED_LABELS + ['', None]


@pytest.mark.parametrize('label', UNSAFE_LABELS)
def test_get_label_profile_rejects_unsafe_label(label):
    driver = _FakeDriver()
    result = mcp_tools.get_label_profile(driver, label)

    assert result['status'] == 'error'
    assert result['profile'] is None
    assert 'Invalid label' in result['error']
    # Rejected before any Cypher was built or run.
    assert driver.calls == []


@pytest.mark.parametrize('label', MALFORMED_LABELS)
def test_summarize_dataset_rejects_unsafe_label(label):
    driver = _FakeDriver()
    result = mcp_tools.summarize_dataset(driver, label=label)

    assert result['status'] == 'error'
    assert 'Invalid label' in result['error']
    assert driver.calls == []


def test_summarize_dataset_rejects_unsafe_relationship():
    driver = _FakeDriver()
    result = mcp_tools.summarize_dataset(
        driver, relationship='REL`]->() DETACH DELETE (n) //'
    )

    assert result['status'] == 'error'
    assert 'Invalid relationship' in result['error']
    assert driver.calls == []


@pytest.mark.parametrize('label', ['Sample', '_Internal', 'Sample_Type', 'File2'])
def test_get_label_profile_accepts_valid_labels(label, missing_settings_db):
    driver = _FakeDriver(responses={'count(n) as count': [{'count': 3}]})
    result = mcp_tools.get_label_profile(
        driver, label, settings_db_path=missing_settings_db
    )

    assert result['status'] == 'success', result['error']
    assert result['profile']['label'] == label
    # The label reached the query inside backticks, so the label index is used.
    assert f'(n:`{label}`)' in driver.calls[0]['cypher']


# ── Task C: get_label_profile is shaped by the Schema Intelligence layer ──────

# Neo4j frequency order for the fixture label. Ranking must be able to reorder
# this, so the assertions below only hold if SI actually drove the order.
PROFILE_RESPONSES = {
    'count(n) as count': [{'count': 42}],
    'UNWIND keys(n) AS prop': [
        {'prop': 'name', 'freq': 42},
        {'prop': 'path', 'freq': 40},
        {'prop': 'size', 'freq': 30},
        {'prop': 'genotype', 'freq': 3},
        {'prop': '_imported_stub', 'freq': 1},
    ],
    'WITH type(r) as rel_type': [
        {'rel_type': 'CONTAINS', 'target_label': 'File', 'freq': 12},
    ],
}


@pytest.fixture()
def si_db(tmp_path):
    """A settings DB with the Schema Intelligence tables created."""
    path = tmp_path / 'scidk_settings.db'
    conn = sqlite3.connect(str(path))
    ensure_schema_intelligence_tables(conn)
    conn.commit()
    yield conn, str(path)
    conn.close()


@pytest.fixture()
def missing_settings_db(tmp_path):
    """A path where no settings DB exists, to force the fallback path."""
    return str(tmp_path / 'does_not_exist.db')


def _profile_driver():
    return _FakeDriver(responses=PROFILE_RESPONSES)


def _rank(conn, label, prop, rank):
    conn.execute(
        "INSERT INTO property_ranking (label_name, property_name, rank) "
        "VALUES (?, ?, ?)",
        (label, prop, rank),
    )
    conn.commit()


def test_properties_returned_in_rank_order_not_frequency_order(si_db):
    conn, path = si_db
    # Rank the rarest property highest — the opposite of frequency order.
    _rank(conn, 'Sample', 'genotype', 9.0)
    _rank(conn, 'Sample', 'size', 5.0)

    result = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )

    profile = result['profile']
    assert profile['schema_intelligence'] == 'applied'
    names = [p['name'] for p in profile['properties']]
    assert names[:2] == ['genotype', 'size']
    # Frequencies from Neo4j survive the reordering.
    assert profile['properties'][0]['frequency'] == 3
    # Unranked properties follow, and nothing is lost.
    assert set(names) == {'name', 'path', 'size', 'genotype', '_imported_stub'}
    assert path  # fixture sanity


def test_profile_includes_context_mode_and_pins(si_db):
    conn, _ = si_db
    conn.execute(
        "INSERT INTO label_profile (label_name, description, chat_context_mode, "
        "chat_context_n, always_include, never_include) VALUES (?, ?, ?, ?, ?, ?)",
        ('Sample', 'A biological sample', 'top_n', 3,
         '["genotype"]', '["_imported_stub"]'),
    )
    conn.commit()

    result = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )

    profile = result['profile']
    assert profile['description'] == 'A biological sample'
    assert profile['chat_context_mode'] == 'top_n'
    assert profile['chat_context_n'] == 3
    assert profile['always_include'] == ['genotype']
    assert profile['never_include'] == ['_imported_stub']

    names = [p['name'] for p in profile['properties']]
    # always_include is pinned to the front...
    assert names[0] == 'genotype'
    # ...and never_include is dropped entirely.
    assert '_imported_stub' not in names
    # chat_context_properties is the truncated view the chat path would send.
    assert profile['chat_context_properties'] == names[:3]


def test_excluded_label_reports_empty_chat_context(si_db):
    conn, _ = si_db
    conn.execute(
        "INSERT INTO label_profile (label_name, chat_context_mode) VALUES (?, ?)",
        ('Sample', 'exclude'),
    )
    conn.commit()

    profile = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )['profile']

    assert profile['chat_context_mode'] == 'exclude'
    assert profile['chat_context_properties'] == []
    # The label is excluded from chat prompts, not from an explicit lookup.
    assert profile['node_count'] == 42
    assert len(profile['properties']) == 5


def test_falls_back_to_si_defaults_when_no_profile_row(si_db):
    """Tables exist, this label has no label_profile row."""
    conn, _ = si_db

    profile = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )['profile']

    assert profile['schema_intelligence'] == 'applied'
    assert profile['description'] is None
    assert profile['chat_context_mode'] == 'top_n'
    assert profile['chat_context_n'] == 5
    assert profile['always_include'] == []
    assert profile['never_include'] == []
    # No ranking rows either, so frequency order is preserved.
    assert [p['name'] for p in profile['properties']] == [
        'name', 'path', 'size', 'genotype', '_imported_stub'
    ]


def test_falls_back_when_settings_db_is_absent(missing_settings_db):
    result = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', settings_db_path=missing_settings_db
    )

    profile = result['profile']
    assert result['status'] == 'success'
    assert profile['schema_intelligence'] == 'unavailable'
    assert profile['node_count'] == 42
    assert [p['name'] for p in profile['properties']] == [
        'name', 'path', 'size', 'genotype', '_imported_stub'
    ]
    assert profile['chat_context_mode'] == 'top_n'


def test_absent_settings_db_is_not_created(missing_settings_db):
    import os

    mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', settings_db_path=missing_settings_db
    )

    assert not os.path.exists(missing_settings_db)


def test_falls_back_when_si_tables_are_missing(tmp_path):
    """A settings DB that predates the SI tables must not break the tool."""
    path = tmp_path / 'bare.db'
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()

    result = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )
    conn.close()

    assert result['status'] == 'success'
    assert result['profile']['schema_intelligence'] == 'unavailable'
    assert len(result['profile']['properties']) == 5


def test_caller_supplied_connection_is_left_open(si_db):
    conn, _ = si_db

    mcp_tools.get_label_profile(_profile_driver(), 'Sample', sqlite_conn=conn)

    # Still usable — the tool only closes connections it opened itself.
    conn.execute("SELECT 1").fetchone()


def test_property_truncation_is_reported(si_db):
    conn, _ = si_db
    many = [
        {'prop': f'p{i}', 'freq': mcp_tools.MAX_PROPERTY_KEYS - i}
        for i in range(mcp_tools.MAX_PROPERTY_KEYS)
    ]
    driver = _FakeDriver(responses={
        'count(n) as count': [{'count': 1}],
        'UNWIND keys(n) AS prop': many,
        'WITH type(r) as rel_type': [],
    })

    profile = mcp_tools.get_label_profile(
        driver, 'Sample', sqlite_conn=conn
    )['profile']

    assert profile['properties_truncated'] is True
    assert f'LIMIT {mcp_tools.MAX_PROPERTY_KEYS}' in driver.calls[1]['cypher']


def test_property_truncation_flag_false_for_small_labels(si_db):
    conn, _ = si_db

    profile = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )['profile']

    assert profile['properties_truncated'] is False


def test_no_raw_count_ordering_left_in_the_response(si_db):
    """The relationship list is still Neo4j's, and still shaped as before."""
    conn, _ = si_db

    profile = mcp_tools.get_label_profile(
        _profile_driver(), 'Sample', sqlite_conn=conn
    )['profile']

    assert profile['relationships'] == [
        {'type': 'CONTAINS', 'target': 'File', 'frequency': 12}
    ]
