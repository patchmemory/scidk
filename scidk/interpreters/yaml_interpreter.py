from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - environment without PyYAML
    yaml = None


class YamlInterpreter:
    id = "yaml"
    name = "YAML Interpreter"
    version = "0.1.0"

    def __init__(self, max_bytes: int = 5 * 1024 * 1024):
        self.max_bytes = max_bytes

    def interpret(self, file_path: Path):
        if yaml is None:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'YAML_DEPENDENCY_MISSING',
                    'details': 'PyYAML is not installed',
                }
            }
        try:
            size = file_path.stat().st_size
            if size > self.max_bytes:
                return {
                    'status': 'error',
                    'data': {
                        'error_type': 'FILE_TOO_LARGE',
                        'max_bytes': self.max_bytes,
                        'size_bytes': size,
                        'details': f"YAML file exceeds limit of {self.max_bytes} bytes"
                    }
                }
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                obj = yaml.safe_load(f)
            if isinstance(obj, dict):
                keys = list(obj.keys())
                preview = {}
                key_types = {}
                for k in keys[:10]:
                    v = obj.get(k)
                    key_types[k] = type(v).__name__
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        preview[k] = v
                    elif isinstance(v, list):
                        preview[k] = v[:1]
                    elif isinstance(v, dict):
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
                        'type': 'yaml',
                        'top_level_keys': keys[:50],
                        'key_types': key_types,
                        'preview': preview,
                    }
                }
            else:
                summary = {
                    'status': 'success',
                    'data': {
                        'type': 'yaml',
                        'top_level_type': type(obj).__name__,
                        'preview': obj if not isinstance(obj, list) else obj[:3]
                    }
                }
                return summary
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'YAML_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
