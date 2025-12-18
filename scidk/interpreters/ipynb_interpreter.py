import json
import re
from pathlib import Path
from typing import Dict, List


MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+.+")
IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))")


class IpynbInterpreter:
    id = "ipynb"
    name = "Jupyter Notebook Interpreter"
    version = "0.2.0"

    def __init__(self, max_bytes: int = 5 * 1024 * 1024):
        self.max_bytes = max_bytes

    def _interpret_streaming(self, file_path: Path) -> Dict:
        """Best-effort streaming parse using ijson if available. Falls back to full-load if ijson missing."""
        try:
            import ijson  # type: ignore
        except Exception:
            # Fallback: full load
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                nb = json.load(f)
            return self._summarize_notebook(nb)

        counts = {'code': 0, 'markdown': 0, 'raw': 0}
        first_headings: List[str] = []
        imports: List[str] = []
        kernel = ''
        language = ''
        try:
            with open(file_path, 'rb') as f:
                # Stream metadata bits
                for prefix, event, value in ijson.parse(f):
                    # Metadata
                    if prefix == 'metadata.kernelspec.name' and event == 'string' and not kernel:
                        kernel = str(value)
                    elif prefix == 'metadata.language_info.name' and event == 'string' and not language:
                        language = str(value).lower()
                    # Cells counting
                    elif prefix.endswith('.cell_type') and event == 'string':
                        ct = (str(value) or '').lower()
                        if ct in counts:
                            counts[ct] += 1
                    # Headings from markdown sources (capture a few only)
                    elif prefix.endswith('.source.item') and event in ('string', 'number'):
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
                        # Early stop if we have enough summaries
                        if len(first_headings) >= 5 and len(imports) >= 50 and all(v > 0 for v in counts.values()):
                            # Not a formal break since ijson is a generator; we can stop by closing file
                            break
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

    def _summarize_notebook(self, nb: Dict) -> Dict:
        # Kernel / language metadata (nbformat 4 typical structure)
        meta = nb.get('metadata') or {}
        kernelspec = meta.get('kernelspec') or {}
        language_info = meta.get('language_info') or {}
        kernel = kernelspec.get('name') or language_info.get('name') or ''
        language = (language_info.get('name') or kernelspec.get('language') or '').lower() or ''

        # Cells summary
        cells: List[Dict] = nb.get('cells') or []
        counts = {'code': 0, 'markdown': 0, 'raw': 0}
        first_headings: List[str] = []
        imports: List[str] = []

        for cell in cells:
            ctype = (cell.get('cell_type') or '').lower()
            if ctype in counts:
                counts[ctype] += 1
            src_lines = cell.get('source')
            if isinstance(src_lines, str):
                src_iter = src_lines.splitlines()
            else:
                src_iter = [str(x) for x in (src_lines or [])]
            if ctype == 'markdown' and len(first_headings) < 5:
                for line in src_iter:
                    if MD_HEADING_RE.match(line):
                        first_headings.append(line.strip())
                        if len(first_headings) >= 5:
                            break
            elif ctype == 'code' and len(imports) < 50:
                for line in src_iter:
                    m = IMPORT_RE.match(line)
                    if m:
                        mod = m.group(1) or m.group(2) or ''
                        if mod:
                            root = mod.split('.')[0]
                            if root not in imports:
                                imports.append(root)
                    if len(imports) >= 50:
                        break

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

            # Try streaming first for memory efficiency
            try:
                return self._interpret_streaming(file_path)
            except Exception:
                # As a safety net, do a traditional full parse
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    nb = json.load(f)
                return self._summarize_notebook(nb)
        except json.JSONDecodeError as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'JSON_DECODE_ERROR',
                    'line': getattr(e, 'lineno', None),
                    'col': getattr(e, 'colno', None),
                    'details': str(e),
                }
            }
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'IPYNB_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
