from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


def inject_fake_neo4j(monkeypatch, *, uri: str = "", user: str = "", password: str = "",
                      database: Optional[str] = None) -> None:
    """
    Disable real Neo4j connections for tests by blanking credentials/URI.
    This nudges the app into its non-Neo4j code paths where supported.
    """
    monkeypatch.setenv("NEO4J_URI", uri)
    monkeypatch.setenv("NEO4J_USER", user)
    monkeypatch.setenv("NEO4J_PASSWORD", password)
    if database is not None:
        monkeypatch.setenv("SCIDK_NEO4J_DATABASE", database)


@dataclass
class CypherRecord:
    query: str
    params: Dict[str, Any]


@dataclass
class CypherRecorder:
    """
    Minimal recorder utility for tests that want to capture the sequence of
    Cypher statements a function would issue. This does not execute Cypher;
    tests should wire it into the code under test where a client is expected.
    """
    records: List[CypherRecord] = field(default_factory=list)

    def run(self, query: str, **params: Any) -> None:
        self.records.append(CypherRecord(query=query, params=dict(params)))

    def last(self) -> Optional[CypherRecord]:
        return self.records[-1] if self.records else None

    def clear(self) -> None:
        self.records.clear()
