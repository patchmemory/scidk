"""Shared helpers for the Pipeline tests.

Nothing here talks to a real database. That is deliberate rather than incidental:
``scidk/app.py`` calls ``load_dotenv()`` at import, so any test that reaches
``get_neo4j_params`` picks up whatever credentials the developer's ``.env`` holds
— which made an earlier version of these tests pass alone, fail in the full
suite, and write into a live dev graph in between. Use :class:`CapturingWriter`
(or the ``fake_graph`` fixture in ``test_api_pipeline.py``) instead of letting a
run find its own connection.
"""
from __future__ import annotations

from typing import Any, Dict, List


class CapturingWriter:
    """Stands in for Neo4j: records what was declared, reports it all written.

    Satisfies the only thing ``PipelineRunner`` needs — the
    :class:`~scidk.pipeline.runner.Neo4jWriter` protocol — so it can be passed
    anywhere a client can. For a writer that fails, or fails only on a particular
    batch, see the scriptable ``FakeWriter`` in ``test_runner.py``: those tests are
    about how failures are reported, and keeping the scripting next to them reads
    better than one class with every knob.
    """

    def __init__(self) -> None:
        self.nodes: List[Dict[str, Any]] = []
        self.relationships: List[Dict[str, Any]] = []
        self.batches = 0

    def write_declared_nodes(
        self, nodes: List[Dict[str, Any]], relationships: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.batches += 1
        self.nodes.extend(nodes)
        self.relationships.extend(relationships)
        return {
            "written_nodes": len(nodes),
            "written_relationships": len(relationships),
            "errors": [],
        }
