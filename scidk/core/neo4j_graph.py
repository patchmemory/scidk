from typing import Dict, List, Optional
from neo4j import GraphDatabase
import logging

logger = logging.getLogger(__name__)


class Neo4jGraph:
    """Lightweight graph backend backed by Neo4j.
    Implements the subset of methods used by the web layer to avoid heavy in-memory state.
    """

    def __init__(self, uri: str, auth: Optional[tuple] = None, database: Optional[str] = None, auth_mode: str = "basic"):
        self._uri = uri
        self._auth = auth
        self._auth_mode = auth_mode
        self._driver = GraphDatabase.driver(uri, auth=auth) if auth is not None else GraphDatabase.driver(uri)
        self._db = database
        logger.info(f"Neo4jGraph initialized with backend=neo4j, uri={uri}, database={database}")

    def close(self):
        try:
            self._driver.close()
        except Exception:
            pass

    def _session(self):
        return self._driver.session(database=self._db) if self._db else self._driver.session()

    # Dataset APIs (kept minimal to reduce RAM usage)
    def upsert_dataset(self, ds: Dict):
        # No-op: we don't mirror datasets in memory when using Neo4j backend
        return

    def add_interpretation(self, checksum: str, interpreter_id: str, payload: Dict,
                           file_path: Optional[str] = None, host: Optional[str] = None):
        """Record an Interpretation node and link it to the File it came from.

        The node used to carry a status and nothing else, with no edge to
        anything — unreachable from the graph and holding no payload.

        ``checksum`` stays first and positional because seven call sites and the
        in-memory twin in ``core/graph.py`` share this signature. Pass
        ``file_path`` to get the edge; a checksum cannot be matched against
        ``:File``, which is keyed on ``(path, host)``.

        The node is MERGEd before the File is looked up, so an interpretation is
        still recorded when the File has not been committed yet. Matching on
        path alone when ``host`` is unknown links every host holding that path,
        which is the useful reading of an unqualified path.

        **Pass ``host`` whenever it is known.** The only index on ``:File`` is
        the composite ``file_identity`` on ``(path, host)``, and a Neo4j
        composite index requires *every* property in the pattern — a lookup on
        ``path`` alone cannot use it and degrades to a full label scan. Measured
        on the AIPT graph at 5.5M File nodes: 3.72s by path alone, 0.01s by
        ``(path, host)``. The host therefore has to be in the MATCH pattern, not
        in a WHERE clause filtering the scan's output, which is why there are
        two query forms below rather than one with a nullable parameter.
        """
        import json as _json
        try:
            data_json = _json.dumps(payload.get('data') or {}, default=str)
        except Exception:
            data_json = '{}'
        identity = file_path or checksum

        merge_interpretation = (
            "MERGE (i:Interpretation {id:$iid}) "
            "  SET i.status = $status, "
            "      i.data_json = $data_json, "
            "      i.interpreter_id = $interpreter_id, "
            "      i.source_path = $path, "
            "      i.checksum = $checksum, "
            "      i.updated_at = timestamp() "
            "WITH i "
        )
        link_file = (
            "FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END | "
            "  MERGE (f)-[:INTERPRETED_AS]->(i) )"
        )
        if host:
            match_file = "OPTIONAL MATCH (f:File {path: $path, host: $host}) "
        else:
            match_file = "OPTIONAL MATCH (f:File {path: $path}) "

        try:
            with self._session() as s:
                s.run(
                    merge_interpretation + match_file + link_file,
                    iid=f"{interpreter_id}:{identity}",
                    status=payload.get('status') or 'unknown',
                    data_json=data_json,
                    interpreter_id=interpreter_id,
                    path=file_path,
                    checksum=checksum,
                    host=host,
                ).consume()
        except Exception:
            logger.debug("add_interpretation failed for %s on %s", interpreter_id, identity, exc_info=True)

    def list_datasets(self) -> List[Dict]:
        return []

    # Scan lifecycle
    def commit_scan(self, scan: Dict, rows: Optional[List[Dict]] = None, folder_rows: Optional[List[Dict]] = None) -> Dict:
        """Commit a scan with optional file and folder data.

        If rows and folder_rows are provided, writes them to Neo4j along with the scan node.
        Returns verification dict with counts: {'db_scan_exists', 'db_files', 'db_folders', 'db_verified'}.

        Args:
            scan: Scan metadata dict with id, path, started, ended, etc.
            rows: Optional list of file dicts to write
            folder_rows: Optional list of folder dicts to write

        Returns:
            Dict with verification results including counts
        """
        if not scan or not scan.get('id'):
            return {'db_scan_exists': False, 'db_verified': False, 'db_files': 0, 'db_folders': 0}

        sid = scan.get('id')

        # If rows/folders provided, use full write_scan flow via Neo4jClient
        if rows is not None or folder_rows is not None:
            try:
                from ..services.neo4j_client import Neo4jClient
                client = Neo4jClient(self._uri, self._auth[0] if self._auth else None,
                                   self._auth[1] if self._auth else None,
                                   self._db, self._auth_mode).connect()
                try:
                    client.ensure_constraints()
                    wres = client.write_scan(rows or [], folder_rows or [], scan)
                    vres = client.verify(sid)
                    logger.info(f"Neo4j commit completed: {wres.get('written_files', 0)} files, "
                              f"{wres.get('written_folders', 0)} folders for scan {sid}")
                    return vres
                finally:
                    client.close()
            except Exception as e:
                logger.error(f"Neo4j commit_scan failed: {e}")
                return {'db_scan_exists': False, 'db_verified': False, 'db_files': 0, 'db_folders': 0, 'error': str(e)}

        # Otherwise just create scan node (backward compat with old behavior)
        with self._session() as s:
            s.run(
                "MERGE (sc:Scan {id:$id}) SET sc.started=$started, sc.ended=$ended, sc.path=$path, "
                "sc.provider_id=$provider_id, sc.host_type=$host_type, sc.host_id=$host_id, sc.root_id=$root_id, sc.root_label=$root_label, sc.scan_source=$scan_source",
                id=sid,
                started=scan.get('started'), ended=scan.get('ended'), path=scan.get('path'),
                provider_id=scan.get('provider_id'), host_type=scan.get('host_type'), host_id=scan.get('host_id'),
                root_id=scan.get('root_id'), root_label=scan.get('root_label'), scan_source=scan.get('source')
            ).consume()

        return {'db_scan_exists': True, 'db_verified': False, 'db_files': 0, 'db_folders': 0}

    def delete_scan(self, scan_id: str):
        if not scan_id:
            return
        with self._session() as s:
            s.run("MATCH (sc:Scan {id:$id}) DETACH DELETE sc", id=scan_id).consume()

    # Schema/introspection utilities used by endpoints
    def schema_triples(self, limit: int = 500) -> Dict:
        with self._session() as s:
            nodes = s.run(
                "MATCH (f:File) WITH count(f) AS cf MATCH (d:Folder) WITH cf, count(d) AS cd MATCH (sc:Scan) RETURN [{label:'File',count:cf},{label:'Folder',count:cd},{label:'Scan',count:count(sc)}] AS ns"
            ).single().get('ns')
            edges_rows = s.run(
                "CALL { MATCH (:Folder)-[:CONTAINS]->(:File) RETURN 'Folder' AS s,'CONTAINS' AS r,'File' AS e, count(*) AS c } "
                "UNION ALL CALL { MATCH (:Folder)-[:CONTAINS]->(:Folder) RETURN 'Folder','CONTAINS','Folder', count(*) } "
                "UNION ALL CALL { MATCH (:File)-[:SCANNED_IN]->(:Scan) RETURN 'File','SCANNED_IN','Scan', count(*) } "
                "UNION ALL CALL { MATCH (:Folder)-[:SCANNED_IN]->(:Scan) RETURN 'Folder','SCANNED_IN','Scan', count(*) }"
            ).data()
            edges = [{'start_label': r['s'], 'rel_type': r['r'], 'end_label': r['e'], 'count': r.get('c') or r.get('count')} for r in edges_rows]
            edges.sort(key=lambda x: x['count'], reverse=True)
            if limit and len(edges) > limit:
                edges = edges[:limit]
            # filter nodes with zero count
            nodes = [n for n in nodes if n.get('count')]
            return {'nodes': nodes, 'edges': edges, 'truncated': False}

    def list_instances(self, label: str) -> List[Dict]:
        label = (label or '').strip()
        if not label:
            return []

        with self._session() as s:
            # For hardcoded labels, use specific optimized queries
            if label == 'File':
                rows = s.run(
                    "MATCH (f:File) RETURN f.path AS path, f.filename AS filename, f.extension AS extension, f.size_bytes AS size_bytes, f.created AS created, f.modified AS modified, f.mime_type AS mime_type LIMIT 1000"
                ).data()
                return [{**r, 'id': r['path'], 'checksum': None} for r in rows]
            if label == 'Folder':
                return s.run(
                    "MATCH (d:Folder) OPTIONAL MATCH (d)-[:CONTAINS]->(f:File) WITH d, count(f) AS file_count RETURN d.path AS path, d.name AS name, file_count ORDER BY path LIMIT 1000"
                ).data()
            if label == 'Scan':
                return s.run(
                    "MATCH (sc:Scan) WITH sc ORDER BY sc.started DESC NULLS LAST RETURN sc.id AS id, sc.started AS started, sc.ended AS ended, coalesce(sc.committed,true) AS committed, 0 AS num_files LIMIT 1000"
                ).data()
            if label == 'ResearchObject':
                return []

            # For arbitrary labels, query all nodes with that label and return all properties
            try:
                # Use backticks to handle labels with special characters
                query = f"MATCH (n:`{label}`) RETURN n LIMIT 1000"
                result = s.run(query).data()

                # Extract node properties and add an id field
                rows = []
                for record in result:
                    node = record.get('n')
                    if node:
                        props = dict(node)
                        # Try to find a good id field
                        if 'id' not in props:
                            if 'path' in props:
                                props['id'] = props['path']
                            elif 'name' in props:
                                props['id'] = props['name']
                            else:
                                # Use Neo4j internal id as fallback
                                props['id'] = str(node.id)
                        rows.append(props)
                return rows
            except Exception as e:
                # If query fails (e.g., label doesn't exist), return empty list
                print(f"Error querying instances for label '{label}': {e}")
                return []
