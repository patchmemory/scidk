from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch


@dataclass
class Rule:
    id: str
    interpreter_id: str
    pattern: str  # glob pattern applied to filename or full path
    priority: int = 0
    conditions: Optional[Dict[str, Any]] = None  # e.g., {"ext": ".py", "max_size": 10_000}


class PatternMatcher:
    """MVP rule evaluation with simple glob matching and a couple of basic conditions.
    - pattern: glob applied to filename and full path (match if either matches)
    - conditions:
      - ext: require dataset['extension'] to equal the given value (case-insensitive)
      - max_size: require dataset['size_bytes'] <= max_size
      - min_size: require dataset['size_bytes'] >= min_size
    """
    def matches(self, rule: Rule, path: Path, dataset: Dict) -> bool:
        # Glob match on filename or full path
        fn = path.name
        full = str(path)
        pat = rule.pattern or "*"
        if not (fnmatch.fnmatch(fn, pat) or fnmatch.fnmatch(full, pat)):
            return False
        cond = rule.conditions or {}
        # ext condition
        if 'ext' in cond:
            want = str(cond['ext']).lower()
            if (dataset.get('extension') or '').lower() != want:
                return False
        # size conditions
        size = dataset.get('size_bytes')
        if size is not None:
            if 'max_size' in cond and size > int(cond['max_size']):
                return False
            if 'min_size' in cond and size < int(cond['min_size']):
                return False
        return True


class RuleEngine:
    """Holds rules and can select applicable ones ordered by priority."""
    def __init__(self):
        self.rules: List[Rule] = []

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def applicable(self, path: Path, dataset: Dict) -> List[Rule]:
        pm = PatternMatcher()
        matched = [r for r in self.rules if pm.matches(r, path, dataset)]
        return sorted(matched, key=lambda r: r.priority, reverse=True)
