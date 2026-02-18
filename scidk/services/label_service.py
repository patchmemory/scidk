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

    # Class-level transfer tracking
    _active_transfers = {}  # {label_name: {'status': 'running', 'cancelled': False}}

    def __init__(self, app):
        self.app = app

    def _get_conn(self):
        """Get a database connection."""
        from ..core import path_index_sqlite as pix
        return pix.connect()

    def get_transfer_status(self, label_name: str) -> Optional[Dict[str, Any]]:
        """Get the current transfer status for a label."""
        return self._active_transfers.get(label_name)

    def cancel_transfer(self, label_name: str) -> bool:
        """Cancel an active transfer for a label."""
        if label_name in self._active_transfers:
            self._active_transfers[label_name]['cancelled'] = True
            return True
        return False

    def _is_transfer_cancelled(self, label_name: str) -> bool:
        """Check if transfer has been cancelled."""
        transfer = self._active_transfers.get(label_name)
        return transfer and transfer.get('cancelled', False)

    def list_labels(self) -> List[Dict[str, Any]]:
        """
        Get all label definitions from SQLite.

        Returns:
            List of label definition dicts with keys: name, properties, relationships, created_at, updated_at,
            source_type, source_id, sync_config
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, properties, relationships, created_at, updated_at,
                       source_type, source_id, sync_config, neo4j_source_profile, matching_key
                FROM label_definitions
                ORDER BY name
                """
            )
            rows = cursor.fetchall()

            labels = []
            for row in rows:
                name, props_json, rels_json, created_at, updated_at, source_type, source_id, sync_config_json, neo4j_source_profile, matching_key = row
                labels.append({
                    'name': name,
                    'properties': json.loads(props_json) if props_json else [],
                    'relationships': json.loads(rels_json) if rels_json else [],
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'source_type': source_type or 'manual',
                    'source_id': source_id,
                    'sync_config': json.loads(sync_config_json) if sync_config_json else {},
                    'neo4j_source_profile': neo4j_source_profile,
                    'matching_key': matching_key
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
                SELECT name, properties, relationships, created_at, updated_at,
                       source_type, source_id, sync_config, neo4j_source_profile, matching_key
                FROM label_definitions
                WHERE name = ?
                """,
                (name,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            name, props_json, rels_json, created_at, updated_at, source_type, source_id, sync_config_json, neo4j_source_profile, matching_key = row

            # Get outgoing relationships (defined on this label)
            relationships = json.loads(rels_json) if rels_json else []

            # Find incoming relationships (from all labels to this label)
            # Include self-referential relationships (e.g., Sample -> Sample)
            cursor.execute(
                """
                SELECT name, relationships
                FROM label_definitions
                """,
                ()
            )

            incoming_relationships = []
            for other_name, other_rels_json in cursor.fetchall():
                if other_rels_json:
                    other_rels = json.loads(other_rels_json)
                    for rel in other_rels:
                        # Include if target is this label (including self-referential)
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
                'updated_at': updated_at,
                'source_type': source_type or 'manual',
                'source_id': source_id,
                'sync_config': json.loads(sync_config_json) if sync_config_json else {},
                'neo4j_source_profile': neo4j_source_profile,
                'matching_key': matching_key
            }
        finally:
            conn.close()

    def save_label(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a label definition.

        Args:
            definition: Dict with keys: name, properties (list), relationships (list),
                       source_type (optional), source_id (optional), sync_config (optional)

        Returns:
            Updated label definition
        """
        name = definition.get('name', '').strip()
        if not name:
            raise ValueError("Label name is required")

        properties = definition.get('properties', [])
        relationships = definition.get('relationships', [])
        source_type = definition.get('source_type', 'manual')
        source_id = definition.get('source_id')
        sync_config = definition.get('sync_config', {})
        neo4j_source_profile = definition.get('neo4j_source_profile')
        matching_key = definition.get('matching_key')

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
        sync_config_json = json.dumps(sync_config)
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
                    SET properties = ?, relationships = ?, source_type = ?, source_id = ?,
                        sync_config = ?, neo4j_source_profile = ?, matching_key = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (props_json, rels_json, source_type, source_id, sync_config_json, neo4j_source_profile, matching_key, now, name)
                )
                created_at = existing['created_at']
            else:
                # Insert
                cursor.execute(
                    """
                    INSERT INTO label_definitions (name, properties, relationships, source_type,
                                                   source_id, sync_config, neo4j_source_profile, matching_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, props_json, rels_json, source_type, source_id, sync_config_json, neo4j_source_profile, matching_key, now, now)
                )
                created_at = now

            conn.commit()

            return {
                'name': name,
                'properties': properties,
                'relationships': relationships,
                'source_type': source_type,
                'source_id': source_id,
                'sync_config': sync_config,
                'created_at': created_at,
                'updated_at': now
            }
        finally:
            conn.close()

    def get_matching_key(self, label_name: str) -> str:
        """
        Get the matching key for a label to use during node matching/merging.

        Resolution order:
        1. User-configured matching_key (if set)
        2. First required property
        3. Fallback to 'id'

        Args:
            label_name: Name of the label

        Returns:
            Property name to use for matching
        """
        label_def = self.get_label(label_name)
        if not label_def:
            # Fallback to 'id' if label doesn't exist
            return 'id'

        # Check if user configured a matching key
        if label_def.get('matching_key'):
            return label_def['matching_key']

        # Find first required property
        for prop in label_def.get('properties', []):
            if prop.get('required'):
                return prop.get('name')

        # Fallback to 'id'
        return 'id'

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
        Pull properties and relationships for a specific label from Neo4j and merge with existing definition.

        Uses the 'labels_source' role connection if configured, otherwise falls back to 'primary'.

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
            # Try labels_source role first, falls back to primary automatically
            neo4j_client = get_neo4j_client(role='labels_source')

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Query for properties of this specific label
            props_query = """
            CALL db.schema.nodeTypeProperties()
            YIELD nodeType, propertyName, propertyTypes
            WHERE nodeType = $nodeType
            RETURN propertyName, propertyTypes
            """

            props_results = neo4j_client.execute_read(props_query, {'nodeType': f':{name}'})

            # Get existing property names to avoid duplicates
            existing_props = {p['name'] for p in label_def.get('properties', [])}

            # Map properties from Neo4j
            new_properties = []
            for record in props_results:
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

            # Query for relationships originating from this label
            # Sample actual relationships from the graph
            rels_query = """
            MATCH (source)-[rel]->(target)
            WHERE $labelName IN labels(source)
            WITH DISTINCT type(rel) AS relType, [label IN labels(target) | label][0] AS targetLabel
            RETURN relType, targetLabel
            """

            rels_results = neo4j_client.execute_read(rels_query, {'labelName': name})

            # Get existing relationships to avoid duplicates (by type + target combination)
            existing_rels = {(r['type'], r['target_label']) for r in label_def.get('relationships', [])}

            # Map relationships from Neo4j
            new_relationships = []
            for record in rels_results:
                rel_type = record.get('relType')
                target_label = record.get('targetLabel')

                # Skip if missing or already exists
                if not rel_type or not target_label:
                    continue

                # Clean label (strip backticks)
                target_label = target_label.strip('`')

                # Skip if already exists
                if (rel_type, target_label) in existing_rels:
                    continue

                new_relationships.append({
                    'type': rel_type,
                    'target_label': target_label,
                    'properties': []
                })

            # Merge with existing properties and relationships
            all_properties = label_def.get('properties', []) + new_properties
            all_relationships = label_def.get('relationships', []) + new_relationships

            # Update label
            updated_label = self.save_label({
                'name': name,
                'properties': all_properties,
                'relationships': all_relationships
            })

            return {
                'status': 'success',
                'label': updated_label,
                'new_properties_count': len(new_properties),
                'new_relationships_count': len(new_relationships)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def pull_from_neo4j(self, neo4j_client=None, source_profile_name=None) -> Dict[str, Any]:
        """
        Pull label schema (properties and relationships) from Neo4j and import as label definitions.

        Args:
            neo4j_client: Optional Neo4jClient instance to use. If not provided, uses the 'labels_source'
                         role connection if configured, otherwise falls back to 'primary'.
            source_profile_name: Optional name of the Neo4j profile being pulled from. Will be stored
                                in label metadata for source-aware instance operations.

        Returns:
            Dict with status and imported labels
        """
        try:
            if neo4j_client is None:
                from .neo4j_client import get_neo4j_client
                # Try labels_source role first, falls back to primary automatically
                neo4j_client = get_neo4j_client(role='labels_source')

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Query for node labels and their properties
            props_query = """
            CALL db.schema.nodeTypeProperties()
            YIELD nodeType, propertyName, propertyTypes
            RETURN nodeType, propertyName, propertyTypes
            """

            props_results = neo4j_client.execute_read(props_query)

            # Group properties by label
            labels_map = {}
            for record in props_results:
                node_type = record.get('nodeType')
                if not node_type or not node_type.startswith(':'):
                    continue

                # Remove leading ':' and any backticks
                label_name = node_type[1:].strip('`')
                prop_name = record.get('propertyName')
                prop_types = record.get('propertyTypes', [])

                if label_name not in labels_map:
                    labels_map[label_name] = {'properties': [], 'relationships': []}

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

                labels_map[label_name]['properties'].append({
                    'name': prop_name,
                    'type': prop_type,
                    'required': False  # Can't determine from schema introspection
                })

            # Query for all relationships by sampling actual relationships from the graph
            rels_query = """
            MATCH (source)-[rel]->(target)
            WITH DISTINCT
                [label IN labels(source) | label][0] AS sourceLabel,
                type(rel) AS relType,
                [label IN labels(target) | label][0] AS targetLabel
            RETURN sourceLabel, relType, targetLabel
            """

            rels_results = neo4j_client.execute_read(rels_query)

            # Group relationships by source label
            for record in rels_results:
                source_label = record.get('sourceLabel')
                rel_type = record.get('relType')
                target_label = record.get('targetLabel')

                # Skip if any field is missing
                if not source_label or not rel_type or not target_label:
                    continue

                # Clean labels (strip backticks)
                source_label = source_label.strip('`')
                target_label = target_label.strip('`')

                # Ensure source label exists in map
                if source_label not in labels_map:
                    labels_map[source_label] = {'properties': [], 'relationships': []}

                # Add relationship (deduplicate by type+target combination)
                rel_key = (rel_type, target_label)
                existing_rels = {(r['type'], r['target_label']) for r in labels_map[source_label]['relationships']}

                if rel_key not in existing_rels:
                    labels_map[source_label]['relationships'].append({
                        'type': rel_type,
                        'target_label': target_label,
                        'properties': []
                    })

            # Save imported labels with properties and relationships
            imported = []
            for label_name, schema in labels_map.items():
                try:
                    label_def = {
                        'name': label_name,
                        'properties': schema['properties'],
                        'relationships': schema['relationships']
                    }
                    # Store source profile if provided
                    if source_profile_name:
                        label_def['neo4j_source_profile'] = source_profile_name
                    self.save_label(label_def)
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

    def get_label_instances(self, name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get instances of a label from Neo4j.

        If the label has a source profile configured, instances will be pulled from that profile's
        connection. Otherwise, uses the default (primary) connection.

        Args:
            name: Label name
            limit: Maximum number of instances to return
            offset: Pagination offset

        Returns:
            Dict with status, instances list, and pagination info
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        try:
            from .neo4j_client import get_neo4j_client

            # Check if label has a source profile - if so, use that connection
            source_profile = label_def.get('neo4j_source_profile')
            neo4j_client = None
            created_client = False

            if source_profile:
                # Load and use the source profile connection
                from scidk.core.settings import get_setting
                import json

                profile_key = f'neo4j_profile_{source_profile.replace(" ", "_")}'
                profile_json = get_setting(profile_key)

                if profile_json:
                    profile = json.loads(profile_json)
                    password_key = f'neo4j_profile_password_{source_profile.replace(" ", "_")}'
                    password = get_setting(password_key)

                    from .neo4j_client import Neo4jClient
                    neo4j_client = Neo4jClient(
                        uri=profile.get('uri'),
                        user=profile.get('user'),
                        password=password,
                        database=profile.get('database', 'neo4j'),
                        auth_mode='basic'
                    )
                    neo4j_client.connect()
                    created_client = True

            # Fall back to default connection if no source profile or profile not found
            if not neo4j_client:
                neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            try:
                # Query for instances of this label
                query = f"""
                MATCH (n:{name})
                RETURN elementId(n) as id, properties(n) as properties
                SKIP $offset
                LIMIT $limit
                """

                results = neo4j_client.execute_read(query, {'offset': offset, 'limit': limit})

                instances = []
                for r in results:
                    instances.append({
                        'id': r.get('id'),
                        'properties': r.get('properties', {})
                    })

                # Get total count
                count_query = f"MATCH (n:{name}) RETURN count(n) as total"
                count_results = neo4j_client.execute_read(count_query)
                total = count_results[0].get('total', 0) if count_results else 0

                return {
                    'status': 'success',
                    'instances': instances,
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'source_profile': source_profile  # Include source info
                }
            finally:
                # Clean up temporary client if we created one
                if created_client and neo4j_client:
                    neo4j_client.close()
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def get_label_instance_count(self, name: str) -> Dict[str, Any]:
        """
        Get count of instances for a label from Neo4j.

        If the label has a source profile configured, count will be from that profile's
        connection. Otherwise, uses the default (primary) connection.

        Args:
            name: Label name

        Returns:
            Dict with status and count
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        try:
            from .neo4j_client import get_neo4j_client

            # Check if label has a source profile - if so, use that connection
            source_profile = label_def.get('neo4j_source_profile')
            neo4j_client = None
            created_client = False

            if source_profile:
                # Load and use the source profile connection
                from scidk.core.settings import get_setting
                import json

                profile_key = f'neo4j_profile_{source_profile.replace(" ", "_")}'
                profile_json = get_setting(profile_key)

                if profile_json:
                    profile = json.loads(profile_json)
                    password_key = f'neo4j_profile_password_{source_profile.replace(" ", "_")}'
                    password = get_setting(password_key)

                    from .neo4j_client import Neo4jClient
                    neo4j_client = Neo4jClient(
                        uri=profile.get('uri'),
                        user=profile.get('user'),
                        password=password,
                        database=profile.get('database', 'neo4j'),
                        auth_mode='basic'
                    )
                    neo4j_client.connect()
                    created_client = True

            # Fall back to default connection if no source profile
            if not neo4j_client:
                neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            try:
                # Query for count
                query = f"MATCH (n:{name}) RETURN count(n) as count"
                results = neo4j_client.execute_read(query)
                count = results[0].get('count', 0) if results else 0

                return {
                    'status': 'success',
                    'count': count,
                    'source_profile': source_profile  # Include source info
                }
            finally:
                # Clean up temporary client if we created one
                if created_client and neo4j_client:
                    neo4j_client.close()
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def update_label_instance(self, name: str, instance_id: str, property_name: str, property_value: Any) -> Dict[str, Any]:
        """
        Update a single property of a label instance in Neo4j.

        Args:
            name: Label name
            instance_id: Neo4j element ID
            property_name: Property to update
            property_value: New value

        Returns:
            Dict with status and updated instance
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        # Verify property exists in label definition
        prop_names = [p.get('name') for p in label_def.get('properties', [])]
        if property_name not in prop_names:
            raise ValueError(f"Property '{property_name}' not defined for label '{name}'")

        try:
            from .neo4j_client import get_neo4j_client

            # Check if label has a source profile - if so, use that connection
            source_profile = label_def.get('neo4j_source_profile')
            neo4j_client = None
            created_client = False

            if source_profile:
                # Load and use the source profile connection
                from scidk.core.settings import get_setting
                import json

                profile_key = f'neo4j_profile_{source_profile.replace(" ", "_")}'
                profile_json = get_setting(profile_key)

                if profile_json:
                    profile = json.loads(profile_json)
                    password_key = f'neo4j_profile_password_{source_profile.replace(" ", "_")}'
                    password = get_setting(password_key)

                    from .neo4j_client import Neo4jClient
                    neo4j_client = Neo4jClient(
                        uri=profile.get('uri'),
                        user=profile.get('user'),
                        password=password,
                        database=profile.get('database', 'neo4j'),
                        auth_mode='basic'
                    )
                    neo4j_client.connect()
                    created_client = True

            # Fall back to default connection if no source profile
            if not neo4j_client:
                neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Update the property
            query = f"""
            MATCH (n:{name})
            WHERE elementId(n) = $instance_id
            SET n.{property_name} = $value
            RETURN elementId(n) as id, properties(n) as properties
            """

            results = neo4j_client.execute_write(query, {
                'instance_id': instance_id,
                'value': property_value
            })

            if not results:
                raise Exception(f"Instance with ID '{instance_id}' not found")

            instance = {
                'id': results[0].get('id'),
                'properties': results[0].get('properties', {})
            }

            return {
                'status': 'success',
                'instance': instance
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def overwrite_label_instance(self, name: str, instance_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Overwrite all properties of a label instance in Neo4j.
        This removes any properties not in the provided dictionary.

        Args:
            name: Label name
            instance_id: Neo4j element ID
            properties: Complete set of properties to set (removes all others)

        Returns:
            Dict with status and updated instance
        """
        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        try:
            from .neo4j_client import get_neo4j_client
            neo4j_client = get_neo4j_client()

            if not neo4j_client:
                raise Exception("Neo4j client not configured")

            # Use SET n = {properties} to overwrite all properties
            # This removes any properties not in the provided dict
            query = f"""
            MATCH (n:{name})
            WHERE elementId(n) = $instance_id
            SET n = $properties
            RETURN elementId(n) as id, properties(n) as properties
            """

            results = neo4j_client.execute_write(query, {
                'instance_id': instance_id,
                'properties': properties
            })

            if not results:
                raise Exception(f"Instance with ID '{instance_id}' not found")

            instance = {
                'id': results[0].get('id'),
                'properties': results[0].get('properties', {})
            }

            return {
                'status': 'success',
                'instance': instance
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _transfer_relationships_batch(
        self,
        source_client,
        primary_client,
        source_label: str,
        target_label: str,
        rel_type: str,
        source_matching_key: str,
        target_matching_key: str,
        batch_size: int = 100,
        create_missing_targets: bool = False
    ) -> int:
        """
        Transfer relationships in batches with proper per-label matching keys.

        Args:
            source_client: Neo4j client for source database
            primary_client: Neo4j client for primary database
            source_label: Source node label
            target_label: Target node label
            rel_type: Relationship type
            source_matching_key: Property to match source nodes on
            target_matching_key: Property to match target nodes on
            batch_size: Number of relationships per batch
            create_missing_targets: Create target nodes if they don't exist

        Returns:
            Number of relationships transferred
        """
        offset = 0
        total_transferred = 0

        while True:
            # Query relationships from source in batches
            rel_query = f"""
            MATCH (source:{source_label})-[r:{rel_type}]->(target:{target_label})
            RETURN properties(source) as source_props,
                   properties(target) as target_props,
                   properties(r) as rel_props
            SKIP $offset
            LIMIT $batch_size
            """

            batch = source_client.execute_read(rel_query, {
                'offset': offset,
                'batch_size': batch_size
            })

            if not batch:
                break

            # Transfer each relationship in the batch
            for rel_record in batch:
                source_props = rel_record.get('source_props', {})
                target_props = rel_record.get('target_props', {})
                rel_props = rel_record.get('rel_props', {})

                # Get matching keys for source and target
                source_key_value = source_props.get(source_matching_key)
                target_key_value = target_props.get(target_matching_key)

                if not source_key_value or not target_key_value:
                    continue

                # Create relationship in primary with per-label matching
                if create_missing_targets:
                    # Use MERGE to create target if missing - Neo4j handles updates naturally
                    # First pass: creates minimal node with relationship properties
                    # Second pass: MERGE finds existing node and updates with full properties
                    create_rel_query = f"""
                    MATCH (source:{source_label} {{{source_matching_key}: $source_key}})
                    MERGE (target:{target_label} {{{target_matching_key}: $target_key}})
                    SET target = $target_props
                    MERGE (source)-[r:{rel_type}]->(target)
                    SET r = $rel_props
                    """
                    try:
                        primary_client.execute_write(create_rel_query, {
                            'source_key': source_key_value,
                            'target_key': target_key_value,
                            'target_props': target_props,
                            'rel_props': rel_props
                        })
                        total_transferred += 1
                    except Exception:
                        # Skip if source node doesn't exist
                        pass
                else:
                    # Only create relationship if both nodes exist (original behavior)
                    create_rel_query = f"""
                    MATCH (source:{source_label} {{{source_matching_key}: $source_key}})
                    MATCH (target:{target_label} {{{target_matching_key}: $target_key}})
                    MERGE (source)-[r:{rel_type}]->(target)
                    SET r = $rel_props
                    """
                    try:
                        primary_client.execute_write(create_rel_query, {
                            'source_key': source_key_value,
                            'target_key': target_key_value,
                            'rel_props': rel_props
                        })
                        total_transferred += 1
                    except Exception:
                        # Skip if nodes don't exist
                        pass

            offset += batch_size

        return total_transferred

    def transfer_to_primary(
        self,
        name: str,
        batch_size: int = 100,
        mode: str = 'nodes_and_outgoing',
        create_missing_targets: bool = False
    ) -> Dict[str, Any]:
        """
        Transfer instances of a label from its source database to the primary database.

        Transfer Modes:
        - 'nodes_only': Transfer only nodes, skip relationships (fastest)
        - 'nodes_and_outgoing': Transfer nodes + outgoing relationships (recommended)

        Features:
        - Batch processing for memory efficiency
        - Per-label matching key resolution (configured or auto-detected)
        - Relationship preservation with proper matching
        - Optional automatic creation of missing target nodes
        - Progress logging to server logs

        Args:
            name: Label name to transfer
            batch_size: Number of instances to process per batch (default 100)
            mode: Transfer mode - 'nodes_only' or 'nodes_and_outgoing' (default)
            create_missing_targets: Auto-create target nodes if they don't exist (default False)

        Returns:
            Dict with status, counts, matching keys used, and any errors
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check if transfer already running for this label
        if name in self._active_transfers and self._active_transfers[name].get('status') == 'running':
            return {
                'status': 'error',
                'error': f"Transfer already in progress for label '{name}'. Please wait or cancel the existing transfer."
            }

        label_def = self.get_label(name)
        if not label_def:
            raise ValueError(f"Label '{name}' not found")

        source_profile = label_def.get('neo4j_source_profile')
        if not source_profile:
            return {
                'status': 'error',
                'error': f"Label '{name}' has no source profile configured. Cannot transfer."
            }

        try:
            from .neo4j_client import get_neo4j_client, Neo4jClient
            from scidk.core.settings import get_setting

            # Get source client
            profile_key = f'neo4j_profile_{source_profile.replace(" ", "_")}'
            profile_json = get_setting(profile_key)
            if not profile_json:
                return {
                    'status': 'error',
                    'error': f"Source profile '{source_profile}' not found"
                }

            profile = json.loads(profile_json)
            password_key = f'neo4j_profile_password_{source_profile.replace(" ", "_")}'
            password = get_setting(password_key)

            source_client = Neo4jClient(
                uri=profile.get('uri'),
                user=profile.get('user'),
                password=password,
                database=profile.get('database', 'neo4j'),
                auth_mode='basic'
            )
            source_client.connect()

            # Get primary client
            primary_client = get_neo4j_client(role='primary')
            if not primary_client:
                source_client.close()
                return {
                    'status': 'error',
                    'error': 'Primary Neo4j connection not configured'
                }

            try:
                # Get matching key for this label using new resolution method
                matching_key = self.get_matching_key(name)

                # Get total count for progress tracking
                count_query = f"MATCH (n:{name}) RETURN count(n) as total"
                count_result = source_client.execute_read(count_query)
                total_nodes = count_result[0].get('total', 0) if count_result else 0

                logger.info(f"Starting transfer of {total_nodes} {name} nodes from {source_profile} (mode={mode}, batch_size={batch_size})")

                # Initialize progress tracking with two-phase structure
                import time
                self._active_transfers[name] = {
                    'status': 'running',
                    'cancelled': False,
                    'progress': {
                        'phase': 1,  # 1=nodes, 2=relationships
                        'phase_1': {
                            'total': total_nodes,
                            'completed': 0,
                            'percent': 0
                        },
                        'phase_2': {
                            'total': 0,
                            'completed': 0,
                            'percent': 0
                        },
                        'start_time': time.time(),
                        'phase_1_start': time.time(),
                        'phase_2_start': None
                    }
                }

                # Phase 1: Transfer nodes in batches
                offset = 0
                total_transferred = 0

                while True:
                    # Check for cancellation
                    if self._is_transfer_cancelled(name):
                        logger.info(f"Transfer cancelled by user at {total_transferred}/{total_nodes} nodes")
                        return {
                            'status': 'cancelled',
                            'nodes_transferred': total_transferred,
                            'message': f'Transfer cancelled after {total_transferred} nodes'
                        }

                    # Pull batch from source
                    batch_query = f"""
                    MATCH (n:{name})
                    RETURN elementId(n) as source_id, properties(n) as props
                    SKIP $offset
                    LIMIT $batch_size
                    """
                    batch = source_client.execute_read(batch_query, {
                        'offset': offset,
                        'batch_size': batch_size
                    })

                    if not batch:
                        break

                    # Create nodes in primary
                    for record in batch:
                        source_id = record.get('source_id')
                        props = record.get('props', {})

                        # Merge node in primary using matching key
                        merge_query = f"""
                        MERGE (n:{name} {{{matching_key}: $key_value}})
                        SET n = $props
                        RETURN elementId(n) as primary_id
                        """

                        key_value = props.get(matching_key)
                        if not key_value:
                            # Skip nodes without matching key
                            continue

                        result = primary_client.execute_write(merge_query, {
                            'key_value': key_value,
                            'props': props
                        })

                        if result:
                            total_transferred += 1

                    offset += batch_size

                    # Update Phase 1 progress tracking
                    progress_pct = min(100, int((total_transferred / total_nodes * 100))) if total_nodes > 0 else 0
                    if name in self._active_transfers:
                        self._active_transfers[name]['progress']['phase_1'].update({
                            'completed': total_transferred,
                            'percent': progress_pct
                        })

                    # Log progress every batch
                    logger.info(f"Phase 1 progress: {total_transferred}/{total_nodes} nodes ({progress_pct}%)")

                # Phase 2: Transfer relationships (if mode includes them)
                total_rels_transferred = 0
                matching_keys_used = {name: matching_key}

                if mode == 'nodes_and_outgoing':
                    relationships = label_def.get('relationships', [])
                    logger.info(f"Phase 2: Counting relationships for {len(relationships)} relationship types")

                    # Count total relationships before starting Phase 2
                    total_rels = 0
                    for rel in relationships:
                        rel_type = rel.get('type')
                        target_label = rel.get('target_label')
                        count_query = f"""
                        MATCH (:{name})-[:{rel_type}]->(:{target_label})
                        RETURN count(*) as count
                        """
                        try:
                            count_result = source_client.execute_read(count_query)
                            if count_result:
                                total_rels += count_result[0].get('count', 0)
                        except Exception as e:
                            logger.warning(f"Failed to count {rel_type} relationships: {e}")

                    logger.info(f"Phase 2: Transferring {total_rels} total relationships")

                    # Mark Phase 2 start and set total count
                    import time
                    if name in self._active_transfers:
                        self._active_transfers[name]['progress'].update({
                            'phase': 2,
                            'phase_2_start': time.time(),
                            'phase_2': {
                                'total': total_rels,
                                'completed': 0,
                                'percent': 0
                            }
                        })

                    for rel in relationships:
                        rel_type = rel.get('type')
                        target_label = rel.get('target_label')

                        # Get matching key for target label
                        target_matching_key = self.get_matching_key(target_label)
                        matching_keys_used[target_label] = target_matching_key

                        logger.info(f"Transferring {rel_type} relationships to {target_label}")

                        # Use batched relationship transfer with per-label matching
                        rels_count = self._transfer_relationships_batch(
                            source_client,
                            primary_client,
                            name,
                            target_label,
                            rel_type,
                            matching_key,
                            target_matching_key,
                            batch_size,
                            create_missing_targets
                        )
                        total_rels_transferred += rels_count

                        # Update Phase 2 relationship progress
                        if name in self._active_transfers and total_rels > 0:
                            rel_pct = min(100, int((total_rels_transferred / total_rels * 100)))
                            self._active_transfers[name]['progress']['phase_2'].update({
                                'completed': total_rels_transferred,
                                'percent': rel_pct
                            })

                        logger.info(f"Phase 2 progress: {total_rels_transferred}/{total_rels} relationships ({int((total_rels_transferred / total_rels * 100)) if total_rels > 0 else 0}%)")

                logger.info(f"Transfer complete: {total_transferred} nodes, {total_rels_transferred} relationships")

                return {
                    'status': 'success',
                    'nodes_transferred': total_transferred,
                    'relationships_transferred': total_rels_transferred,
                    'source_profile': source_profile,
                    'matching_keys': matching_keys_used,
                    'mode': mode
                }

            finally:
                source_client.close()
                # Clean up transfer tracking
                if name in self._active_transfers:
                    del self._active_transfers[name]

        except Exception as e:
            # Clean up on error
            if name in self._active_transfers:
                del self._active_transfers[name]
            return {
                'status': 'error',
                'error': str(e)
            }
