"""
Tests for the Schema Intelligence layer.

Covers table creation (Cycle 1, Task A) and per-label property attribution
(Cycle 1, Task B).
"""
import sqlite3

import pytest

from scidk.services.schema_intelligence import (
    ensure_schema_intelligence_tables,
    extract_labels_and_properties,
    flush_rankings,
    log_query_usage,
)


SI_TABLES = ('usage_event', 'label_profile', 'property_ranking',
             'relationship_profile')


@pytest.fixture()
def si_conn(tmp_path):
    """A fresh scidk_settings.db-shaped database with the SI tables applied."""
    conn = sqlite3.connect(str(tmp_path / 'settings.db'))
    ensure_schema_intelligence_tables(conn)
    yield conn
    conn.close()


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _table_names(conn):
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


# ─────────────────────────────────────────────
# Task A: table creation
# ─────────────────────────────────────────────

def test_ensure_creates_all_four_tables(si_conn):
    """A fresh database gets every SI table."""
    assert SI_TABLES[0] in _table_names(si_conn)
    for table in SI_TABLES:
        assert table in _table_names(si_conn), f"{table} missing"


def test_usage_event_has_traversal_json_from_the_start(si_conn):
    """traversal_json was added by migrations.py v25; it is now part of the DDL."""
    assert 'traversal_json' in _columns(si_conn, 'usage_event')


def test_ensure_is_idempotent(tmp_path):
    """Calling it on every startup must not fail or duplicate anything."""
    conn = sqlite3.connect(str(tmp_path / 'settings.db'))
    try:
        ensure_schema_intelligence_tables(conn)
        before = _table_names(conn)
        ensure_schema_intelligence_tables(conn)
        ensure_schema_intelligence_tables(conn)
        assert _table_names(conn) == before
    finally:
        conn.close()


def test_ensure_backfills_traversal_json_on_older_database(tmp_path):
    """A usage_event created before traversal_json existed gets the column added."""
    conn = sqlite3.connect(str(tmp_path / 'settings.db'))
    try:
        conn.execute(
            """
            CREATE TABLE usage_event (
                id            INTEGER PRIMARY KEY,
                event_type    TEXT NOT NULL,
                label_name    TEXT NOT NULL,
                property_name TEXT,
                session_id    TEXT,
                source        TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        assert 'traversal_json' not in _columns(conn, 'usage_event')

        ensure_schema_intelligence_tables(conn)

        assert 'traversal_json' in _columns(conn, 'usage_event')
    finally:
        conn.close()


def test_usage_logging_works_against_the_created_tables(si_conn):
    """End to end: the tables ensure() creates are the ones the layer writes to."""
    log_query_usage(
        "MATCH (p:Project) RETURN p.cac_protocol",
        session_id='s1', sqlite_conn=si_conn,
    )
    rows = si_conn.execute(
        "SELECT label_name, property_name FROM usage_event ORDER BY id"
    ).fetchall()
    assert ('Project', None) in rows
    assert ('Project', 'cac_protocol') in rows

    assert flush_rankings(si_conn)['updated'] == 1
    ranked = si_conn.execute(
        "SELECT label_name, property_name FROM property_ranking"
    ).fetchall()
    assert ranked == [('Project', 'cac_protocol')]


# ─────────────────────────────────────────────
# Task B: property attribution
# ─────────────────────────────────────────────

def test_two_aliases_two_properties_attributed_to_the_right_label_only():
    """The contamination case from the bug report.

    Before the fix, both cac_protocol and email were logged against both
    Project and Person.
    """
    result = extract_labels_and_properties(
        "MATCH (p:Project)-[:PI_OF]-(u:Person) "
        "RETURN p.cac_protocol, u.email"
    )

    assert set(result) == {'Project', 'Person'}
    assert result['Project'] == ['cac_protocol']
    assert result['Person'] == ['email']


def test_relationship_alias_property_is_not_attributed_to_a_node_label():
    """r.since belongs to a relationship, not to Project or Person."""
    result = extract_labels_and_properties(
        "MATCH (p:Project)-[r:PI_OF]-(u:Person) RETURN p.name, r.since"
    )

    assert result['Project'] == ['name']
    assert result['Person'] == []
    assert 'since' not in result['Project']


def test_unlabelled_alias_properties_are_dropped():
    """An alias with no label cannot be attributed, so it must not spread."""
    result = extract_labels_and_properties(
        "MATCH (p:Project)-[:HAS]->(x) RETURN p.name, x.mystery"
    )

    assert result['Project'] == ['name']
    assert 'mystery' not in result['Project']


def test_multiple_aliases_on_the_same_label():
    """Two aliases bound to Person both contribute to Person."""
    result = extract_labels_and_properties(
        "MATCH (a:Person), (b:Person) RETURN a.email, b.orcid"
    )

    assert set(result) == {'Person'}
    assert sorted(result['Person']) == ['email', 'orcid']


def test_multi_label_node_attributes_to_every_label():
    result = extract_labels_and_properties(
        "MATCH (n:Project:Archived) RETURN n.cac_protocol"
    )

    assert result == {'Project': ['cac_protocol'],
                      'Archived': ['cac_protocol']}


def test_inline_map_properties_attributed_to_their_own_pattern():
    """{email: $e} on the Person pattern is a Person property, not a Project one."""
    result = extract_labels_and_properties(
        "MATCH (p:Project {cac_protocol: $c})-[:PI_OF]-(u:Person {email: $e}) "
        "RETURN p, u"
    )

    assert result['Project'] == ['cac_protocol']
    assert result['Person'] == ['email']


def test_label_with_no_properties_is_still_recorded():
    """Label-level usage events must still fire for labels with no property access."""
    result = extract_labels_and_properties("MATCH (p:Project) RETURN count(p)")

    assert result == {'Project': []}


def test_properties_are_deduplicated():
    result = extract_labels_and_properties(
        "MATCH (p:Project) WHERE p.name = 'x' RETURN p.name, p.name"
    )

    assert result['Project'] == ['name']


def test_numeric_literals_are_not_read_as_property_access():
    """1.5 must not become property '5' on some label."""
    result = extract_labels_and_properties(
        "MATCH (p:Project) WHERE p.score > 1.5 RETURN p"
    )

    assert result['Project'] == ['score']


def test_procedure_namespace_is_not_read_as_property_access():
    """db.labels() is a procedure call, not a property of any node."""
    result = extract_labels_and_properties(
        "MATCH (p:Project) CALL db.labels() YIELD label RETURN p.name, label"
    )

    assert result['Project'] == ['name']


def test_empty_and_label_free_queries_return_nothing():
    assert extract_labels_and_properties("") == {}
    assert extract_labels_and_properties("RETURN 1") == {}
    assert extract_labels_and_properties("MATCH (n) RETURN n.foo") == {}


def test_logged_usage_reflects_the_corrected_attribution(si_conn):
    """The fix reaches usage_event, not just the parser."""
    log_query_usage(
        "MATCH (p:Project)-[:PI_OF]-(u:Person) "
        "RETURN p.cac_protocol, u.email",
        session_id='s1', sqlite_conn=si_conn,
    )

    rows = set(si_conn.execute(
        "SELECT label_name, property_name FROM usage_event "
        "WHERE property_name IS NOT NULL"
    ).fetchall())

    assert rows == {('Project', 'cac_protocol'), ('Person', 'email')}
