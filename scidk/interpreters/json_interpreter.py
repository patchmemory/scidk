import json
from pathlib import Path


class JsonInterpreter:
    id = "json"
    name = "JSON Interpreter"
    version = "0.1.0"

    def __init__(self, max_bytes: int = 5 * 1024 * 1024):
        self.max_bytes = max_bytes

    def interpret(self, file_path: Path):
        try:
            size = file_path.stat().st_size
            if size > self.max_bytes:
                return {
                    'status': 'error',
                    'data': {
                        'error_type': 'FILE_TOO_LARGE',
                        'max_bytes': self.max_bytes,
                        'size_bytes': size,
                        'details': f"JSON file exceeds limit of {self.max_bytes} bytes"
                    }
                }
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                keys = list(obj.keys())
                preview = {}
                key_types = {}
                for k in keys[:10]:
                    v = obj.get(k)
                    key_types[k] = type(v).__name__
                    # shallow preview for simple types and first 1 item for lists/dicts
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        preview[k] = v
                    elif isinstance(v, list):
                        preview[k] = v[:1]
                    elif isinstance(v, dict):
                        # only copy up to 3 items
                        pv = {}
                        for i, (kk, vv) in enumerate(v.items()):
                            if i >= 3:
                                break
                            pv[kk] = vv if isinstance(vv, (str, int, float, bool)) or vv is None else type(vv).__name__
                        preview[k] = pv
                    else:
                        preview[k] = type(v).__name__
                return {
                    'status': 'success',
                    'data': {
                        'type': 'json',
                        'top_level_keys': keys[:50],
                        'key_types': key_types,
                        'preview': preview,
                    }
                }
            else:
                # array or primitive at top-level
                summary = {
                    'type': 'json',
                    'top_level_type': type(obj).__name__,
                }
                if isinstance(obj, list):
                    summary['length'] = len(obj)
                    summary['preview'] = obj[:3]
                else:
                    summary['preview'] = obj
                return {
                    'status': 'success',
                    'data': summary
                }
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
                    'error_type': 'JSON_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
