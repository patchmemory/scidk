from pathlib import Path
from typing import Dict


class TxtInterpreter:
    id = "txt"
    name = "Text File Interpreter"
    version = "0.1.0"
    extensions = [".txt"]

    def __init__(self, max_bytes: int = 10 * 1024 * 1024, max_preview_bytes: int = 4096, max_preview_lines: int = 100):
        self.max_bytes = max_bytes
        self.max_preview_bytes = max_preview_bytes
        self.max_preview_lines = max_preview_lines

    def _read_with_fallback(self, file_path: Path) -> str:
        # Try utf-8 first, then latin-1 fallback
        try:
            with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
                return f.read(self.max_preview_bytes)
        except Exception:
            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                return f.read(self.max_preview_bytes)

    def interpret(self, file_path: Path) -> Dict:
        try:
            size = file_path.stat().st_size
            if size > self.max_bytes:
                return {
                    'status': 'error',
                    'data': {
                        'error_type': 'FILE_TOO_LARGE',
                        'max_bytes': self.max_bytes,
                        'size_bytes': size,
                        'details': f"Text file exceeds limit of {self.max_bytes} bytes"
                    }
                }
            # Count lines efficiently up to a cap; for larger files we still read all to count
            line_count = 0
            with open(file_path, 'rb') as fb:
                for chunk in iter(lambda: fb.read(1024 * 64), b''):
                    line_count += chunk.count(b"\n")
            # Preview
            preview_blob = self._read_with_fallback(file_path)
            # Normalize preview to max lines
            preview_lines = preview_blob.splitlines()[: self.max_preview_lines]
            return {
                'status': 'success',
                'data': {
                    'type': 'txt',
                    'line_count': int(line_count),
                    'preview': preview_lines,
                }
            }
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'TXT_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
