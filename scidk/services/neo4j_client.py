from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List
import os

from scidk.schema.sanitization import sanitize_node_properties


def get_neo4j_params(app: Optional[Any] = None) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Read Neo4j connection parameters from app extensions or environment.

    Priority order:
    1. UI settings (app.extensions['scidk']['neo4j_config']) - set via Settings page
    2. Environment variables - fallback for headless/Docker deployments

    Returns (uri, user, password, database, auth_mode) where auth_mode is 'basic' or 'none'.
    """
    cfg = {}
    try:
        if app is not None:
            cfg = getattr(app, 'extensions', {}).get('scidk', {}).get('neo4j_config', {}) or {}
    except Exception:
        cfg = {}

    # Priority: UI settings first, then environment variables
    uri = cfg.get('uri') or os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
    user = cfg.get('user') or os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
    pwd = cfg.get('password') or os.environ.get('NEO4J_PASSWORD')
    database = cfg.get('database') or os.environ.get('SCIDK_NEO4J_DATABASE') or None
    # Parse NEO4J_AUTH env var if provided (formats: "user/pass" or "none")
    neo4j_auth = (os.environ.get('NEO4J_AUTH') or '').strip()
    auth_mode = 'basic'
    if neo4j_auth:
        if neo4j_auth.lower() == 'none':
            user = user or None
            pwd = pwd or None
            auth_mode = 'none'
        else:
            try:
                parts = neo4j_auth.split('/')
                if len(parts) >= 2 and not (user and pwd):
                    user = user or parts[0]
                    pwd = pwd or '/'.join(parts[1:])
            except Exception:
                pass
    # If user/password still missing, try to parse from URI (bolt://user:pass@host:port)
    try:
        if uri and (not user or not pwd):
            from urllib.parse import urlparse, unquote  # type: ignore
            parsed = urlparse(uri)
            if parsed.username and parsed.password:
                user = user or unquote(parsed.username)
                pwd = pwd or unquote(parsed.password)
    except Exception:
        pass
    # Determine auth mode final: none only when explicitly set via NEO4J_AUTH=none
    if (os.environ.get('NEO4J_AUTH') or '').strip().lower() == 'none':
        auth_mode = 'none'
    else:
        auth_mode = 'basic'
    return uri, user, pwd, database, auth_mode


class Neo4jClient:
    """
    Thin client around neo4j-python-driver used by commit pipeline.
    Provides ensure_constraints, write_scan, and verify operations.
    """

    def __init__(self, uri: str, user: Optional[str], password: Optional[str], database: Optional[str] = None, auth_mode: str = "basic"):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._auth_mode = (auth_mode or 'basic').lower()
        self._driver = None

    def connect(self):
        from neo4j import GraphDatabase  # type: ignore
        auth = None if self._auth_mode == 'none' else (self._user, self._password)
        self._driver = GraphDatabase.driver(self._uri, auth=auth)
        return self

    def close(self):
        try:
            if self._driver is not None:
                self._driver.close()
        except Exception:
            pass

    def _session(self):
        if self._driver is None:
            raise RuntimeError("Neo4jClient not connected")
        if self._database:
            return self._driver.session(database=self._database)
        return self._driver.session()

    # --- Query Operations ---
    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read query and return results as list of dicts.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of records as dictionaries
        """
        with self._session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def execute_write(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a write query and return results as list of dicts.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of records as dictionaries
        """
        with self._session() as session:
            result = session.run(query, parameters or {})
            records = [dict(record) for record in result]
            return records

    # --- Operations ---
    def ensure_constraints(self) -> None:
        try:
            with self._session() as s:
                try:
                    s.run("CREATE CONSTRAINT file_identity IF NOT EXISTS FOR (f:File) REQUIRE (f.path, f.host) IS UNIQUE").consume()
                except Exception:
                    pass
                try:
                    s.run("CREATE CONSTRAINT folder_identity IF NOT EXISTS FOR (d:Folder) REQUIRE (d.path, d.host) IS UNIQUE").consume()
                except Exception:
                    pass
        except Exception:
            # best-effort, ignore errors
            pass

    def write_scan(self, rows: List[Dict[str, Any]], folder_rows: List[Dict[str, Any]], scan: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert Scan, Folders, Files and relationships for one scan in a single query."""
        with self._session() as sess:
            cypher = (
                "MERGE (s:Scan {id: $scan_id}) "
                "SET s.path = $scan_path, s.started = $scan_started, s.ended = $scan_ended, "
                "    s.provider_id = $scan_provider, s.host_type = $scan_host_type, s.host_id = $scan_host_id, "
                "    s.root_id = $scan_root_id, s.root_label = $scan_root_label, s.scan_source = $scan_source "
                "WITH s "
                "UNWIND $folders AS folder "
                "MERGE (fo:Folder {path: folder.path, host: $node_host}) "
                "  SET fo.name = folder.name, fo.provider_id = $scan_provider, fo.host_type = $scan_host_type, fo.host_id = $scan_host_id "
                "MERGE (fo)-[:SCANNED_IN]->(s) "
                "WITH s "
                "UNWIND $folders AS folder "
                "WITH s, folder WHERE folder.parent IS NOT NULL AND folder.parent <> '' AND folder.parent <> folder.path "
                "MERGE (child:Folder {path: folder.path, host: $node_host}) "
                "MERGE (parent:Folder {path: folder.parent, host: $node_host}) "
                "MERGE (parent)-[:CONTAINS]->(child) "
                "WITH s "
                "UNWIND $rows AS r "
                "MERGE (f:File {path: r.path, host: $node_host}) "
                "  SET f.filename = r.filename, f.extension = r.extension, f.size_bytes = r.size_bytes, f.created = r.created, f.modified = r.modified, f.mime_type = r.mime_type, f.provider_id = $scan_provider, f.host_type = $scan_host_type, f.host_id = $scan_host_id "
                "MERGE (f)-[:SCANNED_IN]->(s) "
                "WITH r, f, s "
                "FOREACH (iid IN coalesce(r.interps, []) | "
                "  MERGE (i:Interpreter {id: iid}) "
                "  MERGE (f)-[:INTERPRETED_AS]->(i) "
                ") "
                "WITH r, f, s "
                "WHERE r.folder IS NOT NULL AND r.folder <> '' "
                "MERGE (fo:Folder {path: r.folder, host: $node_host}) "
                "MERGE (fo)-[:CONTAINS]->(f) "
                "RETURN $scan_id AS scan_id"
            )
            params = dict(
                rows=rows,
                folders=folder_rows,
                scan_id=scan.get('id'),
                scan_path=scan.get('path'),
                scan_started=scan.get('started'),
                scan_ended=scan.get('ended'),
                scan_provider=scan.get('provider_id'),
                scan_host_type=scan.get('host_type'),
                scan_host_id=scan.get('host_id'),
                scan_root_id=scan.get('root_id'),
                scan_root_label=scan.get('root_label'),
                scan_source=scan.get('scan_source'),
                node_host=scan.get('host_id'),
                node_port=None,
            )
            _ = list(sess.run(cypher, **params))
            return {
                'written_files': len(rows),
                'written_folders': len(folder_rows),
            }

    def verify(self, scan_id: str) -> Dict[str, Any]:
        verify_q = (
            "OPTIONAL MATCH (s:Scan {id: $scan_id}) "
            "WITH s "
            "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(f:File) "
            "WITH s, count(DISTINCT f) AS files_cnt "
            "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(fo:Folder) "
            "RETURN coalesce(s IS NOT NULL, false) AS scan_exists, files_cnt AS files_cnt, count(DISTINCT fo) AS folders_cnt"
        )
        with self._session() as sess:
            vrec = sess.run(verify_q, scan_id=scan_id).single()
            if not vrec:
                return {'db_verified': False}
            scan_exists = bool(vrec.get('scan_exists'))
            files_cnt = int(vrec.get('files_cnt') or 0)
            folders_cnt = int(vrec.get('folders_cnt') or 0)
            return {
                'db_scan_exists': scan_exists,
                'db_files': files_cnt,
                'db_folders': folders_cnt,
                'db_verified': bool(scan_exists and (files_cnt > 0 or folders_cnt > 0)),
            }

    def write_declared_nodes(self, nodes: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Write interpreter-declared nodes and relationships at commit time.

        Args:
            nodes: List of node declarations with format:
                   [{'label': 'ImagingDataset', 'key_property': 'path', 'properties': {...}}]
            relationships: List of relationship declarations with format:
                          [{'type': 'METADATA_SOURCE', 'from_label': 'X', 'from_match': {...},
                            'to_label': 'Y', 'to_match': {...}}]

        Returns:
            Dict with keys: written_nodes (int), written_relationships (int), errors (list)
        """
        result = {'written_nodes': 0, 'written_relationships': 0, 'errors': []}

        with self._session() as sess:
            # Write nodes using MERGE on key property
            for node_decl in nodes:
                try:
                    label = node_decl.get('label')
                    key_prop = node_decl.get('key_property')
                    props = node_decl.get('properties', {})

                    # Apply Label-defined sanitization rules before write
                    props = sanitize_node_properties(label, props)

                    if not label or not key_prop or key_prop not in props:
                        result['errors'].append(f"Invalid node declaration: missing label, key_property, or key in properties")
                        continue

                    # Build MERGE query with key property, SET all other properties
                    key_val = props[key_prop]
                    other_props = {k: v for k, v in props.items() if k != key_prop}

                    # Cypher parameter construction
                    params = {'key_val': key_val}
                    set_clauses = []
                    for idx, (k, v) in enumerate(other_props.items()):
                        param_name = f'prop_{idx}'
                        params[param_name] = v
                        set_clauses.append(f'n.{k} = ${param_name}')

                    set_clause = ', '.join(set_clauses) if set_clauses else ''
                    cypher = f"MERGE (n:{label} {{{key_prop}: $key_val}})"
                    if set_clause:
                        cypher += f" SET {set_clause}"
                    cypher += " RETURN elementId(n) as node_id"

                    sess.run(cypher, **params).consume()
                    result['written_nodes'] += 1

                except Exception as e:
                    result['errors'].append(f"Failed to write node {node_decl.get('label')}: {str(e)}")

            # Write relationships using MATCH by key properties
            for rel_decl in relationships:
                try:
                    rel_type = rel_decl.get('type')
                    from_label = rel_decl.get('from_label')
                    from_match = rel_decl.get('from_match', {})
                    to_label = rel_decl.get('to_label')
                    to_match = rel_decl.get('to_match', {})

                    if not rel_type or not from_label or not to_label or not from_match or not to_match:
                        result['errors'].append(f"Invalid relationship declaration: missing required fields")
                        continue

                    # Build MATCH clauses with provided properties
                    from_props_str = ', '.join([f'{k}: $from_{k}' for k in from_match.keys()])
                    to_props_str = ', '.join([f'{k}: $to_{k}' for k in to_match.keys()])

                    params = {}
                    for k, v in from_match.items():
                        params[f'from_{k}'] = v
                    for k, v in to_match.items():
                        params[f'to_{k}'] = v

                    cypher = (
                        f"MATCH (from:{from_label} {{{from_props_str}}}) "
                        f"MATCH (to:{to_label} {{{to_props_str}}}) "
                        f"MERGE (from)-[:{rel_type}]->(to)"
                    )

                    sess.run(cypher, **params).consume()
                    result['written_relationships'] += 1

                except Exception as e:
                    result['errors'].append(f"Failed to write relationship {rel_decl.get('type')}: {str(e)}")

        return result

    def push_label_constraints(self) -> Dict[str, Any]:
        """Push all Label schema constraints and indexes to Neo4j.

        Loads all registered Label definitions and creates their constraints/indexes.
        Uses IF NOT EXISTS so this operation is idempotent.

        Returns:
            Dict with keys:
                - created: List of constraint/index names that were created
                - already_existed: List of constraint/index names that already existed
                - errors: List of error messages for any failures
        """
        from scidk.schema.registry import LabelRegistry

        result = {
            'created': [],
            'already_existed': [],
            'errors': []
        }

        # Load all labels
        all_labels = LabelRegistry.all()

        with self._session() as session:
            for label_name, label_def in all_labels.items():
                try:
                    # Generate Cypher constraint statements
                    statements = label_def.generate_cypher_constraints()

                    for statement in statements:
                        try:
                            # Execute the constraint/index creation
                            session.run(statement).consume()

                            # Extract constraint/index name from statement
                            # Format: "CREATE CONSTRAINT name IF NOT EXISTS..." or "CREATE INDEX name IF NOT EXISTS..."
                            parts = statement.split()
                            if len(parts) >= 3:
                                constraint_name = parts[2]  # Third token is the name

                                # Check if it already existed by trying to query it
                                # Neo4j returns success even if it existed due to IF NOT EXISTS
                                # So we'll consider it as created (idempotent operation)
                                result['created'].append(f"{label_name}.{constraint_name}")

                        except Exception as e:
                            error_msg = str(e).lower()
                            # If it already exists, Neo4j might still raise in some versions
                            if 'already exists' in error_msg or 'equivalent' in error_msg:
                                if len(statement.split()) >= 3:
                                    constraint_name = statement.split()[2]
                                    result['already_existed'].append(f"{label_name}.{constraint_name}")
                            else:
                                result['errors'].append(f"{label_name}: {str(e)}")

                except Exception as e:
                    result['errors'].append(f"Failed to process {label_name}: {str(e)}")

        return result


def get_neo4j_client_for_profile(profile_name: str) -> Optional['Neo4jClient']:
    """Get Neo4j client for a specific named profile.

    Args:
        profile_name: Name of the Neo4j profile (e.g., 'Read-Only Source')

    Returns:
        Connected Neo4jClient instance or None if profile not found

    Raises:
        ValueError: If profile configuration is invalid
    """
    try:
        from flask import current_app
        from ..core.settings import get_setting
        import json

        # Normalize profile name for key lookup
        profile_key = f'neo4j_profile_{profile_name.replace(" ", "_")}'
        profile_json = get_setting(profile_key)

        if not profile_json:
            raise ValueError(f"Neo4j profile '{profile_name}' not found in settings")

        profile = json.loads(profile_json)

        # Load password
        password_key = f'neo4j_profile_password_{profile_name.replace(" ", "_")}'
        password = get_setting(password_key)

        uri = profile.get('uri')
        user = profile.get('user')
        database = profile.get('database')
        auth_mode = 'basic'  # Default for profiles

        if not uri:
            raise ValueError(f"Neo4j profile '{profile_name}' has no URI configured")

        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        return client

    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Failed to create Neo4j client for profile '{profile_name}': {e}")
        except:
            pass
        return None


def list_neo4j_profiles() -> List[Dict[str, Any]]:
    """List all configured Neo4j profiles.

    Returns:
        List of profile dicts with keys: name, uri, user, database, role
    """
    try:
        from ..core.settings import get_settings_by_prefix
        import json

        profiles = []
        settings = get_settings_by_prefix('neo4j_profile_')

        # Find all neo4j_profile_* settings
        for key, value in settings.items():
            if not key.endswith('_password'):
                # Extract profile name from key
                profile_name_normalized = key.replace('neo4j_profile_', '')
                profile_name = profile_name_normalized.replace('_', ' ')

                try:
                    profile_data = json.loads(value)
                    profiles.append({
                        'name': profile_name,
                        'uri': profile_data.get('uri', ''),
                        'user': profile_data.get('user', ''),
                        'database': profile_data.get('database', 'neo4j'),
                        'role': profile_data.get('role', 'unknown')
                    })
                except:
                    continue

        return profiles

    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Failed to list Neo4j profiles: {e}")
        except:
            pass
        return []


def get_neo4j_client(role: Optional[str] = None):
    """Get or create Neo4j client instance.

    Args:
        role: Optional role to get connection for (e.g., 'primary', 'labels_source').
              If None, uses the primary connection.

    Returns:
        Neo4jClient instance if connection parameters are available, None otherwise
    """
    # Try to get Flask app context to read updated config
    app = None
    try:
        from flask import current_app
        app = current_app._get_current_object()
    except (ImportError, RuntimeError):
        # No Flask context or not in request context
        pass

    # If role specified, try to get connection params for that role
    if role and app:
        try:
            from ..core.settings import get_setting
            import json

            # Get active profile for this role
            active_key = f'neo4j_active_role_{role}'
            active_name = get_setting(active_key)

            if active_name:
                # Load profile
                profile_key = f'neo4j_profile_{active_name.replace(" ", "_")}'
                profile_json = get_setting(profile_key)

                if profile_json:
                    profile = json.loads(profile_json)

                    # Load password
                    password_key = f'neo4j_profile_password_{active_name.replace(" ", "_")}'
                    password = get_setting(password_key)

                    uri = profile.get('uri')
                    user = profile.get('user')
                    database = profile.get('database')
                    auth_mode = 'basic'  # Default for profiles

                    if uri:
                        client = Neo4jClient(uri, user, password, database, auth_mode)
                        client.connect()
                        return client
        except Exception as e:
            # Fall back to default connection
            if app:
                app.logger.warning(f"Failed to get Neo4j connection for role {role}: {e}")

    # Fall back to primary connection
    uri, user, pwd, database, auth_mode = get_neo4j_params(app)

    if not uri:
        return None

    client = Neo4jClient(uri, user, pwd, database, auth_mode)
    client.connect()
    return client
