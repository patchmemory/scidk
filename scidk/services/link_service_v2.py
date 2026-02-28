"""
Link execution service for the new LinkRegistry pattern.

This service executes link scripts (Cypher and Python) against Neo4j,
tracks execution status, and applies sanitization to relationship properties.

IMPORTANT: This is separate from the deprecated link_service.py which handles
the old wizard-based link_definitions system. The two can coexist but serve
different purposes.
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Any, Optional
import sqlite3

from ..schema.link_registry import LinkRegistry, LinkDefinition
from ..schema.registry import LabelRegistry
from ..schema.sanitization import apply_sanitization
from ..core import path_index_sqlite as pix

logger = logging.getLogger(__name__)


class SciDKLinkResult:
    """
    Result accumulator for Python link scripts.

    Python links receive this object and call methods to report:
    - Relationships created
    - Pairs skipped (candidates but threshold not met)
    - Warnings

    Usage in Python link script:
        def link(neo4j_session, params, logger, result):
            result.relationship_created(
                rel_type="SUBJECT_OF",
                from_label="Sample",
                from_key="S001",
                to_label="ImagingDataset",
                to_key="/data/exp/...",
                properties={"confidence": 0.95}
            )
    """

    def __init__(self, link_id: str):
        self.link_id = link_id
        self.relationships_created: List[Dict[str, Any]] = []
        self.pairs_skipped: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def relationship_created(
        self,
        rel_type: str,
        from_label: str,
        to_label: str,
        from_key: Optional[str] = None,
        to_key: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ):
        """Report a relationship that was created."""
        self.relationships_created.append({
            'rel_type': rel_type,
            'from_label': from_label,
            'from_key': from_key,
            'to_label': to_label,
            'to_key': to_key,
            'properties': properties or {}
        })

    def pair_skipped(
        self,
        from_label: str,
        from_key: str,
        to_label: str,
        to_key: str,
        reason: str,
        score: Optional[float] = None
    ):
        """Report a candidate pair that was skipped (e.g. below threshold)."""
        self.pairs_skipped.append({
            'from_label': from_label,
            'from_key': from_key,
            'to_label': to_label,
            'to_key': to_key,
            'reason': reason,
            'score': score
        })

    def warning(self, message: str):
        """Report a warning message."""
        self.warnings.append(message)

    def error(self, message: str):
        """Report an error message."""
        self.errors.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            'link_id': self.link_id,
            'relationships_created': len(self.relationships_created),
            'relationships_details': self.relationships_created,
            'pairs_skipped': len(self.pairs_skipped),
            'pairs_skipped_details': self.pairs_skipped,
            'warnings': self.warnings,
            'errors': self.errors,
            'success': len(self.errors) == 0
        }


class LinkExecutionService:
    """Service for executing link scripts against Neo4j."""

    def __init__(self, app=None):
        self.app = app

    def _get_neo4j_client(self):
        """Get Neo4j client instance."""
        from .neo4j_client import Neo4jClient, get_neo4j_params

        uri, user, pwd, database, auth_mode = get_neo4j_params(self.app)
        if not uri:
            raise RuntimeError("Neo4j connection not configured")

        client = Neo4jClient(uri, user, pwd, database, auth_mode)
        client.connect()
        return client

    def _update_link_status(self, link_id: str, status: str, last_run_at: float):
        """Update link execution status in SQLite registry."""
        try:
            conn = pix.connect()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE links
                SET validation_status = ?, last_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, last_run_at, time.time(), link_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to update link status in registry: {e}")

    def run_link(
        self,
        link_id: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a link script against Neo4j.

        Args:
            link_id: Link ID from LinkRegistry
            params: Optional parameters to pass to the link script

        Returns:
            Result dictionary with:
                - status: 'success' | 'error'
                - relationships_created: int
                - execution_time_ms: int
                - error: str (if status='error')
                - details: dict (full execution details)
        """
        start_time = time.time()
        params = params or {}

        try:
            # Load link definition
            LinkRegistry._ensure_loaded()
            link_def = LinkRegistry.get(link_id)

            if not link_def:
                return {
                    'status': 'error',
                    'error': f'Link "{link_id}" not found in registry',
                    'relationships_created': 0,
                    'execution_time_ms': 0
                }

            # Validate label references
            LabelRegistry._ensure_loaded()
            validation_errors = link_def.validate_references(LabelRegistry)
            if validation_errors:
                return {
                    'status': 'error',
                    'error': 'Validation failed: ' + '; '.join(validation_errors),
                    'relationships_created': 0,
                    'execution_time_ms': 0
                }

            # Execute based on format
            if link_def.format == 'cypher':
                result = self._execute_cypher_link(link_def, params)
            elif link_def.format == 'python':
                result = self._execute_python_link(link_def, params)
            else:
                return {
                    'status': 'error',
                    'error': f'Unsupported link format: {link_def.format}',
                    'relationships_created': 0,
                    'execution_time_ms': 0
                }

            execution_time_ms = int((time.time() - start_time) * 1000)
            result['execution_time_ms'] = execution_time_ms

            # Update link status
            status = 'passed' if result['status'] == 'success' else 'failed'
            self._update_link_status(link_id, status, time.time())

            return result

        except Exception as e:
            logger.exception(f"Failed to execute link {link_id}")
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Update status to failed
            self._update_link_status(link_id, 'failed', time.time())

            return {
                'status': 'error',
                'error': str(e),
                'relationships_created': 0,
                'execution_time_ms': execution_time_ms
            }

    def _execute_cypher_link(
        self,
        link_def: LinkDefinition,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Cypher link script."""
        try:
            # Read the Cypher code from the source file
            with open(link_def.source_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract Cypher (everything after the header)
            cypher_code = self._extract_cypher_code(content)

            if not cypher_code:
                return {
                    'status': 'error',
                    'error': 'No Cypher code found in link file',
                    'relationships_created': 0
                }

            # Get Neo4j client and execute
            client = self._get_neo4j_client()
            try:
                results = client.execute_write(cypher_code, params)

                # Extract relationship count from result
                # Cypher links should RETURN count(r) as created
                rel_count = 0
                if results and len(results) > 0:
                    # Try different common field names
                    first_result = results[0]
                    rel_count = first_result.get('created') or first_result.get('count') or first_result.get('relationships_created') or 0

                return {
                    'status': 'success',
                    'relationships_created': rel_count,
                    'details': {
                        'link_id': link_def.id,
                        'format': 'cypher',
                        'from_label': link_def.from_label,
                        'to_label': link_def.to_label,
                        'relationship_type': link_def.relationship_type,
                        'results': results
                    }
                }
            finally:
                client.close()

        except Exception as e:
            logger.exception(f"Failed to execute Cypher link {link_def.id}")
            return {
                'status': 'error',
                'error': f'Cypher execution failed: {str(e)}',
                'relationships_created': 0
            }

    def _execute_python_link(
        self,
        link_def: LinkDefinition,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Python link script."""
        try:
            # Read and execute Python code
            with open(link_def.source_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # Create execution namespace
            namespace = {}
            exec(code, namespace)

            # Get the link function
            link_func = namespace.get('link')
            if not link_func:
                return {
                    'status': 'error',
                    'error': 'Python link must define a link() function',
                    'relationships_created': 0
                }

            # Create result accumulator
            result_obj = SciDKLinkResult(link_def.id)

            # Get Neo4j client and session
            client = self._get_neo4j_client()
            try:
                with client._session() as session:
                    # Call the link function
                    link_func(session, params, logger, result_obj)

                # Convert result to dict
                result_dict = result_obj.to_dict()

                return {
                    'status': 'success' if result_dict['success'] else 'error',
                    'relationships_created': result_dict['relationships_created'],
                    'details': result_dict
                }
            finally:
                client.close()

        except Exception as e:
            logger.exception(f"Failed to execute Python link {link_def.id}")
            return {
                'status': 'error',
                'error': f'Python execution failed: {str(e)}',
                'relationships_created': 0
            }

    def _extract_cypher_code(self, content: str) -> str:
        """Extract Cypher code from file content (everything after header)."""
        lines = content.split('\n')
        in_header = False
        header_ended = False
        cypher_lines = []

        for line in lines:
            stripped = line.strip()

            # Detect header start
            if stripped == '# ---':
                if not in_header:
                    in_header = True
                    continue
                else:
                    # End of header
                    header_ended = True
                    continue

            # Collect Cypher after header
            if header_ended:
                cypher_lines.append(line)
            elif in_header:
                # Still in header, skip
                continue
            else:
                # Before header started (shouldn't happen but handle it)
                continue

        return '\n'.join(cypher_lines).strip()

    def list_links(self) -> List[Dict[str, Any]]:
        """List all registered links with their status."""
        LinkRegistry._ensure_loaded()
        all_links = LinkRegistry.all()

        result = []
        for link_id, link_def in all_links.items():
            result.append({
                'id': link_def.id,
                'name': link_def.name,
                'format': link_def.format,
                'from_label': link_def.from_label,
                'to_label': link_def.to_label,
                'relationship_type': link_def.relationship_type,
                'matching_strategy': link_def.matching_strategy,
                'description': link_def.description,
                'created_at': link_def.created_at,
                'updated_at': link_def.updated_at
            })

        return result

    def reload_registry(self) -> Dict[str, Any]:
        """Reload the LinkRegistry from disk."""
        try:
            LinkRegistry.reload()
            all_links = LinkRegistry.all()
            return {
                'status': 'success',
                'links_loaded': len(all_links)
            }
        except Exception as e:
            logger.exception("Failed to reload LinkRegistry")
            return {
                'status': 'error',
                'error': str(e)
            }


def get_link_service(app=None) -> LinkExecutionService:
    """Get or create LinkExecutionService instance."""
    if app and hasattr(app, 'extensions'):
        if 'scidk' not in app.extensions:
            app.extensions['scidk'] = {}

        if 'link_execution_service' not in app.extensions['scidk']:
            app.extensions['scidk']['link_execution_service'] = LinkExecutionService(app)

        return app.extensions['scidk']['link_execution_service']

    return LinkExecutionService(app)
