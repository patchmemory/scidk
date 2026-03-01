"""
Link service for managing Label→Label relationship creation workflows.

This service provides operations for:
- CRUD operations on link definitions (stored in SQLite)
- Preview and execution of link jobs
- Label→Label mapping enforcement (both source and target are Labels)
- Match strategies: Property, Fuzzy, Table Import, API Endpoint
- Legacy migration support for old source/target types
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional
import json
import time
import sqlite3
import uuid
import csv
import io
import requests
import re
import logging

logger = logging.getLogger(__name__)


class LinkService:
    """Service for managing link definitions and executing relationship creation workflows."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _validate_relationship_type(rel_type: str) -> str:
        """
        Validate and sanitize relationship type for Cypher queries.

        Prevents Cypher injection by ensuring relationship type matches Neo4j naming conventions.
        Valid relationship types: alphanumeric, underscores only (e.g., HAS_CHILD, RELATED_TO).

        Args:
            rel_type: Relationship type string

        Returns:
            Validated relationship type

        Raises:
            ValueError: If relationship type contains invalid characters
        """
        if not rel_type or not isinstance(rel_type, str):
            raise ValueError("Relationship type must be a non-empty string")

        # Neo4j relationship type naming rules:
        # - Must start with letter or underscore
        # - Can contain letters, digits, underscores
        # - Typically UPPER_CASE by convention
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type):
            raise ValueError(
                f"Invalid relationship type '{rel_type}'. "
                "Must contain only letters, digits, and underscores, and start with a letter or underscore."
            )

        return rel_type

    def _get_conn(self):
        """Get a database connection."""
        from ..core import path_index_sqlite as pix
        return pix.connect()

    def list_all_links(self) -> List[Dict[str, Any]]:
        """
        Get links from both link_definitions (wizard) and analyses_scripts (code).

        Returns normalized list of all links regardless of source.
        """
        # Get wizard links
        wizard_links = self.list_link_definitions()

        # Get script links (category='links')
        from ..core.scripts import ScriptsManager
        scripts_mgr = ScriptsManager()
        script_links = scripts_mgr.list_scripts(category='links')

        all_links = []

        # Normalize wizard links
        for link in wizard_links:
            all_links.append({
                'id': link['id'],
                'name': link['name'],
                'source_label': link.get('source_label', ''),
                'target_label': link.get('target_label', ''),
                'relationship_type': link.get('relationship_type', ''),
                'type': 'wizard',
                'match_strategy': link.get('match_strategy', ''),
                'created_at': link.get('created_at', 0),
                'updated_at': link.get('updated_at', 0),
                'status': link.get('status', 'pending')
            })

        # Normalize script links
        # NOTE: Use description instead of trying to infer labels from parameters.
        # This avoids fragile parsing and "Custom → Custom" inconsistencies.
        for script in script_links:
            # Map script is_active to link status for consistent filtering
            status = 'active' if (script.is_active if script.is_active is not None else False) else 'draft'

            all_links.append({
                'id': script.id,
                'name': script.name,
                'description': script.description or '',
                'source_label': None,  # Not inferred
                'target_label': None,  # Not inferred
                'relationship_type': 'Dynamic',  # Defined in code
                'type': 'script',
                'match_strategy': 'custom_code',
                'created_at': script.created_at or 0,
                'updated_at': script.updated_at or 0,
                'validation_status': script.validation_status or 'draft',
                'is_active': script.is_active if script.is_active is not None else False,
                'status': status
            })

        # Sort by most recently updated
        return sorted(all_links, key=lambda x: x.get('updated_at', 0), reverse=True)

    def list_link_definitions(self) -> List[Dict[str, Any]]:
        """
        Get all link definitions from SQLite.

        Returns:
            List of link definition dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # First try new schema with source_label and target_label
            cursor.execute(
                """
                SELECT id, name, source_label, target_label, source_type, source_config,
                       target_type, target_config, match_strategy, match_config,
                       relationship_type, relationship_props, created_at, updated_at, status
                FROM link_definitions
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()

            definitions = []
            for row in rows:
                (id, name, source_label, target_label, source_type, source_config, target_type, target_config,
                 match_strategy, match_config, rel_type, rel_props, created_at, updated_at, status) = row
                definitions.append({
                    'id': id,
                    'name': name,
                    'source_label': source_label,
                    'target_label': target_label,
                    'source_type': source_type,
                    'source_config': json.loads(source_config) if source_config else {},
                    'target_type': target_type,
                    'target_config': json.loads(target_config) if target_config else {},
                    'match_strategy': match_strategy,
                    'match_config': json.loads(match_config) if match_config else {},
                    'relationship_type': rel_type,
                    'relationship_props': json.loads(rel_props) if rel_props else {},
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'status': status or 'pending'
                })
            return definitions
        finally:
            conn.close()

    def get_link_definition(self, link_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific link definition by ID.

        Args:
            link_id: Link definition ID

        Returns:
            Link definition dict or None if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, source_label, target_label, source_type, source_config,
                       target_type, target_config, match_strategy, match_config,
                       relationship_type, relationship_props, created_at, updated_at, status
                FROM link_definitions
                WHERE id = ?
                """,
                (link_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            (id, name, source_label, target_label, source_type, source_config, target_type, target_config,
             match_strategy, match_config, rel_type, rel_props, created_at, updated_at, status) = row
            return {
                'id': id,
                'name': name,
                'source_label': source_label,
                'target_label': target_label,
                'source_type': source_type,
                'source_config': json.loads(source_config) if source_config else {},
                'target_type': target_type,
                'target_config': json.loads(target_config) if target_config else {},
                'match_strategy': match_strategy,
                'match_config': json.loads(match_config) if match_config else {},
                'relationship_type': rel_type,
                'relationship_props': json.loads(rel_props) if rel_props else {},
                'created_at': created_at,
                'updated_at': updated_at,
                'status': status or 'pending'
            }
        finally:
            conn.close()

    def save_link_definition(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a link definition (Label→Label).

        Args:
            definition: Dict with required keys: name, source_label, target_label, match_strategy, relationship_type

        Returns:
            Updated link definition
        """
        link_id = definition.get('id') or str(uuid.uuid4())
        if not link_id or not link_id.strip():
            link_id = str(uuid.uuid4())

        name = definition.get('name', '').strip()
        if not name:
            raise ValueError("Link name is required")

        # New Label→Label model
        source_label = definition.get('source_label', '').strip()
        if not source_label:
            raise ValueError("source_label is required (must reference an existing Label)")

        target_label = definition.get('target_label', '').strip()
        if not target_label:
            raise ValueError("target_label is required (must reference an existing Label)")

        # Validate that labels exist
        self._validate_label_exists(source_label)
        self._validate_label_exists(target_label)

        # Legacy support: auto-migrate old source_type/target_type to new model
        source_type = definition.get('source_type', 'label')
        target_type = definition.get('target_type', 'label')

        # Match strategy now includes table_import and api_endpoint
        match_strategy = definition.get('match_strategy', '').strip()
        if match_strategy not in ['property', 'fuzzy', 'table_import', 'api_endpoint', 'id', 'cypher']:
            raise ValueError("match_strategy must be 'property', 'fuzzy', 'table_import', 'api_endpoint', 'id', or 'cypher'")

        relationship_type = definition.get('relationship_type', '').strip()
        if not relationship_type:
            raise ValueError("relationship_type is required")

        source_config = json.dumps(definition.get('source_config', {}))
        target_config = json.dumps(definition.get('target_config', {}))
        match_config = json.dumps(definition.get('match_config', {}))
        relationship_props = json.dumps(definition.get('relationship_props', {}))

        # Default status to 'pending' for new links
        status = definition.get('status', 'pending')

        now = time.time()

        # Check if link exists
        existing = self.get_link_definition(link_id)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if existing:
                # Update - preserve status if not explicitly provided
                if 'status' not in definition:
                    status = existing.get('status', 'pending')
                cursor.execute(
                    """
                    UPDATE link_definitions
                    SET name = ?, source_label = ?, target_label = ?, source_type = ?, source_config = ?,
                        target_type = ?, target_config = ?, match_strategy = ?, match_config = ?,
                        relationship_type = ?, relationship_props = ?, updated_at = ?, status = ?
                    WHERE id = ?
                    """,
                    (name, source_label, target_label, source_type, source_config, target_type, target_config,
                     match_strategy, match_config, relationship_type, relationship_props, now, status, link_id)
                )
                created_at = existing['created_at']
            else:
                # Insert - new links default to 'pending'
                cursor.execute(
                    """
                    INSERT INTO link_definitions
                    (id, name, source_label, target_label, source_type, source_config, target_type, target_config,
                     match_strategy, match_config, relationship_type, relationship_props,
                     created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (link_id, name, source_label, target_label, source_type, source_config, target_type, target_config,
                     match_strategy, match_config, relationship_type, relationship_props, now, now, status)
                )
                created_at = now

            conn.commit()

            return {
                'id': link_id,
                'name': name,
                'source_label': source_label,
                'target_label': target_label,
                'source_type': source_type,
                'source_config': json.loads(source_config),
                'target_type': target_type,
                'target_config': json.loads(target_config),
                'match_strategy': match_strategy,
                'match_config': json.loads(match_config),
                'relationship_type': relationship_type,
                'relationship_props': json.loads(relationship_props),
                'created_at': created_at,
                'updated_at': now,
                'status': status
            }
        finally:
            conn.close()

    def delete_link_definition(self, link_id: str) -> bool:
        """
        Delete a link definition.

        Args:
            link_id: Link definition ID

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM link_definitions WHERE id = ?", (link_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def preview_matches(self, definition: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Dry-run preview of link matches.

        Args:
            definition: Link definition dict
            limit: Maximum number of matches to return

        Returns:
            List of match dicts with source and target info
        """
        # Fetch source data
        source_data = self._fetch_source_data(definition)
        if not source_data:
            return []

        # Limit source data for preview
        source_data = source_data[:limit]

        # Match with targets
        matches = self._match_with_targets(definition, source_data, limit)

        return matches

    def execute_link_job(self, link_def_id: str, use_background_task: bool = True) -> str:
        """
        Start background job to create relationships.

        Args:
            link_def_id: Link definition ID
            use_background_task: If True, use /api/tasks background worker (default). If False, run synchronously.

        Returns:
            Job ID (if use_background_task=False) or Task ID (if use_background_task=True)
        """
        definition = self.get_link_definition(link_def_id)
        if not definition:
            raise ValueError(f"Link definition '{link_def_id}' not found")

        # Use background task pattern (preferred for production)
        if use_background_task:
            import hashlib
            from flask import current_app

            now = time.time()
            tid_src = f"link_execution|{link_def_id}|{now}"
            task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]

            # Create task record for tracking
            task = {
                'id': task_id,
                'type': 'link_execution',
                'status': 'running',
                'link_def_id': link_def_id,
                'link_name': definition.get('name', 'Unknown'),
                'started': now,
                'ended': None,
                'total': 0,  # Will be set after preview
                'processed': 0,
                'progress': 0.0,
                'error': None,
                'cancel_requested': False,
                'eta_seconds': None,
                'status_message': 'Initializing relationship creation...',
                'relationships_created': 0,
            }
            current_app.extensions['scidk'].setdefault('tasks', {})[task_id] = task

            # Run in background thread
            import threading
            app = current_app._get_current_object()

            def _worker():
                with app.app_context():
                    try:
                        job_id = str(uuid.uuid4())
                        self._execute_job_impl_with_progress(job_id, definition, task)
                        task['ended'] = time.time()
                        task['status'] = 'completed'
                        task['progress'] = 1.0
                        task['status_message'] = f'Created {task["relationships_created"]} relationships'
                    except Exception as e:
                        task['ended'] = time.time()
                        task['status'] = 'error'
                        task['error'] = str(e)

            threading.Thread(target=_worker, daemon=True).start()
            return task_id

        # Legacy synchronous execution (for backward compatibility)
        job_id = str(uuid.uuid4())
        now = time.time()

        # Create job record
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO link_jobs
                (id, link_def_id, status, preview_count, executed_count, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, link_def_id, 'pending', 0, 0, now)
            )
            conn.commit()

            # Execute job synchronously
            try:
                self._execute_job_impl(job_id, definition)
            except Exception as e:
                # Update job with error
                cursor.execute(
                    """
                    UPDATE link_jobs
                    SET status = ?, error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    ('failed', str(e), time.time(), job_id)
                )
                conn.commit()
                raise

            return job_id
        finally:
            conn.close()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status and progress.

        Args:
            job_id: Job ID

        Returns:
            Job status dict or None if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, link_def_id, status, preview_count, executed_count, error,
                       started_at, completed_at
                FROM link_jobs
                WHERE id = ?
                """,
                (job_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            (id, link_def_id, status, preview_count, executed_count, error,
             started_at, completed_at) = row
            return {
                'id': id,
                'link_def_id': link_def_id,
                'status': status,
                'preview_count': preview_count,
                'executed_count': executed_count,
                'error': error,
                'started_at': started_at,
                'completed_at': completed_at
            }
        finally:
            conn.close()

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        List recent jobs.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job status dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, link_def_id, status, preview_count, executed_count, error,
                       started_at, completed_at
                FROM link_jobs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()

            jobs = []
            for row in rows:
                (id, link_def_id, status, preview_count, executed_count, error,
                 started_at, completed_at) = row
                jobs.append({
                    'id': id,
                    'link_def_id': link_def_id,
                    'status': status,
                    'preview_count': preview_count,
                    'executed_count': executed_count,
                    'error': error,
                    'started_at': started_at,
                    'completed_at': completed_at
                })
            return jobs
        finally:
            conn.close()

    # --- Internal helpers ---

    def _validate_label_exists(self, label_name: str):
        """
        Validate that a label exists in the label registry.

        Args:
            label_name: Name of the label to validate

        Raises:
            ValueError: If label does not exist
        """
        from .label_service import LabelService
        label_service = LabelService(self.app)
        label = label_service.get_label(label_name)
        if not label:
            raise ValueError(f"Label '{label_name}' does not exist. Please create it in the Labels page first.")

    def _fetch_source_data(self, definition: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch data from source based on source_type."""
        source_type = definition.get('source_type')
        source_config = definition.get('source_config', {})

        # 'label' type: Fetch nodes by label from Neo4j (new Label→Label format)
        if source_type == 'label':
            source_label = definition.get('source_label')
            if not source_label:
                raise ValueError("source_label is required when source_type is 'label'")
            # Convert to graph query format
            return self._fetch_graph_source({'label': source_label})
        elif source_type == 'graph':
            return self._fetch_graph_source(source_config)
        elif source_type == 'csv':
            return self._fetch_csv_source(source_config)
        elif source_type == 'api':
            return self._fetch_api_source(source_config)
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

    def _fetch_graph_source(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch nodes from Neo4j."""
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            label = config.get('label', '')
            where_clause = config.get('where_clause', '')

            # Build query
            query = f"MATCH (n:{label})"
            if where_clause:
                query += f" WHERE {where_clause}"
            query += " RETURN n LIMIT 1000"

            results = neo4j_client.execute_read(query)

            # Convert to dicts
            nodes = []
            for record in results:
                node = record.get('n')
                if node:
                    node_dict = dict(node)
                    node_dict['_id'] = node.id if hasattr(node, 'id') else None
                    nodes.append(node_dict)

            return nodes
        except Exception as e:
            raise Exception(f"Failed to fetch graph source: {str(e)}")

    def _fetch_csv_source(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse CSV data."""
        csv_data = config.get('csv_data', '')
        if not csv_data:
            return []

        try:
            reader = csv.DictReader(io.StringIO(csv_data))
            return list(reader)
        except Exception as e:
            raise Exception(f"Failed to parse CSV: {str(e)}")

    def _fetch_api_source(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch data from API endpoint."""
        url = config.get('url', '')
        if not url:
            raise ValueError("API URL is required")

        headers = config.get('headers', {})
        json_path = config.get('json_path', '')

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Apply JSONPath if specified
            if json_path:
                # Simple JSONPath implementation for basic cases
                # For production, use jsonpath-ng library
                parts = json_path.strip('$').strip('.').split('.')
                for part in parts:
                    if part.endswith('[*]'):
                        key = part[:-3]
                        data = data.get(key, [])
                    else:
                        data = data.get(part, data)

            return data if isinstance(data, list) else [data]
        except Exception as e:
            raise Exception(f"Failed to fetch API source: {str(e)}")

    def _match_with_targets(self, definition: Dict[str, Any], source_data: List[Dict[str, Any]],
                           limit: int = 10) -> List[Dict[str, Any]]:
        """Match source data with target nodes."""
        target_type = definition.get('target_type')
        target_config = definition.get('target_config', {})
        match_strategy = definition.get('match_strategy')
        match_config = definition.get('match_config', {})

        if target_type == 'graph':
            return self._match_graph_target(source_data, target_config, match_strategy, match_config, limit)
        elif target_type == 'label':
            return self._match_label_target(source_data, target_config, match_strategy, match_config, limit)
        else:
            raise ValueError(f"Unknown target_type: {target_type}")

    def _match_graph_target(self, source_data: List[Dict[str, Any]], target_config: Dict[str, Any],
                           match_strategy: str, match_config: Dict[str, Any],
                           limit: int) -> List[Dict[str, Any]]:
        """Match with existing graph nodes."""
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            matches = []
            for source_item in source_data[:limit]:
                if match_strategy == 'property':
                    source_field = match_config.get('source_field', '')
                    target_field = match_config.get('target_field', '')
                    target_label = target_config.get('label', '')

                    source_value = source_item.get(source_field)
                    if not source_value:
                        continue

                    query = f"MATCH (t:{target_label}) WHERE t.{target_field} = $value RETURN t LIMIT 1"
                    results = neo4j_client.execute_read(query, {'value': source_value})

                    if results:
                        target_node = results[0].get('t')
                        matches.append({
                            'source': source_item,
                            'target': dict(target_node) if target_node else None
                        })
                elif match_strategy == 'id':
                    # Direct ID match
                    target_id = source_item.get('target_id')
                    if not target_id:
                        continue

                    query = "MATCH (t) WHERE id(t) = $id RETURN t"
                    results = neo4j_client.execute_read(query, {'id': int(target_id)})

                    if results:
                        target_node = results[0].get('t')
                        matches.append({
                            'source': source_item,
                            'target': dict(target_node) if target_node else None
                        })
                elif match_strategy == 'cypher':
                    # Custom Cypher matching
                    cypher_template = match_config.get('cypher', '')
                    # Execute custom Cypher (with source_item parameters)
                    # This is a simplified version - production would need proper parameter binding
                    pass

            return matches
        except Exception as e:
            raise Exception(f"Failed to match graph target: {str(e)}")

    def _match_label_target(self, source_data: List[Dict[str, Any]], target_config: Dict[str, Any],
                           match_strategy: str, match_config: Dict[str, Any],
                           limit: int) -> List[Dict[str, Any]]:
        """Match with nodes by label."""
        # Similar to _match_graph_target but filters by label
        return self._match_graph_target(source_data, target_config, match_strategy, match_config, limit)

    def _execute_job_impl(self, job_id: str, definition: Dict[str, Any]):
        """Execute the link job (create relationships in Neo4j)."""
        conn = self._get_conn()
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Update status to running
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE link_jobs SET status = ? WHERE id = ?",
                ('running', job_id)
            )
            conn.commit()

            # Fetch all source data
            source_data = self._fetch_source_data(definition)

            # Match with targets
            matches = self._match_with_targets(definition, source_data, limit=len(source_data))

            # Create relationships in batches
            relationship_type = self._validate_relationship_type(definition.get('relationship_type', ''))
            relationship_props = definition.get('relationship_props', {})

            batch_size = 1000
            total_created = 0

            for i in range(0, len(matches), batch_size):
                batch = matches[i:i + batch_size]

                # Build batch create query
                batch_data = []
                for match in batch:
                    source = match.get('source', {})
                    target = match.get('target', {})

                    if not target:
                        continue

                    batch_data.append({
                        'source_id': source.get('_id') or source.get('id'),
                        'target_id': target.get('_id') or target.get('id'),
                        'properties': relationship_props
                    })

                if batch_data:
                    query = f"""
                    UNWIND $batch AS row
                    MATCH (source) WHERE id(source) = row.source_id
                    MATCH (target) WHERE id(target) = row.target_id
                    CREATE (source)-[r:{relationship_type}]->(target)
                    SET r = row.properties
                    """
                    neo4j_client.execute_write(query, {'batch': batch_data})
                    total_created += len(batch_data)

            # Update job status to completed
            cursor.execute(
                """
                UPDATE link_jobs
                SET status = ?, executed_count = ?, completed_at = ?
                WHERE id = ?
                """,
                ('completed', total_created, time.time(), job_id)
            )

            # Update link definition status to 'active' after successful execution
            link_def_id = definition.get('id')
            if link_def_id and total_created > 0:
                cursor.execute(
                    """
                    UPDATE link_definitions
                    SET status = ?
                    WHERE id = ?
                    """,
                    ('active', link_def_id)
                )

            conn.commit()
        except Exception as e:
            # Update job with error
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE link_jobs
                SET status = ?, error = ?, completed_at = ?
                WHERE id = ?
                """,
                ('failed', str(e), time.time(), job_id)
            )
            conn.commit()
            raise
        finally:
            conn.close()

    def _execute_job_impl_with_progress(self, job_id: str, definition: Dict[str, Any], task: Dict[str, Any]):
        """
        Execute the link job with progress tracking for /api/tasks integration.

        Args:
            job_id: Job ID for database tracking
            definition: Link definition
            task: Task dict to update with progress
        """
        # Special handling for data_import strategy
        if definition.get('match_strategy') == 'data_import':
            return self._execute_data_import_with_progress(job_id, definition, task)

        conn = self._get_conn()
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Create job record
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO link_jobs
                (id, link_def_id, status, preview_count, executed_count, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, definition.get('id'), 'running', 0, 0, task['started'])
            )
            conn.commit()

            # Fetch all source data
            task['status_message'] = 'Fetching source data...'
            source_data = self._fetch_source_data(definition)
            task['status_message'] = f'Found {len(source_data)} source items'

            # Match with targets
            task['status_message'] = 'Matching with targets...'
            matches = self._match_with_targets(definition, source_data, limit=len(source_data))

            task['total'] = len(matches)
            task['status_message'] = f'Found {len(matches)} matches to process'

            if len(matches) == 0:
                task['status_message'] = 'No matches found'
                cursor.execute(
                    """
                    UPDATE link_jobs
                    SET status = ?, executed_count = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    ('completed', 0, time.time(), job_id)
                )
                conn.commit()
                return

            # Create relationships in batches
            relationship_type = self._validate_relationship_type(definition.get('relationship_type', ''))
            relationship_props = definition.get('relationship_props', {})

            batch_size = 1000
            total_created = 0
            eta_window_start = time.time()

            for i in range(0, len(matches), batch_size):
                # Check for cancel
                if task.get('cancel_requested'):
                    task['status'] = 'canceled'
                    cursor.execute(
                        """
                        UPDATE link_jobs
                        SET status = ?, error = ?, completed_at = ?
                        WHERE id = ?
                        """,
                        ('cancelled', 'Job cancelled by user', time.time(), job_id)
                    )
                    conn.commit()
                    return

                batch = matches[i:i + batch_size]

                # Build batch create query
                batch_data = []
                for match in batch:
                    source = match.get('source', {})
                    target = match.get('target', {})

                    if not target:
                        continue

                    batch_data.append({
                        'source_id': source.get('_id') or source.get('id'),
                        'target_id': target.get('_id') or target.get('id'),
                        'properties': relationship_props
                    })

                if batch_data:
                    query = f"""
                    UNWIND $batch AS row
                    MATCH (source) WHERE id(source) = row.source_id
                    MATCH (target) WHERE id(target) = row.target_id
                    CREATE (source)-[r:{relationship_type}]->(target)
                    SET r = row.properties
                    """
                    neo4j_client.execute_write(query, {'batch': batch_data})
                    total_created += len(batch_data)

                # Update progress
                task['processed'] = min(i + batch_size, len(matches))
                task['relationships_created'] = total_created
                task['progress'] = task['processed'] / task['total'] if task['total'] > 0 else 0

                # Calculate ETA
                elapsed = time.time() - eta_window_start
                if elapsed > 0 and task['processed'] > 0:
                    rate = task['processed'] / elapsed
                    remaining = task['total'] - task['processed']
                    task['eta_seconds'] = int(remaining / rate) if rate > 0 else None
                    task['status_message'] = f'Creating relationships... {task["processed"]}/{task["total"]} ({int(rate)}/s)'
                else:
                    task['status_message'] = f'Creating relationships... {task["processed"]}/{task["total"]}'

            # Update job status to completed
            cursor.execute(
                """
                UPDATE link_jobs
                SET status = ?, executed_count = ?, completed_at = ?
                WHERE id = ?
                """,
                ('completed', total_created, time.time(), job_id)
            )

            # Update link definition status to 'active' after successful execution
            link_def_id = definition.get('id')
            if link_def_id and total_created > 0:
                cursor.execute(
                    """
                    UPDATE link_definitions
                    SET status = ?
                    WHERE id = ?
                    """,
                    ('active', link_def_id)
                )

            conn.commit()

            task['relationships_created'] = total_created
            task['status_message'] = f'Completed: {total_created} relationships created'

        except Exception as e:
            # Update job with error
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE link_jobs
                SET status = ?, error = ?, completed_at = ?
                WHERE id = ?
                """,
                ('failed', str(e), time.time(), job_id)
            )
            conn.commit()
            raise
        finally:
            conn.close()

    def verify_active_links(self) -> Dict[str, int]:
        """
        Verify all active link definitions against primary Neo4j graph.

        For each link with status='active', checks if relationships actually exist
        in the primary graph. If no relationships found, the link is stale and should
        be moved to 'pending' status.

        Returns:
            Dict mapping link_id to relationship count in primary graph.
            Links with count=0 are stale and will be updated to 'pending' status.
        """
        from .neo4j_client import get_neo4j_client

        # Get all active links
        links = self.list_link_definitions()
        active_links = [link for link in links if link.get('status') == 'active']

        if not active_links:
            return {}

        # Get primary Neo4j client
        neo4j_client = get_neo4j_client()
        if not neo4j_client:
            logger.warning("Cannot verify active links - Neo4j client not available")
            return {}

        verification_results = {}
        conn = self._get_conn()

        try:
            cursor = conn.cursor()

            for link in active_links:
                link_id = link['id']
                source_label = link.get('source_label')
                target_label = link.get('target_label')
                rel_type = link.get('relationship_type')

                if not all([source_label, target_label, rel_type]):
                    # Skip links without required fields
                    continue

                try:
                    # Validate relationship type for Cypher safety
                    rel_type_validated = self._validate_relationship_type(rel_type)

                    # Count relationships in primary graph
                    count_query = f"""
                    MATCH (a:{source_label})-[r:{rel_type_validated}]->(b:{target_label})
                    RETURN count(r) as rel_count
                    """

                    results = neo4j_client.execute_read(count_query)
                    rel_count = results[0].get('rel_count', 0) if results else 0

                    verification_results[link_id] = rel_count

                    # Update status if stale (no relationships found)
                    if rel_count == 0:
                        cursor.execute(
                            "UPDATE link_definitions SET status = ?, updated_at = ? WHERE id = ?",
                            ('pending', time.time(), link_id)
                        )
                        logger.info(f"Link {link_id} ({link['name']}) moved to pending - no relationships found in primary graph")

                except Exception as e:
                    logger.warning(f"Failed to verify link {link_id}: {e}")
                    verification_results[link_id] = -1  # Mark as error

            conn.commit()
            return verification_results

        finally:
            conn.close()
            if neo4j_client:
                neo4j_client.close()

    def discover_relationships(self, profile_name: Optional[str] = None, promote_to_active: bool = True) -> List[Dict[str, Any]]:
        """
        Query Neo4j to discover existing relationship types across all nodes.

        For discovered patterns that exist in primary graph:
        - If link definition exists → mark as 'active'
        - If no link definition exists → auto-create as 'active'

        Args:
            profile_name: Optional Neo4j profile name. If None, queries all configured databases.
            promote_to_active: If True, promote discovered patterns that exist in primary to 'active' status

        Returns:
            List of discovered relationships with:
            - source_label: Source node label
            - rel_type: Relationship type
            - target_label: Target node label
            - triple_count: Count of existing triples
            - database: 'PRIMARY' or profile name
        """
        from .neo4j_client import get_neo4j_client, get_neo4j_client_for_profile, list_neo4j_profiles

        discovered = []

        # Discovery query - finds all relationship patterns in the graph
        discovery_query = """
        MATCH (a)-[r]->(b)
        WITH labels(a) as source_labels, type(r) as rel_type, labels(b) as target_labels
        WHERE size(source_labels) > 0 AND size(target_labels) > 0
        WITH source_labels[0] as source_label, rel_type, target_labels[0] as target_label
        RETURN source_label, rel_type, target_label, count(*) as triple_count
        ORDER BY triple_count DESC
        """

        if profile_name:
            # Query specific profile only
            try:
                client = get_neo4j_client_for_profile(profile_name)
                if client:
                    try:
                        results = client.execute_read(discovery_query)
                        for record in results:
                            discovered.append({
                                'source_label': record.get('source_label'),
                                'rel_type': record.get('rel_type'),
                                'target_label': record.get('target_label'),
                                'triple_count': record.get('triple_count', 0),
                                'database': profile_name
                            })
                    finally:
                        client.close()
            except Exception as e:
                # Log error but continue
                try:
                    from flask import current_app
                    current_app.logger.warning(f"Failed to discover relationships from profile '{profile_name}': {e}")
                except:
                    pass

        else:
            # Query primary database
            try:
                primary_client = get_neo4j_client()
                if primary_client:
                    try:
                        results = primary_client.execute_read(discovery_query)
                        for record in results:
                            discovered.append({
                                'source_label': record.get('source_label'),
                                'rel_type': record.get('rel_type'),
                                'target_label': record.get('target_label'),
                                'triple_count': record.get('triple_count', 0),
                                'database': 'PRIMARY'
                            })
                    finally:
                        primary_client.close()
            except Exception as e:
                try:
                    from flask import current_app
                    current_app.logger.warning(f"Failed to discover relationships from primary database: {e}")
                except:
                    pass

            # Query all configured external profiles
            profiles = list_neo4j_profiles()
            for profile in profiles:
                profile_name = profile['name']
                try:
                    client = get_neo4j_client_for_profile(profile_name)
                    if client:
                        try:
                            results = client.execute_read(discovery_query)
                            for record in results:
                                discovered.append({
                                    'source_label': record.get('source_label'),
                                    'rel_type': record.get('rel_type'),
                                    'target_label': record.get('target_label'),
                                    'triple_count': record.get('triple_count', 0),
                                    'database': profile_name
                                })
                        finally:
                            client.close()
                except Exception as e:
                    # Log error but continue with other profiles
                    try:
                        from flask import current_app
                        current_app.logger.warning(f"Failed to discover relationships from profile '{profile_name}': {e}")
                    except:
                        pass

        # Promote discovered patterns that exist in primary to 'active' status
        if promote_to_active and discovered:
            self._promote_discovered_to_active(discovered)

        # Filter out PRIMARY database entries - they belong in Active tab, not Available
        # Available should only show external/read-only database relationships
        discovered = [d for d in discovered if d['database'] != 'PRIMARY']

        # Deduplicate by triple pattern - show one entry per unique (source, rel, target)
        # Keep all database sources in a list for the badge display
        triple_map = {}
        for rel in discovered:
            triple_key = (rel['source_label'], rel['rel_type'], rel['target_label'])
            if triple_key not in triple_map:
                triple_map[triple_key] = {
                    'source_label': rel['source_label'],
                    'rel_type': rel['rel_type'],
                    'target_label': rel['target_label'],
                    'triple_count': rel['triple_count'],
                    'database': rel['database'],  # Keep first database as primary
                    'databases': [rel['database']]  # Track all databases
                }
            else:
                # Add this database to the list if not already present
                if rel['database'] not in triple_map[triple_key]['databases']:
                    triple_map[triple_key]['databases'].append(rel['database'])
                # Sum up the triple counts
                triple_map[triple_key]['triple_count'] += rel['triple_count']

        discovered = list(triple_map.values())

        return discovered

    def _promote_discovered_to_active(self, discovered: List[Dict[str, Any]]):
        """
        Promote discovered relationship patterns to 'active' status if they exist in primary.

        For each discovered pattern:
        1. Check if it exists in PRIMARY graph
        2. If yes and link definition exists → mark as 'active'
        3. If yes and no link definition → auto-create as 'active'

        Args:
            discovered: List of discovered relationship patterns
        """
        from .neo4j_client import get_neo4j_client

        # Get primary client to check which patterns exist
        primary_client = get_neo4j_client()
        if not primary_client:
            return

        conn = self._get_conn()

        try:
            cursor = conn.cursor()

            # Find patterns that exist in PRIMARY
            primary_patterns = [d for d in discovered if d['database'] == 'PRIMARY']

            for pattern in primary_patterns:
                source_label = pattern['source_label']
                target_label = pattern['target_label']
                rel_type = pattern['rel_type']
                triple_count = pattern.get('triple_count', 0)

                if triple_count == 0:
                    continue  # Skip patterns with no relationships

                # Check if link definition already exists
                cursor.execute(
                    """
                    SELECT id, status FROM link_definitions
                    WHERE source_label = ? AND target_label = ? AND relationship_type = ?
                    LIMIT 1
                    """,
                    (source_label, target_label, rel_type)
                )
                existing = cursor.fetchone()

                if existing:
                    # Link definition exists - mark as active if not already
                    link_id, current_status = existing
                    if current_status != 'active':
                        cursor.execute(
                            "UPDATE link_definitions SET status = 'active', updated_at = ? WHERE id = ?",
                            (time.time(), link_id)
                        )
                        logger.info(f"Promoted existing link {link_id} to 'active' - {triple_count} relationships found in primary")
                else:
                    # No link definition - auto-create as 'active'
                    link_id = str(uuid.uuid4())
                    link_name = f"{source_label} → {rel_type} → {target_label}"
                    now = time.time()

                    cursor.execute(
                        """
                        INSERT INTO link_definitions
                        (id, name, source_label, target_label, source_type, source_config,
                         target_type, target_config, match_strategy, match_config,
                         relationship_type, relationship_props, created_at, updated_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (link_id, link_name, source_label, target_label, 'label', '{}',
                         'label', '{}', 'id', '{}', rel_type, '{}', now, now, 'active')
                    )
                    logger.info(f"Auto-created link definition {link_id} as 'active' - {triple_count} relationships found in primary")

            conn.commit()

        finally:
            conn.close()
            if primary_client:
                primary_client.close()

    def preview_discovered_import(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        import_rel_properties: bool = True
    ) -> Dict[str, Any]:
        """
        Preview stub node import from discovered relationship (dry run).

        Analyzes what would be imported without making any changes.

        Args:
            source_label: Source node label
            target_label: Target node label
            rel_type: Relationship type
            source_database: External Neo4j database name
            source_uid_property: Property to use as unique ID for source nodes
            target_uid_property: Property to use as unique ID for target nodes
            import_rel_properties: Whether to import relationship properties

        Returns:
            Preview statistics dict with counts of nodes/relationships
        """
        from .neo4j_client import get_neo4j_client, get_neo4j_client_for_profile
        import time

        logger.warning(f"[Preview] source_database={source_database!r}, source_label={source_label!r}, rel_type={rel_type!r}")

        start_time = time.time()

        # Get source database client
        if source_database == 'PRIMARY':
            source_client = get_neo4j_client()
        else:
            source_client = get_neo4j_client_for_profile(source_database)

        if not source_client:
            raise ValueError(f"Database '{source_database}' not found")

        # Get primary database client for checking existing nodes
        primary_client = get_neo4j_client()
        if not primary_client:
            raise ValueError("Primary database not connected")

        try:
            # Query source database for relationship count
            # Use separate queries to avoid potential Neo4j optimization issues with complex aggregations
            logger.info(f"[Preview] Running count queries on '{source_database}' - {source_label}-[{rel_type}]->{target_label}")

            # Count total relationships
            rel_count_query = f"""
            MATCH (:{source_label})-[r:{rel_type}]->(:{target_label})
            RETURN count(r) as total_relationships
            """
            rel_results = source_client.execute_read(rel_count_query)
            total_rels = rel_results[0].get('total_relationships', 0) if rel_results else 0

            logger.info(f"[Preview] Total relationships found: {total_rels}")

            # Count unique source nodes with valid UID
            source_count_query = f"""
            MATCH (a:{source_label})-[:{rel_type}]->(:{target_label})
            WHERE a.{source_uid_property} IS NOT NULL
            RETURN count(DISTINCT a.{source_uid_property}) as unique_source_nodes
            """
            source_results = source_client.execute_read(source_count_query)
            unique_sources = source_results[0].get('unique_source_nodes', 0) if source_results else 0

            # Count unique target nodes with valid UID
            target_count_query = f"""
            MATCH (:{source_label})-[:{rel_type}]->(b:{target_label})
            WHERE b.{target_uid_property} IS NOT NULL
            RETURN count(DISTINCT b.{target_uid_property}) as unique_target_nodes
            """
            target_results = source_client.execute_read(target_count_query)
            unique_targets = target_results[0].get('unique_target_nodes', 0) if target_results else 0

            logger.info(f"[Preview] Counts - total_rels={total_rels}, unique_sources={unique_sources}, unique_targets={unique_targets}")

            # Get exact source and target UIDs from source database
            logger.info(f"[Preview] Fetching distinct UIDs from source database...")

            source_uids_query = f"""
            MATCH (a:{source_label})-[:{rel_type}]->(:{target_label})
            WHERE a.{source_uid_property} IS NOT NULL
            RETURN DISTINCT a.{source_uid_property} as uid
            """
            source_uid_results = source_client.execute_read(source_uids_query)
            source_uids = [row['uid'] for row in source_uid_results]

            target_uids_query = f"""
            MATCH (:{source_label})-[:{rel_type}]->(b:{target_label})
            WHERE b.{target_uid_property} IS NOT NULL
            RETURN DISTINCT b.{target_uid_property} as uid
            """
            target_uid_results = source_client.execute_read(target_uids_query)
            target_uids = [row['uid'] for row in target_uid_results]

            logger.info(f"[Preview] Got {len(source_uids)} source UIDs and {len(target_uids)} target UIDs")

            # Check exact matches in primary database
            logger.info(f"[Preview] Checking existing nodes in primary...")

            existing_sources = 0
            if source_uids:
                existing_sources_query = f"""
                MATCH (a:{source_label})
                WHERE a.{source_uid_property} IN $uids
                RETURN count(a) as count
                """
                existing_sources_result = primary_client.execute_read(existing_sources_query, {'uids': source_uids})
                existing_sources = existing_sources_result[0].get('count', 0) if existing_sources_result else 0

            existing_targets = 0
            if target_uids:
                existing_targets_query = f"""
                MATCH (a:{target_label})
                WHERE a.{target_uid_property} IN $uids
                RETURN count(a) as count
                """
                existing_targets_result = primary_client.execute_read(existing_targets_query, {'uids': target_uids})
                existing_targets = existing_targets_result[0].get('count', 0) if existing_targets_result else 0

            # Calculate exact new vs merge counts
            sources_to_merge = existing_sources
            sources_to_create = len(source_uids) - existing_sources

            targets_to_merge = existing_targets
            targets_to_create = len(target_uids) - existing_targets

            logger.info(f"[Preview] Exact counts - sources: {sources_to_create} new + {sources_to_merge} existing = {len(source_uids)} total")
            logger.info(f"[Preview] Exact counts - targets: {targets_to_create} new + {targets_to_merge} existing = {len(target_uids)} total")

            # Get relationship property count if importing properties
            rel_prop_count = 0
            if import_rel_properties:
                prop_query = f"""
                MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                RETURN size(keys(r)) as prop_count
                LIMIT 1
                """
                prop_results = source_client.execute_read(prop_query)
                rel_prop_count = prop_results[0].get('prop_count', 0) if prop_results else 0

            duration = time.time() - start_time

            return {
                'total_relationships': total_rels,
                'source_nodes_to_create': sources_to_create,
                'source_nodes_to_merge': sources_to_merge,
                'target_nodes_to_create': targets_to_create,
                'target_nodes_to_merge': targets_to_merge,
                'relationships_to_create': total_rels,
                'rel_property_count': rel_prop_count if import_rel_properties else 0,
                'duration_seconds': duration
            }

        finally:
            if source_client and source_database != 'PRIMARY':
                source_client.close()

    def execute_discovered_import_with_task(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        import_rel_properties: bool = True,
        batch_size: int = 100
    ) -> str:
        """
        Execute discovered import as background task with progress tracking.
        Automatically creates/updates Link Definition for reusability.

        Returns:
            Task ID for polling progress
        """
        import hashlib
        from flask import current_app

        now = time.time()
        tid_src = f"discovered_import|{source_database}|{source_label}|{rel_type}|{target_label}|{now}"
        task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]

        # Auto-create or update Link Definition for this import
        # This allows the user to rerun the import later from the Active tab
        link_def_id = self._get_or_create_discovered_link_definition(
            source_label=source_label,
            target_label=target_label,
            rel_type=rel_type,
            source_database=source_database,
            source_uid_property=source_uid_property,
            target_uid_property=target_uid_property,
            import_rel_properties=import_rel_properties
        )

        # Create task record
        task = {
            'id': task_id,
            'type': 'discovered_import',
            'status': 'running',
            'link_def_id': link_def_id,
            'source_database': source_database,
            'source_label': source_label,
            'target_label': target_label,
            'rel_type': rel_type,
            'started': now,
            'ended': None,
            'total': 0,  # Will be updated as we discover total
            'processed': 0,
            'progress': 0.0,
            'error': None,
            'status_message': 'Initializing import...',
            'relationships_created': 0,
            'source_nodes_created': 0,
            'target_nodes_created': 0,
        }
        current_app.extensions['scidk'].setdefault('tasks', {})[task_id] = task

        # Run in background thread
        import threading
        app = current_app._get_current_object()

        def _worker():
            with app.app_context():
                try:
                    self._execute_discovered_import_with_progress(
                        task=task,
                        source_label=source_label,
                        target_label=target_label,
                        rel_type=rel_type,
                        source_database=source_database,
                        source_uid_property=source_uid_property,
                        target_uid_property=target_uid_property,
                        import_rel_properties=import_rel_properties,
                        batch_size=batch_size,
                        link_def_id=link_def_id
                    )
                    task['ended'] = time.time()
                    task['status'] = 'completed'
                    task['progress'] = 1.0
                    task['status_message'] = f'Imported {task["relationships_created"]} relationships. Link Definition saved in Active tab.'
                except Exception as e:
                    logger.exception("Discovered import failed")
                    task['ended'] = time.time()
                    task['status'] = 'error'
                    task['error'] = str(e)

        threading.Thread(target=_worker, daemon=True).start()
        return task_id

    def _get_or_create_discovered_link_definition(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        import_rel_properties: bool
    ) -> str:
        """
        Create or update a Link Definition for a discovered relationship import.
        This allows the import to be rerun later.
        """
        # Check if definition already exists for this exact pattern
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status FROM link_definitions
                WHERE source_label = ? AND target_label = ? AND relationship_type = ?
                AND json_extract(match_config, '$.source_database') = ?
                LIMIT 1
                """,
                (source_label, target_label, rel_type, source_database)
            )
            existing = cursor.fetchone()

            link_def_id = existing[0] if existing else str(uuid.uuid4())
            link_name = f"{source_label} → {rel_type} → {target_label} ({source_database})"

            match_config = {
                'source_database': source_database,
                'source_uid_property': source_uid_property,
                'target_uid_property': target_uid_property,
                'import_rel_properties': import_rel_properties
            }

            now = time.time()

            if existing:
                # Update existing - set to active since import is running
                cursor.execute(
                    """
                    UPDATE link_definitions
                    SET match_config = ?, updated_at = ?, status = 'active'
                    WHERE id = ?
                    """,
                    (json.dumps(match_config), now, link_def_id)
                )
            else:
                # Create new - start as pending, will become active on completion
                cursor.execute(
                    """
                    INSERT INTO link_definitions
                    (id, name, source_label, target_label, source_type, source_config,
                     target_type, target_config,
                     match_strategy, match_config, relationship_type, relationship_props,
                     created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (link_def_id, link_name, source_label, target_label, 'label', '{}',
                     'label', '{}',
                     'id', json.dumps(match_config), rel_type, '{}', now, now, 'pending')
                )

            conn.commit()
            return link_def_id
        finally:
            conn.close()

    def _execute_discovered_import_with_progress(
        self,
        task: Dict[str, Any],
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        import_rel_properties: bool,
        batch_size: int,
        link_def_id: str
    ):
        """Execute discovered import with live progress updates to task dict."""
        # This wraps the existing execute_discovered_import logic with progress tracking
        result = self.execute_discovered_import(
            source_label=source_label,
            target_label=target_label,
            rel_type=rel_type,
            source_database=source_database,
            source_uid_property=source_uid_property,
            target_uid_property=target_uid_property,
            import_rel_properties=import_rel_properties,
            batch_size=batch_size,
            progress_callback=lambda current, total, msg: self._update_task_progress(task, current, total, msg),
            task=task
        )

        # Update final task state
        task['relationships_created'] = result.get('relationships_created', 0)
        task['source_nodes_created'] = result.get('source_nodes_created', 0)
        task['target_nodes_created'] = result.get('target_nodes_created', 0)

        # Mark Link Definition as active on successful completion and store sync metadata
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            now = time.time()
            relationships_created = result.get('relationships_created', 0)
            cursor.execute(
                """UPDATE link_definitions
                   SET status = 'active', last_synced_count = ?, last_synced_at = ?, updated_at = ?
                   WHERE id = ?""",
                (relationships_created, now, now, link_def_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_task_progress(self, task: Dict[str, Any], current: int, total: int, message: str):
        """Update task progress dict (called from import worker thread)."""
        task['processed'] = current
        task['total'] = total
        task['progress'] = current / total if total > 0 else 0
        task['status_message'] = message

    def execute_discovered_import(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        import_rel_properties: bool = True,
        batch_size: int = 5000,
        progress_callback=None,
        task: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Import stub nodes and relationships from discovered relationship.

        Creates lightweight stub nodes with only UID property, then creates
        relationships. Idempotent - running multiple times produces same result.

        Args:
            source_label: Source node label
            target_label: Target node label
            rel_type: Relationship type
            source_database: External Neo4j database name
            source_uid_property: Property to use as unique ID for source nodes
            target_uid_property: Property to use as unique ID for target nodes
            import_rel_properties: Whether to import relationship properties
            batch_size: Number of relationships to import per batch

        Returns:
            Summary dict with counts of nodes/relationships created/merged
        """
        from .neo4j_client import get_neo4j_client, get_neo4j_client_for_profile
        import time

        start_time = time.time()

        # Get source database client
        if source_database == 'PRIMARY':
            source_client = get_neo4j_client()
        else:
            source_client = get_neo4j_client_for_profile(source_database)

        if not source_client:
            raise ValueError(f"Database '{source_database}' not found")

        # Get primary database client
        primary_client = get_neo4j_client()
        if not primary_client:
            raise ValueError("Primary database not connected")

        try:
            # Get total count upfront for accurate progress tracking
            logger.info(f"[Import] Counting total relationships in '{source_database}'...")
            count_query = f"""
            MATCH (:{source_label})-[r:{rel_type}]->(:{target_label})
            RETURN count(r) as total
            """
            count_result = source_client.execute_read(count_query)
            total_relationships = count_result[0].get('total', 0) if count_result else 0
            logger.info(f"[Import] Total relationships to import: {total_relationships}")

            # Report initial progress
            if progress_callback:
                progress_callback(0, total_relationships, f"Starting import of {total_relationships:,} relationships...")

            # Track statistics
            source_nodes_created = 0
            source_nodes_merged = 0
            target_nodes_created = 0
            target_nodes_merged = 0
            relationships_created = 0

            # Use keyset pagination to avoid O(n) SKIP overhead
            # This makes each batch O(log n) instead, keeping speed constant
            last_source_uid = None
            last_target_uid = None
            total_fetched = 0

            logger.info(f"[Import] Starting streaming import from '{source_database}' - batch_size={batch_size}")

            while True:
                # Check for cancellation
                if task and task.get('cancel_requested'):
                    logger.info(f"[Import] Cancellation requested, stopping import")
                    task['status'] = 'cancelled'
                    task['status_message'] = 'Import cancelled by user'
                    return {
                        'source_nodes_created': source_nodes_created,
                        'source_nodes_merged': source_nodes_merged,
                        'target_nodes_created': target_nodes_created,
                        'target_nodes_merged': target_nodes_merged,
                        'relationships_created': relationships_created,
                        'duration_seconds': time.time() - start_time
                    }

                # Fetch one batch from source database using keyset pagination
                # Keyset pagination: WHERE (source_uid, target_uid) > (last_source, last_target)
                if last_source_uid is None:
                    # First batch - no cursor
                    if import_rel_properties:
                        fetch_query = f"""
                        MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                        WHERE a.{source_uid_property} IS NOT NULL AND b.{target_uid_property} IS NOT NULL
                        RETURN a.{source_uid_property} as source_uid,
                               b.{target_uid_property} as target_uid,
                               properties(r) as rel_props
                        ORDER BY source_uid, target_uid
                        LIMIT {batch_size}
                        """
                    else:
                        fetch_query = f"""
                        MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                        WHERE a.{source_uid_property} IS NOT NULL AND b.{target_uid_property} IS NOT NULL
                        RETURN a.{source_uid_property} as source_uid,
                               b.{target_uid_property} as target_uid
                        ORDER BY source_uid, target_uid
                        LIMIT {batch_size}
                        """
                    logger.info(f"[Import] Fetching first batch: batch_size={batch_size}")
                    batch = source_client.execute_read(fetch_query)
                else:
                    # Subsequent batches - use keyset cursor
                    if import_rel_properties:
                        fetch_query = f"""
                        MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                        WHERE a.{source_uid_property} IS NOT NULL AND b.{target_uid_property} IS NOT NULL
                        AND (a.{source_uid_property} > $last_source
                             OR (a.{source_uid_property} = $last_source AND b.{target_uid_property} > $last_target))
                        RETURN a.{source_uid_property} as source_uid,
                               b.{target_uid_property} as target_uid,
                               properties(r) as rel_props
                        ORDER BY source_uid, target_uid
                        LIMIT {batch_size}
                        """
                    else:
                        fetch_query = f"""
                        MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                        WHERE a.{source_uid_property} IS NOT NULL AND b.{target_uid_property} IS NOT NULL
                        AND (a.{source_uid_property} > $last_source
                             OR (a.{source_uid_property} = $last_source AND b.{target_uid_property} > $last_target))
                        RETURN a.{source_uid_property} as source_uid,
                               b.{target_uid_property} as target_uid
                        ORDER BY source_uid, target_uid
                        LIMIT {batch_size}
                        """
                    logger.info(f"[Import] Fetching batch after cursor: last_source={last_source_uid}, last_target={last_target_uid}")
                    batch = source_client.execute_read(
                        fetch_query,
                        last_source=last_source_uid,
                        last_target=last_target_uid
                    )

                batch_len = len(batch) if batch else 0
                logger.info(f"[Import] Fetched batch: len(batch)={batch_len}")

                if not batch:
                    # No more relationships to fetch
                    logger.info(f"[Import] No more batches - stopping")
                    break

                # Update cursor for next batch (keyset pagination)
                last_source_uid = batch[-1]['source_uid']
                last_target_uid = batch[-1]['target_uid']

                total_fetched += len(batch)

                # Build UNWIND query for batch import
                if import_rel_properties:
                    import_query = f"""
                    UNWIND $batch as row
                    MERGE (a:{source_label} {{{source_uid_property}: row.source_uid}})
                    ON CREATE SET a._imported_stub = true
                    MERGE (b:{target_label} {{{target_uid_property}: row.target_uid}})
                    ON CREATE SET b._imported_stub = true
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += row.rel_props
                    RETURN
                        count(DISTINCT CASE WHEN a._imported_stub THEN a END) as sources_created,
                        count(DISTINCT CASE WHEN NOT a._imported_stub THEN a END) as sources_merged,
                        count(DISTINCT CASE WHEN b._imported_stub THEN b END) as targets_created,
                        count(DISTINCT CASE WHEN NOT b._imported_stub THEN b END) as targets_merged,
                        count(r) as rels_created
                    """
                else:
                    import_query = f"""
                    UNWIND $batch as row
                    MERGE (a:{source_label} {{{source_uid_property}: row.source_uid}})
                    ON CREATE SET a._imported_stub = true
                    MERGE (b:{target_label} {{{target_uid_property}: row.target_uid}})
                    ON CREATE SET b._imported_stub = true
                    MERGE (a)-[r:{rel_type}]->(b)
                    RETURN
                        count(DISTINCT CASE WHEN a._imported_stub THEN a END) as sources_created,
                        count(DISTINCT CASE WHEN NOT a._imported_stub THEN a END) as sources_merged,
                        count(DISTINCT CASE WHEN b._imported_stub THEN b END) as targets_created,
                        count(DISTINCT CASE WHEN NOT b._imported_stub THEN b END) as targets_merged,
                        count(r) as rels_created
                    """

                # Execute batch import
                batch_data = [
                    {
                        'source_uid': rel['source_uid'],
                        'target_uid': rel['target_uid'],
                        'rel_props': rel.get('rel_props', {}) if import_rel_properties else {}
                    }
                    for rel in batch
                ]

                result = primary_client.execute_write(import_query, {'batch': batch_data})

                if result:
                    stats = result[0]
                    source_nodes_created += stats.get('sources_created', 0)
                    source_nodes_merged += stats.get('sources_merged', 0)
                    target_nodes_created += stats.get('targets_created', 0)
                    target_nodes_merged += stats.get('targets_merged', 0)
                    relationships_created += stats.get('rels_created', 0)
                    logger.info(f"[Import] Batch processed - relationships_created so far: {relationships_created}")

                    # Report progress if callback provided (with ETA like tqdm)
                    if progress_callback:
                        elapsed = time.time() - start_time
                        if relationships_created > 0 and elapsed > 0:
                            rate = relationships_created / elapsed  # relationships per second
                            remaining = total_relationships - relationships_created
                            eta_seconds = remaining / rate if rate > 0 else 0

                            # Format ETA (like tqdm: 2m 15s or 45s)
                            if eta_seconds > 60:
                                eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                            else:
                                eta_str = f"{int(eta_seconds)}s"

                            message = f"Importing... {relationships_created:,} / {total_relationships:,} relationships (ETA: {eta_str})"
                        else:
                            message = f"Importing... {relationships_created:,} / {total_relationships:,} relationships"

                        progress_callback(
                            relationships_created,
                            total_relationships,
                            message
                        )

                # If we got fewer results than batch_size, we've reached the end
                if len(batch) < batch_size:
                    logger.info(f"[Import] Completed - final batch had {len(batch)} rows (< {batch_size}), total fetched: {total_fetched}")
                    break

            # Clean up _imported_stub flags
            cleanup_query = f"""
            MATCH (n)
            WHERE n._imported_stub = true
            REMOVE n._imported_stub
            """
            primary_client.execute_write(cleanup_query)

            duration = time.time() - start_time

            return {
                'source_nodes_created': source_nodes_created,
                'source_nodes_merged': source_nodes_merged,
                'target_nodes_created': target_nodes_created,
                'target_nodes_merged': target_nodes_merged,
                'relationships_created': relationships_created,
                'duration_seconds': duration
            }

        finally:
            if source_client and source_database != 'PRIMARY':
                source_client.close()

    def preview_triple_import(self, source_database: str, rel_type: str, source_label: str, target_label: str) -> Dict[str, Any]:
        """
        Preview triples that would be imported from an external database.

        Args:
            source_database: Name of the source Neo4j profile
            rel_type: Relationship type to import
            source_label: Source node label
            target_label: Target node label

        Returns:
            Dict with status, preview triples list (limited to 100), and total count
        """
        import re
        import hashlib
        import json
        from .neo4j_client import get_neo4j_client_for_profile

        logger.warning(f"[Preview] source_database={source_database!r}, source_label={source_label!r}, rel_type={rel_type!r}")

        # Validate relationship type (Cypher injection protection)
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type):
            return {
                'status': 'error',
                'error': 'Invalid relationship type format'
            }

        # Validate labels
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', source_label) or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', target_label):
            return {
                'status': 'error',
                'error': 'Invalid label format'
            }

        try:
            # Connect to source database
            source_client = get_neo4j_client_for_profile(source_database)
            if not source_client:
                return {
                    'status': 'error',
                    'error': f"Could not connect to source database '{source_database}'"
                }

            try:
                # Query for triples (limit preview to 100)
                preview_query = f"""
                MATCH (source:{source_label})-[r:{rel_type}]->(target:{target_label})
                RETURN elementId(source) as source_id,
                       properties(source) as source_props,
                       type(r) as rel_type,
                       properties(r) as rel_props,
                       elementId(target) as target_id,
                       properties(target) as target_props
                LIMIT 100
                """

                preview_results = source_client.execute_read(preview_query)

                # Get total count
                count_query = f"""
                MATCH (:{source_label})-[r:{rel_type}]->(:{target_label})
                RETURN count(r) as total
                """
                count_results = source_client.execute_read(count_query)
                total_count = count_results[0].get('total', 0) if count_results else 0

                # Format preview
                preview_triples = []
                for record in preview_results:
                    preview_triples.append({
                        'source_node': {
                            'id': record.get('source_id'),
                            'label': source_label,
                            'properties': record.get('source_props', {})
                        },
                        'relationship': {
                            'type': record.get('rel_type'),
                            'properties': record.get('rel_props', {})
                        },
                        'target_node': {
                            'id': record.get('target_id'),
                            'label': target_label,
                            'properties': record.get('target_props', {})
                        }
                    })

                # Generate preview hash for validation on commit
                preview_data = {
                    'source_database': source_database,
                    'rel_type': rel_type,
                    'source_label': source_label,
                    'target_label': target_label,
                    'total_count': total_count
                }
                preview_hash = hashlib.sha256(json.dumps(preview_data, sort_keys=True).encode()).hexdigest()

                return {
                    'status': 'success',
                    'preview': preview_triples,
                    'total_count': total_count,
                    'preview_hash': preview_hash,
                    'showing': len(preview_triples)
                }

            finally:
                source_client.close()

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def commit_triple_import(self, source_database: str, rel_type: str, source_label: str, target_label: str, preview_hash: str) -> Dict[str, Any]:
        """
        Import triples from external database to primary database.

        Optimization strategy:
        1. Try APOC-based direct copy (fastest, ~30s for 500K triples)
        2. Fall back to streaming batches if APOC unavailable
        3. Use large batch size (10000) to minimize round trips

        Args:
            source_database: Name of the source Neo4j profile
            rel_type: Relationship type to import
            source_label: Source node label
            target_label: Target node label
            preview_hash: Hash from preview to validate request hasn't changed

        Returns:
            Dict with status, triples_imported count, duration, and method used
        """
        import re
        import time
        from .neo4j_client import get_neo4j_client_for_profile, get_neo4j_client

        # Validate inputs
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type):
            return {'status': 'error', 'error': 'Invalid relationship type format'}
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', source_label) or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', target_label):
            return {'status': 'error', 'error': 'Invalid label format'}

        start_time = time.time()

        try:
            # Connect to source database
            source_client = get_neo4j_client_for_profile(source_database)
            if not source_client:
                return {'status': 'error', 'error': f"Could not connect to source database '{source_database}'"}

            # Connect to primary database
            primary_client = get_neo4j_client()
            if not primary_client:
                return {'status': 'error', 'error': 'Could not connect to primary database'}

            try:
                import_timestamp = time.time()

                # Strategy 1: Try APOC-based import (fastest)
                apoc_result = self._try_apoc_import(
                    source_client, primary_client, source_database,
                    rel_type, source_label, target_label, import_timestamp
                )

                if apoc_result['success']:
                    duration = time.time() - start_time
                    return {
                        'status': 'success',
                        'triples_imported': apoc_result['count'],
                        'duration_seconds': round(duration, 2),
                        'method': 'apoc'
                    }

                # Strategy 2: Streaming batch import (fallback)
                result = self._streaming_batch_import(
                    source_client, primary_client, source_database,
                    rel_type, source_label, target_label, import_timestamp
                )

                duration = time.time() - start_time

                return {
                    'status': 'success',
                    'triples_imported': result['count'],
                    'duration_seconds': round(duration, 2),
                    'method': 'streaming_batch',
                    'batches_processed': result.get('batches', 0)
                }

            finally:
                source_client.close()
                primary_client.close()

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _try_apoc_import(self, source_client, primary_client, source_database: str,
                        rel_type: str, source_label: str, target_label: str,
                        import_timestamp: float) -> Dict[str, Any]:
        """
        Attempt APOC-based direct copy between databases.

        Returns dict with 'success' (bool) and 'count' (int) if successful.
        """
        try:
            # Check if APOC is available
            apoc_check = primary_client.execute_read("RETURN apoc.version() as version")
            if not apoc_check:
                return {'success': False}

            # Get source connection details
            from .neo4j_client import get_settings_by_prefix
            source_settings = get_settings_by_prefix(f'neo4j_profile_{source_database}')

            if not source_settings:
                return {'success': False}

            source_uri = source_settings.get('uri')
            source_user = source_settings.get('user')
            source_password = source_settings.get('password', '')
            source_db = source_settings.get('database', 'neo4j')

            if not source_uri:
                return {'success': False}

            # APOC query to copy triples directly
            # Use elementId with database prefix for unique identification
            apoc_query = f"""
            CALL apoc.bolt.load(
                $source_uri,
                "MATCH (source:{source_label})-[r:{rel_type}]->(target:{target_label})
                 RETURN elementId(source) as source_id,
                        properties(source) as source_props,
                        properties(r) as rel_props,
                        elementId(target) as target_id,
                        properties(target) as target_props",
                {{}},
                {{username: $source_user, password: $source_password, database: $source_db}}
            ) YIELD row
            WITH row, $external_db + '::' + row.source_id as prefixed_source_id,
                      $external_db + '::' + row.target_id as prefixed_target_id
            MERGE (source:{source_label} {{__import_id__: prefixed_source_id}})
            SET source += row.source_props,
                source.__source_db__ = $external_db
            MERGE (target:{target_label} {{__import_id__: prefixed_target_id}})
            SET target += row.target_props,
                target.__source_db__ = $external_db
            MERGE (source)-[r:{rel_type}]->(target)
            SET r += row.rel_props,
                r.__source__ = 'graph_import',
                r.__external_db__ = $external_db,
                r.__imported_at__ = $imported_at,
                r.__imported_by__ = 'scidk'
            RETURN count(r) as imported
            """

            result = primary_client.execute_write(apoc_query, {
                'source_uri': source_uri,
                'source_user': source_user,
                'source_password': source_password,
                'source_db': source_db,
                'external_db': source_database,
                'imported_at': import_timestamp
            })

            if result:
                return {'success': True, 'count': result[0].get('imported', 0)}

            return {'success': False}

        except Exception as e:
            # APOC not available or failed, fall back to streaming
            return {'success': False}

    def _streaming_batch_import(self, source_client, primary_client, source_database: str,
                                rel_type: str, source_label: str, target_label: str,
                                import_timestamp: float) -> Dict[str, Any]:
        """
        Streaming batch import - fetch and write in chunks without loading all into memory.
        Uses batch size of 10000 for better performance.
        """
        batch_size = 10000  # Increased from 1000
        total_imported = 0
        batch_count = 0
        skip = 0

        logger.info(f"[Import] Reading from source database '{source_database}', writing to PRIMARY")

        while True:
            # Fetch one batch from source with Neo4j element IDs
            triples_query = f"""
            MATCH (source:{source_label})-[r:{rel_type}]->(target:{target_label})
            RETURN elementId(source) as source_id,
                   properties(source) as source_props,
                   properties(r) as rel_props,
                   elementId(target) as target_id,
                   properties(target) as target_props
            SKIP {skip}
            LIMIT {batch_size}
            """

            batch_triples = source_client.execute_read(triples_query)

            if not batch_triples:
                break  # No more triples to fetch

            # Write batch to primary
            # Use prefixed elementId for unique identification across databases
            import_query = f"""
            UNWIND $triples as triple
            MERGE (source:{source_label} {{__import_id__: triple.source_id}})
            SET source += triple.source_props,
                source.__source_db__ = $external_db
            MERGE (target:{target_label} {{__import_id__: triple.target_id}})
            SET target += triple.target_props,
                target.__source_db__ = $external_db
            MERGE (source)-[r:{rel_type}]->(target)
            SET r += triple.rel_props,
                r.__source__ = 'graph_import',
                r.__external_db__ = $external_db,
                r.__imported_at__ = $imported_at,
                r.__imported_by__ = 'scidk'
            RETURN count(r) as imported
            """

            batch_data = [
                {
                    'source_id': f"{source_database}::{triple.get('source_id')}",
                    'source_props': triple.get('source_props', {}),
                    'rel_props': triple.get('rel_props', {}),
                    'target_id': f"{source_database}::{triple.get('target_id')}",
                    'target_props': triple.get('target_props', {})
                }
                for triple in batch_triples
            ]

            result = primary_client.execute_write(import_query, {
                'triples': batch_data,
                'external_db': source_database,
                'imported_at': import_timestamp
            })

            if result:
                total_imported += result[0].get('imported', 0)

            batch_count += 1
            skip += batch_size

            # If we got fewer results than batch_size, we're done
            if len(batch_triples) < batch_size:
                break

        return {'count': total_imported, 'batches': batch_count}

    def _execute_data_import_with_progress(self, job_id: str, definition: Dict[str, Any], task: Dict[str, Any]):
        """
        Execute data import with progress tracking.

        Args:
            job_id: Job ID for database tracking
            definition: Link definition with match_strategy='data_import'
            task: Task dict to update with progress
        """
        import time

        # Extract config
        match_config = definition.get('match_config', {})
        source_database = match_config.get('source_database')
        rel_type = definition.get('relationship_type')
        source_label = definition.get('source_label')
        target_label = definition.get('target_label')

        if not all([source_database, rel_type, source_label, target_label]):
            raise ValueError("Missing required data_import configuration")

        task['status_message'] = f'Importing {match_config.get("triple_count", "?")} triples from {source_database}...'

        # Use commit_triple_import with empty hash (no preview validation needed for saved links)
        result = self.commit_triple_import(
            source_database=source_database,
            rel_type=rel_type,
            source_label=source_label,
            target_label=target_label,
            preview_hash=''  # Skip hash validation for saved link execution
        )

        if result['status'] == 'success':
            task['relationships_created'] = result['triples_imported']
            task['status_message'] = f'Imported {result["triples_imported"]} triples in {result["duration_seconds"]}s using {result["method"]}'
        else:
            raise Exception(result.get('error', 'Unknown error during import'))

    def create_validated_relationships(self, link_id: str, matches: List[Dict[str, Any]]) -> int:
        """
        Create relationships for human-validated matches from CSV import.

        Args:
            link_id: The link definition ID
            matches: List of validated matches with source_id, target_id, match_score

        Returns:
            Number of relationships created
        """
        try:
            link = self.get_link(link_id)
            if not link:
                raise ValueError(f"Link {link_id} not found")

            rel_type = link.get('relationship_type')
            rel_props = link.get('relationship_props', {})

            relationships_created = 0

            with self.neo4j_client.driver.session(database=self.neo4j_client.database) as session:
                for match in matches:
                    source_id = match.get('source_id')
                    target_id = match.get('target_id')
                    match_score = match.get('match_score', '')

                    if not source_id or not target_id:
                        continue

                    # Build relationship properties
                    props = dict(rel_props)
                    props['__source__'] = 'csv_validation'
                    props['__validated_at__'] = datetime.now().isoformat()
                    if match_score:
                        props['__match_score__'] = match_score

                    # Create relationship using Neo4j element IDs
                    query = f"""
                    MATCH (s), (t)
                    WHERE elementId(s) = $source_id AND elementId(t) = $target_id
                    MERGE (s)-[r:`{rel_type}`]->(t)
                    SET r += $props
                    RETURN count(r) as created
                    """

                    result = session.run(query, source_id=source_id, target_id=target_id, props=props)
                    record = result.single()
                    if record and record['created'] > 0:
                        relationships_created += 1

            logger.info(f"Created {relationships_created} validated relationships for link {link_id}")
            return relationships_created

        except Exception as e:
            logger.exception(f"Failed to create validated relationships for link {link_id}")
            raise

    def enrich_relationships_with_task(
        self,
        link_id: str,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        batch_size: int = 1000
    ) -> str:
        """
        Enrich relationship properties from source database as background task.

        Updates properties on existing relationships in primary without creating
        new nodes or relationships. Only touches relationships that already exist.

        Returns:
            Task ID for polling progress
        """
        import hashlib
        from flask import current_app

        now = time.time()
        tid_src = f"enrich_rels|{link_id}|{source_database}|{now}"
        task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]

        # Create task record
        task = {
            'id': task_id,
            'type': 'enrich_relationships',
            'status': 'running',
            'link_def_id': link_id,
            'source_database': source_database,
            'source_label': source_label,
            'target_label': target_label,
            'rel_type': rel_type,
            'started': now,
            'ended': None,
            'total': 0,
            'processed': 0,
            'progress': 0.0,
            'error': None,
            'status_message': 'Initializing enrichment...',
            'relationships_enriched': 0,
        }
        current_app.extensions['scidk'].setdefault('tasks', {})[task_id] = task

        # Run in background thread
        import threading
        app = current_app._get_current_object()

        def _worker():
            with app.app_context():
                try:
                    self._enrich_relationships_with_progress(
                        task=task,
                        source_label=source_label,
                        target_label=target_label,
                        rel_type=rel_type,
                        source_database=source_database,
                        source_uid_property=source_uid_property,
                        target_uid_property=target_uid_property,
                        batch_size=batch_size
                    )
                    task['ended'] = time.time()
                    task['status'] = 'completed'
                    task['progress'] = 1.0
                    task['status_message'] = f'Enriched {task["relationships_enriched"]} relationships.'
                except Exception as e:
                    logger.exception("Relationship enrichment failed")
                    task['ended'] = time.time()
                    task['status'] = 'error'
                    task['error'] = str(e)

        threading.Thread(target=_worker, daemon=True).start()
        return task_id

    def _enrich_relationships_with_progress(
        self,
        task: Dict[str, Any],
        source_label: str,
        target_label: str,
        rel_type: str,
        source_database: str,
        source_uid_property: str,
        target_uid_property: str,
        batch_size: int = 1000
    ):
        """Execute relationship enrichment with live progress updates to task dict."""
        from .neo4j_client import get_neo4j_client, get_neo4j_client_for_profile

        # Validate relationship type
        rel_type = self._validate_relationship_type(rel_type)

        # Get source database client
        source_client = get_neo4j_client_for_profile(source_database)
        if not source_client:
            raise ValueError(f'Source database "{source_database}" not found')

        # Get primary database client
        primary_client = get_neo4j_client()
        if not primary_client:
            raise ValueError('Primary database not configured')

        try:
            # First, count total relationships in source
            count_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
            RETURN count(r) as total
            """
            count_results = source_client.execute_read(count_query)
            total_count = count_results[0]['total'] if count_results else 0

            task['total'] = total_count
            task['status_message'] = f'Enriching {total_count:,} relationships...'

            if total_count == 0:
                task['status_message'] = 'No relationships found in source database'
                return

            # Use keyset pagination to fetch relationships with properties from source
            last_source_uid = None
            last_target_uid = None
            relationships_enriched = 0

            while True:
                # Build keyset pagination query
                if last_source_uid is None:
                    # First batch
                    data_query = f"""
                    MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                    RETURN a.{source_uid_property} as source_uid,
                           properties(r) as rel_props,
                           b.{target_uid_property} as target_uid
                    ORDER BY source_uid, target_uid
                    LIMIT {batch_size}
                    """
                else:
                    # Subsequent batches using keyset
                    data_query = f"""
                    MATCH (a:{source_label})-[r:{rel_type}]->(b:{target_label})
                    WHERE (a.{source_uid_property} > $last_source_uid)
                       OR (a.{source_uid_property} = $last_source_uid AND b.{target_uid_property} > $last_target_uid)
                    RETURN a.{source_uid_property} as source_uid,
                           properties(r) as rel_props,
                           b.{target_uid_property} as target_uid
                    ORDER BY source_uid, target_uid
                    LIMIT {batch_size}
                    """

                # Fetch batch from source
                if last_source_uid is None:
                    batch_results = source_client.execute_read(data_query)
                else:
                    batch_results = source_client.execute_read(
                        data_query,
                        {'last_source_uid': last_source_uid, 'last_target_uid': last_target_uid}
                    )

                if not batch_results:
                    break  # No more relationships

                # Prepare batch data for primary update
                rows = []
                for record in batch_results:
                    rows.append({
                        'source_uid': record['source_uid'],
                        'target_uid': record['target_uid'],
                        'rel_props': dict(record['rel_props'])
                    })

                # Update relationships in primary (MATCH only - never creates)
                update_query = f"""
                UNWIND $rows AS row
                MATCH (a:{source_label} {{{source_uid_property}: row.source_uid}})-[r:{rel_type}]->(b:{target_label} {{{target_uid_property}: row.target_uid}})
                SET r += row.rel_props
                RETURN count(r) as updated
                """
                update_results = primary_client.execute_write(update_query, {'rows': rows})
                updated_count = update_results[0]['updated'] if update_results else 0

                relationships_enriched += updated_count
                task['relationships_enriched'] = relationships_enriched
                task['processed'] += len(rows)
                task['progress'] = min(task['processed'] / total_count, 1.0) if total_count > 0 else 1.0
                task['status_message'] = f'Enriched {relationships_enriched:,} / {total_count:,} relationships...'

                # Update keyset for next batch
                last_record = batch_results[-1]
                last_source_uid = last_record['source_uid']
                last_target_uid = last_record['target_uid']

                # Check if we've processed fewer than batch_size (means we're done)
                if len(batch_results) < batch_size:
                    break

        finally:
            source_client.close()


def get_neo4j_client():
    """Get or create Neo4j client instance."""
    from .neo4j_client import get_neo4j_params, Neo4jClient
    uri, user, pwd, database, auth_mode = get_neo4j_params()

    if not uri:
        return None

    client = Neo4jClient(uri, user, pwd, database, auth_mode)
    client.connect()
    return client
