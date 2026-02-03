import re
from pathlib import Path
from typing import Dict, List

import ijson  # type: ignore


MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+.+")
IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))")


class IpynbInterpreter:
    id = "ipynb"
    name = "Jupyter Notebook Interpreter"
    version = "0.3.0"
    extensions = [".ipynb"]

    def __init__(self, max_bytes: int = 5 * 1024 * 1024):
        self.max_bytes = max_bytes

    def _interpret_streaming(self, file_path: Path) -> Dict:
        """Streaming parse using ijson for memory efficiency."""

        counts = {'code': 0, 'markdown': 0, 'raw': 0}
        first_headings: List[str] = []
        imports: List[str] = []
        kernel = ''
        language = ''
        # Track if we've collected enough content samples (but keep counting cells)
        content_collection_done = False

        try:
            with open(file_path, 'rb') as f:
                # Stream metadata bits
                for prefix, event, value in ijson.parse(f):
                    # Metadata
                    if prefix == 'metadata.kernelspec.name' and event == 'string' and not kernel:
                        kernel = str(value)
                    elif prefix == 'metadata.language_info.name' and event == 'string' and not language:
                        language = str(value).lower()
                    # Cells counting - always count all cells
                    elif prefix.endswith('.cell_type') and event == 'string':
                        ct = (str(value) or '').lower()
                        if ct in counts:
                            counts[ct] += 1
                    # Headings from markdown sources (capture a few only for efficiency)
                    elif not content_collection_done and prefix.endswith('.source.item') and event in ('string', 'number'):
                        # We only try to detect headings/imports from first few items; keep it cheap
                        # ijson emits scalar items for list entries
                        s = str(value)
                        if len(first_headings) < 5 and MD_HEADING_RE.match(s):
                            first_headings.append(s.strip())
                        if len(imports) < 50:
                            m = IMPORT_RE.match(s)
                            if m:
                                mod = m.group(1) or m.group(2) or ''
                                if mod:
                                    root = mod.split('.')[0]
                                    if root not in imports:
                                        imports.append(root)
                        # Stop collecting content once we have enough samples (saves processing)
                        if len(first_headings) >= 5 and len(imports) >= 50:
                            content_collection_done = True
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'IPYNB_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
        result = {
            'type': 'ipynb',
            'kernel': kernel,
            'language': language,
            'cells': counts,
            'first_headings': first_headings,
            'imports': imports,
        }
        return {'status': 'success', 'data': result}

    def interpret(self, file_path: Path) -> Dict:
        """Interpret a Jupyter notebook using streaming parse for memory efficiency."""
        try:
            size = file_path.stat().st_size
            if size > self.max_bytes:
                return {
                    'status': 'error',
                    'data': {
                        'error_type': 'FILE_TOO_LARGE',
                        'max_bytes': self.max_bytes,
                        'size_bytes': size,
                        'details': f"Notebook exceeds limit of {self.max_bytes} bytes"
                    }
                }

            return self._interpret_streaming(file_path)
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'IPYNB_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
