from __future__ import annotations
from typing import Dict, Any, List, Optional
import re

DEFAULT_PROPERTY_EXCLUDE = [
    r".*password.*",
    r".*ssn.*",
    r".*token.*",
    r".*secret.*",
    r".*email.*",
]

def parse_ttl(s: Optional[str]) -> int:
    if not s:
        return 0
    try:
        return int(s)
    except Exception:
        pass
    m = re.fullmatch(r"(\d+)([smhd])", s.strip().lower())
    if not m:
        return 0
    val = int(m.group(1)); unit = m.group(2)
    mult = dict(s=1, m=60, h=3600, d=86400)[unit]
    return val * mult


def filter_schema(raw: Dict[str, Any], allow_labels: Optional[List[str]] = None,
                  deny_labels: Optional[List[str]] = None,
                  prop_exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    labels = list(raw.get("labels") or [])
    rels = list(raw.get("relationships") or [])
    if allow_labels:
        labels = [l for l in labels if l in allow_labels]
    if deny_labels:
        labels = [l for l in labels if l not in set(deny_labels)]
    # properties are not collected in Phase 1; we just store exclusion patterns for future
    prop_patterns = [re.compile(pat, re.I) for pat in (prop_exclude or DEFAULT_PROPERTY_EXCLUDE)]
    return {
        "labels": labels,
        "relationships": rels,
        "property_exclude": [p.pattern for p in prop_patterns],
    }


def normalize_error(status: str, error: str, code: Optional[str] = None, hint: Optional[str] = None, detail: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": status, "error": error}
    if code:
        payload["code"] = code
    if hint:
        payload["hint"] = hint
    if detail:
        payload["detail"] = detail
    return payload
