from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .pattern_matcher import Rule, RuleEngine


class InterpreterRegistry:
    def __init__(self):
        self.by_extension: Dict[str, List] = defaultdict(list)
        self.by_id: Dict[str, object] = {}
        self.rules = RuleEngine()
        # Global defaults for metadata
        self.default_enabled: bool = True

    def register_extension(self, ext: str, interpreter):
        # Track by extension and by id for direct selection
        self.by_extension[ext.lower()].append(interpreter)
        if getattr(interpreter, 'id', None):
            self.by_id[interpreter.id] = interpreter

    def register_rule(self, rule: Rule):
        """Register a selection rule that points to an interpreter by id."""
        self.rules.add_rule(rule)

    def get_by_extension(self, ext: str) -> List:
        return list(self.by_extension.get(ext.lower(), []))

    def get_by_id(self, interpreter_id: str) -> Optional[object]:
        return self.by_id.get(interpreter_id)

    def select_for_dataset(self, dataset: Dict) -> List:
        """Selection with rule precedence and extension fallback.
        - Evaluate rules; if any match, return interpreters in rule priority order (deduped).
        - Otherwise, return interpreters registered for the dataset's extension.
        """
        path = Path(dataset.get('path', ''))
        matches = self.rules.applicable(path, dataset)
        if matches:
            result: List[object] = []
            seen = set()
            for r in matches:
                interp = self.get_by_id(r.interpreter_id)
                if interp and interp.id not in seen:
                    result.append(interp)
                    seen.add(interp.id)
            if result:
                return result
        return self.get_by_extension(dataset.get('extension', ''))
