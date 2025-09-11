from typing import Dict, List, Optional
from neo4j import GraphDatabase


class Neo4jGraph:
    """Lightweight graph backend backed by Neo4j.
    Implements the subset of methods used by the web layer to avoid heavy in-memory state.
    """

    def __init__(self, uri: str, auth: Optional[tuple] = None, database: Optional[str] = None):
        self._driver = GraphDatabase.driver(uri, auth=auth) if auth is not None else GraphDatabase.driver(uri)
        self._db = database

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

    def add_interpretation(self, checksum: str, interpreter_id: str, payload: Dict):
        # Optional: record a small interpretation marker
        try:
            with self._session() as s:
                s.run(
                    "MERGE (i:Interpretation {id:$id}) SET i.status=$st, i.updated_at=timestamp()",
                    id=f"{interpreter_id}:{checksum}", st=payload.get('status') or 'unknown'
                ).consume()
        except Exception:
            pass

    def list_datasets(self) -> List[Dict]:
        return []

    # Scan lifecycle
    def commit_scan(self, scan: Dict):
        if not scan or not scan.get('id'):
            return
        sid = scan.get('id')
        with self._session() as s:
            s.run(
                "MERGE (sc:Scan {id:$id}) SET sc.started=$started, sc.ended=$ended, sc.path=$path, "
                "sc.provider_id=$provider_id, sc.host_type=$host_type, sc.host_id=$host_id, sc.root_id=$root_id, sc.root_label=$root_label, sc.scan_source=$scan_source",
                id=sid,
                started=scan.get('started'), ended=scan.get('ended'), path=scan.get('path'),
                provider_id=scan.get('provider_id'), host_type=scan.get('host_type'), host_id=scan.get('host_id'),
                root_id=scan.get('root_id'), root_label=scan.get('root_label'), scan_source=scan.get('source')
            ).consume()

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
        with self._session() as s:
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
            return []
