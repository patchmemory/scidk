"""GET /api/platform/tools — the third consumer of the canonical tool registry.

Cycle 6 Task A. Uses a real app from ``create_app()`` so blueprint registration
and RBAC are exercised as they actually are, following the pattern in
``tests/pipeline/test_api_pipeline.py``. Neo4j environment is cleared for the
same reason it is there: ``scidk/app.py`` calls ``load_dotenv()`` at import, so a
full-suite run would otherwise reach a developer's live graph. This route never
touches a graph — the registry is a module-level constant — but create_app() does
look for one.
"""
from __future__ import annotations

import pytest

_NEO4J_ENV = (
    "NEO4J_URI", "BOLT_URI", "NEO4J_USER", "NEO4J_USERNAME",
    "NEO4J_PASSWORD", "NEO4J_AUTH", "SCIDK_NEO4J_DATABASE",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIDK_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("SCIDK_SETTINGS_DB", str(tmp_path / "scidk_settings.db"))
    for name in _NEO4J_ENV:
        monkeypatch.delenv(name, raising=False)

    from scidk.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["SCIDK_SETTINGS_DB"] = str(tmp_path / "scidk_settings.db")
    app.extensions["scidk"]["neo4j_config"] = {}
    return app.test_client()


def test_returns_the_whole_registry(client):
    from scidk.ai import mcp_tools

    resp = client.get('/api/platform/tools')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['count'] == len(mcp_tools.TOOL_DEFINITIONS)
    assert [t['name'] for t in body['tools']] == [
        t['name'] for t in mcp_tools.TOOL_DEFINITIONS
    ]


def test_entries_carry_the_full_registry_shape(client):
    from scidk.ai import mcp_tools

    body = client.get('/api/platform/tools').get_json()

    for tool in body['tools']:
        assert set(tool) == {'name', 'description', 'input_schema', 'category'}
        assert tool['category'] in mcp_tools.TOOL_CATEGORIES
        assert tool['input_schema']['type'] == 'object'


def test_category_filter_narrows_the_list(client):
    body = client.get('/api/platform/tools?category=schema').get_json()

    assert {t['name'] for t in body['tools']} == {
        'get_schema', 'get_label_profile', 'list_labels'
    }
    assert body['count'] == 3


def test_categories_lists_all_categories_even_when_filtered(client):
    """A filtered response still tells the UI what else it could ask for."""
    from scidk.ai import mcp_tools

    body = client.get('/api/platform/tools?category=data_query').get_json()

    assert body['count'] == 1
    assert body['categories'] == list(mcp_tools.TOOL_CATEGORIES)


def test_unknown_category_is_a_400(client):
    resp = client.get('/api/platform/tools?category=bogus')

    assert resp.status_code == 400
    assert 'Unknown category' in resp.get_json()['error']


def test_empty_category_param_is_treated_as_absent(client):
    """``?category=`` from a cleared UI dropdown means "no filter", not a 400."""
    from scidk.ai import mcp_tools

    resp = client.get('/api/platform/tools?category=')

    assert resp.status_code == 200
    assert resp.get_json()['count'] == len(mcp_tools.TOOL_DEFINITIONS)
