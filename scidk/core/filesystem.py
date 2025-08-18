from pathlib import Path
import hashlib
import mimetypes
import os
import time
from typing import Dict

from .graph import InMemoryGraph
from .registry import InterpreterRegistry


class FilesystemManager:
    def __init__(self, graph: InMemoryGraph, registry: InterpreterRegistry):
        self.graph = graph
        self.registry = registry

    def scan_directory(self, path: Path, recursive: bool = True) -> int:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        files = path.rglob('*') if recursive else path.glob('*')
        count = 0
        for p in files:
            if p.is_file():
                ds = self.create_dataset_node(p)
                self.graph.upsert_dataset(ds)
                # Try interpretations
                interpreters = self.registry.get_by_extension(ds['extension'])
                for interp in interpreters:
                    try:
                        result = interp.interpret(p)
                        self.graph.add_interpretation(ds['checksum'], interp.id, {
                            'status': result.get('status', 'success'),
                            'data': result.get('data', result),
                            'interpreter_version': getattr(interp, 'version', '0.0.1'),
                        })
                    except Exception as e:
                        self.graph.add_interpretation(ds['checksum'], interp.id, {
                            'status': 'error',
                            'data': {'error': str(e)},
                            'interpreter_version': getattr(interp, 'version', '0.0.1'),
                        })
                count += 1
        return count

    def create_dataset_node(self, file_path: Path) -> Dict:
        st = file_path.stat()
        checksum = self.calculate_checksum(file_path)
        mime, _ = mimetypes.guess_type(str(file_path))
        return {
            'path': str(file_path),
            'filename': file_path.name,
            'extension': file_path.suffix.lower(),
            'size_bytes': st.st_size,
            'created': st.st_ctime,
            'modified': st.st_mtime,
            'mime_type': mime or 'application/octet-stream',
            'checksum': checksum,
            'lifecycle_state': 'active'
        }

    @staticmethod
    def calculate_checksum(file_path: Path, chunk_size: int = 65536) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
