"""
Label service for managing graph schema definitions.

This service provides operations for:
- CRUD operations on label definitions (stored in SQLite)
- Push/pull schema synchronization with Neo4j
- Schema introspection and validation
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional
import json
import time
import sqlite3


class LabelService:
    """Service for managing label definitions and Neo4j schema sync."""

    def __init__(self, app):
        self.app = app

    def _get_conn(self):
        """Get a database connection."""
        from ..core import path_index_sqlite as pix
        return pix.connect()

    def list_labels(self) -> List[Dict[str, Any]]:
        """
        Get all label definitions from SQLite.

        Returns:
            List of label definition dicts with keys: name, properties, relationships, created_at, updated_at
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, properties, relationships, created_at, updated_at
                FROM label_definitions
                ORDER BY name
                """
            )
            rows = cursor.fetchall()

            labels = []
            for row in rows:
                name, props_json, rels_json, created_at, updated_at = row
                labels.append({
                    'name': name,
                    'properties': json.loads(props_json) if props_json else [],
                    'relationships': json.loads(rels_json) if rels_json else [],
                    'created_at': created_at,
                    'updated_at': updated_at
                })
            return labels
        finally:
            conn.close()

    def get_label(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific label definition by name.

        Args:
            name: Label name

        Returns:
            Label definition dict or None if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, properties, relationships, created_at, updated_at
                FROM label_definitions
                WHERE name = ?
                """,
                (name,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            name, props_json, rels_json, created_at, updated_at = row

            # Get outgoing relationships (defined on this label)
            relationships = json.loads(rels_json) if rels_json else []

            # Find incoming relationships (from other labels to this label)
            cursor.execute(
                """
                SELECT name, relationships
                FROM label_definitions
                WHERE name != ?
                """,
                (name,)
            )

            incoming_relationships = []
            for other_name, other_rels_json in cursor.fetchall():
                if other_rels_json:
                    other_rels = json.loads(other_rels_json)
                    for rel in other_rels:
                        if rel.get('target_label') == name:
                            incoming_relationships.append({
                                'type': rel['type'],
                                'source_label': other_name,
                                'properties': rel.get('properties', [])
                            })

            return {
                'name': name,
                'properties': json.loads(props_json) if props_json else [],
                'relationships': relationships,
                'incoming_relationships': incoming_relationships,
                'created_at': created_at,
                'updated_at': updated_at
            }
        finally:
            conn.close()

    def save_label(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a label definition.

        Args:
            definition: Dict with keys: name, properties (list), relationships (list)

        Returns:
            Updated label definition
        """
        name = definition.get('name', '').strip()
        if not name:
            raise ValueError("Label name is required")

        properties = definition.get('properties', [])
        relationships = definition.get('relationships', [])

        # Validate property structure
        for prop in properties:
            if not isinstance(prop, dict) or 'name' not in prop or 'type' not in prop:
                raise ValueError(f"Invalid property structure: {prop}")

        # Validate relationship structure
        for rel in relationships:
            if not isinstance(rel, dict) or 'type' not in rel or 'target_label' not in rel:
                raise ValueError(f"Invalid relationship structure: {rel}")

        props_json = json.dumps(properties)
        rels_json = json.dumps(relationships)
        now = time.time()

        # Check if label exists
        existing = self.get_label(name)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if existing:
                # Update
                cursor.execute(
                    """
                    UPDATE label_definitions
                    SET properties = ?, relationships = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (props_json, rels_json, now, name)
                )
                created_at = existing['created_at']
            else:
                # Insert
                cursor.execute(
                    """
                    INSERT INTO label_definitions (name, properties, relationships, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, props_json, rels_json, now, now)
                )
                created_at = now

            conn.commit()

            return {
                'name': name,
                'properties': properties,
                'relationships': relationships,
                'created_at': created_at,
                'updated_at': now
            }
        finally:
            conn.close()

    def delete_label(self, name: str) -> bool:
        """
        Delete a label definition.

        Args:
            name: Label name

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM label_definitions WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def push_to_neo4j(self, name: str) -> Dict[str, Any]:
        """
        Push label definition to Neo4j (create constraints/indexes).

        Args:
            name: Label name

        Returns:
            Dict with status and details
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Create constraints for required properties
            constraints_created = []
            indexes_created = []

            for prop in label_def.get('properties', []):
                prop_name = prop.get('name')
                required = prop.get('required', False)

                if required and prop_name:
                    # Create unique constraint
                    try:
                        constraint_name = f"constraint_{name}_{prop_name}"
                        query = f"""
                        CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
                        FOR (n:{name})
                        REQUIRE n.{prop_name} IS UNIQUE
                        """
                        neo4j_client.execute_write(query)
                        constraints_created.append(prop_name)
                    except Exception as e:
                        # Constraint might already exist, continue
                        pass

            return {
                'status': 'success',
                'label': name,
                'constraints_created': constraints_created,
                'indexes_created': indexes_created
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def pull_label_properties_from_neo4j(self, name: str) -> Dict[str, Any]:
        """
        Pull properties for a specific label from Neo4j and merge with existing definition.

        Args:
            name: Label name

        Returns:
            Dict with status and updated label
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Query for properties of this specific label
            query = """
            CALL db.schema.nodeTypeProperties()
            YIELD nodeType, propertyName, propertyTypes
            WHERE nodeType = $nodeType
            RETURN propertyName, propertyTypes
            """

            results = neo4j_client.execute_read(query, {'nodeType': f':{name}'})

            # Get existing property names to avoid duplicates
            existing_props = {p['name'] for p in label_def.get('properties', [])}

            # Map properties from Neo4j
            new_properties = []
            for record in results:
                prop_name = record.get('propertyName')
                prop_types = record.get('propertyTypes', [])

                # Skip if already exists
                if prop_name in existing_props:
                    continue

                # Map Neo4j types to our property types
                prop_type = 'string'
                if prop_types:
                    first_type = prop_types[0].lower()
                    if 'int' in first_type or 'long' in first_type:
                        prop_type = 'number'
                    elif 'bool' in first_type:
                        prop_type = 'boolean'
                    elif 'date' in first_type:
                        prop_type = 'date'
                    elif 'datetime' in first_type or 'localdatetime' in first_type:
                        prop_type = 'datetime'

                new_properties.append({
                    'name': prop_name,
                    'type': prop_type,
                    'required': False  # Can't determine from schema introspection
                })

            # Merge with existing properties
            all_properties = label_def.get('properties', []) + new_properties

            # Update label
            updated_label = self.save_label({
                'name': name,
                'properties': all_properties,
                'relationships': label_def.get('relationships', [])
            })

            return {
                'status': 'success',
                'label': updated_label,
                'new_properties_count': len(new_properties)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def pull_from_neo4j(self) -> Dict[str, Any]:
        """
        Pull label schema from Neo4j and import as label definitions.

        Returns:
            Dict with status and imported labels
        """
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Query for node labels and their properties
            query = """
            CALL db.schema.nodeTypeProperties()
            YIELD nodeType, propertyName, propertyTypes
            RETURN nodeType, propertyName, propertyTypes
            """

            results = neo4j_client.execute_read(query)

            # Group by label
            labels_map = {}
            for record in results:
                node_type = record.get('nodeType')
                if not node_type or not node_type.startswith(':'):
                    continue

                # Remove leading ':' and any backticks
                label_name = node_type[1:].strip('`')
                prop_name = record.get('propertyName')
                prop_types = record.get('propertyTypes', [])

                if label_name not in labels_map:
                    labels_map[label_name] = []

                # Map Neo4j types to our property types
                prop_type = 'string'
                if prop_types:
                    first_type = prop_types[0].lower()
                    if 'int' in first_type or 'long' in first_type:
                        prop_type = 'number'
                    elif 'bool' in first_type:
                        prop_type = 'boolean'
                    elif 'date' in first_type:
                        prop_type = 'date'
                    elif 'datetime' in first_type or 'localdatetime' in first_type:
                        prop_type = 'datetime'

                labels_map[label_name].append({
                    'name': prop_name,
                    'type': prop_type,
                    'required': False  # Can't determine from schema introspection
                })

            # Save imported labels
            imported = []
            for label_name, properties in labels_map.items():
                try:
                    self.save_label({
                        'name': label_name,
                        'properties': properties,
                        'relationships': []
                    })
                    imported.append(label_name)
                except Exception as e:
                    # Continue with other labels
                    pass

            return {
                'status': 'success',
                'imported_labels': imported,
                'count': len(imported)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def get_neo4j_schema(self) -> Dict[str, Any]:
        """
        Get current Neo4j schema information.

        Returns:
            Dict with schema details
        """
        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                return {
                    'status': 'error',
                    'error': 'Neo4j client not configured'
                }

            # Get labels
            labels_query = "CALL db.labels() YIELD label RETURN label"
            labels_results = neo4j_client.execute_read(labels_query)
            labels = [r.get('label') for r in labels_results]

            # Get relationship types
            rels_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
            rels_results = neo4j_client.execute_read(rels_query)
            rel_types = [r.get('relationshipType') for r in rels_results]

            # Get constraints
            constraints_query = "SHOW CONSTRAINTS YIELD name, type RETURN name, type"
            try:
                constraints_results = neo4j_client.execute_read(constraints_query)
                constraints = [{'name': r.get('name'), 'type': r.get('type')} for r in constraints_results]
            except:
                constraints = []

            return {
                'status': 'success',
                'labels': labels,
                'relationship_types': rel_types,
                'constraints': constraints
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
