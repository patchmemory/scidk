from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .pattern_matcher import Rule, RuleEngine


class InterpreterRegistry:
    def __init__(self):
        self.by_extension: Dict[str, List] = defaultdict(list)
        self.by_id: Dict[str, object] = {}
        self.rules = RuleEngine()
        # Global defaults for metadata and toggle system
        self.default_enabled: bool = True
        # Toggle system additions (non-breaking defaults)
        self.enabled_interpreters = set()  # if empty -> treat as all enabled
        self.usage_stats = {}
        self._last_used = {}

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

    # Lightweight usage tracking (in-memory)
    def record_usage(self, interpreter_id: str, success: bool = True, execution_time_ms: int = 0):
        st = self.usage_stats.setdefault(interpreter_id, {
            'total_uses': 0,
            'successes': 0,
            'failures': 0,
            'total_time_ms': 0,
        })
        st['total_uses'] += 1
        st['total_time_ms'] += int(execution_time_ms or 0)
        if success:
            st['successes'] += 1
        else:
            st['failures'] += 1
        try:
            import time
            self._last_used[interpreter_id] = int(time.time())
        except Exception:
            pass

    def get_last_used(self, interpreter_id: str):
        return self._last_used.get(interpreter_id)

    def get_success_rate(self, interpreter_id: str) -> float:
        st = self.usage_stats.get(interpreter_id) or {}
        total = int(st.get('total_uses') or 0)
        if not total:
            return 0.0
        return float(st.get('successes') or 0) / float(total)

    def _is_enabled(self, interpreter_id: str) -> bool:
        # If no explicit enables recorded, treat all as enabled for backwards compatibility
        return (not self.enabled_interpreters) or (interpreter_id in self.enabled_interpreters)

    def enable_interpreter(self, interpreter_id: str):
        if interpreter_id in self.by_id:
            self.enabled_interpreters.add(interpreter_id)

    def disable_interpreter(self, interpreter_id: str):
        if interpreter_id in self.by_id:
            self.enabled_interpreters.discard(interpreter_id)

    def select_for_dataset(self, dataset: Dict) -> List:
        """Selection with rule precedence and extension fallback.
        - Evaluate rules; if any match, return interpreters in rule priority order (deduped).
        - Otherwise, return interpreters registered for the dataset's extension.
        - Respect enabled state (when any enables recorded).
        """
        path = Path(dataset.get('path', ''))
        matches = self.rules.applicable(path, dataset)
        def _enabled_list(candidates: List[object]) -> List[object]:
            if not self.enabled_interpreters:
                return candidates
            return [i for i in candidates if self._is_enabled(getattr(i, 'id', ''))]
        if matches:
            result: List[object] = []
            seen = set()
            for r in matches:
                interp = self.get_by_id(r.interpreter_id)
                if interp and interp.id not in seen and self._is_enabled(interp.id):
                    result.append(interp)
                    seen.add(interp.id)
            if result:
                return result
        return _enabled_list(self.get_by_extension(dataset.get('extension', '')))
