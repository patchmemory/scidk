import hashlib
import time
from typing import Dict, List, Optional


class InMemoryGraph:
    """Very simple in-memory storage for datasets and interpretations.
    Dataset identity is by checksum.
    Also supports ResearchObject nodes (representing RO-Crates) that can link to
    files and folders contained in the crate.
    """

    def __init__(self):
        self.datasets: Dict[str, Dict] = {}  # checksum -> dataset dict
        # index by id for convenience as well
        self.by_id: Dict[str, str] = {}  # dataset_id -> checksum
        # Scan nodes committed to the graph (scan_id -> scan dict)
        self.scans: Dict[str, Dict] = {}
        # Mapping from dataset checksum -> set of scan_ids that included it
        self.dataset_scans: Dict[str, set] = {}
        # ResearchObject nodes (id -> ro dict) and their relationships
        self.research_objects: Dict[str, Dict] = {}
        # ro_id -> set of dataset checksums (files contained in RO)
        self.ro_files: Dict[str, set] = {}
        # ro_id -> set of folder paths (strings) contained in RO
        self.ro_folders: Dict[str, set] = {}

    def _dataset_id(self, checksum: str) -> str:
        return hashlib.sha1(checksum.encode()).hexdigest()[:16]

    def _ro_id(self, key: str) -> str:
        """Derive a stable ResearchObject id from a key (e.g., path)."""
        try:
            return 'ro_' + hashlib.sha1((key or '').encode('utf-8')).hexdigest()[:16]
        except Exception:
            return 'ro_' + hashlib.sha1(b'').hexdigest()[:16]

    def upsert_research_object(self, meta: Dict, file_checksums: List[str], folder_paths: List[str]) -> Dict:
        """Create or update a ResearchObject and link it to files/folders.
        - meta should include at least 'path' or 'name' to derive id; arbitrary keys allowed.
        - file_checksums should reference datasets already known in self.datasets (unknown are ignored).
        - folder_paths are strings (absolute paths recommended).
        Returns stored ResearchObject dict.
        """
        key = meta.get('path') or meta.get('name') or meta.get('id') or ''
        ro_id = meta.get('id') or self._ro_id(key)
        ro = self.research_objects.get(ro_id)
        if ro:
            # update metadata (shallow)
            ro.update(meta)
        else:
            ro = meta.copy()
            ro['id'] = ro_id
            ro['label'] = 'ResearchObject'
            ro['created_at'] = ro.get('created_at') or time.time()
            self.research_objects[ro_id] = ro
        # Link files
        files_set = self.ro_files.setdefault(ro_id, set())
        for ch in file_checksums or []:
            if ch in self.datasets:
                files_set.add(ch)
        # Link folders
        folders_set = self.ro_folders.setdefault(ro_id, set())
        for p in folder_paths or []:
            if p:
                folders_set.add(p)
        return ro

    def list_research_objects(self) -> List[Dict]:
        return list(self.research_objects.values())

    def get_research_object(self, ro_id: str) -> Optional[Dict]:
        return self.research_objects.get(ro_id)

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
        Nodes: Dataset count (+ ResearchObject and derived File/Folder/Scan counts).
        Relations (in-memory approximation):
          - INTERPRETED_AS: number of interpretation entries across datasets.
          - CONTAINS: Folder→File (aggregate), Folder→Folder (aggregate), ResearchObject→File/Folder.
          - SCANNED_IN: File→Scan, Folder→Scan.
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
        # Derive file/folder counts
        folder_paths = set()
        for d in datasets:
            p = d.get('path')
            if p:
                try:
                    from pathlib import Path as _P
                    folder_paths.add(str(_P(p).parent))
                except Exception:
                    pass
        nodes = {
            'Dataset': len(datasets),
        }
        if folder_paths:
            nodes['Folder'] = len(folder_paths)
        if self.scans:
            nodes['Scan'] = len(self.scans)
        if self.research_objects:
            nodes['ResearchObject'] = len(self.research_objects)
        # Summarize relations minimalistically
        relations = {
            'INTERPRETED_AS': interpreted_edges,
        }
        # Include aggregate CONTAINS edges
        if datasets and folder_paths:
            relations['CONTAINS'] = relations.get('CONTAINS', 0) + len(datasets)  # Folder→File aggregate count
        # ResearchObject→File and →Folder counts
        if self.ro_files:
            relations['CONTAINS'] = relations.get('CONTAINS', 0) + sum(len(v) for v in self.ro_files.values())
        if self.ro_folders:
            relations['CONTAINS'] = relations.get('CONTAINS', 0) + sum(len(v) for v in self.ro_folders.values())
        # SCANNED_IN implicit counts
        if self.dataset_scans:
            file_scan_edges = sum(len(s) for s in self.dataset_scans.values())
            if file_scan_edges:
                relations['SCANNED_IN'] = relations.get('SCANNED_IN', 0) + file_scan_edges
        return {
            'nodes': nodes,
            'relations': relations,
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
        if self.research_objects:
            nodes['ResearchObject'] = len(self.research_objects)
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
        # (2b) Folder -[CONTAINS]-> Folder (count unique child folders that have a parent)
        try:
            from pathlib import Path as _P
            unique_folders = set(folder_paths)
            parent_child_pairs = set()
            for f in unique_folders:
                try:
                    p = str(_P(f).parent)
                except Exception:
                    p = ''
                # Only count Folder->Folder when the parent folder is also part of the observed set
                if p and p != f and p in unique_folders:
                    parent_child_pairs.add((p, f))
            if parent_child_pairs:
                # One edge record representing Folder→CONTAINS→Folder, count = number of unique child folders
                edge_counts[('Folder', 'CONTAINS', 'Folder')] = edge_counts.get(('Folder', 'CONTAINS', 'Folder'), 0) + len(parent_child_pairs)
        except Exception:
            pass
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
        # (5) ResearchObject -[CONTAINS]-> File and Folder
        if self.research_objects:
            total_rof = sum(len(v) for v in self.ro_files.values()) if self.ro_files else 0
            total_rod = sum(len(v) for v in self.ro_folders.values()) if self.ro_folders else 0
            if total_rof:
                edge_counts[('ResearchObject', 'CONTAINS', 'File')] = edge_counts.get(('ResearchObject', 'CONTAINS', 'File'), 0) + total_rof
            if total_rod:
                edge_counts[('ResearchObject', 'CONTAINS', 'Folder')] = edge_counts.get(('ResearchObject', 'CONTAINS', 'Folder'), 0) + total_rod
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

    def commit_scan(self, scan: Dict, rows: Optional[List[Dict]] = None, folder_rows: Optional[List[Dict]] = None) -> Dict:
        """Commit a scan session into the graph as a Scan node and SCANNED_IN edges.
        Expects scan to contain 'id' and 'checksums'.

        Args:
            scan: Scan metadata dict
            rows: Optional file rows (not used for InMemoryGraph)
            folder_rows: Optional folder rows (not used for InMemoryGraph)

        Returns:
            Dict with keys: {'db_scan_exists', 'db_files', 'db_folders', 'db_verified'}
        """
        if not scan or not scan.get('id'):
            return {'db_scan_exists': False, 'db_verified': False, 'db_files': 0, 'db_folders': 0}
        sid = scan['id']
        # store a shallow copy
        self.scans[sid] = {k: scan[k] for k in scan.keys()}
        checksums = scan.get('checksums') or []
        file_count = 0
        for ch in checksums:
            if ch in self.datasets:
                s = self.dataset_scans.setdefault(ch, set())
                s.add(sid)
                file_count += 1
        # Return in-memory stats
        return {'db_scan_exists': True, 'db_verified': True, 'db_files': file_count, 'db_folders': 0}

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
            rows = [{'path': k, 'name': (_P(k).name if k else ''), 'file_count': v} for k, v in counts.items()]
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
        if label == 'ResearchObject':
            rows = []
            for ro_id, ro in self.research_objects.items():
                rows.append({
                    'id': ro_id,
                    'name': ro.get('name'),
                    'path': ro.get('path'),
                    'created_at': ro.get('created_at'),
                    'file_count': len(self.ro_files.get(ro_id, set())),
                    'folder_count': len(self.ro_folders.get(ro_id, set())),
                })
            rows.sort(key=lambda r: (r.get('name') or r.get('path') or ''))
            return rows
        return []
