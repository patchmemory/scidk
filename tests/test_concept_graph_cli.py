"""``scidk-concept-graph`` / ``python -m scidk.concept_graph`` — Cycle 8 Task C.

``pyproject.toml`` declared no entry point for concept-graph seeding, so a clean
re-initialisation meant either a running server (``POST /chat/concept-graph/reseed``)
or the repo-root ``seed_concept_graph.py``, which builds a whole Flask app and
resolves ``intents.yaml`` against the working directory. Neither seeded MCP tools
from the canonical registry and neither could clear first.

The three seeders and the driver factory are monkeypatched: what is under test is
the CLI's control flow — the reset gate, exit codes, and that the driver is always
closed — not the seeding itself, which its own tests cover.
"""
from __future__ import annotations

import pytest

from scidk.concept_graph import INTENTS_YAML, SCHEMA_CYPHER
from scidk.concept_graph.cli import CONCEPT_LABEL_PREFIX, main


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


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._driver.queries.append(query)
        # Order matters: the per-label breakdown also selects `count(n) AS total`.
        if 'labels(n)[0]' in query:
            return _Result([{'label': 'Concept_Intent', 'total': 9}])
        if 'count(n) AS total' in query:
            return _Result([{'total': 12}])
        if 'count(r) AS total' in query:
            return _Result([{'total': 6}])
        return _Result([])


class _FakeDriver:
    def __init__(self):
        self.queries = []
        self.closed = False

    def session(self):
        return _FakeSession(self)

    def close(self):
        self.closed = True

    def deleted(self):
        return [q for q in self.queries if 'DETACH DELETE' in q]


class _Calls(dict):
    """Records which seeders ran, in order."""

    def __init__(self):
        super().__init__()
        self.order = []

    def record(self, name, result):
        def _fake(*args, **kwargs):
            self.order.append(name)
            self[name] = (args, kwargs)
            return result
        return _fake


@pytest.fixture()
def cli(monkeypatch):
    """A CLI wired to a fake driver and fake seeders. Yields (driver, calls)."""
    from scidk.services import concept_graph_service as cgs

    driver = _FakeDriver()
    calls = _Calls()

    monkeypatch.setattr(cgs, 'get_concept_driver', lambda app=None: driver)
    monkeypatch.setattr(cgs, 'seed_intents_from_yaml',
                        calls.record('intents', {'embedded': 9, 'failed': 0}))
    monkeypatch.setattr(cgs, 'seed_tools_from_yaml',
                        calls.record('tools', {'embedded': 4, 'failed': 0}))
    monkeypatch.setattr(cgs, 'seed_mcp_tools', calls.record(
        'mcp', {'seeded': 5, 'failed': 0, 'edges_created': 6, 'errors': []}))
    monkeypatch.setattr(cgs, 'sync_labels_from_schema', calls.record(
        'labels', {'labels': 3, 'relationships': 2, 'edges': 1}))

    return driver, calls


# ─────────────────────────────────────────────
# Packaging
# ─────────────────────────────────────────────

def test_the_definitions_ship_with_the_package():
    """The CLI resolves intents.yaml off the package, not the working directory."""
    assert INTENTS_YAML.is_file()
    assert SCHEMA_CYPHER.is_file()


def test_the_console_script_points_at_a_real_callable():
    """`scidk-concept-graph` in [project.scripts] must import and be callable."""
    import tomllib
    from importlib import import_module
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / 'pyproject.toml'
    with pyproject.open('rb') as fh:
        scripts = tomllib.load(fh)['project']['scripts']

    target = scripts['scidk-concept-graph']
    module_path, _, attr = target.partition(':')
    assert callable(getattr(import_module(module_path), attr))


def test_module_execution_entry_point_exists():
    """`python -m scidk.concept_graph` needs a __main__ in the package."""
    import importlib.util

    assert importlib.util.find_spec('scidk.concept_graph.__main__') is not None


# ─────────────────────────────────────────────
# Argument handling
# ─────────────────────────────────────────────

def test_a_subcommand_is_required():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_unknown_subcommand_is_rejected():
    with pytest.raises(SystemExit) as exc:
        main(['reindex'])
    assert exc.value.code == 2


# ─────────────────────────────────────────────
# seed
# ─────────────────────────────────────────────

def test_seed_runs_every_seeder_and_succeeds(cli, capsys):
    driver, calls = cli

    assert main(['seed']) == 0

    assert calls.order == ['intents', 'tools', 'mcp']
    assert driver.deleted() == []
    assert driver.closed

    out = capsys.readouterr().out
    assert '9 embedded' in out
    assert '5 seeded' in out
    assert 'SATISFIES edges: 6' in out


def test_seed_passes_the_packaged_yaml_and_the_ollama_endpoint(cli, monkeypatch):
    monkeypatch.setenv('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://ollama.internal:11434')
    _, calls = cli

    main(['seed'])

    args, _ = calls['intents']
    assert args[1] == str(INTENTS_YAML)
    assert args[2] == 'http://ollama.internal:11434'


def test_skip_mcp_tools_leaves_the_registry_alone(cli):
    _, calls = cli

    assert main(['seed', '--skip-mcp-tools']) == 0
    assert calls.order == ['intents', 'tools']


def test_with_labels_mirrors_the_research_schema(cli, monkeypatch):
    driver, calls = cli
    monkeypatch.setenv('NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setenv('NEO4J_PASSWORD', 'secret')
    monkeypatch.setattr('neo4j.GraphDatabase.driver',
                        lambda *a, **k: _FakeDriver())

    assert main(['seed', '--with-labels']) == 0
    assert 'labels' in calls.order


def test_with_labels_reports_an_unconfigured_research_graph(cli, monkeypatch, capsys):
    for var in ('NEO4J_URI', 'BOLT_URI', 'NEO4J_PASSWORD', 'NEO4J_AUTH'):
        monkeypatch.delenv(var, raising=False)
    _, calls = cli

    assert main(['seed', '--with-labels']) == 1

    assert 'labels' not in calls.order
    assert 'research graph not configured' in capsys.readouterr().err


# ─────────────────────────────────────────────
# --reset
# ─────────────────────────────────────────────

def test_reset_clears_then_seeds(cli, capsys):
    driver, calls = cli

    assert main(['seed', '--reset', '--yes']) == 0

    assert len(driver.deleted()) == 1
    assert calls.order == ['intents', 'tools', 'mcp']
    assert f"Cleared 12 {CONCEPT_LABEL_PREFIX}* nodes" in capsys.readouterr().out


def test_reset_deletes_by_label_prefix_not_an_enumerated_list(cli):
    """A :Concept_ label added later must still be cleared."""
    driver, _ = cli
    main(['seed', '--reset', '--yes'])

    delete_query = driver.deleted()[0]
    assert "labels(n) WHERE l STARTS WITH $prefix" in delete_query


def test_reset_refuses_without_confirmation_when_not_on_a_tty(cli, monkeypatch, capsys):
    """Non-interactive callers must say --yes; a bare --reset must not delete."""
    driver, calls = cli
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)

    assert main(['seed', '--reset']) == 1

    assert driver.deleted() == []
    assert calls.order == []
    assert '--yes' in capsys.readouterr().err


def test_reset_honours_a_declined_prompt(cli, monkeypatch):
    driver, calls = cli
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': 'n')

    assert main(['seed', '--reset']) == 1

    assert driver.deleted() == []
    assert calls.order == []


def test_reset_proceeds_on_an_accepted_prompt(cli, monkeypatch):
    driver, calls = cli
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': 'y')

    assert main(['seed', '--reset']) == 0
    assert len(driver.deleted()) == 1


def test_a_declined_reset_never_opens_a_driver(cli, monkeypatch):
    """The gate comes before the connection, so a refusal touches nothing."""
    driver, _ = cli
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)

    main(['seed', '--reset'])

    assert driver.queries == []
    assert not driver.closed


# ─────────────────────────────────────────────
# status
# ─────────────────────────────────────────────

def test_status_reports_counts_and_writes_nothing(cli, capsys):
    driver, calls = cli

    assert main(['status']) == 0

    assert calls.order == []
    assert driver.deleted() == []
    assert not any('MERGE' in q or 'SET ' in q for q in driver.queries)
    assert driver.closed

    out = capsys.readouterr().out
    assert 'Concept_Intent: 9' in out
    assert 'SATISFIES edges: 6' in out


def test_status_exits_nonzero_when_the_graph_is_unreachable(monkeypatch):
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'get_concept_driver', lambda app=None: None)
    assert main(['status']) == 1


# ─────────────────────────────────────────────
# Failure paths
# ─────────────────────────────────────────────

def test_an_unreachable_graph_exits_nonzero_with_the_variables_to_check(
        monkeypatch, capsys):
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'get_concept_driver', lambda app=None: None)

    assert main(['seed']) == 1

    err = capsys.readouterr().err
    assert 'SCIDK_CONCEPT_NEO4J_URI' in err
    assert 'SCIDK_CONCEPT_NEO4J_AUTH' in err


def test_embedding_failures_are_reported_as_a_nonzero_exit(cli, monkeypatch, capsys):
    """Ollama down means nodes without embeddings — that is not a successful seed."""
    from scidk.services import concept_graph_service as cgs

    monkeypatch.setattr(cgs, 'seed_intents_from_yaml',
                        lambda *a, **k: {'embedded': 0, 'failed': 9})

    assert main(['seed']) == 1
    assert 'failure' in capsys.readouterr().err


def test_the_driver_is_closed_when_a_seeder_raises(cli, monkeypatch, capsys):
    from scidk.services import concept_graph_service as cgs

    driver, _ = cli
    monkeypatch.setattr(cgs, 'seed_tools_from_yaml',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))

    assert main(['seed']) == 1
    assert driver.closed
    assert 'boom' in capsys.readouterr().err


def test_missing_definitions_fail_before_connecting(cli, monkeypatch, capsys):
    from pathlib import Path

    driver, _ = cli
    monkeypatch.setattr('scidk.concept_graph.cli.INTENTS_YAML',
                        Path('/nonexistent/intents.yaml'))

    assert main(['seed']) == 1
    assert driver.queries == []
    assert 'not found' in capsys.readouterr().err
