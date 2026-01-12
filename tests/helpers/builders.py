from __future__ import annotations
from pathlib import Path
from typing import Iterable, List, Dict, Any
import csv


def build_tree(base: Path, layout: Dict[str, Any]) -> None:
    """
    Create a filesystem tree under base according to a simple dict layout.
    Example:
      build_tree(tmp, {
        'a': {
          'b.txt': 'hello',
        },
        'c.csv': [['id','name'], [1,'a']]
      })
    Rules:
    - str value creates a text file
    - list[list] with first row strings → CSV
    - dict value creates a directory and recurses
    """
    base.mkdir(parents=True, exist_ok=True)
    for name, spec in layout.items():
        p = base / name
        if isinstance(spec, dict):
            build_tree(p, spec)
        elif isinstance(spec, list) and spec and isinstance(spec[0], list):
            # CSV
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(spec)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(spec), encoding='utf-8')


def write_csv(path: Path, rows: List[List[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
