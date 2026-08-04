"""``seed_mcp_tools`` — the Concept Graph consumer of the canonical tool registry.

Cycle 6 Task A moved this function off a second, drifted list and onto
``mcp_tools.TOOL_DEFINITIONS``. The registry's schema key is ``input_schema``
where the old list's was ``parameters``, and the write is
``json.dumps(tool.get('input_schema', {}))`` — a ``.get`` with a default, so
reading the wrong key would not raise, it would quietly store ``{}`` on every
:Concept_Tool node. That is what these tests are for.

No database and no Ollama: the driver is a fake that records Cypher, and
``embed_text`` is monkeypatched. Both are the only two things the function
touches externally.
"""
from __future__ import annotations

import json

import pytest


class FakeSession:
    """Records every ``run`` call. Returns nothing — the function ignores results."""

    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._calls.append((query, params))
        return None


class FakeDriver:
    def __init__(self):
        self.calls = []

    def session(self):
        return FakeSession(self.calls)


@pytest.fixture
def seeded(monkeypatch):
    """Run ``seed_mcp_tools`` against a fake driver; return (result, driver)."""
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'embed_text', lambda text, endpoint: [0.1, 0.2, 0.3])

    driver = FakeDriver()
    result = cgs.seed_mcp_tools(driver, 'http://localhost:11434')
    return result, driver


def _tool_writes(driver):
    """The MERGE-on-Concept_Tool calls, keyed by tool name."""
    return {
        params['name']: params
        for query, params in driver.calls
        if 'MERGE (t:Concept_Tool' in query
    }


def test_seeds_every_tool_in_the_canonical_registry(seeded):
    from scidk.ai import mcp_tools

    result, driver = seeded

    assert result['failed'] == 0
    assert result['errors'] == []
    assert result['seeded'] == len(mcp_tools.TOOL_DEFINITIONS)
    assert set(_tool_writes(driver)) == {
        t['name'] for t in mcp_tools.TOOL_DEFINITIONS
    }


def test_stores_the_real_json_schema_not_an_empty_dict(seeded):
    """The ``parameters`` → ``input_schema`` key rename actually took effect."""
    from scidk.ai import mcp_tools

    _, driver = seeded
    writes = _tool_writes(driver)
    registry = {t['name']: t for t in mcp_tools.TOOL_DEFINITIONS}

    for name, params in writes.items():
        stored = json.loads(params['schema'])
        assert stored == registry[name]['input_schema']
        assert stored != {}, f"{name} was seeded with an empty schema"

    # And the schema is a real JSON Schema, not the old pseudo-type map.
    assert json.loads(writes['query_knowledge_graph']['schema'])['required'] == [
        'cypher'
    ]


def test_stores_the_registry_category(seeded):
    """Cycle 8 Task B. Deferred in Cycle 6 until export/import could carry it —
    see tests/test_concept_graph_export_import.py for the round trip."""
    from scidk.ai import mcp_tools

    _, driver = seeded
    registry = {t['name']: t for t in mcp_tools.TOOL_DEFINITIONS}

    for name, params in _tool_writes(driver).items():
        assert params['category'] == registry[name]['category']
        assert params['category'] in mcp_tools.TOOL_CATEGORIES


def test_descriptions_come_from_the_registry(seeded):
    from scidk.ai import mcp_tools

    _, driver = seeded
    writes = _tool_writes(driver)
    registry = {t['name']: t for t in mcp_tools.TOOL_DEFINITIONS}

    for name, params in writes.items():
        assert params['description'] == registry[name]['description']


def test_wires_intent_satisfies_edges(seeded):
    """Edge wiring is unchanged by the registry swap."""
    result, driver = seeded

    satisfies = [q for q, _ in driver.calls if 'SATISFIES' in q]
    assert len(satisfies) == 6
    assert result['edges_created'] == 6
