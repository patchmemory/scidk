"""Context object passed to analysis scripts for Results integration."""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalysisContext:
    """
    Runtime context for analysis scripts.

    Provides:
    - neo4j: Neo4j client wrapper with auto-provenance
    - script_id: Current script ID (auto-injected)
    - execution_id: Current execution ID (auto-injected)
    - ran_at: Execution timestamp
    - parameters: User-provided parameters
    - register_panel(): Register visual output (deferred until success)
    """

    def __init__(
        self,
        script_id: str,
        execution_id: str,
        neo4j_driver,
        neo4j_database: Optional[str],
        parameters: Optional[Dict[str, Any]] = None
    ):
        self.script_id = script_id
        self.execution_id = execution_id
        self.ran_at = time.time()
        self.parameters = parameters or {}

        # Wrap Neo4j driver with provenance injection
        self.neo4j = Neo4jContextWrapper(
            driver=neo4j_driver,
            database=neo4j_database,
            provenance={
                'source': 'analysis',
                'script_id': script_id,
                'execution_id': execution_id,
                'created_at': self.ran_at
            }
        )

        # Deferred panel registrations (written only on script success)
        self._pending_panels: List[Dict[str, Any]] = []

    def register_panel(
        self,
        panel_type: str,
        title: str,
        data: Any,
        visualization: Optional[str] = None
    ):
        """
        Register a visual panel for Results page (deferred until script completes).

        Args:
            panel_type: 'table', 'metric', 'figure', 'schema'
            title: Panel title shown on Results page
            data: Panel data (list of dicts for table, single value for metric, etc.)
            visualization: Optional chart type ('bar_chart', 'line_chart', etc.)
        """
        # Serialize data to JSON
        try:
            panel_data_json = json.dumps(data)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Panel data must be JSON-serializable: {e}")

        # Store for deferred write
        self._pending_panels.append({
            'id': str(uuid.uuid4()),
            'panel_type': panel_type,
            'title': title,
            'panel_data': panel_data_json,
            'visualization': visualization
        })

        logger.info(f"Registered panel '{title}' (type={panel_type}) for script {self.script_id}")

    def _flush_panels(self, script_name: str):
        """
        Write all pending panels to database (called by ScriptsManager on success).

        Internal method — not for script authors.
        """
        from scidk.core import path_index_sqlite as pix

        if not self._pending_panels:
            return

        conn = pix.connect()
        try:
            cur = conn.cursor()
            for panel in self._pending_panels:
                cur.execute("""
                    INSERT INTO analysis_panels
                    (id, script_id, execution_id, script_name, ran_at, panel_type,
                     title, panel_data, visualization, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'success')
                """, (
                    panel['id'],
                    self.script_id,
                    self.execution_id,
                    script_name,
                    self.ran_at,
                    panel['panel_type'],
                    panel['title'],
                    panel['panel_data'],
                    panel['visualization']
                ))
            conn.commit()
            logger.info(f"Flushed {len(self._pending_panels)} panels for script {self.script_id}")
        finally:
            conn.close()


class Neo4jContextWrapper:
    """
    Wraps Neo4j driver to auto-inject provenance on writes.

    Provides simplified query/write interface for script authors.
    """

    def __init__(self, driver, database: Optional[str], provenance: Dict[str, Any]):
        self._driver = driver
        self._database = database
        self._provenance = provenance

    def query(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute read-only Cypher query.

        Args:
            cypher: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dicts
        """
        if not self._driver:
            raise RuntimeError("Neo4j driver not available")

        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, parameters or {})
            return [dict(record) for record in result]

    def write_node(
        self,
        label: str,
        properties: Dict[str, Any],
        merge_key: Optional[str] = None
    ):
        """
        Write node to KG with automatic provenance injection.

        Args:
            label: Node label
            properties: Node properties (provenance auto-added)
            merge_key: If provided, MERGE on this property instead of CREATE
        """
        if not self._driver:
            raise RuntimeError("Neo4j driver not available")

        # Inject provenance
        enriched_props = {
            **properties,
            '__source__': self._provenance['source'],
            '__script_id__': self._provenance['script_id'],
            '__execution_id__': self._provenance['execution_id'],
            '__created_at__': self._provenance['created_at'],
            '__created_via__': 'scidk_analysis'
        }

        with self._driver.session(database=self._database) as session:
            if merge_key:
                # MERGE on specified key
                session.run(
                    f"MERGE (n:{label} {{{merge_key}: $props.{merge_key}}}) "
                    f"SET n = $props",
                    {'props': enriched_props}
                )
            else:
                # CREATE new node
                session.run(
                    f"CREATE (n:{label} $props)",
                    {'props': enriched_props}
                )
