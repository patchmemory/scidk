from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Rule:
    id: str
    pattern: str  # glob or regex in future
    priority: int = 0
    conditions: Dict[str, Any] = None  # e.g., size < X, has sibling file, etc.


class PatternMatcher:
    """MVP stub for rule evaluation. Currently returns False for all rules.
    Future: implement glob/regex matching, sibling/parent checks, size expressions, etc.
    """
    def matches(self, rule: Rule, path: Path, dataset: Dict) -> bool:
        return False


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
