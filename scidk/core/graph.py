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
