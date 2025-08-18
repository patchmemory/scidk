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
