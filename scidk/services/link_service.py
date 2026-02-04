"""
Link service for managing relationship creation workflows.

This service provides operations for:
- CRUD operations on link definitions (stored in SQLite)
- Preview and execution of link jobs
- Source adapters (Graph, CSV, API)
- Target adapters (Graph, Label)
- Matching strategies (Property, ID, Custom Cypher)
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


class LinkService:
    """Service for managing link definitions and executing relationship creation workflows."""

    def __init__(self, app):
        self.app = app

    def _get_conn(self):
        """Get a database connection."""
        from ..core import path_index_sqlite as pix
        return pix.connect()

    def list_link_definitions(self) -> List[Dict[str, Any]]:
        """
        Get all link definitions from SQLite.

        Returns:
            List of link definition dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, source_type, source_config, target_type, target_config,
                       match_strategy, match_config, relationship_type, relationship_props,
                       created_at, updated_at
                FROM link_definitions
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()

            definitions = []
            for row in rows:
                (id, name, source_type, source_config, target_type, target_config,
                 match_strategy, match_config, rel_type, rel_props, created_at, updated_at) = row
                definitions.append({
                    'id': id,
                    'name': name,
                    'source_type': source_type,
                    'source_config': json.loads(source_config) if source_config else {},
                    'target_type': target_type,
                    'target_config': json.loads(target_config) if target_config else {},
                    'match_strategy': match_strategy,
                    'match_config': json.loads(match_config) if match_config else {},
                    'relationship_type': rel_type,
                    'relationship_props': json.loads(rel_props) if rel_props else {},
                    'created_at': created_at,
                    'updated_at': updated_at
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
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, source_type, source_config, target_type, target_config,
                   match_strategy, match_config, relationship_type, relationship_props,
                   created_at, updated_at
            FROM link_definitions
            WHERE id = ?
            """,
            (link_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        (id, name, source_type, source_config, target_type, target_config,
         match_strategy, match_config, rel_type, rel_props, created_at, updated_at) = row
        return {
            'id': id,
            'name': name,
            'source_type': source_type,
            'source_config': json.loads(source_config) if source_config else {},
            'target_type': target_type,
            'target_config': json.loads(target_config) if target_config else {},
            'match_strategy': match_strategy,
            'match_config': json.loads(match_config) if match_config else {},
            'relationship_type': rel_type,
            'relationship_props': json.loads(rel_props) if rel_props else {},
            'created_at': created_at,
            'updated_at': updated_at
        }

    def save_link_definition(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a link definition.

        Args:
            definition: Dict with required keys: name, source_type, target_type, match_strategy, relationship_type

        Returns:
            Updated link definition
        """
        link_id = definition.get('id', str(uuid.uuid4()))
        name = definition.get('name', '').strip()
        if not name:
            raise ValueError("Link name is required")

        source_type = definition.get('source_type', '').strip()
        if source_type not in ['graph', 'csv', 'api']:
            raise ValueError("source_type must be 'graph', 'csv', or 'api'")

        target_type = definition.get('target_type', '').strip()
        if target_type not in ['graph', 'label']:
            raise ValueError("target_type must be 'graph' or 'label'")

        match_strategy = definition.get('match_strategy', '').strip()
        if match_strategy not in ['property', 'id', 'cypher']:
            raise ValueError("match_strategy must be 'property', 'id', or 'cypher'")

        relationship_type = definition.get('relationship_type', '').strip()
        if not relationship_type:
            raise ValueError("relationship_type is required")

        source_config = json.dumps(definition.get('source_config', {}))
        target_config = json.dumps(definition.get('target_config', {}))
        match_config = json.dumps(definition.get('match_config', {}))
        relationship_props = json.dumps(definition.get('relationship_props', {}))

        now = time.time()

        # Check if link exists
        existing = self.get_link_definition(link_id)

        cursor = conn.cursor()
        if existing:
            # Update
            cursor.execute(
                """
                UPDATE link_definitions
                SET name = ?, source_type = ?, source_config = ?, target_type = ?,
                    target_config = ?, match_strategy = ?, match_config = ?,
                    relationship_type = ?, relationship_props = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, source_type, source_config, target_type, target_config,
                 match_strategy, match_config, relationship_type, relationship_props, now, link_id)
            )
            created_at = existing['created_at']
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO link_definitions
                (id, name, source_type, source_config, target_type, target_config,
                 match_strategy, match_config, relationship_type, relationship_props,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (link_id, name, source_type, source_config, target_type, target_config,
                 match_strategy, match_config, relationship_type, relationship_props, now, now)
            )
            created_at = now

        conn.commit()

        return {
            'id': link_id,
            'name': name,
            'source_type': source_type,
            'source_config': json.loads(source_config),
            'target_type': target_type,
            'target_config': json.loads(target_config),
            'match_strategy': match_strategy,
            'match_config': json.loads(match_config),
            'relationship_type': relationship_type,
            'relationship_props': json.loads(relationship_props),
            'created_at': created_at,
            'updated_at': now
        }

    def delete_link_definition(self, link_id: str) -> bool:
        """
        Delete a link definition.

        Args:
            link_id: Link definition ID

        Returns:
            True if deleted, False if not found
        """
        cursor = conn.cursor()
        cursor.execute("DELETE FROM link_definitions WHERE id = ?", (link_id,))
        conn.commit()
        return cursor.rowcount > 0

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

    def execute_link_job(self, link_def_id: str) -> str:
        """
        Start background job to create relationships.

        Args:
            link_def_id: Link definition ID

        Returns:
            Job ID
        """
        definition = self.get_link_definition(link_def_id)
        if not definition:
            raise ValueError(f"Link definition '{link_def_id}' not found")

        job_id = str(uuid.uuid4())
        now = time.time()

        # Create job record
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

        # Execute job (synchronously for MVP, could be async later)
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

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status and progress.

        Args:
            job_id: Job ID

        Returns:
            Job status dict or None if not found
        """
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

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        List recent jobs.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job status dicts
        """
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

    # --- Internal helpers ---

    def _fetch_source_data(self, definition: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch data from source based on source_type."""
        source_type = definition.get('source_type')
        source_config = definition.get('source_config', {})

        if source_type == 'graph':
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
            relationship_type = definition.get('relationship_type', '')
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


def get_neo4j_client():
    """Get or create Neo4j client instance."""
    from .neo4j_client import get_neo4j_params, Neo4jClient
    uri, user, pwd, database, auth_mode = get_neo4j_params()

    if not uri:
        return None

    client = Neo4jClient(uri, user, pwd, database, auth_mode)
    client.connect()
    return client
