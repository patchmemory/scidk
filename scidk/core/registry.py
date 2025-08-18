from collections import defaultdict
from typing import Dict, List, Optional


class InterpreterRegistry:
    def __init__(self):
        self.by_extension: Dict[str, List] = defaultdict(list)
        self.by_id: Dict[str, object] = {}

    def register_extension(self, ext: str, interpreter):
        # Track by extension and by id for direct selection
        self.by_extension[ext.lower()].append(interpreter)
        if getattr(interpreter, 'id', None):
            self.by_id[interpreter.id] = interpreter

    def get_by_extension(self, ext: str) -> List:
        return list(self.by_extension.get(ext.lower(), []))

    def get_by_id(self, interpreter_id: str) -> Optional[object]:
        return self.by_id.get(interpreter_id)

    def select_for_dataset(self, dataset: Dict) -> List:
        """Minimal selection: return interpreters registered for the dataset's extension.
        Later this can apply pattern rules and precedence.
        """
        return self.get_by_extension(dataset.get('extension', ''))
