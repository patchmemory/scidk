import hashlib
import time
from typing import Dict, List, Optional


class InMemoryGraph:
    """Very simple in-memory storage for datasets and interpretations.
    Dataset identity is by checksum.
    """

    def __init__(self):
        self.datasets: Dict[str, Dict] = {}  # checksum -> dataset dict
        # index by id for convenience as well
        self.by_id: Dict[str, str] = {}  # dataset_id -> checksum
        # Scan nodes committed to the graph (scan_id -> scan dict)
        self.scans: Dict[str, Dict] = {}
        # Mapping from dataset checksum -> set of scan_ids that included it
        self.dataset_scans: Dict[str, set] = {}

    def _dataset_id(self, checksum: str) -> str:
        return hashlib.sha1(checksum.encode()).hexdigest()[:16]

    def upsert_dataset(self, dataset: Dict) -> Dict:
        checksum = dataset['checksum']
        existing = self.datasets.get(checksum)
        if existing:
            # Update basic fields and timestamps
            existing.update({
                'path': dataset['path'],
                'filename': dataset['filename'],
                'extension': dataset['extension'],
                'size_bytes': dataset['size_bytes'],
                'created': dataset['created'],
                'modified': dataset['modified'],
                'mime_type': dataset['mime_type'],
                'lifecycle_state': dataset.get('lifecycle_state', 'active'),
            })
            ds = existing
        else:
            ds = dataset.copy()
            ds['id'] = self._dataset_id(checksum)
            ds['interpretations'] = {}
            ds['interpretation_errors'] = []
            self.datasets[checksum] = ds
            self.by_id[ds['id']] = checksum
        return ds

    def add_interpretation(self, checksum: str, interpreter_id: str, payload: Dict):
        ds = self.datasets.get(checksum)
        if not ds:
            return
        payload = payload.copy()
        payload['timestamp'] = payload.get('timestamp') or time.time()
        ds['interpretations'][interpreter_id] = payload

    def list_datasets(self) -> List[Dict]:
        return list(self.datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[Dict]:
        checksum = self.by_id.get(dataset_id)
        if not checksum:
            return None
        return self.datasets.get(checksum)

    def schema_summary(self) -> Dict:
        """Compute a lightweight schema summary for UI display.
        Nodes: Dataset count.
        Relations (in-memory approximation):
          - INTERPRETED_AS: number of interpretation entries across datasets.
        Interpretation types: unique interpreter ids present.
        """
        datasets = list(self.datasets.values())
        interp_types = set()
        interpreted_edges = 0
        for d in datasets:
            interps = d.get('interpretations') or {}
            interpreted_edges += len(interps)
            for k in interps.keys():
                interp_types.add(k)
        return {
            'nodes': {
                'Dataset': len(datasets),
            },
            'relations': {
                'INTERPRETED_AS': interpreted_edges,
            },
            'interpretation_types': sorted(list(interp_types)),
        }

    def schema_triples(self, limit: int = 500) -> Dict:
        """Backend-agnostic unique triples schema view.
        Returns nodes and edges with counts, capped by 'limit'.
        Nodes: list of {label, count}
        Edges: list of {start_label, rel_type, end_label, count}
        For this demo iteration, we derive File/Folder labels and CONTAINS edges
        from the stored datasets (files) and their parent directories, without
        changing the internal storage model.
        """
        datasets = list(self.datasets.values())
        # Derive File and Folder counts
        file_count = len(datasets)
        # collect parent folders from file paths
        folder_paths = set()
        for d in datasets:
            p = d.get('path')
            if p:
                try:
                    from pathlib import Path as _P
                    folder_paths.add(str(_P(p).parent))
                except Exception:
                    pass
        folder_count = len(folder_paths)
        nodes = {}
        if file_count:
            nodes['File'] = file_count
        if folder_count:
            nodes['Folder'] = folder_count
        if self.scans:
            nodes['Scan'] = len(self.scans)
        # Edge counts
        edge_counts: Dict[tuple, int] = {}
        # (1) File -[INTERPRETED_AS]-> <InterpreterId>
        for d in datasets:
            interps = d.get('interpretations') or {}
            for interp_id in interps.keys():
                key = ('File', 'INTERPRETED_AS', interp_id)
                edge_counts[key] = edge_counts.get(key, 0) + 1
        # (2) Folder -[CONTAINS]-> File (count files per parent dir)
        # For unique triples view, we aggregate all Folder→File into a single triple with total file count
        if file_count and folder_count:
            key_cf = ('Folder', 'CONTAINS', 'File')
            edge_counts[key_cf] = sum(1 for _ in datasets)
        # (3) File -[SCANNED_IN]-> Scan (count files linked to any committed scan)
        # (4) Folder -[SCANNED_IN]-> Scan (count unique folders that had files in committed scans)
        if self.dataset_scans:
            # File→Scan count is number of dataset-scan memberships
            file_scan_edges = 0
            folder_scan_set = set()
            for checksum, scan_ids in self.dataset_scans.items():
                if checksum not in self.datasets:
                    continue
                file_scan_edges += len(scan_ids)
                # derive folder for this file
                try:
                    from pathlib import Path as _P
                    folder_scan_set.add(str(_P(self.datasets[checksum]['path']).parent))
                except Exception:
                    pass
            if file_scan_edges:
                edge_counts[('File', 'SCANNED_IN', 'Scan')] = edge_counts.get(('File', 'SCANNED_IN', 'Scan'), 0) + file_scan_edges
            if folder_scan_set:
                edge_counts[('Folder', 'SCANNED_IN', 'Scan')] = edge_counts.get(('Folder', 'SCANNED_IN', 'Scan'), 0) + len(folder_scan_set)
        # Build edges list sorted by count desc
        edges_all = [
            {'start_label': k[0], 'rel_type': k[1], 'end_label': k[2], 'count': c}
            for k, c in edge_counts.items()
        ]
        edges_all.sort(key=lambda e: e['count'], reverse=True)
        truncated = False
        if limit and len(edges_all) > limit:
            edges = edges_all[:limit]
            truncated = True
        else:
            edges = edges_all
        return {
            'nodes': [{'label': label, 'count': count} for label, count in nodes.items()],
            'edges': edges,
            'truncated': truncated,
        }

    def commit_scan(self, scan: Dict):
        """Commit a scan session into the graph as a Scan node and SCANNED_IN edges.
        Expects scan to contain 'id' and 'checksums'.
        """
        if not scan or not scan.get('id'):
            return
        sid = scan['id']
        # store a shallow copy
        self.scans[sid] = {k: scan[k] for k in scan.keys()}
        checksums = scan.get('checksums') or []
        for ch in checksums:
            if ch in self.datasets:
                s = self.dataset_scans.setdefault(ch, set())
                s.add(sid)

    def delete_scan(self, scan_id: str):
        """Delete a committed scan node and unlink SCANNED_IN edges. Datasets remain intact."""
        if not scan_id:
            return
        if scan_id in self.scans:
            del self.scans[scan_id]
        # remove from dataset->scans mapping
        to_del = []
        for ch, sids in self.dataset_scans.items():
            if scan_id in sids:
                sids.discard(scan_id)
            if not sids:
                to_del.append(ch)
        for ch in to_del:
            del self.dataset_scans[ch]

    def list_instances(self, label: str) -> List[Dict]:
        """Return instance rows for the given node label.
        Supported labels: File, Folder, Scan.
        - File: returns dataset dicts with key fields
        - Folder: returns dicts with path and file_count
        - Scan: returns committed scans with id, started/ended timestamps and counts
        """
        label = (label or '').strip()
        if label == 'File':
            rows = []
            for d in self.list_datasets():
                rows.append({
                    'id': d.get('id'),
                    'path': d.get('path'),
                    'filename': d.get('filename'),
                    'extension': d.get('extension'),
                    'size_bytes': d.get('size_bytes'),
                    'created': d.get('created'),
                    'modified': d.get('modified'),
                    'mime_type': d.get('mime_type'),
                    'checksum': d.get('checksum'),
                })
            return rows
        if label == 'Folder':
            from pathlib import Path as _P
            counts: Dict[str, int] = {}
            for d in self.list_datasets():
                p = d.get('path')
                if not p:
                    continue
                parent = str(_P(p).parent)
                counts[parent] = counts.get(parent, 0) + 1
            rows = [{'path': k, 'file_count': v} for k, v in counts.items()]
            rows.sort(key=lambda r: r['path'])
            return rows
        if label == 'Scan':
            rows = []
            for sid, s in self.scans.items():
                rows.append({
                    'id': sid,
                    'started': s.get('started'),
                    'ended': s.get('ended'),
                    'committed': s.get('committed', True),
                    'num_files': len(s.get('checksums') or []),
                })
            rows.sort(key=lambda r: r.get('started') or 0, reverse=True)
            return rows
        return []
