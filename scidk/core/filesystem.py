from pathlib import Path
import hashlib
import mimetypes
import os
import shutil
import subprocess
import time
from typing import Dict, Iterable, List, Optional

from .graph import InMemoryGraph
from .registry import InterpreterRegistry


class FilesystemManager:
    def __init__(self, graph: InMemoryGraph, registry: InterpreterRegistry):
        self.graph = graph
        self.registry = registry
        self.last_scan_source = 'python'  # one of: ncdu, gdu, python

    def _list_files_with_ncdu(self, path: Path, recursive: bool = True) -> List[Path]:
        """Attempt to use ncdu to enumerate files under path.
        Returns a list of file Paths. If ncdu is unavailable or parsing fails, returns an empty list.
        Note: ncdu's export format is not a stable public API; we heuristically extract absolute paths
        from stdout. This is best-effort and falls back to Python traversal when empty.
        """
        ncdu = shutil.which('ncdu')
        if not ncdu:
            return []
        try:
            # -q quiet, -o - output to stdout, -x stay on one filesystem
            # We do not use interactive TUI (ncurses) because -o implies export without UI.
            # Some ncdu versions may write a binary-like export. We'll scan stdout for path tokens.
            proc = subprocess.run(
                [ncdu, '-q', '-o', '-', '-x', str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            blob = proc.stdout or b''
            if not blob:
                return []
            root_bytes = os.fsencode(str(path.resolve()))
            # Collect candidate strings separated by common delimiters
            candidates: List[bytes] = []
            for sep in (b'\x00', b'\n', b'\r', b'\t'):
                candidates.extend(blob.split(sep))
            found: List[Path] = []
            seen = set()
            for c in candidates:
                if not c:
                    continue
                # Heuristic: look for substrings that start with the root path
                idx = c.find(root_bytes)
                if idx == -1:
                    continue
                # Trim to the end of token (strip control chars)
                token = c[idx:]
                # Clean potential trailing non-printables
                token = token.strip(b'\x00\r\n\t\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f')
                try:
                    s = os.fsdecode(token)
                except Exception:
                    continue
                # Filter to within root and existing files
                try:
                    p = Path(s)
                except Exception:
                    continue
                if p.exists() and p.is_file():
                    # For non-recursive mode, later we'll filter by parent
                    if s not in seen:
                        seen.add(s)
                        found.append(p)
            # If non-recursive requested, keep only immediate children files
            if not recursive:
                found = [p for p in found if p.parent.resolve() == path.resolve()]
            return found
        except Exception:
            return []

    def _list_files_with_gdu(self, path: Path, recursive: bool = True) -> List[Path]:
        """Attempt to use gdu to enumerate files under path via JSON output.
        Returns a list of file Paths. If gdu is unavailable or parsing fails, returns an empty list.
        We avoid strict schema by scanning stdout for absolute path tokens.
        """
        gdu = shutil.which('gdu')
        if not gdu:
            return []
        try:
            # Common flags: --json --no-progress
            proc = subprocess.run(
                [gdu, '--json', '--no-progress', str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            blob = proc.stdout or b''
            if not blob:
                return []
            root_bytes = os.fsencode(str(path.resolve()))
            candidates: List[bytes] = []
            for sep in (b'\x00', b'\n', b'\r', b'\t', b'"', b"'"):
                candidates.extend(blob.split(sep))
            found: List[Path] = []
            seen = set()
            for c in candidates:
                if not c:
                    continue
                idx = c.find(root_bytes)
                if idx == -1:
                    continue
                token = c[idx:]
                token = token.strip(b'\x00\r\n\t\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f')
                try:
                    s = os.fsdecode(token)
                except Exception:
                    continue
                try:
                    p = Path(s)
                except Exception:
                    continue
                if p.exists() and p.is_file():
                    if not recursive and p.parent.resolve() != path.resolve():
                        continue
                    if s not in seen:
                        seen.add(s)
                        found.append(p)
            return found
        except Exception:
            return []

    def _iter_files_python(self, path: Path, recursive: bool = True) -> Iterable[Path]:
        files = path.rglob('*') if recursive else path.glob('*')
        for p in files:
            if p.is_file():
                yield p

    def scan_directory(self, path: Path, recursive: bool = True) -> int:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        # Prefer ncdu; then gdu; fall back to Python
        paths_iter: Iterable[Path]
        ncdu_files = self._list_files_with_ncdu(path, recursive=recursive)
        if ncdu_files:
            self.last_scan_source = 'ncdu'
            paths_iter = ncdu_files
        else:
            gdu_files = self._list_files_with_gdu(path, recursive=recursive)
            if gdu_files:
                self.last_scan_source = 'gdu'
                paths_iter = gdu_files
            else:
                self.last_scan_source = 'python'
                paths_iter = self._iter_files_python(path, recursive=recursive)
        count = 0
        for p in paths_iter:
            ds = self.create_dataset_node(p)
            self.graph.upsert_dataset(ds)
            # Try interpretations
            # Select interpreters using registry rules with extension fallback
            interpreters = self.registry.select_for_dataset(ds)
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

    def create_dataset_remote(self, remote_path: str, size_bytes: int = 0, modified_ts: float = 0.0, mime: Optional[str] = None) -> Dict:
        """Create a dataset node for a remote (non-local) file.
        Uses a stable checksum derived from the remote path string to ensure idempotency.
        """
        # Derive filename and extension heuristically
        from pathlib import PurePosixPath
        p = PurePosixPath(remote_path)
        name = p.name or remote_path
        ext = ('.' + name.split('.')[-1].lower()) if ('.' in name and not name.endswith('.')) else ''
        checksum = hashlib.sha256(remote_path.encode('utf-8')).hexdigest()
        return {
            'path': remote_path,
            'filename': name,
            'extension': ext,
            'size_bytes': int(size_bytes or 0),
            'created': modified_ts or 0.0,
            'modified': modified_ts or 0.0,
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
