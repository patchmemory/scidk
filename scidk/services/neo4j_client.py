from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List


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
                "WITH r, f "
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
