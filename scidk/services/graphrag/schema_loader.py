"""
Dynamic schema discovery for SciDK GraphRAG.

Queries the live Neo4j instance to discover node labels and relationship types,
then injects them into the entity extraction prompt for schema-aware query generation.

Performance: Schema is loaded ONCE at QueryEngine initialization time, not per-request.
Only reloads when /api/chat/schema/refresh is called explicitly.
"""
from typing import Dict, List, Optional
import logging


class SciDKSchemaLoader:
    """Queries SciDK Neo4j to discover the live schema."""

    def __init__(self, driver, database: Optional[str] = None):
        """
        Initialize schema loader.

        Args:
            driver: Neo4j driver instance
            database: Optional Neo4j database name (defaults to driver default)
        """
        self.driver = driver
        self.database = database
        self._cache = None
        self.logger = logging.getLogger(__name__)

    def load(self) -> Dict[str, List[str]]:
        """
        Load schema from Neo4j.

        Returns:
            Dict with keys 'labels' and 'relationships', each containing a list of strings.

        Note: Results are cached. Call refresh() to force reload.
        """
        if self._cache:
            return self._cache

        try:
            # Query Neo4j for node labels and relationship types
            with self._session() as session:
                labels = [r[0] for r in session.run("CALL db.labels()")]
                rels = [r[0] for r in session.run("CALL db.relationshipTypes()")]

            self._cache = {"labels": labels, "relationships": rels}
            self.logger.info(f"Schema loaded: {len(labels)} labels, {len(rels)} relationship types")
            return self._cache

        except Exception as e:
            self.logger.error(f"Failed to load schema: {e}")
            # Return empty schema on error
            return {"labels": [], "relationships": []}

    def get_schema_fragment(self) -> str:
        """
        Get formatted schema string for injection into entity extraction prompt.

        Returns:
            Formatted string describing available node labels and relationship types.
        """
        schema = self.load()
        labels_str = ", ".join(schema["labels"]) if schema["labels"] else "(none)"
        rels_str = ", ".join(schema["relationships"]) if schema["relationships"] else "(none)"

        return (
            f"Node types in this graph: {labels_str}\n"
            f"Relationship types: {rels_str}\n"
            "Extract entities matching these exact types from the user query."
        )

    def refresh(self) -> Dict[str, List[str]]:
        """
        Force a schema reload from Neo4j.

        Call this when new labels or relationship types are added to the graph.

        Returns:
            Updated schema dict.
        """
        self._cache = None
        return self.load()

    def _session(self):
        """Get Neo4j session with optional database parameter."""
        if self.database:
            return self.driver.session(database=self.database)
        return self.driver.session()
