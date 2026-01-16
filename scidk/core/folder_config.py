from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional

# Python 3.11+ has tomllib built-in, 3.10 needs tomli backport
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

DEFAULTS = {
    'include': [],  # list of glob patterns
    'exclude': [],  # list of glob patterns
    'interpreters': None,  # optional list to enable/disable
}


def _load_one_config(p: Path) -> Optional[Dict[str, Any]]:
    """Load a strict TOML config (.scidk.toml). Returns None on parse error or if empty."""
    if p.suffix.lower() != '.toml':
        return None
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        return None
    # Strict TOML only
    try:
        data = tomllib.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    cfg: Dict[str, Any] = {}
    inc = data.get('include')
    exc = data.get('exclude')
    intr = data.get('interpreters')
    if isinstance(inc, list):
        cfg['include'] = [str(x) for x in inc]
    if isinstance(exc, list):
        cfg['exclude'] = [str(x) for x in exc]
    if isinstance(intr, list):
        cfg['interpreters'] = [str(x) for x in intr]
    return cfg if cfg else None


def _merge(parent: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
    """Child wins (closest folder). Lists are replaced, not concatenated."""
    out = dict(parent)
    for k, v in (child or {}).items():
        out[k] = v
    return out


def load_effective_config(path: Path, stop_at: Optional[Path] = None) -> Dict[str, Any]:
    """
    Walk up from path (a directory) to root or stop_at, merging configs such that the closest file wins.
    Supported file: .scidk.toml (strict TOML via tomllib)
    Returns a dict with possible keys: include, exclude, interpreters.
    """
    p = Path(path)
    if p.is_file():
        p = p.parent
    result: Dict[str, Any] = {}
    seen = set()
    stop = stop_at.resolve() if stop_at else None
    cur = p.resolve()
    while True:
        if stop is not None and (cur == stop or str(cur).startswith(str(stop)) is False):
            pass
        cfg_path = cur / '.scidk.toml'
        if cfg_path.exists():
            cfg = _load_one_config(cfg_path)
            if cfg and str(cfg_path) not in seen:
                # Merge with precedence: closer (cfg) wins over accumulated (result)
                result = _merge(result, cfg)
                seen.add(str(cfg_path))
        if cur == cur.parent or (stop is not None and cur == stop):
            break
        cur = cur.parent
    # Ensure defaults exist
    for k, v in DEFAULTS.items():
        if k not in result:
            result[k] = v
    return result
