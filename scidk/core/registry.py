from collections import defaultdict
from typing import Dict, List


class InterpreterRegistry:
    def __init__(self):
        self.by_extension: Dict[str, List] = defaultdict(list)

    def register_extension(self, ext: str, interpreter):
        self.by_extension[ext.lower()].append(interpreter)

    def get_by_extension(self, ext: str) -> List:
        return list(self.by_extension.get(ext.lower(), []))
