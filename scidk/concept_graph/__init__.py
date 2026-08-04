"""Concept Graph package data, and the seeding command-line entry point.

This directory has held ``intents.yaml`` and ``schema.cypher`` since ``5d8da6e``,
but had no ``__init__.py`` — so it was a namespace directory that
``[tool.setuptools.packages.find]`` did not collect, and its data files were absent
from any built wheel. Cycle 8 Task C needed a CLI that could find ``intents.yaml``
from an installed package, which is why it is a real package now.

Use :data:`INTENTS_YAML` rather than spelling the path out again. Three callers
currently compute it themselves — ``seed_concept_graph.py``,
``apply_concept_schema.py`` and the reseed route in ``api_chat.py`` — and two of
those three resolve it relative to the working directory.
"""

from pathlib import Path

_HERE = Path(__file__).resolve().parent

#: Intent, tool and SATISFIES-weight definitions read by
#: ``seed_intents_from_yaml`` and ``seed_tools_from_yaml``.
INTENTS_YAML = _HERE / 'intents.yaml'

#: Constraints and indexes for a fresh concept-graph Neo4j instance. Applied by
#: ``apply_concept_schema.py``; the CLI here does not run it.
SCHEMA_CYPHER = _HERE / 'schema.cypher'

__all__ = ['INTENTS_YAML', 'SCHEMA_CYPHER']
