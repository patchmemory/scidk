"""
Lightweight local stub for the 'neo4j' package to allow tests to import and
monkeypatch GraphDatabase without requiring the real neo4j driver.

Tests will replace GraphDatabase via monkeypatch, so this only needs to exist.
"""

class GraphDatabase:  # pragma: no cover - placeholder
    pass
