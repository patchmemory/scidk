"""``export_concept_graph`` / ``import_concept_graph`` — the portability pair.

Cycle 8 Task B added ``category`` to the :Concept_Tool node. Cycle 6 had deliberately
left it off, because a property that survives seeding but not an export/import
round-trip is worse than one the graph never had — so the round trip is what these
tests pin, not just the write.

No database and no Ollama: the driver is a fake that answers canned rows on the way
out and records Cypher on the way in.
"""
from __future__ import annotations

import pytest

from scidk.services.concept_graph_service import (
    export_concept_graph,
    import_concept_graph,
)


# ─────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


def _query_kind(query: str) -> str:
    """Which of export's four reads this is. Order matters: the SATISFIES query
    also matches ``Concept_Intent``, and the RETRIEVES one also matches
    ``Concept_Tool``."""
    if 'SATISFIES' in query:
        return 'satisfies'
    if 'RETRIEVES' in query:
        return 'retrieves'
    if 'Concept_Tool' in query:
        return 'tools'
    return 'intents'


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._driver.calls.append((query, params))
        return _Result(self._driver.rows.get(_query_kind(query), []))


class _FakeDriver:
    """Answers export reads from ``rows``; records every call for import assertions."""

    def __init__(self, **rows):
        self.rows = rows
        self.calls = []

    def session(self):
        return _FakeSession(self)

    def tool_writes(self):
        """The MERGE-on-Concept_Tool calls, keyed by tool name."""
        return {
            params['name']: params
            for query, params in self.calls
            if 'MERGE (t:Concept_Tool' in query
        }

    def tool_merge_query(self):
        return next(q for q, _ in self.calls if 'MERGE (t:Concept_Tool' in q)


def _tool_row(name='query_knowledge_graph', category='data_query'):
    return {
        'name': name,
        'description': 'Execute a read-only Cypher query.',
        'source': 'mcp',
        'active': True,
        'input_schema': '{"type": "object"}',
        'category': category,
    }


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────

def test_export_reads_category_off_the_node():
    driver = _FakeDriver(tools=[_tool_row()])

    data = export_concept_graph(driver)

    assert data['tools'] == [_tool_row()]
    assert data['tools'][0]['category'] == 'data_query'


def test_export_asks_for_category_in_cypher():
    """The RETURN list is the whole contract — a missing projection is a dropped
    field, and every downstream reader uses ``.get`` so nothing would raise."""
    driver = _FakeDriver()
    export_concept_graph(driver)

    tools_query = next(q for q, _ in driver.calls if _query_kind(q) == 'tools')
    assert 't.category AS category' in tools_query


def test_export_tolerates_a_tool_with_no_category():
    """Tools seeded from intents.yaml have none — the YAML declares no categories."""
    driver = _FakeDriver(tools=[_tool_row(name='cypher_query', category=None)])

    data = export_concept_graph(driver)

    assert data['tools'][0]['category'] is None


# ─────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────

def test_import_writes_category():
    target = _FakeDriver()

    result = import_concept_graph(
        target, {'tools': [_tool_row()]}, 'http://localhost:11434')

    assert result['errors'] == []
    assert result['tools_imported'] == 1
    assert target.tool_writes()['query_knowledge_graph']['category'] == 'data_query'


def test_import_of_a_pre_cycle8_snapshot_does_not_clear_category():
    """``SET t.category = null`` *removes* the property in Cypher, so a snapshot
    exported before Cycle 8 would have stripped it off every tool it touched."""
    old_snapshot_tool = {k: v for k, v in _tool_row().items() if k != 'category'}
    target = _FakeDriver()

    import_concept_graph(
        target, {'tools': [old_snapshot_tool]}, 'http://localhost:11434')

    assert target.tool_writes()['query_knowledge_graph']['category'] is None
    assert 'coalesce($category, t.category)' in target.tool_merge_query()


# ─────────────────────────────────────────────
# Round trip
# ─────────────────────────────────────────────

def test_round_trip_carries_category_to_a_fresh_instance():
    source = _FakeDriver(
        intents=[{
            'name': 'data_lookup',
            'description': 'Find specific records.',
            'examples': ['show me the projects'],
            'embedding_present': True,
        }],
        tools=[_tool_row(), _tool_row(name='get_schema', category='schema')],
        satisfies=[{
            'intent': 'data_lookup',
            'tool': 'query_knowledge_graph',
            'weight': 0.7,
            'usage_count': 3,
            'last_updated': '2026-08-01T00:00:00',
        }],
        retrieves=[{'tool': 'query_knowledge_graph', 'label': 'Project'}],
    )
    snapshot = export_concept_graph(source)

    target = _FakeDriver()
    result = import_concept_graph(target, snapshot, 'http://localhost:11434')

    assert result['errors'] == []
    assert result['tools_imported'] == 2
    assert {name: params['category']
            for name, params in target.tool_writes().items()} == {
        'query_knowledge_graph': 'data_query',
        'get_schema': 'schema',
    }


def test_seeded_categories_survive_a_round_trip(monkeypatch):
    """End to end from the canonical registry: seed, export what was written,
    import it, and check every category arrives."""
    from scidk.ai import mcp_tools
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'embed_text', lambda text, endpoint: [0.1, 0.2])

    seed_target = _FakeDriver()
    cgs.seed_mcp_tools(seed_target, 'http://localhost:11434')
    seeded = seed_target.tool_writes()

    # Export sees exactly what seeding wrote.
    source = _FakeDriver(tools=[
        {
            'name': name,
            'description': params['description'],
            'source': 'mcp',
            'active': True,
            'input_schema': params['schema'],
            'category': params['category'],
        }
        for name, params in seeded.items()
    ])
    snapshot = export_concept_graph(source)

    target = _FakeDriver()
    import_concept_graph(target, snapshot, 'http://localhost:11434')

    registry = {t['name']: t for t in mcp_tools.TOOL_DEFINITIONS}
    imported = target.tool_writes()
    assert set(imported) == set(registry)
    for name, params in imported.items():
        assert params['category'] == registry[name]['category']
        assert params['category'] in mcp_tools.TOOL_CATEGORIES


@pytest.mark.parametrize('field', ['name', 'description', 'source', 'active',
                                   'input_schema', 'category'])
def test_every_exported_tool_field_is_one_import_writes(field):
    """Keeps the two field lists from drifting apart again."""
    source = _FakeDriver(tools=[_tool_row()])
    snapshot = export_concept_graph(source)
    assert field in snapshot['tools'][0]

    target = _FakeDriver()
    import_concept_graph(target, snapshot, 'http://localhost:11434')
    written = target.tool_writes()['query_knowledge_graph']
    # `name` is the MERGE key; the rest arrive as SET parameters.
    assert field in written
